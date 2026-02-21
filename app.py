import streamlit as st
import pandas as pd
import statsmodels.api as sm
import plotly.express as px
import requests
import time

# --- SECURE CONFIG ---
try:
    ZYTE_API_KEY = st.secrets["ZYTE_API_KEY"]
except KeyError:
    st.error("Please set the ZYTE_API_KEY in Streamlit Secrets.")
    st.stop()

# --- DATA EXTRACTION ENGINE ---
def extract_with_zyte_ai(url):
    """Uses Zyte's AI to find product details and specific mg dosages."""
    api_url = "https://api.zyte.com/v1/extract"
    
    payload = {
        "url": url,
        "product": True,
        "customAttributes": {
            "mg_oxide": {"type": "integer", "description": "milligrams of magnesium oxide"},
            "mg_citrate": {"type": "integer", "description": "milligrams of magnesium citrate"},
            "mg_chelate": {"type": "integer", "description": "milligrams of magnesium chelate"},
            "count": {"type": "integer", "description": "total tablets or capsules in the bottle"}
        }
    }

    try:
        response = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            prod = res_json.get("product", {})
            # Zyte returns custom attributes in a 'values' list or dict depending on configuration
            custom = res_json.get("customAttributes", {})
            
            return {
                "Brand": prod.get("brand") or prod.get("name", "Unknown")[:20],
                "Price": prod.get("price"),
                "Mg_Oxide_mg": custom.get("mg_oxide", 0),
                "Mg_Citrate_mg": custom.get("mg_citrate", 0),
                "Mg_Chelate_mg": custom.get("mg_chelate", 0),
                "Count": custom.get("count") or 100
            }
    except Exception as e:
        st.warning(f"Failed to scrape {url}: {e}")
    return None

def get_product_links(search_url):
    """Fetches initial links from search page using Zyte's standard extraction."""
    api_url = "https://api.zyte.com/v1/extract"
    payload = {"url": search_url, "productNavigation": True}
    response = requests.post(api_url, auth=(ZYTE_API_KEY, ""), json=payload)
    
    if response.status_code == 200:
        nav = response.json().get("productNavigation", {})
        # Extract URLs from the navigation items
        items = nav.get("items", [])
        links = [item.get("url") for item in items if item.get("url")][:8] # Limit to 8 for speed
        return links
    return []

# --- STREAMLIT UI ---
st.set_page_config(page_title="OverPrice - Magnesium Optimizer", layout="wide")

st.title("⚖️ OverPrice: Magnesium Value Arbitrage")
st.markdown("This tool reverse-engineers the **Market Price** of magnesium ingredients to find which brands are 'Hype' vs 'Value'.")

if st.button("🚀 Start Deep Market Analysis"):
    # 1. Discovery
    search_url = "https://www.amazon.com.au/s?k=Magnesium+Supplements"
    with st.spinner("Finding products on Amazon..."):
        links = get_product_links(search_url)
    
    if not links:
        st.error("No product links found. Check your Zyte API status.")
    else:
        # 2. Deep Scrape
        results = []
        progress_bar = st.progress(0)
        
        for i, link in enumerate(links):
            with st.spinner(f"Analyzing Product {i+1} of {len(links)}..."):
                data = extract_with_zyte_ai(link)
                if data and data['Price']:
                    results.append(data)
            progress_bar.progress((i + 1) / len(links))
        
        df = pd.DataFrame(results).fillna(0)

        # 3. Math Engine
        if len(df) >= 3:
            # Calculate Price Per Tablet
            df['Price_Per_Tab'] = df['Price'] / df['Count']
            
            # Regression: Price ~ Oxide + Citrate + Chelate
            X = df[['Mg_Oxide_mg', 'Mg_Citrate_mg', 'Mg_Chelate_mg']]
            X = sm.add_constant(X)
            
            try:
                model = sm.OLS(df['Price_Per_Tab'], X).fit()
                df['Fair_Value_Per_Tab'] = model.predict(X)
                df['Total_Fair_Value'] = df['Fair_Value_Per_Tab'] * df['Count']
                df['Hype_Tax'] = df['Price'] - df['Total_Fair_Value']
                
                # --- VISUALS ---
                st.subheader("Market Summary")
                
                # Shadow Prices (The coefficients)
                coeffs = model.params
                c1, c2, c3 = st.columns(3)
                c1.metric("Market Rate: Oxide", f"${coeffs.get('Mg_Oxide_mg', 0):.4f}/mg")
                c2.metric("Market Rate: Citrate", f"${coeffs.get('Mg_Citrate_mg', 0):.4f}/mg")
                c3.metric("Market Rate: Chelate", f"${coeffs.get('Mg_Chelate_mg', 0):.4f}/mg")

                st.divider()

                # Comparison Table
                st.write("### Product Value Breakdown")
                # Format table for display
                display_df = df[['Brand', 'Price', 'Total_Fair_Value', 'Hype_Tax']].copy()
                display_df['Hype_Tax'] = display_df['Hype_Tax'].map("${:,.2f}".format)
                st.dataframe(display_df.sort_values('Price'), use_container_width=True)

                # Chart
                fig = px.scatter(df, x="Total_Fair_Value", y="Price", text="Brand",
                                 labels={"Total_Fair_Value": "Calculated Value (Ingredients)", "Price": "Actual Retail Price"},
                                 title="Value vs. Price (Products above the line are OVERPRICED)")
                fig.add_shape(type="line", x0=0, y0=0, x1=df['Price'].max(), y1=df['Price'].max(), line=dict(color="Red", dash="dash"))
                st.plotly_chart(fig)

            except Exception as e:
                st.error(f"Mathematical Error: {e}")
        else:
            st.warning("Insufficient valid data found for a regression. Try again in a few minutes.")
