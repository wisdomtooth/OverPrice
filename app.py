import streamlit as st
import pandas as pd
import statsmodels.api as sm
import plotly.express as px
import requests
import re
import base64
from concurrent.futures import ThreadPoolExecutor

# --- CONFIG ---
ZYTE_API_KEY = st.secrets.get("ZYTE_API_KEY", "47c0ce047e104f9cab87ff9e0e1a7d26")

def extract_single_product(url):
    api_url = "https://api.zyte.com/v1/extract"
    payload = {
        "url": url,
        "httpResponseBody": True,
        "browserHtml": True,
    }
    try:
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=45)
        if r.status_code == 200:
            html = base64.b64decode(r.json()["httpResponseBody"]).decode("utf-8")
            
            # 1. Price (Look for common Amazon price patterns)
            price_match = re.search(r'\"price\":(\d+\.\d+)', html) or re.search(r'priceToPay.*?(\d+\.\d+)', html) or re.search(r'\$(\d+\.\d+)', html)
            price = float(price_match.group(1)) if price_match else None
            
            # 2. Brand
            title_match = re.search(r'<title>(.*?)</title>', html, re.I)
            brand = title_match.group(1).split('|')[0][:20] if title_match else "Unknown"
            
            # 3. Ingredients (Searching for keywords in raw HTML)
            oxide = re.search(r'oxide.*?(\d+)\s?mg', html, re.I)
            citrate = re.search(r'citrate.*?(\d+)\s?mg', html, re.I)
            chelate = re.search(r'chelate.*?(\d+)\s?mg', html, re.I) or re.search(r'glycinate.*?(\d+)\s?mg', html, re.I)
            
            # 4. Count
            count_match = re.search(r'(\d+)\s?(count|tablets|capsules|tabs|caps)', html, re.I)
            count = int(count_match.group(1)) if count_match else 100
            
            success = "✅" if price and (oxide or citrate or chelate) else "❌"
            
            return {
                "Brand": brand.strip(),
                "Price": price,
                "Mg_Oxide": int(oxide.group(1)) if oxide else 0,
                "Mg_Citrate": int(citrate.group(1)) if citrate else 0,
                "Mg_Chelate": int(chelate.group(1)) if chelate else 0,
                "Count": count,
                "Success": success
            }
    except Exception as e:
        return {"Brand": "Error", "Success": "❌", "Price": None}
    return None

# --- UI ---
st.title("⚖️ OverPrice Magnesium Analyzer")

if st.button("🚀 Run Live Analysis"):
    test_links = [
        "https://www.amazon.com.au/dp/B085S3V9R8",
        "https://www.amazon.com.au/dp/B07P8G27L7",
        "https://www.amazon.com.au/dp/B000Z967G6",
        "https://www.amazon.com.au/dp/B07R69B79V"
    ]
    
    with st.spinner("Extracting biological data..."):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(extract_single_product, test_links))
        
        # Filter out None results before making the DF
        results = [r for r in results if r is not None]
        
        if not results:
            st.error("The scraper returned no data. Zyte might be blocked or the URL is invalid.")
        else:
            df = pd.DataFrame(results)
            
            # Check if columns exist to avoid KeyError
            if 'Success' in df.columns:
                st.subheader("Raw Extraction Data")
                st.dataframe(df)
                
                valid_df = df[df['Success'] == "✅"].copy()
                
                if len(valid_df) >= 3:
                    valid_df['Price_Per_Tab'] = valid_df['Price'] / valid_df['Count']
                    X = sm.add_constant(valid_df[['Mg_Oxide', 'Mg_Citrate', 'Mg_Chelate']])
                    model = sm.OLS(valid_df['Price_Per_Tab'], X).fit()
                    
                    valid_df['Fair_Value'] = model.predict(X) * valid_df['Count']
                    st.success("Calculated Market Value!")
                    st.dataframe(valid_df[['Brand', 'Price', 'Fair_Value']])
                else:
                    st.warning(f"Found {len(valid_df)} products with full data. We need at least 3 to run the math.")
            else:
                st.error("Data structure error: 'Success' column missing.")
