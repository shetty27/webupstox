import firebase_admin
from firebase_admin import credentials, db
import json
import threading
import time
import uvicorn
import requests
import os
from fastapi import FastAPI, WebSocket

# ✅ Firebase Initialization Check
if not firebase_admin._apps:  # 🔥 Check अगर पहले से Initialize है तो दोबारा मत करो
    firebase_credentials = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
    cred = credentials.Certificate(firebase_credentials)  # अपने JSON Key का सही Path डालो
    firebase_admin.initialize_app(cred, {
        'databaseURL': os.getenv(DATABASE_URL) # अपना सही URL डालो
    })

# ✅ Railway से API Key और Secret Key लोड करना
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_SECRET_KEY = os.getenv("UPSTOX_SECRET_KEY")

# ✅ FastAPI App Init
app = FastAPI()

# ✅ Firebase से Stock List लाने का Function
def get_stock_list():
    ref = db.reference("/stocks/nifty50")  # 🔥 Firebase से Data लाओ
    stock_data = ref.get()
    
    if not stock_data:
        print("⚠️ Firebase से कोई डेटा नहीं मिला!")
        return {}
    
    print("✅ Firebase Data:", stock_data)
    return stock_data  # Dictionary Format में Return होगा

# ✅ Upstox API से LTP लाने का Function
def get_stock_ltp(instrument_keys):
    headers = {
        "x-api-key": UPSTOX_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {"instrument_keys": instrument_keys}
    response = requests.post(UPSTOX_LTP_URL, headers=headers, json=payload)

    if response.status_code == 200:
        data = response.json()
        return data.get("ltp", {})
    else:
        print(f"❌ Upstox API Error: {response.text}")
        return {}

# ✅ WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket Connected!")
    
    try:
        while True:
            stocks_data = get_stock_list()
            if stocks_data:
                instrument_keys = list(stocks_data.values())
                ltp_data = get_stock_ltp(instrument_keys)

                # 🔥 Data Prepare
                final_data = {
                    "nifty50": {
                        stock: {"instrument_key": stocks_data[stock], "ltp": ltp_data.get(stocks_data[stock], "N/A")}
                        for stock in stocks_data
                    }
                }

                payload = json.dumps(final_data)
                print("📌 Sending Data to WebSocket:", payload)
                await websocket.send_text(payload)

            await asyncio.sleep(5)  # 🔄 5 सेकंड में Data Refresh होगा

    except Exception as e:
        print(f"❌ WebSocket Error: {e}")
    finally:
        print("🔴 WebSocket Closed")

# ✅ FastAPI Run (Railway पर Auto Start होगा)
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
