import streamlit as st
import requests
import base64

st.title("Zyte Connectivity Diagnostic")

# 1. Check Secret
zyte_key = st.secrets.get("ZYTE_API_KEY")
if not zyte_key:
    st.error("❌ ZYTE_API_KEY not found in Streamlit Secrets.")
    st.stop()
else:
    st.success(f"✅ Secret found (Starts with: {zyte_key[:4]}...)")

# 2. Test Connection
if st.button("📡 Send Test Request to Zyte"):
    api_url = "https://api.zyte.com/v1/extract"
    # We'll use a simple, non-Amazon URL to prove the API works
    payload = {
        "url": "https://toscrape.com", 
        "httpResponseBody": True
    }
    
    with st.spinner("Pinging Zyte..."):
        try:
            # Note the auth=(zyte_key, "") - the empty string password is mandatory
            response = requests.post(api_url, auth=(zyte_key, ""), json=payload, timeout=30)
            
            st.write(f"**Status Code:** {response.status_code}")
            
            if response.status_code == 200:
                st.balloons()
                st.success("✅ Zyte API is connected and responding!")
                st.json(response.json().keys()) # Show what data came back
            elif response.status_code == 401:
                st.error("❌ 401 Unauthorized: Your API Key is likely invalid or copied incorrectly.")
            else:
                st.error(f"❌ Error: {response.text}")
                
        except Exception as e:
            st.error(f"❌ Connection Failed: {e}")
