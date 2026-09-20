import os
import re
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Form, Response, Request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
import google.generativeai as genai

from database import get_user_by_phone, update_user_tokens

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ZaikebanHisab")

app = FastAPI(title="ZaikebanHisab Engine")

# Configuration
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "Zaikeban Foods Hisab")
VALID_FLAVOURS = ["CC", "SD", "KD", "RS", "MP"]

model = None
ACTIVE_MODEL_NAME = ""

def setup_ai():
    global model, ACTIVE_MODEL_NAME
    genai.configure(api_key=GOOGLE_API_KEY)
    candidates = [
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
        "models/gemini-1.5-flash",
    ]
    for m_name in candidates:
        try:
            test_model = genai.GenerativeModel(m_name)
            model = test_model
            ACTIVE_MODEL_NAME = m_name
            logger.info(f"AI System Online using: {m_name}")
            return
        except Exception:
            pass
    logger.critical("AI Init Failed. Verify your GEMINI_API_KEY.")

setup_ai()

SYSTEM_PROMPT = f"""
You are the business parser for 'Zaikeban Foods'.
Valid Mukhwas Flavours: {VALID_FLAVOURS}. All quantities must be tracked in integer GRAMS.

You must parse user messages into a strict JSON Array of operations.
Possible actions:

1. ORDER:
   Customer order details.
   Schema:
   {{
     "action": "ORDER",
     "name": string (Customer name, default "Unknown"),
     "area": string (Area/Location, default "Local"),
     "amount": number (Total order value),
     "source": "WhatsApp" | "Instagram" | "Direct",
     "payment_status": "Done" | "Pending",
     "payment_mode": "Bank" | "Cash",
     "order_status": "Delivered" | "Pending",
     "items": [
       {{"flavour": "CC"|"SD"|"KD"|"RS"|"MP", "grams": number}}
     ]
   }}

2. STOCK_ADD:
   New batch of mukhwas prepared/restocked.
   Schema:
   {{
     "action": "STOCK_ADD",
     "items": [
       {{"flavour": "CC"|"SD"|"KD"|"RS"|"MP", "grams": number}}
     ],
     "comments": string
   }}

3. EXPENSE:
   Any business expense (raw materials, couriers, labels, ingredients).
   Schema:
   {{
     "action": "EXPENSE",
     "mode": "Bank" | "Cash",
     "category": string (e.g., "Raw Material", "Courier", "Label", "Personal"),
     "amount": number (positive value),
     "comments": string
   }}

4. INCOME:
   Direct income/transfers (not regular product orders, e.g. bank deposit, personal funds).
   Schema:
   {{
     "action": "INCOME",
     "mode": "Bank" | "Cash",
     "category": string (e.g., "Bank Deposit", "Personal"),
     "amount": number (positive value),
     "comments": string
   }}

5. QUERY_BALANCE:
   User asking for live Bank or Cash balance (e.g., "Bank balance?", "Cash kitna hai?").
   Schema:
   {{
     "action": "QUERY_BALANCE",
     "target": "Bank" | "Cash" | "Both"
   }}

6. QUERY_STOCK:
   User asking for current mukhwas inventory (e.g., "Stock batao", "How much CC left?").
   Schema:
   {{
     "action": "QUERY_STOCK",
     "flavour": "ALL" | "CC" | "SD" | "KD" | "RS" | "MP"
   }}

CRITICAL RULES:
- Return ONLY valid raw JSON Array: [ {{...}} ]. No markdown backticks.
- Understand Hindi/English slang (e.g., "becha", "aaya", "maal banaya", "kharcha").
- Convert any kg inputs to grams (e.g., 2kg = 2000).
"""

def get_gspread_client():
    """Authenticates using the local JSON files instead of MongoDB variables."""
    return gspread.oauth(
        credentials_filename="client_secret.json",
        authorized_user_filename="token.json"
    )

def append_transaction_row(ws, credit_or_debit: str, category: str, amount: float, comments: str = ""):
    now = datetime.now()
    month_name = now.strftime("%b")
    all_vals = ws.get_all_values()
    next_row = len(all_vals) + 1
    prev_row = next_row - 1
    
    final_amount = amount if credit_or_debit == "Credit" else -amount
    
    # Formula for Live balance in Column H
    if prev_row < 3:
        live_formula = f"=G{next_row}"
    else:
        live_formula = f"=H{prev_row}+G{next_row}"

    row_data = [
        now.year,
        month_name,
        now.day,
        credit_or_debit,
        category,
        amount,
        final_amount,
        live_formula,
        comments
    ]
    ws.append_row(row_data, value_input_option="USER_ENTERED")

