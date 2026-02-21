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
    # Using 'pageContent' turns on Zyte's most advanced AI unblocker
    payload = {
        "url": url,
        "pageContent": True, 
        "browserHtml": True
    }
    try:
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        if r.status_code == 200:
            res = r.json()
            # pageContent returns the main text of the page in 'text'
            text_data = res.get("text", "")
            
            # --- SURGICAL REGEX ON RAW TEXT ---
            # 1. Price (Looking for $XX.XX)
            price_match = re.search(r'\$(\d+\.\d+)', text_data)
            price = float(price_match.group(1)) if price_match else None
            
            # 2. Ingredients
            oxide = re.search(r'oxide.*?(\d+)\s?mg', text_data, re.I)
            citrate = re.search(r'citrate.*?(\d+)\s?mg', text_data, re.I)
            # Premium forms often use 'glycinate'
            chelate = re.search(r'(chelate|glycinate).*?(\d+)\s?mg', text_data, re.I)
            
            # 3. Bottle Count
            count_match = re.search(r'(\d+)\s?(count|tablets|capsules|tabs)', text_data, re.I)
            count = int(count_match.group(1)) if count_match else 100
            
            success = "✅" if price and (oxide or citrate or chelate) else "❌"
            
            return {
                "Brand": url.split("/")[-1][:15], # Fallback brand from URL
                "Price": price,
                "Mg_Oxide": int(oxide.group(1)) if oxide else 0,
                "Mg_Citrate": int(citrate.group(1)) if citrate else 0,
                "Mg_Chelate": int(chelate.group(2)) if chelate else 0,
                "Count": count,
                "Success": success
            }
    except Exception as e:
        return {"Brand": "Error", "Success": "❌"}
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
