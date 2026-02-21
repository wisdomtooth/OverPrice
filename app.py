import streamlit as st
import pandas as pd
import statsmodels.api as sm
import plotly.express as px
import requests
import re
import base64
from bs4 import BeautifulSoup

# --- CONFIG & SECRETS ---
# Access secrets from Streamlit's dashboard settings
ZYTE_API_KEY = st.secrets.get("ZYTE_API_KEY", "47c0ce047e104f9cab87ff9e0e1a7d26")

def get_amazon_html(url):
    response = requests.post(
        "https://api.zyte.com/v1/extract",
        auth=(ZYTE_API_KEY, ""),
        json={"url": url, "httpResponseBody": True},
    )
    if response.status_code == 200:
        return base64.b64decode(response.json()["httpResponseBody"]).decode("utf-8")
    return ""

def parse_ingredients(html):
    # This is a simplified parser. In production, we'd use an LLM call here.
    oxide = re.search(r'oxide.*?(\d+)mg', html, re.I)
    citrate = re.search(r'citrate.*?(\d+)mg', html, re.I)
    chelate = re.search(r'chelate.*?(\d+)mg', html, re.I)
    
    return {
        "Mg_Oxide_mg": int(oxide.group(1)) if oxide else 0,
        "Mg_Citrate_mg": int(citrate.group(1)) if citrate else 0,
        "Mg_Chelate_mg": int(chelate.group(1)) if chelate else 0
    }

# --- STREAMLIT UI ---
st.set_page_config(page_title="OverPrice - Value Arbitrage", layout="wide")
st.title("⚖️ OverPrice: Magnesium Value Detector")

if st.button("🚀 Run Live Market Analysis"):
    with st.spinner("Scraping Amazon.au and calculating shadow prices..."):
        # 1. Get Search Results
        search_url = "https://www.amazon.com.au/s?k=Magnesium+Supplements"
        search_html = get_amazon_html(search_url)
        soup = BeautifulSoup(search_html, 'html.parser')
        
        # 2. Extract first 5 links (keeping it small for the test)
        links = []
        for a in soup.find_all('a', href=True):
            if '/dp/' in a['href'] and len(links) < 5:
                url = "https://www.amazon.com.au" + a['href'].split('?')[0]
                if url not in links: links.append(url)

        # 3. Scrape individual products
        results = []
        for link in links:
            p_html = get_amazon_html(link)
            price_match = re.search(r'\$(\d+\.\d+)', p_html)
            if price_match:
                row = {"Brand": link.split('/')[3], "Price": float(price_match.group(1))}
                row.update(parse_ingredients(p_html))
                # Adding a default 'Count' if not found for math stability
                row['Count'] = 100 
                results.append(row)
        
        df = pd.DataFrame(results)
        
        if len(df) > 3: # Need at least a few points for regression
            df['Price_Per_Tab'] = df['Price'] / df['Count']
            
            # 4. Regression
            X = df[['Mg_Oxide_mg', 'Mg_Citrate_mg', 'Mg_Chelate_mg']]
            X = sm.add_constant(X)
            model = sm.OLS(df['Price_Per_Tab'], X).fit()
            
            # 5. Display results
            st.write("### Market Efficiency Analysis")
            df['Fair_Value'] = model.predict(X) * df['Count']
            df['Hype_Tax'] = df['Price'] - df['Fair_Value']
            
            st.dataframe(df[['Brand', 'Price', 'Fair_Value', 'Hype_Tax']])
            
            fig = px.scatter(df, x="Fair_Value", y="Price", text="Brand", 
                             title="Actual Price vs. Ingredient Value")
            st.plotly_chart(fig)
        else:
            st.warning("Not enough data extracted. Amazon's layout may have changed.")
