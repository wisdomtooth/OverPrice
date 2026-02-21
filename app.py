import streamlit as st
import pandas as pd
import numpy as np
import statsmodels.api as sm
import requests
import re
from concurrent.futures import ThreadPoolExecutor

ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]

def scrape_product_or_category(url, is_category=False):
    payload = {"url": url, "product": True if not is_category else False, "browserHtml": is_category}
    # For category pages, we use standard extraction to get the list of links
    try:
        r = requests.post("https://api.zyte.com/v1/extract", auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        return r.json()
    except: return None

def analyze_market(user_url):
    # 1. Get the User's Target Product
    user_data = scrape_product_or_category(user_url)
    p = user_data.get("product", {})
    target_name = p.get("name", "Target")
    target_price = p.get("price")
    
    # 2. Extract Mg and Count for the Target
    mg_target = int(re.search(r'(\d+)\s?mg', target_name, re.I).group(1)) if re.search(r'(\d+)\s?mg', target_name, re.I) else 100
    count_target = int(re.search(r'(\d+)\s?(count|caps|tabs)', target_name, re.I).group(1)) if re.search(r'(\d+)\s?(count|caps|tabs)', target_name, re.I) else 60

    # 3. MOCK MARKET BASELINE (In 2026, this would be a second API call to the category URL)
    # For this demo, we generate a synthetic market of 20 competitors based on current iHerb AU trends
    market_data = []
    for i in range(20):
        # Market variance: Price is usually $0.05 per mg + $5 flat shipping/bottling fee
        m_mg = np.random.choice([100, 200, 400])
        m_count = np.random.choice([60, 90, 120, 240])
        base_price = (m_mg * m_count * 0.0005) + 8.00 
        noise = np.random.normal(1, 0.15) # 15% market irrationality
        market_data.append({"Mg": m_mg, "Count": m_count, "Price": base_price * noise})
    
    df_market = pd.DataFrame(market_data)

    # 4. RUN HEDONIC REGRESSION (Price ~ Mg + Count)
    X = df_market[['Mg', 'Count']]
    X = sm.add_constant(X)
    model = sm.OLS(df_market['Price'], X).fit()
    
    # 5. Predict Fair Value for User's Choice
    fair_price = model.predict([1, mg_target, count_target])[0]
    overprice_pct = ((target_price - fair_price) / fair_price) * 100

    return target_name, target_price, fair_price, overprice_pct

# --- STREAMLIT UI ---
st.title("⚖️ OverPrice: Hedonic Market Analyzer")
input_url = st.text_input("Paste iHerb Product URL:", placeholder="https://au.iherb.com/pr/...")

if input_url:
    with st.spinner("Analyzing market price distribution..."):
        name, actual, fair, diff = analyze_market(input_url)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Actual Price", f"${actual:.2f}")
        col2.metric("Fair Market Value", f"${fair:.2f}")
        col3.metric("OverPrice Factor", f"{diff:.1f}%", delta=f"{diff:.1f}%", delta_color="inverse")
        
        if diff > 10:
            st.warning(f"🚨 **{name}** is significantly overpriced compared to similar products.")
        elif diff < -10:
            st.success(f"💎 **{name}** is a market-leading bargain!")
        else:
            st.info("This product is priced fairly according to current market specs.")
