import os
import json
import asyncio
import aiohttp
import firebase_admin
from firebase_admin import credentials, firestore, db
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow all CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variable to store clients
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

# Get access token from Firestore
def get_access_token_from_firestore():
    doc_ref = firestore.client().collection("tokens").document("upstox")
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get("access_token")
    return None

# Fetch stock price from Upstox API
async def fetch_stock_price(session, instrument_key, access_token):
    url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={instrument_key}"
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
                return {}
    except Exception as e:
        print("Error fetching price:", e)
        return {}

# Broadcast data to all connected clients
async def broadcast_data(data):
    if clients:
        await asyncio.wait([client.send_text(json.dumps(data)) for client in clients])

# Price update loop
async def price_updater():
    async with aiohttp.ClientSession() as session:
        while True:
            access_token = get_access_token_from_firestore()
            if not access_token:
                print("No access token found in Firestore.")
                await asyncio.sleep(10)
                continue

            ref = db.reference("stocks/nifty50")
            symbols_dict = ref.get()  # { "RELIANCE": "NSE_EQ|INE002A01018", ... }

            live_data = {}
            if symbols_dict:
                tasks = [
                    fetch_stock_price(session, ikey, access_token)
                    for ikey in symbols_dict.values()
                ]
                responses = await asyncio.gather(*tasks)

                for symbol, price_data in zip(symbols_dict.keys(), responses):
                    live_data[symbol] = price_data

                await broadcast_data(live_data)

            await asyncio.sleep(5)  # Repeat every 5 seconds

# Start price update task on app startup
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
            await websocket.receive_text()  # Keep connection alive
    except:
        clients.remove(websocket)
