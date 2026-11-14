"""Manually refreshed Streamlit business dashboard."""
import json, os
import gspread
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
import database

load_dotenv(); SCOPES=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/userinfo.email","openid"]
st.set_page_config(page_title="Zaikeban Foods Hisab",page_icon="🌿",layout="wide")
st.markdown("""<style>
@media (max-width: 768px) {
  .st-key-dashboard_header [data-testid="stHorizontalBlock"] { flex-direction: column !important; align-items: stretch !important; gap: 0.35rem !important; width: 100% !important; }
  .st-key-dashboard_header [data-testid="column"] { width: 100% !important; min-width: 0 !important; flex: 1 1 100% !important; }
  .st-key-dashboard_header h1 { font-size: clamp(1.65rem, 5vw, 1.5rem) !important; line-height: 1.2 !important; white-space: nowrap !important; }
  .st-key-dashboard_header [data-testid="stButton"] { width: max-content !important; margin-left: 0 !important; }
  .st-key-kpi_metrics [data-testid="stHorizontalBlock"] { display: grid !important; grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: 0.4rem 0.5rem !important; }
  .st-key-kpi_metrics [data-testid="column"] { width: 100% !important; min-width: 0 !important; flex: none !important; }
  .st-key-kpi_metrics [data-testid="stMetric"] { width: 100% !important; min-width: 0 !important; padding: 0.45rem 0.4rem !important; }
  .st-key-kpi_metrics [data-testid="stMetricLabel"] { font-size: 0.68rem !important; line-height: 1.15 !important; }
  .st-key-kpi_metrics [data-testid="stMetricValue"] { font-size: clamp(1rem, 3.2vw, 0.92rem) !important; line-height: 1.2 !important; white-space: nowrap !important; }
}
</style>""",unsafe_allow_html=True)
with st.container(key="dashboard_header"):
 header,refresh_col=st.columns([5,1]);header.title("🌿 Zaikeban Foods Hisab");header.caption("Live business analytics")
if refresh_col.button("🔄 Refresh Data"):
 st.cache_data.clear()
 st.rerun()
email=st.query_params.get("email")
try:user=database.get_user_by_email(email) if email else None
except Exception as e:st.error(f"Database unavailable: {e}");st.stop()
if not user:
 try:user=database.get_any_authenticated_user()
 except Exception as e:st.error(f"Database unavailable: {e}");st.stop()
if not user:st.info("Sign in through the web app to connect Google Sheets.");st.stop()
try:
 creds=Credentials.from_authorized_user_info(json.loads(user["creds_json"]),SCOPES)
 if creds.expired and creds.refresh_token:creds.refresh(GoogleRequest());database.save_user(user["email"],creds.to_json(),user.get("sheet_id"))
 gc=gspread.authorize(creds)
 stored_id=user.get("sheet_id")
 try:
  if not stored_id:raise gspread.SpreadsheetNotFound("No stored spreadsheet key")
  book=gc.open_by_key(stored_id)
 except Exception:
  book=gc.open(os.getenv("SPREADSHEET_NAME","Zaikeban Foods Hisab"))
  database.save_user(user["email"],creds.to_json(),book.id)
except Exception as e:st.error(f"Could not connect to spreadsheet: {e}");st.stop()
@st.cache_data(ttl=60)
def fetch_sheet_ranges(spreadsheet_id, credentials_json):
 """Read the four dashboard ranges together and cache the result for one minute."""
 token=Credentials.from_authorized_user_info(json.loads(credentials_json),SCOPES)
 if token.expired and token.refresh_token:token.refresh(GoogleRequest())
 sh=gspread.authorize(token).open_by_key(spreadsheet_id)
 response=sh.values_batch_get(["Mukhwas!A1:E10","Bank!A1:I500","Cash!A1:I500","Orders!A1:J500"])
 return {entry["range"].split("!")[0]:entry.get("values",[]) for entry in response.get("valueRanges",[])}
try:
 values_by_tab=fetch_sheet_ranges(book.id,creds.to_json())
except Exception as e:st.error(f"Unable to read spreadsheet data: {e}");st.stop()
def frame(tab):
 values=values_by_tab.get(tab,[])
 if tab in ("Bank","Cash"):
  if len(values)<2:return pd.DataFrame()
  headers=values[1];data=values[2:]
 else:
  if not values:return pd.DataFrame()
  headers=values[0];data=values[1:]
 # Trailing empty columns/rows are padded so sparse API values align to headers.
 clean=[(list(r)+[""]*len(headers))[:len(headers)] for r in data if any(str(x).strip() for x in r)]
 return pd.DataFrame(clean,columns=headers) if headers else pd.DataFrame()
def num(v):
 try:return float(str(v).replace(",",""))
 except:return 0.0
def live(tab):
 data=values_by_tab.get(tab,[])
 # Include row 3, which can hold the initial/placeholder balance.
 for row in reversed(data[2:]):
  x=row[7] if len(row)>7 else ""
  try:return num(x)
  except:pass
 return 0.0
try:
 orders=frame("Orders");bank=frame("Bank");cash=frame("Cash")
 payments=orders[orders["Payment status"].astype(str).str.lower()=="pending"] if "Payment status" in orders else pd.DataFrame()
 deliveries=orders[orders["Order status"].astype(str).str.lower()=="pending"] if "Order status" in orders else pd.DataFrame()
 pending_sum=sum(num(v) for v in payments.get("Amount",[]))
 with st.container(key="kpi_metrics"):
  a,b,c,d=st.columns(4);a.metric("Live Bank Balance",f"₹{live('Bank'):,.2f}");b.metric("Live Cash Balance",f"₹{live('Cash'):,.2f}");c.metric("Pending Payments",f"{len(payments)} · ₹{pending_sum:,.2f}");d.metric("Pending Deliveries",len(deliveries))
 st.subheader("Mukhwas Stock");raw=book.worksheet("Mukhwas").row_values(2);stock=pd.DataFrame({"Flavour":["CC","SD","KD","RS","MP"],"Live grams":[int(num(raw[i])) if i<len(raw) else 0 for i in range(5)]})
 x,y=st.columns([1.4,1]);x.plotly_chart(px.bar(stock,x="Flavour",y="Live grams",color="Flavour",text="Live grams",title="Current stock in grams"),use_container_width=True,config={"displayModeBar":False});y.dataframe(stock,use_container_width=True,hide_index=True)
 st.subheader("Pending Action Center")
 pending=pd.concat([payments.assign(Action="Payment pending"),deliveries.assign(Action="Delivery pending")]).drop_duplicates() if len(payments) or len(deliveries) else pd.DataFrame()
 if pending.empty:st.success("No pending actions.")
 else:st.dataframe(pending,use_container_width=True,hide_index=True)
 st.subheader("Financial Ledgers");x,y=st.columns(2)
 for col,df,label in [(x,bank,"Bank"),(y,cash,"Cash")]:
  col.markdown(f"**{label} transactions**")
  if not df.empty:col.dataframe(df.iloc[::-1].head(100),use_container_width=True,hide_index=True)
  else:col.info("No transactions yet.")
 st.subheader("Recent Customer Orders")
 if not orders.empty:st.dataframe(orders.iloc[::-1].head(250),use_container_width=True,hide_index=True)
 else:st.info("No orders yet.")
except Exception as e:st.error(f"Unable to load dashboard: {e}")
