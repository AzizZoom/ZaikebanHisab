"""MongoDB persistence and Google Sheets schema."""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient, DESCENDING

load_dotenv()
_uri = os.getenv("MONGO_URI")
client = MongoClient(_uri, serverSelectionTimeoutMS=5000) if _uri else None
users = client["ZaikebanHisabDB"]["users"] if client is not None else None
DEFAULT_SHEET_NAME = os.getenv("SPREADSHEET_NAME", "Zaikeban Foods Hisab")
DEFAULT_SHEET = DEFAULT_SHEET_NAME
HEADERS = {
    "Bank": ["Year", "Month", "Date", "Credit/Debit", "Category Of Income Or Expense", "Amount", "Final Amount", "Live", "Comments"],
    "Cash": ["Year", "Month", "Date", "Credit/Debit", "Category Of Income Or Expense", "Amount", "Final Amount", "Live", "Comments"],
    "Mukhwas": ["CC", "SD", "KD", "RS", "MP"],
    "Orders": ["Year", "Month", "Date", "Name", "Area", "Amount", "Source", "Payment status", "Order status", "Order details"],
}

def _users():
    if users is None: raise RuntimeError("MONGO_URI is not configured")
    return users

def normalize_phone(phone: str) -> str:
    value = str(phone or "").replace("whatsapp:", "").strip()
    value = "".join(c for c in value if c.isdigit() or c == "+")
    return value if value.startswith("+") else "+" + value

def save_user(email: str, creds_json: str, sheet_id: str = None):
    fields = {"creds_json": creds_json, "updated_at": datetime.now(timezone.utc)}
    on_insert = {"email": email, "phone": ""}
    if sheet_id is not None:
        fields["sheet_id"] = sheet_id
    else:
        on_insert["sheet_id"] = DEFAULT_SHEET_NAME
    _users().update_one({"email": email}, {"$set": fields, "$setOnInsert": on_insert}, upsert=True)

def link_phone(email: str, phone: str):
    _users().update_one({"email": email}, {"$set": {"phone": normalize_phone(phone), "updated_at": datetime.now(timezone.utc)}})

def get_user_by_phone(phone: str):
    number = normalize_phone(phone)
    return _users().find_one({"phone": number}) or _users().find_one({"phone": {"$regex": number[-10:] + "$"}})

def get_user_by_email(email: str):
    return _users().find_one({"email": email}) if email else None

def get_any_authenticated_user():
    return _users().find_one({"creds_json": {"$nin": [None, ""]}}, sort=[("updated_at", DESCENDING)])

def initialize_user_sheet(client, email: str):
    user = get_user_by_email(email)
    stored_id = (user or {}).get("sheet_id")
    book = None
    if stored_id:
        try: book = client.open_by_key(stored_id)
        except Exception: pass
    if book is None:
        try: book = client.open(DEFAULT_SHEET_NAME)
        except Exception: book = client.create(DEFAULT_SHEET_NAME)
        if user:
            save_user(email, user.get("creds_json", ""), book.id)
    sheets = {ws.title: ws for ws in book.worksheets()}
    for title, headers in HEADERS.items():
        ws = sheets.get(title)
        if ws is None: ws = book.add_worksheet(title=title, rows=1000, cols=max(10, len(headers)))
        values = ws.get_all_values()
        if title in ("Bank", "Cash"):
            if not values: ws.update("A1", [[f"{title} Transactions"]])
            if len(values) < 2 or values[1][:len(headers)] != headers: ws.update("A2", [headers])
        elif title == "Mukhwas":
            if not values:
                ws.update("A1", [headers]); ws.update("A2", [["0"] * 5])
            else:
                if values[0][:5] != headers: ws.update("A1", [headers])
                if len(values) < 2 or not any(values[1][:5]): ws.update("A2", [["0"] * 5])
        elif not values or values[0][:len(headers)] != headers: ws.update("A1", [headers])
    return book
