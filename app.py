import streamlit as st
import pandas as pd
import statsmodels.api as sm
import plotly.express as px
import requests
from concurrent.futures import ThreadPoolExecutor

# --- SECURE CONFIG ---
try:
    ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]
except KeyError:
    st.error("Please set the ZYTE_API_KEY in Streamlit Secrets.")
    st.stop()

# --- CACHED SCRAPER ---
@st.cache_data(ttl=86400) # Results stay fresh for 24 hours
def get_product_links_cached(search_url):
    api_url = "https://api.zyte.com/v1/extract"
    payload = {"url": search_url, "productNavigation": True}
    response = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload)
    if response.status_code == 200:
        items = response.json().get("productNavigation", {}).get("items", [])
        return [item.get("url") for item in items if item.get("url")][:12]
    return []

@st.cache_data(ttl=604800) # Individual product specs stay for 7 days
def extract_single_product(url):
    """The heavy lifting for one product."""
    api_url = "https://api.zyte.com/v1/extract"
    payload = {
        "url": url,
        "product": True,
        "customAttributes": {
            "mg_oxide": {"type": "integer", "description": "mg of magnesium oxide"},
            "mg_citrate": {"type": "integer", "description": "mg of magnesium citrate"},
            "mg_chelate": {"type": "integer", "description": "mg of magnesium chelate"},
            "count": {"type": "integer", "description": "total tablets"}
        }
    }
    try:
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=30)
        if r.status_code == 200:
            res = r.json()
            p = res.get("product", {})
            c = res.get("customAttributes", {})
            return {
                "Brand": p.get("brand") or p.get("name", "Unknown")[:15],
                "Price": p.get("price"),
                "Mg_Oxide_mg": c.get("mg_oxide", 0),
                "Mg_Citrate_mg": c.get("mg_citrate", 0),
                "Mg_Chelate_mg": c.get("mg_chelate", 0),
                "Count": c.get("count") or 100,
                "URL": url
            }
    except:
        return None

# --- STREAMLIT UI ---
st.title("⚖️ OverPrice Fast-Engine")

if st.button("🚀 Run Analysis"):
    search_url = "https://www.amazon.com.au/s?k=Magnesium+Supplements"
    
    # 1. Get Links (Cached)
    links = get_product_links_cached(search_url)
    
    if links:
        # 2. Parallel Scraping (THE SPEED BOOST)
        st.write(f"Gathering data for {len(links)} products in parallel...")
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            # This launches 5 requests at once
            scraped_data = list(executor.map(extract_single_product, links))
        
        # Filter out failed scrapes
        results = [d for d in scraped_data if d is not None and d['Price'] is not None]
        
        # 3. Analytics
        df = pd.DataFrame(results).fillna(0)
        if len(df) >= 3:
            df['Price_Per_Tab'] = df['Price'] / df['Count']
            X = sm.add_constant(df[['Mg_Oxide_mg', 'Mg_Citrate_mg', 'Mg_Chelate_mg']])
            model = sm.OLS(df['Price_Per_Tab'], X).fit()
            
            # Show Table & Plot
            df['Fair_Value'] = model.predict(X) * df['Count']
            st.success("Analysis Complete! (Cached for next time)")
            st.dataframe(df[['Brand', 'Price', 'Fair_Value']])
            
            # Visualize
            fig = px.scatter(df, x="Fair_Value", y="Price", text="Brand", trendline="ols")
            st.plotly_chart(fig)
