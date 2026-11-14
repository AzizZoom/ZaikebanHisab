"""FastAPI OAuth and WhatsApp ERP assistant."""
import json, os, re
from datetime import datetime
from pathlib import Path
from io import BytesIO
import gspread, requests
import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from PIL import Image
from starlette.middleware.sessions import SessionMiddleware
from twilio.twiml.messaging_response import MessagingResponse
import database

load_dotenv(); os.environ["OAUTHLIB_INSECURE_TRANSPORT"]="1"
SCOPES=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/userinfo.email","openid"]
app=FastAPI(title="Zaikeban Foods Hisab")
app.add_middleware(SessionMiddleware,secret_key=os.getenv("SESSION_SECRET","change-me"))
templates=Jinja2Templates(directory=str(Path(__file__).parent/"templates")); FLAVOURS=["CC","SD","KD","RS","MP"]
CARD_STYLE="""<style>*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:linear-gradient(135deg,#fff8ed,#f1f7eb);font:16px system-ui,-apple-system,'Segoe UI',sans-serif;color:#233026}.card{width:min(100%,520px);padding:48px;border-radius:24px;background:#fff;box-shadow:0 18px 60px #263b2518;text-align:center}.leaf{font-size:2.5rem}h1{font-size:2.2rem;margin:.2em 0;color:#244b35}p{color:#667268;line-height:1.6}label{display:block;text-align:left;margin:18px 0 6px;color:#33443a;font-weight:600}input{width:100%;padding:14px;border:1px solid #dce5dc;border-radius:10px;font:inherit}.btn{display:inline-block;width:100%;margin-top:18px;padding:14px 24px;border:0;border-radius:12px;background:#2e7049;color:white;text-decoration:none;font:700 16px system-ui;cursor:pointer}.btn:hover{background:#245d3b}</style>"""
SYSTEM_PROMPT='''Parse English, Hindi and Hinglish business messages/images. Return ONLY JSON array. Actions: ORDER {name,area,amount,source,payment_status,payment_mode,order_status,items:[{flavour,grams}]}; STOCK_ADD {items:[{flavour,grams}],comments}; EXPENSE/INCOME {mode,category,amount,comments}; QUERY_LIVE {target,flavour}; REPORT_OVERVIEW {days}; FETCH_PENDING {filter}; UPDATE_ORDER_STATUS {name,payment_status,payment_mode,order_status}. Valid flavours CC SD KD RS MP. Convert kg to grams. Never invent missing data; return [] if unclear.''' 
MODEL=None
if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
 genai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
 for m in ["models/gemini-2.5-flash","models/gemini-2.0-flash","models/gemini-1.5-flash"]:
  try: MODEL=genai.GenerativeModel(m); MODEL.generate_content("OK"); break
  except Exception: MODEL=None

def build_oauth_flow(redirect_uri,state=None):
 cid,secret=os.getenv("GOOGLE_CLIENT_ID"),os.getenv("GOOGLE_CLIENT_SECRET")
 if cid and secret:return Flow.from_client_config({"web":{"client_id":cid,"client_secret":secret,"auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token"}},scopes=SCOPES,state=state,redirect_uri=redirect_uri)
 return Flow.from_client_secrets_file("client_secret.json",scopes=SCOPES,state=state,redirect_uri=redirect_uri)
def get_user_client(user):
 creds=Credentials.from_authorized_user_info(json.loads(user["creds_json"]),SCOPES)
 if creds.expired and creds.refresh_token:creds.refresh(GoogleRequest());database.save_user(user["email"],creds.to_json(),user.get("sheet_id"))
 return gspread.authorize(creds)
def book_for(user):
 gc=get_user_client(user)
 try:return gc.open(user.get("sheet_id") or os.getenv("SPREADSHEET_NAME","Zaikeban Foods Hisab"))
 except gspread.SpreadsheetNotFound:return database.initialize_user_sheet(gc,user["email"])
@app.get("/",response_class=HTMLResponse)
async def home(request:Request):return templates.TemplateResponse("index.html",{"request":request})
@app.get("/login")
async def login(request:Request):
 uri=f"{request.headers.get('x-forwarded-proto','http')}://{request.headers.get('host')}/callback"; flow=build_oauth_flow(uri); url,state=flow.authorization_url(access_type="offline",prompt="consent"); request.session.update(state=state,code_verifier=flow.code_verifier,redirect_uri=uri); return RedirectResponse(url)
@app.get("/callback")
async def callback(request:Request):
 flow=build_oauth_flow(request.session.get("redirect_uri"),request.session.get("state")); flow.code_verifier=request.session.get("code_verifier"); flow.fetch_token(authorization_response=str(request.url)); r=requests.get("https://www.googleapis.com/userinfo/v2/me",headers={"Authorization":f"Bearer {flow.credentials.token}"},timeout=15);r.raise_for_status();email=r.json().get("email")
 if not email:raise HTTPException(400,"Google account email missing")
 database.save_user(email,flow.credentials.to_json());database.initialize_user_sheet(gspread.authorize(flow.credentials),email);request.session["email"]=email;return RedirectResponse("/onboard",303)
