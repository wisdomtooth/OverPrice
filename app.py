import streamlit as st
import pandas as pd
import requests
import base64
from concurrent.futures import ThreadPoolExecutor

# --- CONFIG ---
ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]

def extract_iherb_stable(url):
    api_url = "https://api.zyte.com/v1/extract"
    # Simplified payload: Only ask for the Product object
    # This avoids the 400 Error by using Zyte's standard, optimized schema
    payload = {
        "url": url,
        "product": True
    }
    try:
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        
        # If we get a 400, it means the URL or the API Key has an issue
        if r.status_code != 200:
            return {"Brand": f"Error {r.status_code}", "Price": None, "Success": "❌"}

        data = r.json().get("product", {})
        price = data.get("price")
        name = data.get("name", "Unknown")
        
        # We parse the Magnesium MG from the name/description directly
        # iHerb titles usually look like: "Magnesium Citrate, 200 mg, 240 Veggie Caps"
        desc = f"{name} {data.get('description', '')}"
        mg_match = re.search(r'(\d+)\s?mg', desc, re.I)
        count_match = re.search(r'(\d+)\s?(capsules|tablets|caps|count)', desc, re.I)
        
        return {
            "Brand": name[:25],
            "Price": float(price) if price else None,
            "Mg": int(mg_match.group(1)) if mg_match else 0,
            "Count": int(count_match.group(1)) if count_match else 100,
            "Success": "✅" if price and mg_match else "❌"
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
