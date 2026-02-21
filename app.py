import streamlit as st
import pandas as pd
import requests
import base64
from concurrent.futures import ThreadPoolExecutor

# --- CONFIG ---
ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]

def extract_iherb_stable(url):
    api_url = "https://api.zyte.com/v1/extract"
    payload = {
        "url": url,
        "product": True,
        "browserHtml": True,
        # 'actions' tells the browser to behave like a human to trigger the price render
        "actions": [
            {"action": "waitForSelector", "selector": ".price", "timeout": 5},
            {"action": "scrollPage", "blocks": 1}
        ]
    }
    try:
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        
        if r.status_code != 200:
            return {"Brand": f"Error {r.status_code}", "Price": None, "Success": "❌"}

        res = r.json()
        data = res.get("product", {})
        
        # Check if the AI extraction found the price
        price = data.get("price")
        
        # FALLBACK: If AI missed the price, we search the raw browserHtml for a dollar sign
        if not price and "browserHtml" in res:
            html = base64.b64decode(res["browserHtml"]).decode("utf-8")
            price_match = re.search(r'\"price\":\s?\"(\d+\.\d+)\"', html) or re.search(r'\$(\d+\.\d+)', html)
            price = float(price_match.group(1)) if price_match else None

        name = data.get("name", "Unknown")
        desc = f"{name} {data.get('description', '')}"
        mg_match = re.search(r'(\d+)\s?mg', desc, re.I)
        
        return {
            "Brand": name[:25],
            "Price": price,
            "Mg": int(mg_match.group(1)) if mg_match else 0,
            "Count": 100, # Simplified for testing
            "Success": "✅" if price else "❌"
        }
    except Exception as e:
        return {"Brand": "System Error", "Price": None, "Success": "❌"}

# --- UI ---
st.title("⚖️ OverPrice iHerb Stable Analyzer")

if st.button("🚀 Analyze iHerb (Stable Mode)"):
    urls = [
        "https://au.iherb.com/pr/now-foods-magnesium-citrate-240-veg-capsules/69359",
        "https://au.iherb.com/pr/doctor-s-best-high-absorption-magnesium-100-mg-240-tablets/16567",
        "https://au.iherb.com/pr/life-extension-magnesium-caps-500-mg-100-vegetarian-capsules/48803"
    ]
    
    with st.spinner("Accessing iHerb via Zyte Standard Product API..."):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(extract_iherb_stable, urls))
        
        # --- STABILITY GUARD ---
        # We ensure the DataFrame ALWAYS has these columns to prevent KeyError
        df = pd.DataFrame(results).reindex(columns=["Brand", "Price", "Mg", "Count", "Success"])
        
        st.subheader("Extraction Results")
        st.dataframe(df)

        # Only run math if we actually have valid prices
        valid_df = df[df['Price'].notnull()].copy()
        if not valid_df.empty:
            valid_df['Value_Score'] = valid_df['Price'] / (valid_df['Mg'] * valid_df['Count'] / 1000)
            st.write("### Value Analysis (Price per Gram of Mg)")
            st.bar_chart(valid_df.set_index('Brand')['Value_Score'])
        else:
            st.error("Scraper returned data, but no prices were found. iHerb may be blocking the Price selector.")
