import streamlit as st
import pandas as pd
import statsmodels.api as sm
import requests
import re
from concurrent.futures import ThreadPoolExecutor

ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]

def zyte_request(url, mode="product"):
    # mode can be "product" or "productList"
    payload = {"url": url, mode: True, "geolocation": "AU"}
    try:
        r = requests.post("https://api.zyte.com/v1/extract", auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        return r.json()
    except: return None

def analyze_market_auto(user_url):
    # 1. Scrape the specific Target Product
    target_res = zyte_request(user_url, "product")
    p = target_res.get("product", {})
    
    # 2. Find Category via Breadcrumbs
    # Zyte's product schema usually includes breadcrumbs
    breadcrumbs = p.get("breadcrumbs", [])
    if breadcrumbs:
        # Get the URL of the last breadcrumb (the specific category)
        category_url = breadcrumbs[-1].get("link")
        # Ensure it has the Best Sellers sort for AU
        category_url += "?sr=2" 
    else:
        st.error("Could not find category breadcrumbs. Using fallback search.")
        return None

    # 3. Scrape the Category Listings (The Market)
    market_res = zyte_request(category_url, "productList")
    items = market_res.get("productList", {}).get("products", [])
    
    market_data = []
    for item in items:
        name = item.get("name", "")
        price = item.get("price")
        if price:
            # Extract Mg and Count from listing title
            mg = re.search(r'(\d+)\s?mg', name, re.I)
            count = re.search(r'(\d+)\s?(count|caps|tabs|softgels)', name, re.I)
            market_data.append({
                "Brand": name[:30],
                "Price": float(price),
                "Mg": int(mg.group(1)) if mg else 100,
                "Count": int(count.group(1)) if count else 60
            })
    
    df = pd.DataFrame(market_data)
    
    # 4. Regression & THE FIX FOR TYPEERROR
    X = sm.add_constant(df[['Mg', 'Count']])
    model = sm.OLS(df['Price'], X).fit()
    
    # Target values
    t_price = float(p.get("price", 0))
    t_name = p.get("name", "Product")
    t_mg = int(re.search(r'(\d+)\s?mg', t_name, re.I).group(1)) if re.search(r'(\d+)\s?mg', t_name, re.I) else 100
    t_count = int(re.search(r'(\d+)\s?(count|caps|tabs|softgels)', t_name, re.I).group(1)) if re.search(r'(\d+)\s?(count|caps|tabs|softgels)', t_name, re.I) else 60

    # THE FIX: We cast the prediction to a float immediately
    fair_price_array = model.predict([1, t_mg, t_count])
    fair_price = float(fair_price_array[0]) # <--- This kills the TypeError
    
    overprice_pct = ((t_price - fair_price) / fair_price) * 100
    
    return t_name, t_price, fair_price, overprice_pct, df

# --- UI ---
st.title("⚖️ OverPrice: Automated Market Scraper")
input_url = st.text_input("Paste any iHerb Product URL:")

if input_url:
    with st.spinner("Finding market peers and running regression..."):
        data = analyze_market_auto(input_url)
        if data:
            name, actual, fair, diff, market_df = data
            
            # Metrics
            c1, c2, c3 = st.columns(3)
            c1.metric("Actual Price", f"${actual:.2f}")
            c2.metric("Market Fair Value", f"${fair:.2f}")
            c3.metric("OverPrice Factor", f"{diff:.1f}%", delta=f"{diff:.1f}%", delta_color="inverse")
            
            st.write(f"### Market Baseline ({len(market_df)} products)")
            st.dataframe(market_df)