@app.get("/onboard",response_class=HTMLResponse)
async def onboard(request:Request):
 if not request.session.get("email"):return RedirectResponse("/login")
 return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect WhatsApp · Zaikeban Foods Hisab</title>{CARD_STYLE}</head><body><main class="card"><div class="leaf">🌿</div><h1>Connect WhatsApp</h1><p>Link the phone number you use to message your Zaikeban Foods assistant.</p><form method="post" action="/save_phone"><label for="phone">WhatsApp phone number</label><input id="phone" name="phone" type="tel" placeholder="10 digit mobile number" required><button class="btn" type="submit">Save Phone Number</button></form></main></body></html>''')
@app.post("/save_phone",response_class=HTMLResponse)
async def save_phone(request:Request,phone:str=Form(...)):
 email=request.session.get("email")
 if not email:raise HTTPException(401,"Sign in first")
 digits=re.sub(r"\D","",phone);clean="+91"+digits if len(digits)==10 else "+"+digits
 if len(digits)<10:raise HTTPException(400,"Invalid phone number")
 database.link_phone(email,clean);url=os.getenv("STREAMLIT_URL","http://localhost:8501");return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WhatsApp Linked · Zaikeban Foods Hisab</title>{CARD_STYLE}</head><body><main class="card"><div class="leaf">🌿</div><h1>WhatsApp linked</h1><p>{clean} is connected to your Zaikeban Foods account.</p><a class="btn" href="{url}">Open Dashboard</a></main></body></html>''')

def ws(book,tab):return book.worksheet(tab)
def stock_get(book):
 r=ws(book,"Mukhwas").row_values(2);return {f:int(float(r[i] or 0)) if i<len(r) else 0 for i,f in enumerate(FLAVOURS)}
def stock_set(book,s):ws(book,"Mukhwas").update("A2:E2",[[str(s[f]) for f in FLAVOURS]])
def ledger(book,mode,kind,category,amount,comment=""):
 if mode not in ("Bank","Cash"):mode="Bank" if str(mode).lower() in ("upi","gpay") else "Cash"
 sh=ws(book,mode);n=len(sh.get_all_values())+1;now=datetime.now();amt=abs(float(amount));final=amt if kind=="Credit" else -amt;formula=f"=G{n}" if n<=3 else f"=H{n-1}+G{n}"
 sh.append_row([now.year,now.strftime("%b"),now.day,kind,category,amt,final,formula,comment],value_input_option="USER_ENTERED")
def live(book,tab):
 for x in reversed(ws(book,tab).col_values(8)[2:]):
  try:return float(x.replace(",",""))
  except Exception:pass
 return 0
def rows(book,tab):
 v=ws(book,tab).get_all_values();return [dict(zip(v[1],r)) for r in v[2:] if r] if tab in ("Bank","Cash") else [dict(zip(v[0],r)) for r in v[1:] if r]
def money(r,k="Amount"):
 try:return float(str(r.get(k,0)).replace(",",""))
 except:return 0
