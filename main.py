import requests
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import os
import json
import asyncio
import logging

# 🔹 Logging Setup (Debugging के लिए)
logging.basicConfig(level=logging.INFO)

# ✅ Environment Variables Load करना
DATABASE_URL = os.getenv("DATABASE_URL")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS")

if not DATABASE_URL:
    logging.error("❌ DATABASE_URL is Missing! Check Environment Variables.")

if not FIREBASE_CREDENTIALS_JSON:
    logging.error("❌ FIREBASE_CREDENTIALS is Missing! Check Environment Variables.")

# 🔹 Firebase Firestore Setup (Prevent Duplicate Initialization)
try:
    if not firebase_admin._apps:  # पहले से Initialized न हो, तभी Initialize करें
        firebase_credentials = json.loads(FIREBASE_CREDENTIALS_JSON)
        cred = credentials.Certificate(firebase_credentials)
        firebase_admin.initialize_app(cred)
        logging.info("✅ Firebase Firestore Initialized Successfully!")
    
    db_firestore = firestore.client()

except Exception as e:
    logging.error(f"❌ Firebase Initialization Error: {e}")

# 🔹 FastAPI Setup
app = FastAPI()

# 🔹 Active WebSocket Clients List
clients = set()

# ✅ Railway से API Key और Secret Key लोड करना
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_SECRET_KEY = os.getenv("UPSTOX_SECRET_KEY")

# ✅ Firestore से Access Token लेना
def get_access_token():
    try:
        doc_ref = db_firestore.collection("tokens").document("upstox")
        doc = doc_ref.get()

        if doc.exists:
            token_data = doc.to_dict()
            return token_data.get("access_token")

        logging.warning("⚠️ Access Token Not Found in Firestore!")
        return None
    except Exception as e:
        logging.error(f"❌ Firestore Access Token Fetch Error: {e}")
        return None

# ✅ Firestore से Stock Lists लाना
def get_stock_list():
    try:
        stock_ref = db_firestore.collection("stocks")
        docs = stock_ref.stream()

        stock_data = {"nifty50": {}, "niftysmallcap50": {}, "niftymidcap50": {}}

        for doc in docs:
            data = doc.to_dict()
            category = data.get("category", "nifty50")
            stock_name = data.get("stock_name")
            instrument_key = data.get("instrument_key")

            if category in stock_data:
                stock_data[category][stock_name] = instrument_key

        logging.info("✅ Firestore Stock Data Fetched Successfully!")
        return stock_data
    except Exception as e:
        logging.error(f"❌ Firestore Stock Data Fetch Error: {e}")
        return {"nifty50": {}, "niftysmallcap50": {}, "niftymidcap50": {}}

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

    try:
        response = requests.get(url, headers=headers)
        response_data = response.json()

        if response.status_code == 200:
            ltp = response_data.get("data", {}).get(instrument_key, {}).get("ltp")
            if ltp is None:
                logging.warning(f"⚠️ LTP Not Found in Response: {response_data}")
            return ltp

        logging.error(f"❌ API Error {response.status_code}: {response_data}")
    except json.JSONDecodeError:
        logging.error(f"❌ Invalid JSON Response from API: {response.text}")
    
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
