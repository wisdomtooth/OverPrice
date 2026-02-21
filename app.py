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
    # We drop the 'product' AI and just ask for the raw browser HTML
    payload = {
        "url": url,
        "httpResponseBody": True,
        "browserHtml": True,
    }
    try:
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        if r.status_code == 200:
            import base64
            html = base64.b64decode(r.json()["httpResponseBody"]).decode("utf-8")
            
            # --- MANUAL EXTRACTION (The Fail-Safe) ---
            # 1. Price
            price_match = re.search(r'\"price\":(\d+\.\d+)', html) or re.search(r'\$(\d+\.\d+)', html)
            price = float(price_match.group(1)) if price_match else None
            
            # 2. Brand (Usually in the title)
            title_match = re.search(r'<title>(.*?)</title>', html)
            brand = title_match.group(1).split('|')[0][:15] if title_match else "Unknown"
            
            # 3. Ingredients (Searching for keywords in the raw text)
            oxide = re.search(r'oxide.*?(\d+)\s?mg', html, re.I)
            citrate = re.search(r'citrate.*?(\d+)\s?mg', html, re.I)
            chelate = re.search(r'chelate.*?(\d+)\s?mg', html, re.I)
            
            # 4. Count
            count_match = re.search(r'(\d+)\s?(count|tablets|capsules|tabs)', html, re.I)
            count = int(count_match.group(1)) if count_match else 100
            
            success = "✅" if price and (oxide or citrate or chelate) else "❌"
            
            return {
                "Brand": brand,
                "Price": price,
                "Mg_Oxide": int(oxide.group(1)) if oxide else 0,
                "Mg_Citrate": int(citrate.group(1)) if citrate else 0,
                "Mg_Chelate": int(chelate.group(1)) if chelate else 0,
                "Count": count,
                "Success": success
            }
    except Exception as e:
        return {"Brand": "Error", "Success": "❌", "Error": str(e)}
    return None
    
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
