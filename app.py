import streamlit as st
import pandas as pd
import statsmodels.api as sm
import requests
import re
import base64
from concurrent.futures import ThreadPoolExecutor

# --- CONFIG ---
ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]

def extract_iherb(url):
    api_url = "https://api.zyte.com/v1/extract"
    payload = {
        "url": url,
        "httpResponseBody": True,
        "browserHtml": True 
    }
    try:
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=45)
        if r.status_code == 200:
            html = base64.b64decode(r.json()["httpResponseBody"]).decode("utf-8")
            
            # 1. Price (iHerb uses meta tags or specific price classes)
            price_match = re.search(r'\"price\":\s?\"(\d+\.\d+)\"', html) or re.search(r'data-price=\"(\d+\.\d+)\"', html)
            price = float(price_match.group(1)) if price_match else None
            
            # 2. Brand/Product Name
            name_match = re.search(r'<title>(.*?)</title>', html, re.I)
            name = name_match.group(1).split('-')[0].strip()[:25] if name_match else "Unknown"
            
            # 3. Elemental Magnesium (Standardized iHerb layout)
            # Look for Magnesium followed by a number, excluding % values
            mg_match = re.search(r'Magnesium.*?(\d+)\s?mg', html, re.S | re.I)
            mg_total = int(mg_match.group(1)) if mg_match else 0
            
            # 4. Count (Package quantity)
            count_match = re.search(r'(\d+)\s?(Count|Veggie Caps|Tablets)', html, re.I)
            count = int(count_match.group(1)) if count_match else 100
            
            success = "✅" if price and mg_total > 0 else "❌"
            
            return {
                "Product": name,
                "Price": price,
                "Mg_Per_Serving": mg_total,
                "Count": count,
                "Success": success
            }
    except: return None

# --- UI ---
st.set_page_config(page_title="OverPrice iHerb Analyzer", layout="wide")
st.title("⚖️ OverPrice: iHerb Magnesium Market Value")

if st.button("🚀 Analyze iHerb Inventory"):
    # High-yield iHerb AU links
    iherb_links = [
        "https://au.iherb.com/pr/doctor-s-best-high-absorption-magnesium-lysinate-glycinate-chelated-albion-traacs-240-tablets-100-mg-per-tablet/16567",
        "https://au.iherb.com/pr/now-foods-magnesium-citrate-240-veg-capsules-133-mg-per-capsule/69359",
        "https://au.iherb.com/pr/life-extension-magnesium-caps-500-mg-100-vegetarian-capsules/48803",
        "https://au.iherb.com/pr/natural-factors-magnesium-citrate-150-mg-180-capsules/43777",
        "https://au.iherb.com/pr/swanson-triple-magnesium-complex-400-mg-300-vegan-capsules/118361"
    ]
    
    with st.spinner("Extracting biological data from iHerb..."):
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = [r for r in list(executor.map(extract_iherb, iherb_links)) if r]
        
        df = pd.DataFrame(results)
        
        if not df.empty:
            st.subheader("Market Scan: Raw Data")
            st.dataframe(df)
            
            valid_df = df[df['Success'] == "✅"].copy()
            
            if len(valid_df) >= 3:
                # Metric: Cost per 1000mg of elemental Magnesium
                valid_df['Cost_Per_Gram'] = (valid_df['Price'] / (valid_df['Mg_Per_Serving'] * valid_df['Count'])) * 1000
                
                st.success("Calculated Market Efficiency!")
                
                # Visualizing the 'OverPrice' factor
                fig = px.bar(valid_df, x='Product', y='Cost_Per_Gram', 
                             title="Price per Gram of Elemental Magnesium (AU$)",
                             labels={'Cost_Per_Gram': 'Price per Gram (AU$)'},
                             color='Cost_Per_Gram', color_continuous_scale='RdYlGn_r')
                st.plotly_chart(fig)
                
                # Best Value Recommendation
                best_value = valid_df.loc[valid_df['Cost_Per_Gram'].idxmin()]
                st.info(f"🏆 **Best Market Value:** {best_value['Product']} at ${best_value['Cost_Per_Gram']:.2f} per gram.")
            else:
                st.warning("Insufficient valid products found for analysis. Check the extraction results above.")
        else:
            st.error("No data could be retrieved from iHerb. Check Zyte credits or connectivity.")
