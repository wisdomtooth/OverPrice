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
    api_url = "https://api.zyte.com/v1/extract"
    
    # We add a 'description' that acts as a prompt for the AI
    payload = {
        "url": url,
        "product": True,
        "customAttributes": {
            "mg_oxide": {
                "type": "integer", 
                "description": "Total milligrams (mg) of Magnesium Oxide. Look in the 'Ingredients' or 'Supplement Facts' section."
            },
            "mg_citrate": {
                "type": "integer", 
                "description": "Total milligrams (mg) of Magnesium Citrate. Look for 'as citrate' or 'citrate' in ingredients."
            },
            "mg_chelate": {
                "type": "integer", 
                "description": "Total milligrams (mg) of Magnesium Amino Acid Chelate or Bisglycinate."
            },
            "count": {
                "type": "integer", 
                "description": "The number of tablets, capsules, or pills in the entire bottle (e.g., 60, 120, 200)."
            }
        }
    }
    
    try:
        # We increase timeout to 60s because AI extraction is slower
        r = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        if r.status_code == 200:
            res = r.json()
            p = res.get("product", {})
            c = res.get("customAttributes", {})
            
            # CRITICAL: We only return the product if it actually has a price and at least one ingredient
            if p.get("price") and (c.get("mg_oxide") or c.get("mg_citrate") or c.get("mg_chelate")):
                return {
                    "Brand": p.get("brand") or p.get("name", "Unknown")[:15],
                    "Price": float(p.get("price")),
                    "Mg_Oxide_mg": int(c.get("mg_oxide") or 0),
                    "Mg_Citrate_mg": int(c.get("mg_citrate") or 0),
                    "Mg_Chelate_mg": int(c.get("mg_chelate") or 0),
                    "Count": int(c.get("count") or 100),
                    "URL": url
                }
    except Exception as e:
        print(f"Error scraping {url}: {e}")
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
