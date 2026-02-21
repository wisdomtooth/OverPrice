import streamlit as st
import pandas as pd
import requests
import re
from concurrent.futures import ThreadPoolExecutor

# --- CONFIG ---
ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]

def extract_iherb_clean(url):
    api_url = "https://api.zyte.com/v1/extract"
    # CLEAN PAYLOAD: No 'actions', no 'browserHtml'. 
    # Just the product AI and the location.
    payload = {
        "url": url,
        "product": True,
        "geolocation": "AU" 
    }
    try:
        # Auth must be (key, "")
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        
        if r.status_code == 200:
            data = r.json().get("product", {})
            price = data.get("price")
            name = data.get("name", "Unknown")
            
            # Simple Python-based parsing for Mg (Free and reliable)
            # Looks for "200 mg" or "200mg" in the title
            mg_match = re.search(r'(\d+)\s?mg', name, re.I)
            
            return {
                "Brand": name[:30],
                "Price": float(price) if price else None,
                "Mg": int(mg_match.group(1)) if mg_match else 0,
                "Success": "✅" if price else "❌"
            }
        else:
            # This captures the 400 error details
            return {"Brand": f"API Error {r.status_code}", "Success": "❌"}
    except Exception as e:
        return {"Brand": "Connection Error", "Success": "❌"}

# --- UI ---
st.title("⚖️ OverPrice: Clean AI Extraction")

if st.button("🚀 Scrape iHerb (Clean Mode)"):
    # Use the most popular IDs which have the most stable HTML
    urls = [
        "https://au.iherb.com/pr/now-foods-magnesium-citrate-240-veg-capsules/69359",
        "https://au.iherb.com/pr/doctor-s-best-high-absorption-magnesium-100-mg-240-tablets/16567"
    ]
    
    with st.spinner("Requesting AI-authenticated data..."):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(extract_iherb_clean, urls))
        
        # Stability: Ensure these columns exist even if the API fails
        df = pd.DataFrame(results).reindex(columns=["Brand", "Price", "Mg", "Success"])
        st.dataframe(df)

        if "Price" in df.columns and df['Price'].notnull().any():
            st.success("Prices found!")
        else:
            st.error("Still no prices. This suggests your Zyte account may not have 'E-commerce AI' enabled.")
