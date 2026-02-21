import streamlit as st
import pandas as pd
import statsmodels.api as sm
import plotly.express as px
import requests
from concurrent.futures import ThreadPoolExecutor

# --- CONFIG ---
ZYTE_API_KEY = st.secrets.get("ZYTE_API_KEY", "47c0ce047e104f9cab87ff9e0e1a7d26")

def extract_single_product(url):
    api_url = "https://api.zyte.com/v1/extract"
    payload = {
        "url": url,
        "product": True,
        "browserHtml": True, # <--- FORCE BROWSER RENDERING
        "customAttributes": {
            "mg_oxide": {"type": "integer", "description": "Total mg of Magnesium Oxide"},
            "mg_citrate": {"type": "integer", "description": "Total mg of Magnesium Citrate"},
            "mg_chelate": {"type": "integer", "description": "Total mg of Magnesium Chelate/Bisglycinate"},
            "count": {"type": "integer", "description": "Number of capsules/tablets in bottle"}
        }
    }
    try:
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        if r.status_code == 200:
            res = r.json()
            p = res.get("product", {})
            c = res.get("customAttributes", {})
            return {
                "Brand": (p.get("brand") or p.get("name", "Unknown"))[:15],
                "Price": p.get("price"),
                "Mg_Oxide": c.get("mg_oxide", 0),
                "Mg_Citrate": c.get("mg_citrate", 0),
                "Mg_Chelate": c.get("mg_chelate", 0),
                "Count": c.get("count"),
                "Success": "✅" if p.get("price") and c.get("count") else "❌"
            }
    except: return None

# --- UI ---
st.title("⚖️ OverPrice Deep-Debugger")

if st.button("🚀 Run Deep Scrape"):
    # Using a list of known high-quality links for the first test
    test_links = [
        "https://www.amazon.com.au/dp/B085S3V9R8", # Nature's Own
        "https://www.amazon.com.au/dp/B07P8G27L7", # Swisse
        "https://www.amazon.com.au/dp/B000Z967G6", # Doctors Best
        "https://www.amazon.com.au/dp/B07R69B79V"  # Cenovis
    ]
    
    with st.spinner("Analyzing Market Data..."):
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(extract_single_product, test_links))
        
        df = pd.DataFrame([r for r in results if r]).fillna(0)
        
        # --- DEBUG VIEW ---
        st.subheader("Raw Scrape Data (Debug)")
        st.dataframe(df)
        
        # --- MATH ENGINE ---
        valid_df = df[df['Success'] == "✅"].copy()
        
        if len(valid_df) >= 3:
            valid_df['Price_Per_Tab'] = valid_df['Price'] / valid_df['Count']
            X = sm.add_constant(valid_df[['Mg_Oxide', 'Mg_Citrate', 'Mg_Chelate']])
            model = sm.OLS(valid_df['Price_Per_Tab'], X).fit()
            
            valid_df['Fair_Value'] = model.predict(X) * valid_df['Count']
            st.success("Regression Successful!")
            st.dataframe(valid_df[['Brand', 'Price', 'Fair_Value']])
        else:
            st.error(f"Only found {len(valid_df)} valid products. We need 3. Look at the red ❌ above.")
