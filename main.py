import firebase_admin
from firebase_admin import credentials, db
import json
import websocket
import threading
import time
import requests

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

# ✅ Firebase से Stock List Fetch करने का Function
def get_stock_list():
    try:
        ref = db.reference("/stocks/nifty50")  # 🔥 "stocks/nifty50" से Data लाओ
        stock_data = ref.get()  # ✅ Data Fetch

        if not stock_data:
            print("⚠️ Firebase से कोई Data नहीं मिला!")
            return {}

        print("✅ Firebase Data Received:", stock_data)  # Debugging Log
        return stock_data  # Dictionary Format में Return करेगा
    except Exception as e:
        print(f"❌ Firebase Error: {str(e)}")
        return {}

# ✅ Upstox API से LTP (Last Traded Price) लाने का Function
def get_stock_ltp(instrument_keys):
    try:
        headers = {
            "x-api-key": UPSTOX_API_KEY, 
            "Content-Type": "application/json"
        }
        
        payload = {"instrument_keys": instrument_keys}  # 🔥 Upstox को सभी Stocks की Keys भेजो
        response = requests.post(UPSTOX_LTP_URL, headers=headers, json=payload)  # ✅ API Call

        if response.status_code == 200:
            data = response.json()
            return data.get("ltp", {})  # 🔥 LTP Data Return करो
        else:
            print(f"❌ Upstox API Error: {response.text}")
            return {}
    except Exception as e:
        print(f"❌ Upstox API Exception: {str(e)}")
        return {}

# ✅ WebSocket से Data Send करने का Function
def send_stock_data(ws):
    while True:
        stocks_data = get_stock_list()  # 🔥 Firebase से Stock Symbols और उनकी Instrument Keys लो
        if stocks_data:
            instrument_keys = list(stocks_data.values())  # 🔥 सभी Instrument Keys लो
            ltp_data = get_stock_ltp(instrument_keys)  # ✅ Upstox से LTP लो

            # 🔥 Final Payload बनाओ
            final_data = {
                "nifty50": {
                    stock: {"instrument_key": stocks_data[stock], "ltp": ltp_data.get(stocks_data[stock], "N/A")}
                    for stock in stocks_data
                }
            }

            payload = json.dumps(final_data)  # JSON Format में Convert
            print("📌 Sending Data to WebSocket:", payload)  # Debugging Log
            ws.send(payload)  # ✅ WebSocket को Send करो

        time.sleep(5)  # 🔄 हर 5 सेकंड में Data Refresh होगा

# ✅ WebSocket Connection Function
def on_open(ws):
    print("✅ Connected to WebSocket Server")
    threading.Thread(target=send_stock_data, args=(ws,)).start()

def on_message(ws, message):
    print(f"📩 Server Response: {message}")

def on_error(ws, error):
    print(f"❌ WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("🔴 WebSocket Closed")

# ✅ WebSocket Server URL (अपना सही URL डालो)
ws_url = "ws://your-websocket-server.com"

# ✅ WebSocket Client Setup
ws = websocket.WebSocketApp(ws_url, 
                            on_open=on_open, 
                            on_message=on_message, 
                            on_error=on_error, 
                            on_close=on_close)

# ✅ WebSocket को अलग Thread में Start करो
ws_thread = threading.Thread(target=ws.run_forever)
ws_thread.start()
