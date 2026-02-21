import streamlit as st
import pandas as pd
import statsmodels.api as sm
import plotly.express as px
import requests
from concurrent.futures import ThreadPoolExecutor
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIG & SECURE KEYS ---
try:
    ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]
except KeyError:
    st.error("Please set ZYTE_API_KEY in Streamlit Secrets.")
    st.stop()

# --- 2. ZYTE AI EXTRACTION LOGIC ---
def extract_single_product(url):
    """Uses Zyte AI to turn a product page into structured JSON."""
    api_url = "https://api.zyte.com/v1/extract"
    payload = {
        "url": url,
        "product": True,
        "customAttributes": {
            "mg_oxide": {"type": "integer", "description": "mg of magnesium oxide"},
            "mg_citrate": {"type": "integer", "description": "mg of magnesium citrate"},
            "mg_chelate": {"type": "integer", "description": "mg of magnesium chelate"},
            "count": {"type": "integer", "description": "total tablets/capsules"}
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

@st.cache_data(ttl=3600)
def get_search_links(search_url):
    """Finds the top product URLs from the search results."""
    api_url = "https://api.zyte.com/v1/extract"
    payload = {"url": search_url, "productNavigation": True}
    r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload)
    if r.status_code == 200:
        items = r.json().get("productNavigation", {}).get("items", [])
        return [item.get("url") for item in items if item.get("url")][:10]
    return []

# --- 3. UI & LEADERBOARD LOGIC ---
st.set_page_config(page_title="OverPrice Master", layout="wide")
st.title("⚖️ OverPrice: Global Magnesium Arbitrage")

# Initialize Google Sheets Connection
conn = st.connection("gsheets", type=GSheetsConnection)

# Display Global Leaderboard
st.subheader("🏆 Global Value Leaderboard")
try:
    global_df = conn.read(worksheet="Sheet1")
    if not global_df.empty:
        # We calculate the 'Value Score' (Higher is better)
        # Value Score = Ingredient Value / Price
        global_df['Value_Score'] = global_df['Total_Fair_Value'] / global_df['Price']
        leaderboard = global_df.sort_values('Value_Score', ascending=False).head(10)
        st.dataframe(leaderboard[['Brand', 'Price', 'Value_Score', 'URL']], use_container_width=True)
except Exception as e:
    st.info("Leaderboard is ready for its first contribution.")

# --- 4. THE MAIN RUNNER ---
if st.button("🚀 Run Analysis & Update Global Stats"):
    search_url = "https://www.amazon.com.au/s?k=Magnesium+Supplements"
    
    with st.spinner("Executing Parallel Scrape (Zyte AI)..."):
        links = get_search_links(search_url)
        
        # Parallel Execution for Speed
        with ThreadPoolExecutor(max_workers=5) as executor:
            scraped_results = list(executor.map(extract_single_product, links))
        
        # Clean Data
        results = [r for r in scraped_results if r and r['Price']]
        df = pd.DataFrame(results).fillna(0)
        
        if len(df) >= 3:
            # Regression Math
            df['Price_Per_Tab'] = df['Price'] / df['Count']
            X = df[['Mg_Oxide_mg', 'Mg_Citrate_mg', 'Mg_Chelate_mg']]
            X = sm.add_constant(X)
            
            model = sm.OLS(df['Price_Per_Tab'], X).fit()
            df['Total_Fair_Value'] = model.predict(X) * df['Count']
            
            # --- UPDATE DATABASE ---
            try:
                # Merge with existing data to avoid duplicates
                existing_data = conn.read(worksheet="Sheet1")
                final_df = pd.concat([existing_data, df]).drop_duplicates(subset=['URL'])
                conn.update(worksheet="Sheet1", data=final_df)
                st.success("Successfully contributed to Global Leaderboard!")
            except Exception as e:
                st.warning(f"Analysis complete, but database sync failed: {e}")

            # --- SHOW RESULTS ---
            st.write("### Current Search Results")
            st.dataframe(df[['Brand', 'Price', 'Total_Fair_Value']])
            
            fig = px.scatter(df, x="Total_Fair_Value", y="Price", text="Brand", trendline="ols",
                             title="Current Market Snapshot: Price vs. Ingredient Value")
            st.plotly_chart(fig)
            st.rerun()
        else:
            st.error("Not enough data points found. Try again.")
