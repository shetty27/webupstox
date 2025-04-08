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
    encoded_keys = quote(joined_keys, safe=',')
    url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={encoded_keys}"

    headers = {
        "accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {access_token}"
    }

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

            index_refs = {
                "NIFTY50": "stocks/nifty50",
                "MIDCAP": "stocks/niftymidcap50",
                "SMALLCAP": "stocks/niftysmallcap50"
            }

            all_instrument_keys = []
            symbol_index_map = {}  # e.g. {"RELIANCE": ("NSE_EQ|xxx", "NIFTY50")}

            for index_name, path in index_refs.items():
                ref = db.reference(path)
                symbols_dict = ref.get()
                if symbols_dict:
                    for symbol, ikey in symbols_dict.items():
                        all_instrument_keys.append(ikey)
                        symbol_index_map[symbol] = (ikey, index_name)

            if all_instrument_keys:
                response_data = await fetch_all_prices(session, all_instrument_keys, access_token)
                live_data = {
                    "NIFTY50": {},
                    "MIDCAP": {},
                    "SMALLCAP": {}
                }

                for symbol, (ikey, index_name) in symbol_index_map.items():
                    response_key = f"NSE_EQ:{symbol}"
                    stock_data = response_data.get(response_key, {})
                    ltp = stock_data.get("last_price")
                    live_data[index_name][symbol] = ltp

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
