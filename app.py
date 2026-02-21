import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor

# --- CONFIG ---
ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]

def extract_iherb_ai(url):
    api_url = "https://api.zyte.com/v1/extract"
    # Using 'product': True enables Zyte's specialized E-commerce AI unblocker
    payload = {
        "url": url,
        "product": True,
        "customAttributes": {
            "mg_elemental": {"type": "integer", "description": "Milligrams of elemental Magnesium per serving."},
            "bottle_count": {"type": "integer", "description": "Total number of tablets or capsules in the bottle."}
        },
        "customAttributesMethod": "generate" # AI 'looks' at the page to find values
    }
    try:
        # Increase timeout to 90s; AI extraction takes longer to 'think'
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=90)
        
        if r.status_code == 200:
            res = r.json()
            p = res.get("product", {})
            c = res.get("customAttributes", {})
            
            # If the AI found a price, we have bypassed the block
            price = p.get("price")
            return {
                "Brand": p.get("brand") or "Unknown",
                "Price": float(price) if price else None,
                "Mg": c.get("mg_elemental", 0),
                "Count": c.get("bottle_count", 100),
                "Success": "✅" if price else "❌"
            }
        else:
            return {"Brand": f"Error {r.status_code}", "Success": "❌"}
    except:
        return {"Brand": "Timeout", "Success": "❌"}

# --- UI ---
st.title("⚖️ OverPrice iHerb AI Analyzer")

if st.button("🚀 Run AI-Powered Scrape"):
    # Target IDs directly to bypass landing page redirects
    iherb_urls = [
        "https://au.iherb.com/pr/now-foods-magnesium-citrate-240-veg-capsules/69359",
        "https://au.iherb.com/pr/doctor-s-best-high-absorption-magnesium-100-mg-240-tablets/16567",
        "https://au.iherb.com/pr/life-extension-magnesium-caps-500-mg-100-vegetarian-capsules/48803"
    ]
    
    with st.spinner("Zyte AI is bypassing iHerb security..."):
        # Reduce concurrency to avoid 'noisy' patterns
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(extract_iherb_ai, iherb_urls))
        
        df = pd.DataFrame([r for r in results if r])
        st.dataframe(df)

        if not df.empty and df['Price'].notnull().any():
            st.success("Data secured!")
        else:
            st.error("AI could not find price data. iHerb may be requiring a CAPTCHA solver.")
