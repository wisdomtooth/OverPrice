import streamlit as st
import pandas as pd
import statsmodels.api as sm
import requests
import re
from concurrent.futures import ThreadPoolExecutor

ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]

def zyte_request(url, mode="product"):
    # geolocation: AU is critical for iHerb AU prices and sorting
    payload = {"url": url, mode: True, "geolocation": "AU"}
    try:
        r = requests.post("https://api.zyte.com/v1/extract", auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def analyze_market_auto(user_url):
    # 1. Scrape the Target Product
    target_res = zyte_request(user_url, "product")
    p = target_res.get("product", {})
    if not p:
        st.error("Could not extract product data. Check the URL.")
        return None

    # 2. Extract Breadcrumbs with Safety
    breadcrumbs = p.get("breadcrumbs", [])
    if not breadcrumbs or not isinstance(breadcrumbs[-1].get("link"), str):
        st.error("Breadcrumb link missing. iHerb might be blocking the structure.")
        return None
    
    # 3. Build the Category Market URL
    category_url = str(breadcrumbs[-1].get("link"))
    if "?" in category_url:
        category_url += "&sr=2" # Best Sellers
    else:
        category_url += "?sr=2"

    # 4. Scrape Category (Market Baseline)
    market_res = zyte_request(category_url, "productList")
    items = market_res.get("productList", {}).get("products", [])
    
    market_data = []
    for item in items:
        name = item.get("name", "")
        price = item.get("price")
        if price:
            # We use Regex to find 'Servings' in the title or metadata if available
            servings_match = re.search(r'(\d+)\s?(servings|serves)', name, re.I)
            # Fallback to 60 servings if not found
            servings = int(servings_match.group(1)) if servings_match else 60
            
            market_data.append({
                "Brand": name[:30],
                "Price": float(price),
                "Servings": servings
            })
    
    if len(market_data) < 5:
        st.error("Insufficient market data found in this category.")
        return None

    df = pd.DataFrame(market_data)
    
    # 5. HEDONIC REGRESSION: Price ~ Servings
    # Note: We use Servings as the primary value driver
    X = sm.add_constant(df[['Servings']])
    model = sm.OLS(df['Price'], X).fit()
    
    # Target values
    t_price = float(p.get("price", 0))
    t_name = p.get("name", "Product")
    t_serv_match = re.search(r'(\d+)\s?(servings|serves)', t_name, re.I)
    t_servings = int(t_serv_match.group(1)) if t_serv_match else 60

    # THE CRITICAL FIX: Explicit conversion to float
    fair_price_pred = model.predict([1, t_servings])
    fair_price = float(fair_price_pred[0])
    
    overprice_pct = ((t_price - fair_price) / fair_price) * 100
    
    return t_name, t_price, fair_price, overprice_pct, df

# --- UI ---
st.title("⚖️ OverPrice: Hedonic Servings Analyzer")
input_url = st.text_input("Paste iHerb Product URL:", placeholder="https://au.iherb.com/pr/...")

if input_url:
    with st.spinner("Analyzing market category..."):
        data = analyze_market_auto(input_url)
        if data:
            name, actual, fair, diff, market_df = data
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Actual Price", f"${actual:.2f}")
            c2.metric("Fair Value", f"${fair:.2f}")
            c3.metric("OverPrice Factor", f"{diff:.1f}%", delta=f"{diff:.1f}%", delta_color="inverse")
            
            st.write(f"### Category Competitors (Top Sellers)")
            st.dataframe(market_df)