def act(book,a):
 k=a.get("action","").upper()
 if k=="ORDER":
  s=stock_get(book);items=a.get("items",[]);details=[]
  for it in items:
   f=it.get("flavour","").upper();g=int(it.get("grams",0))
   if f not in FLAVOURS or g<=0:raise ValueError("Invalid item")
   s[f]-=g;details.append(f"{g}g {f}")
  stock_set(book,s);n=datetime.now();ws(book,"Orders").append_row([n.year,n.strftime("%b"),n.day,a.get("name",""),a.get("area",""),float(a.get("amount",0)),a.get("source","WhatsApp"),a.get("payment_status","Pending"),a.get("order_status","Pending"),", ".join(details)],value_input_option="USER_ENTERED")
  amt=float(a.get("amount",0))
  if a.get("payment_status")=="Done" and amt>0:ledger(book,a.get("payment_mode","Cash"),"Credit","Order",amt,"Order from "+a.get("name",""))
  return "Order saved. Live stock: "+", ".join(f"{f} {max(0,s[f])}g" for f in FLAVOURS)
 if k=="STOCK_ADD":
  s=stock_get(book)
  for it in a.get("items",[]):
   f=it.get("flavour","").upper();g=int(it.get("grams",0))
   if f not in FLAVOURS or g<=0:raise ValueError("Invalid stock item")
   s[f]+=g
  stock_set(book,s);return "Stock: "+", ".join(f"{f} {v}g" for f,v in s.items())
 if k in ("EXPENSE","INCOME"):ledger(book,a.get("mode","Cash"),"Debit" if k=="EXPENSE" else "Credit",a.get("category",k),a["amount"],a.get("comments",""));return f"{k.title()} ₹{float(a['amount']):,.2f} saved."
 if k=="QUERY_LIVE":
  t=a.get("target","All");out=[]
  if t in ("Bank","Both","All"):out.append(f"Bank ₹{live(book,'Bank'):,.2f}")
  if t in ("Cash","Both","All"):out.append(f"Cash ₹{live(book,'Cash'):,.2f}")
  if t in ("Stock","All"):
   s=stock_get(book);f=a.get("flavour","ALL").upper();out.append("Stock "+", ".join(f"{x}: {v}g" for x,v in s.items() if f in ("ALL",x)))
  return " | ".join(out)
 if k=="FETCH_PENDING":
  f=a.get("filter","Both");found=[]
  for r in rows(book,"Orders"):
   p=r.get("Payment status","").lower()=="pending";d=r.get("Order status","").lower()=="pending"
   if (f in ("Payments","Both") and p) or (f in ("Orders","Both") and d):found.append(f"{len(found)+1}. {r.get('Name')} ({r.get('Area')}) ₹{money(r):,.0f} {r.get('Year')}-{r.get('Month')}-{r.get('Date')} {r.get('Order details')} — payment {'Pending' if p else 'Done'}, order {'Pending' if d else 'Delivered'}")
  return "\n".join(found) if found else "No pending items."
 if k=="REPORT_OVERVIEW":
  cutoff=datetime.now().date().toordinal()-int(a.get("days",30));o=[];tx={x:[] for x in ["Bank","Cash"]}
  def recent(r):
   try:return datetime(int(float(r['Year'])),datetime.strptime(r['Month'],'%b').month,int(float(r['Date']))).date().toordinal()>=cutoff
   except:return False
  orders=[r for r in rows(book,"Orders") if recent(r)]
  for t in tx:tx[t]=[r for r in rows(book,t) if recent(r)]
  sold={f:0 for f in FLAVOURS}
  for r in orders:
   for g,f in re.findall(r"(\d+)\s*g\s+(CC|SD|KD|RS|MP)",r.get("Order details",""),re.I):sold[f.upper()]+=int(g)
  o.append(f"{len(orders)} orders, value ₹{sum(money(r) for r in orders):,.2f}")
  for t,rs in tx.items():o.append(f"{t}: income ₹{sum(money(r) for r in rs if r.get('Credit/Debit')=='Credit'):,.2f}; expense ₹{sum(money(r) for r in rs if r.get('Credit/Debit')=='Debit'):,.2f}")
  o.append("Sold: "+", ".join(f"{f} {n}g" for f,n in sold.items())+f" (total {sum(sold.values())}g). Stock: "+", ".join(f"{f} {v}g" for f,v in stock_get(book).items()));return "\n".join(o)
 if k=="UPDATE_ORDER_STATUS":
  sh=ws(book,"Orders");v=sh.get_all_values();count=0
  for i,r in enumerate(v[1:],2):
   if len(r)<10 or r[3].strip().lower()!=str(a.get("name","")).strip().lower():continue
   paid=a.get("payment_status")=="Done" and r[7].lower()=="pending";delivered=a.get("order_status")=="Delivered" and r[8].lower()=="pending"
   if paid:sh.update_cell(i,8,"Done");ledger(book,a.get("payment_mode","Cash"),"Credit","Order",money({"Amount":r[5]}),"Order from "+r[3])
   if delivered:sh.update_cell(i,9,"Delivered")
   count+=bool(paid or delivered)
  return f"Updated {count} order(s)." if count else "No matching pending order."
 return "Unsupported action."

@app.post("/whatsapp")
async def whatsapp(request:Request):
 form=await request.form();sender=str(form.get("From",""));resp=MessagingResponse();user=database.get_user_by_phone(sender)
 if not user:resp.message("Number not linked. Please connect it in the web app.");return Response(str(resp),media_type="application/xml")
 if MODEL is None:resp.message("AI is not configured.");return Response(str(resp),media_type="application/xml")
 try:
  parts=[SYSTEM_PROMPT+"\n"+str(form.get("Body",""))]
  if int(form.get("NumMedia",0))>0:
   r=requests.get(form["MediaUrl0"],auth=(os.getenv("TWILIO_SID",""),os.getenv("TWILIO_AUTH","")),timeout=20);r.raise_for_status();parts.append(Image.open(BytesIO(r.content)).convert("RGB"))
  raw=MODEL.generate_content(parts).text.strip();raw=re.sub(r"^```(?:json)?|```$","",raw,flags=re.I|re.M).strip();actions=json.loads(raw)
  if not isinstance(actions,list):raise ValueError("Expected action array")
  b=book_for(user);out=[]
  for a in actions:
   try:out.append(act(b,a))
   except Exception as e:out.append(f"Could not process action: {e}")
  resp.message("\n\n".join(out) if out else "Please clarify the request.")
 except Exception:resp.message("Sorry, couldn't process that. Please try again with clear details.")
 return Response(str(resp),media_type="application/xml")
