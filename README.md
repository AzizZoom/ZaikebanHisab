# 🌿 Zaikeban Foods Hisab — WhatsApp AI ERP & Ledger Assistant

An end-to-end conversational ERP, inventory tracker, and accounting assistant built for **Zaikeban Foods**. Business owners can log orders, track Mukhwas stock across flavours, record Bank/Cash income and expenses, and query real-time financial reports directly through **WhatsApp** using natural English, Hindi, or Hinglish messages and images.

---

## 👆 Links:
Render    - https://zaikebanhisab.onrender.com/
Streamlit - https://zaikebanhisab.streamlit.app/

---

## ✨ Key Features

- **Conversational WhatsApp ERP (Text & Image):** Powered by Google Gemini (`gemini-2.5-flash` with multi-model fallback) to parse unstructured English, Hindi, and Hinglish messages or bill photos into structured ERP actions.
- **Strict Dual-Ledger Accounting (`Bank` vs. `Cash`):** Automatically routes UPI, GPay, NEFT, and Bank transactions to the **Bank** ledger and cash transactions to the **Cash** ledger. Blocks ambiguous payment entries until a payment mode is explicitly specified so ledgers never drift.
- **Real-Time Mukhwas Inventory & Smart Alerts:** Tracks gram-level stock across all 5 signature flavours (`CC`, `SD`, `KD`, `RS`, `MP`) and triggers automatic WhatsApp stock alerts:
  - 🟡 **Yellow Alert:** Stock below `1,000g`
  - 🔴 **Red Alert:** Critically low stock below `400g`
- **Multi-User Google OAuth 2.0 & Auto-Provisioning:** One-click Google Sign-In automatically provisions a structured Google Spreadsheet (`Bank`, `Cash`, `Orders`, and `Mukhwas` tabs with live running-balance formulas) and links it to the user's WhatsApp number.
- **Live Streamlit Analytics Dashboard:** Interactive visual dashboard displaying KPI cards, revenue vs. expense charts, pending order/payment queues, and flavour-wise inventory levels.

---

## 🏗️ System Architecture

1. **Messaging Layer:** Meta WhatsApp Cloud API (Graph API v21.0) receives incoming user messages/media and delivers real-time confirmations.
2. **Backend & OAuth Server:** FastAPI (`main.py`) hosted on Render handles Meta webhooks, Google OAuth 2.0 authentication, and spreadsheet orchestration via `gspread`.
3. **AI Parsing Engine:** Google Gemini (`models/gemini-2.5-flash` -> `gemini-2.5-flash-lite` -> `gemini-2.0-flash`) translates natural language into validated JSON action schemas (`ORDER`, `STOCK_ADD`, `EXPENSE`, `INCOME`, `QUERY_LIVE`, `FETCH_PENDING`, `REPORT_OVERVIEW`, `UPDATE_ORDER_STATUS`).
4. **Database & Storage:**
   - **MongoDB Atlas:** Stores encrypted user OAuth credentials and WhatsApp phone-to-account mappings (`database.py`).
   - **Google Sheets:** Serves as the live, auditable cloud ledger for transactions, orders, and inventory.
5. **Analytics Frontend:** Streamlit (`dashboard.py`) for visual business intelligence.

---

## 💬 Sample WhatsApp Commands

| Action | Example WhatsApp Message | Bot Behaviour |
| :--- | :--- | :--- |
| **Paid Order** | *"Order from Rahul in Andheri for 250 rupees, 200g CC and 100g MP, payment done via UPI and order delivered"* | Deducts `200g CC` & `100g MP`, logs order in `Orders`, and credits `₹250` to `Bank` hisab. |
| **Pending Order** | *"Order from Anit in Bombay for 1000 rupees, 1600g CC, payment is pending and order is delivered"* | Deducts `1600g CC`, logs order with `Payment: Pending`, leaves `Bank`/`Cash` untouched, and triggers low-stock alert if `<400g`. |
| **Settle Pending Payment** | *"Anit has completed pending payment via GPay"* | Marks Anit's order `Done` in `Orders` and credits `₹1,000` to `Bank` hisab. |
| **Expense / Income** | *"Spent 40 rupees cash on courier"* | Debits `₹40` from `Cash` hisab and confirms ledger name in reply. |
| **Restock Inventory** | *"Added 500g KD stock"* | Increments `KD` stock in `Mukhwas` tab and returns updated inventory. |
| **Live Status Query** | *"What is my live bank balance, cash balance, and Mukhwas stock?"* | Returns real-time Bank balance, Cash balance, and gram-wise stock across all flavours. |
| **Pending Queue** | *"Show pending payments and orders"* | Lists all orders with pending payment or delivery status. |

---

## 🚀 Local Setup & Environment Variables

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure .env
```bash
Create a .env file in the project root:
```

Code snippet

```bash
GEMINI_API_KEY=your_google_ai_studio_key
MONGO_URI=your_mongodb_atlas_connection_string
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
SESSION_SECRET=your_random_session_secret
WHATSAPP_TOKEN=your_permanent_meta_system_user_token
WHATSAPP_PHONE_NUMBER_ID=your_meta_phone_number_id
WHATSAPP_VERIFY_TOKEN=zaikeban_verify_token
GRAPH_API_VERSION=v21.0
SPREADSHEET_NAME=your_spreadsheet_name
STREAMLIT_URL=[https://your-streamlit-dashboard-url.streamlit.app]
```

### 3. Run the Services
```Bash
# Start FastAPI Backend & Webhook Server
uvicorn main:app --host 0.0.0.0 --port 8000

# Start Streamlit Analytics Dashboard
streamlit run dashboard.py
```
