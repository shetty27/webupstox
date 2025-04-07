import json
import asyncio
import websockets
import firebase_admin
from firebase_admin import credentials, db
from fastapi import FastAPI, WebSocket
import aiohttp
import os

# Firebase initialization
cred = credentials.Certificate(json.loads(os.getenv("FIREBASE_CREDENTIALS")))
firebase_admin.initialize_app(cred, {
    'databaseURL': os.getenv("FIREBASE_DB_URL")
})

# Upstox Credentials
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

app = FastAPI()
clients = set()

# Function to fetch stock prices using Upstox API
async def fetch_stock_price(session, instrument_key):
    url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={instrument_key}"
    headers = {
        "accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}"
    }
    async with session.get(url, headers=headers) as resp:
        data = await resp.json()
        return data.get("data", {})

# Broadcast data to all clients
async def broadcast_data(data):
    if clients:
        await asyncio.wait([client.send_text(json.dumps(data)) for client in clients])

# Main loop to fetch and send data
async def price_updater():
    async with aiohttp.ClientSession() as session:
        while True:
            ref = db.reference("stocks/nifty50")
            symbols_dict = ref.get()  # { "RELIANCE": "NSE_EQ|INE002A01018", ... }

            live_data = {}
            if symbols_dict:
                tasks = [fetch_stock_price(session, ikey) for ikey in symbols_dict.values()]
                responses = await asyncio.gather(*tasks)

                for symbol, price_data in zip(symbols_dict.keys(), responses):
                    live_data[symbol] = price_data

                await broadcast_data(live_data)
            await asyncio.sleep(5)  # update every 5 seconds

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(price_updater())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # Just to keep it alive
    except:
        clients.remove(websocket)