@app.post("/whatsapp")
async def whatsapp_webhook(
    From: str = Form(...),
    Body: Optional[str] = Form(None)
):
    sender_phone = From.replace("whatsapp:", "").strip()
    twiml = MessagingResponse()
    
    user = get_user_by_phone(sender_phone)
    if not user:
        twiml.message("⚠️ Number not authorized for ZaikebanHisab.")
        return Response(content=str(twiml), media_type="application/xml")

    if not Body:
        twiml.message("Please send a text message or query.")
        return Response(content=str(twiml), media_type="application/xml")

    try:
        # 1. Ask Gemini to Parse Intent
        response = model.generate_content(f"{SYSTEM_PROMPT}\n\nUser Message: {Body}")
        clean_text = re.sub(r"```(json)?", "", response.text).strip()
        operations = json.loads(clean_text)

        gc = get_gspread_client()
        sh = gc.open(SPREADSHEET_NAME)
        
        reply_lines = []

        for op in operations:
            action = op.get("action")

            # --- ACTION: ORDER ---
            if action == "ORDER":
                ws_orders = sh.worksheet("Orders")
                now = datetime.now()
                items = op.get("items", [])
                details_str = ", ".join([f"{it['grams']}g {it['flavour']}" for it in items])
                
                order_row = [
                    now.year,
                    now.strftime("%b"),
                    now.day,
                    op.get("name", "Unknown"),
                    op.get("area", "Local"),
                    op.get("amount", 0),
                    op.get("source", "WhatsApp"),
                    op.get("payment_status", "Done"),
                    op.get("order_status", "Delivered"),
                    details_str
                ]
                ws_orders.append_row(order_row, value_input_option="USER_ENTERED")

                # Deduct inventory in Mukhwas tab
                if items:
                    ws_mukhwas = sh.worksheet("Mukhwas")
                    headers = [h.strip().upper() for h in ws_mukhwas.row_values(1)]
                    curr_stock = ws_mukhwas.row_values(2)
                    
                    for it in items:
                        flavour = it.get("flavour", "").upper()
                        grams = it.get("grams", 0)
                        if flavour in headers:
                            col_idx = headers.index(flavour)
                            current_val = float(curr_stock[col_idx]) if col_idx < len(curr_stock) and curr_stock[col_idx] else 0.0
                            new_val = max(0.0, current_val - grams)
                            ws_mukhwas.update_cell(2, col_idx + 1, new_val)
                            curr_stock[col_idx] = str(new_val)

                # Log payment if Done
                if op.get("payment_status") == "Done":
                    mode = op.get("payment_mode", "Bank")
                    ws_target = sh.worksheet("Bank" if mode == "Bank" else "Cash")
                    append_transaction_row(
                        ws_target, 
                        credit_or_debit="Credit", 
                        category="Order", 
                        amount=float(op.get("amount", 0)), 
                        comments=f"Order from {op.get('name')}"
                    )

                reply_lines.append(f"✅ Order Logged: {op.get('name')} (₹{op.get('amount')}) | Stock Deducted: {details_str}")

            # --- ACTION: STOCK ADD ---
            elif action == "STOCK_ADD":
                items = op.get("items", [])
                ws_mukhwas = sh.worksheet("Mukhwas")
                headers = [h.strip().upper() for h in ws_mukhwas.row_values(1)]
                curr_stock = ws_mukhwas.row_values(2)
                added_str = []

                for it in items:
                    flavour = it.get("flavour", "").upper()
                    grams = it.get("grams", 0)
                    if flavour in headers:
                        col_idx = headers.index(flavour)
                        current_val = float(curr_stock[col_idx]) if col_idx < len(curr_stock) and curr_stock[col_idx] else 0.0
                        new_val = current_val + grams
                        ws_mukhwas.update_cell(2, col_idx + 1, new_val)
                        curr_stock[col_idx] = str(new_val)
                        added_str.append(f"+{grams}g {flavour} (Live: {new_val}g)")

                reply_lines.append(f"🍃 Stock Updated: {', '.join(added_str)}")

            # --- ACTION: EXPENSE ---
            elif action == "EXPENSE":
                mode = op.get("mode", "Bank")
                ws_target = sh.worksheet("Bank" if mode == "Bank" else "Cash")
                amount = float(op.get("amount", 0))
                category = op.get("category", "Expense")
                comments = op.get("comments", "")
                append_transaction_row(ws_target, "Debit", category, amount, comments)
                reply_lines.append(f"🔴 Expense Recorded: ₹{amount} from {mode} ({category})")

            # --- ACTION: INCOME ---
            elif action == "INCOME":
                mode = op.get("mode", "Bank")
                ws_target = sh.worksheet("Bank" if mode == "Bank" else "Cash")
                amount = float(op.get("amount", 0))
                category = op.get("category", "Income")
                comments = op.get("comments", "")
                append_transaction_row(ws_target, "Credit", category, amount, comments)
                reply_lines.append(f"🟢 Income Logged: ₹{amount} to {mode} ({category})")

            # --- ACTION: QUERY BALANCE ---
            elif action == "QUERY_BALANCE":
                target = op.get("target", "Both")
                balances = []
                sheets_to_check = ["Bank", "Cash"] if target == "Both" else [target]
                
                for s_name in sheets_to_check:
                    try:
                        ws_acc = sh.worksheet(s_name)
                        col_h = ws_acc.col_values(8)  # Column H = Live Balance
                        last_val = col_h[-1] if len(col_h) > 2 else "0.00"
                        balances.append(f"💳 {s_name} Balance: ₹{last_val}")
                    except Exception:
                        balances.append(f"💳 {s_name} Balance: Not available")
                reply_lines.append("\n".join(balances))

            # --- ACTION: QUERY STOCK ---
            elif action == "QUERY_STOCK":
                ws_mukhwas = sh.worksheet("Mukhwas")
                headers = ws_mukhwas.row_values(1)
                vals = ws_mukhwas.row_values(2)
                stock_dict = {headers[i]: vals[i] if i < len(vals) else "0" for i in range(len(headers))}
                
                req_flavour = op.get("flavour", "ALL").upper()
                if req_flavour == "ALL":
                    lines = [f"• {k}: {v}g" for k, v in stock_dict.items()]
                    reply_lines.append("🍃 Current Mukhwas Stock:\n" + "\n".join(lines))
                else:
                    qty = stock_dict.get(req_flavour, "0")
                    reply_lines.append(f"🍃 {req_flavour} Stock: {qty}g")

        twiml.message("\n\n".join(reply_lines) if reply_lines else "Transaction parsed but no action required.")

    except Exception as e:
        logger.error(f"Error handling WhatsApp input: {str(e)}", exc_info=True)
        twiml.message(f"❌ Error: {str(e)}")

    return Response(content=str(twiml), media_type="application/xml")