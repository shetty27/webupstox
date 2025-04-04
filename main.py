import requests
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI, WebSocket
import os
import json
import asyncio

# 🔹 Firebase Setup
if not firebase_admin._apps:
    firebase_credentials = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
    cred = credentials.Certificate(firebase_credentials)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 🔹 FastAPI Setup
app = FastAPI()

# 🔹 WebSocket Clients List
clients = []

# ✅ Firestore से Access Token लेना
def get_access_token():
    doc_ref = db.collection("tokens").document("upstox")
    token_data = doc_ref.get().to_dict()
    return token_data.get("access_token") if token_data else None

# ✅ Firestore से Nifty50, Smallcap50, और Midcap50 की लिस्ट लाना
def get_stock_list():
    stock_ref = db.collection("stocks").document("nifty_lists")
    stock_data = stock_ref.get().to_dict()
    if stock_data:
        return {
            "nifty50": stock_data.get("nifty50", []),
            "niftysmallcap50": stock_data.get("niftysmallcap50", []),
            "niftymidcap50": stock_data.get("niftymidcap50", [])
        }
    return {"nifty50": [], "niftysmallcap50": [], "niftymidcap50": []}

# ✅ Upstox API से Live Stock Price लाने का फंक्शन
def get_stock_price(instrument_key):
    access_token = get_access_token()
    if not access_token:
        return None

    url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={instrument_key}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("data", {}).get(instrument_key, {}).get("ltp")
    return None

# ✅ WebSocket Handler (Live Updates)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)

    try:
        while True:
            stock_lists = get_stock_list()
            stock_prices = {}

            for category, stock_list in stock_lists.items():
                stock_prices[category] = {stock: get_stock_price(stock) for stock in stock_list}

            # 🔹 Live Data सभी Clients को भेजें
            for client in clients:
                await client.send_json(stock_prices)

            await asyncio.sleep(3)  # हर 3 सेकंड में अपडेट करें
    except Exception as e:
        print(f"WebSocket Error: {e}")
    finally:
        clients.remove(websocket)

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
