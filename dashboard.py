import json
import os
import streamlit as st
import pandas as pd
import gspread
from streamlit_autorefresh import st_autorefresh

# 1. Page Configuration & Auto-Refresh
st.set_page_config(page_title="Zaikeban Foods Hisab", page_icon="🍽️", layout="wide")
st_autorefresh(interval=5000, key="data_refresh") # Refreshes every 5 seconds

st.title("🍽️ Zaikeban Foods Live Analytics")

# 3. Connect to Google Sheets
@st.cache_resource(ttl=300)
def get_sheet_client():
    """Authenticates using Streamlit Secrets instead of missing local files."""
    creds_dict = json.loads(st.secrets["GOOGLE_CLIENT_JSON"])
    token_dict = json.loads(st.secrets["GOOGLE_TOKEN_JSON"])
    return gspread.oauth_from_dict(credentials=creds_dict, authorized_user_info=token_dict)

try:
    gc = get_sheet_client()
    sh = gc.open(os.getenv("SPREADSHEET_NAME", "Zaikeban Foods Hisab"))

    # Fetch Data from all 4 tabs
    mukhwas_data = sh.worksheet("Mukhwas").get_all_values()
    bank_data = sh.worksheet("Bank").get_all_values()
    cash_data = sh.worksheet("Cash").get_all_values()
    orders_data = sh.worksheet("Orders").get_all_values()

    # --- TOP ROW: LIVE INVENTORY & BALANCES ---
    st.markdown("### 📊 Live Operations Overview")
    col1, col2, col3 = st.columns(3)
    
    # Render Mukhwas Inventory
    with col1:
        st.info("🍃 Mukhwas Stock (Grams)")
        if len(mukhwas_data) >= 2:
            mukhwas_df = pd.DataFrame([mukhwas_data[1]], columns=mukhwas_data[0])
            st.dataframe(mukhwas_df, hide_index=True)
            
    # Render Live Balances
    with col2:
        bank_bal = bank_data[-1][7] if len(bank_data) > 2 else bank_data[2][7] if len(bank_data) > 1 else "0"
        st.metric(label="💳 Bank Balance", value=f"₹ {bank_bal}")
    with col3:
        cash_bal = cash_data[-1][7] if len(cash_data) > 2 else cash_data[2][7] if len(cash_data) > 1 else "0"
        st.metric(label="💵 Cash Balance", value=f"₹ {cash_bal}")

    st.divider()

    # --- MIDDLE ROW: RECENT TRANSACTIONS ---
    st.markdown("### 💸 Financial Ledgers")
    t_col1, t_col2 = st.columns(2)
    
    with t_col1:
        st.caption("Recent Bank Transactions")
        if len(bank_data) > 1:
            df_bank = pd.DataFrame(bank_data[2:], columns=bank_data[0])
            st.dataframe(df_bank.tail(10).iloc[::-1], hide_index=True) # Shows newest first
            
    with t_col2:
        st.caption("Recent Cash Transactions")
        if len(cash_data) > 1:
            df_cash = pd.DataFrame(cash_data[2:], columns=cash_data[0])
            st.dataframe(df_cash.tail(10).iloc[::-1], hide_index=True)

    st.divider()

    # --- BOTTOM ROW: ORDERS ---
    st.markdown("### 📦 Recent Customer Orders")
    if len(orders_data) > 1:
        df_orders = pd.DataFrame(orders_data[1:], columns=orders_data[0])
        st.dataframe(df_orders.tail(10).iloc[::-1], hide_index=True, use_container_width=True)

except Exception as e:
    st.error(f"Failed to load dashboard data: {str(e)}")