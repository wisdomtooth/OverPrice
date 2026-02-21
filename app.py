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
    
    # We use 'product': True but force the 'generate' method.
    # This uses a multimodal LLM that can 'see' the page layout.
    payload = {
        "url": url,
        "product": True,
        "customAttributes": {
            "mg_oxide": {"type": "integer", "description": "Total mg of Magnesium Oxide"},
            "mg_citrate": {"type": "integer", "description": "Total mg of Magnesium Citrate"},
            "mg_chelate": {"type": "integer", "description": "Total mg of Magnesium Chelate/Bisglycinate/Biglycinate"},
            "count": {"type": "integer", "description": "Number of capsules or tablets in the bottle"}
        },
        "customAttributesMethod": "generate" # <--- THE MAGIC KEY
    }
    
    try:
        # We must use a longer timeout for the AI to 'think'
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=90)
        
        if r.status_code == 200:
            res = r.json()
            prod = res.get("product", {})
            cust = res.get("customAttributes", {})
            
            # If the AI returns a price, we are in business
            price = prod.get("price")
            
            return {
                "Brand": prod.get("brand") or prod.get("name", "Unknown")[:15],
                "Price": float(price) if price else None,
                "Mg_Oxide": cust.get("mg_oxide", 0),
                "Mg_Citrate": cust.get("mg_citrate", 0),
                "Mg_Chelate": cust.get("mg_chelate", 0),
                "Count": cust.get("count") or 100,
                "Success": "✅" if price else "❌"
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
