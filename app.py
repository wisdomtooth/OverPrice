import streamlit as st
import pandas as pd
import statsmodels.api as sm
import plotly.express as px

st.set_page_config(page_title="Supplement Value Arbitrage", layout="wide")

st.title("💊 Magnesium Value Optimizer")
st.write("Decomposing retail price into raw ingredient value.")

# --- SIDEBAR: CONFIG ---
st.sidebar.header("Settings")
zyte_api_key = st.sidebar.text_input("Zyte API Key", type="password")
category_url = st.sidebar.text_input("Amazon Category URL", value="https://www.amazon.com.au/s?k=Magnesium...")

# --- STEP 1: DATA INGESTION ---
# For the MVP, we use a 'Mock' dataset that reflects the Blackmores style
# In Phase 2, we replace this with the scraper output
data = {
    'Brand': ['Blackmores', 'Swisse', 'Cenovis', 'Healthy Care', 'Doctor\'s Best', 'Now Foods'],
    'Price': [27.59, 22.00, 15.50, 18.00, 42.00, 38.00],
    'Count': [200, 120, 100, 250, 120, 180],
    'Mg_Oxide_mg': [245, 150, 300, 250, 0, 50],
    'Mg_Citrate_mg': [45, 100, 0, 0, 0, 150],
    'Mg_Chelate_mg': [15, 0, 0, 0, 200, 100],
}

df = pd.DataFrame(data)
df['Price_Per_Tab'] = df['Price'] / df['Count']

# --- STEP 2: THE HEDONIC REGRESSION ENGINE ---
# We calculate the market rate for each MG type
X = df[['Mg_Oxide_mg', 'Mg_Citrate_mg', 'Mg_Chelate_mg']]
X = sm.add_constant(X)
y = df['Price_Per_Tab']

model = sm.OLS(y, X).fit()
coeffs = model.params

# --- STEP 3: VISUALIZATION ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Market 'Shadow Prices'")
    st.write("What the market charges per mg of:")
    st.metric("Magnesium Oxide", f"${coeffs['Mg_Oxide_mg']:.4f}")
    st.metric("Magnesium Citrate", f"${coeffs['Mg_Citrate_mg']:.4f}")
    st.metric("Magnesium Chelate", f"${coeffs['Mg_Chelate_mg']:.4f}")

with col2:
    st.subheader("Price Decomposition")
    df['Fair_Value_Per_Tab'] = model.predict(X)
    df['Total_Fair_Value'] = df['Fair_Value_Per_Tab'] * df['Count']
    df['Hype_Tax'] = df['Price'] - df['Total_Fair_Value']
    
    fig = px.bar(df, x='Brand', y=['Total_Fair_Value', 'Hype_Tax'], 
                 title="Fair Value vs. Brand Premium (Hype Tax)",
                 barmode='stack')
    st.plotly_chart(fig)

# --- STEP 4: INDIVIDUAL ANALYSIS ---
st.divider()
selected_brand = st.selectbox("Select a Brand to Analyze", df['Brand'])
prod = df[df['Brand'] == selected_brand].iloc[0]

st.write(f"### Analysis for {selected_brand}")
if prod['Hype_Tax'] > 0:
    st.error(f"You are paying a **${prod['Hype_Tax']:.2f}** premium for this brand name.")
else:
    st.success(f"This product is a **BARGAIN**. It is priced ${abs(prod['Hype_Tax']):.2f} below market value for its ingredients.")
