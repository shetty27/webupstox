import requests
import firebase_admin
from firebase_admin import credentials, db
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import os
import json
import asyncio
import logging

# 🔹 Logging Setup (Debugging के लिए)
logging.basicConfig(level=logging.INFO)

# 🔹 Firebase Realtime Database Setup
if not firebase_admin._apps:
    firebase_credentials = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
    cred = credentials.Certificate(firebase_credentials)
    firebase_admin.initialize_app(cred, {"databaseURL": "https://your-project-id.firebaseio.com"})

# 🔹 FastAPI Setup
app = FastAPI()

# 🔹 Active WebSocket Clients List
clients = set()

# ✅ Railway से API Key और Secret Key लोड करना
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_SECRET_KEY = os.getenv("UPSTOX_SECRET_KEY")

# ✅ Firebase से Access Token लेना
def get_access_token():
    token_ref = db.reference("tokens/upstox")
    token_data = token_ref.get()
    return token_data.get("access_token") if token_data else None

# ✅ Firebase से Stock Lists लाना
def get_stock_list():
    stock_ref = db.reference("stocks")
    stock_data = stock_ref.get()
    return {
        "nifty50": stock_data.get("nifty50", {}) if stock_data else {},
        "niftysmallcap50": stock_data.get("niftysmallcap50", {}) if stock_data else {},
        "niftymidcap50": stock_data.get("niftymidcap50", {}) if stock_data else {}
    }

# ✅ Upstox API से Live Stock Price लाने का फंक्शन
def get_stock_price(instrument_key):
    access_token = get_access_token()
    if not access_token:
        logging.error("❌ Access Token Not Found!")
        return None

    url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={instrument_key}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Api-Key": UPSTOX_API_KEY,
        "X-Api-Secret": UPSTOX_SECRET_KEY,
        "Accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("data", {}).get(instrument_key, {}).get("ltp")
    
    logging.error(f"❌ Failed to fetch price for {instrument_key}: {response.text}")
    return None

# ✅ WebSocket Handler (Live Updates)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    logging.info("🔗 New WebSocket Connection Established!")

    try:
        while True:
            stock_lists = get_stock_list()
            stock_prices = {}

            for category, stocks in stock_lists.items():
                stock_prices[category] = {
                    stock_name: {
                        "instrument_key": instrument_key,
                        "ltp": get_stock_price(instrument_key)
                    } 
                    for stock_name, instrument_key in stocks.items()
                }

            # 🔹 Live Data सभी Clients को भेजें
            disconnected_clients = set()
            for client in clients:
                try:
                    await client.send_json(stock_prices)
                except WebSocketDisconnect:
                    logging.warning("🔌 Client Disconnected!")
                    disconnected_clients.add(client)

            # 🔹 Remove Disconnected Clients
            for client in disconnected_clients:
                clients.remove(client)

            await asyncio.sleep(3)  # हर 3 सेकंड में अपडेट करें

    except Exception as e:
        logging.error(f"❌ WebSocket Error: {e}")
    finally:
        clients.remove(websocket)
        logging.info("🔌 Connection Closed!")

# ✅ Server Status Check
@app.get("/")
def home():
    return {"message": "WebSocket Server is Running!"}

@app.get("/ping")
@app.head("/ping")
def ping():
    return {"status": "OK"}

# ✅ Run FastAPI Server (Only for Local Testing)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
