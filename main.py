import os
import json
import asyncio
import aiohttp
import firebase_admin
from firebase_admin import credentials, firestore, db
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import quote  # ✅ added for encoding

app = FastAPI()

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

clients = set()

# Firebase initialization
firebase_initialized = False

def initialize_firebase():
    global firebase_initialized
    if not firebase_initialized:
        cred_dict = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {
            'databaseURL': os.getenv("DATABASE_URL")
        })
        firebase_initialized = True

initialize_firebase()

# Firestore access token fetch
def get_access_token_from_firestore():
    doc_ref = firestore.client().collection("tokens").document("upstox")
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get("access_token")

    return None

# Batch fetch prices
async def fetch_all_prices(session, instrument_keys, access_token):
    joined_keys = ",".join(instrument_keys)
    encoded_keys = quote(joined_keys, safe=',')  # ✅ encode | to %7C
    url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={encoded_keys}"

    headers = {
        "accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {access_token}"
    }

    print("🟢 Access Token:", access_token)
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", {})
            else:
                print(f"❌ Error status code: {resp.status}")
                return {}
    except Exception as e:
        print("❌ Error fetching batch price:", e)
        return {}

# Broadcast to all clients
async def broadcast_data(data):
    if clients:
        await asyncio.wait([client.send_text(json.dumps(data)) for client in clients])

# Price update loop
async def price_updater():
    async with aiohttp.ClientSession() as session:
        while True:
            access_token = get_access_token_from_firestore()
            if not access_token:
                print("No access token found.")
                await asyncio.sleep(10)
                continue

            ref = db.reference("stocks/nifty50")
            symbols_dict = ref.get()  # { "RELIANCE": "NSE_EQ|INE002A01018", ... }

            if symbols_dict:
                instrument_keys = list(symbols_dict.values())
                response_data = await fetch_all_prices(session, instrument_keys, access_token)

                # Map response to symbol
                live_data = {}
                for symbol, ikey in symbols_dict.items():
                    stock_data = response_data.get(ikey, {})
                    ltp = stock_data.get("last_price")
                    live_data[symbol] = ltp
                    print("✅ KEY:", ikey, "| Symbol:", symbol, "| Last Price:", ltp)

                print("📈 Live Data:\n", json.dumps(live_data, indent=2))
                await broadcast_data(live_data)

            await asyncio.sleep(15)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(price_updater())

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        clients.remove(websocket)
