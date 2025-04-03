import json
import firebase_admin
from firebase_admin import credentials, db
from upstox_api.api import Upstox
import websocket
import asyncio
import websockets  # WebSocket Server के लिए

# 🔹 Firebase Auth Setup
cred = credentials.Certificate("serviceAccountKey.json")  # अपनी Firebase Key का Path दें
firebase_admin.initialize_app(cred, {"databaseURL": "https://your-firebase-url.firebaseio.com/"})

# 🔹 Upstox API Credentials
API_KEY = "your-upstox-api-key"
ACCESS_TOKEN = "your-upstox-access-token"

# 🔹 Upstox Object Create करें
u = Upstox(API_KEY, ACCESS_TOKEN)
u.get_master_contract('NSE_EQ')  # NSE के लिए Master Contract लोड करें

# 🔹 Firebase से Stock List Load करें
ref = db.reference("/stocks")  # Firebase में जो 3 Lists हैं, उन्हें Read करें
stock_data = ref.get()

all_symbols = []
if stock_data:
    all_symbols = stock_data["nifty50"] + stock_data["niftysmallcap50"] + stock_data["niftymidcap50"]

# 🔹 WebSocket से Real-time Data Send करने के लिए Clients की Dynamic List
clients = set()

async def send_data_to_clients(data):
    """ WebSocket Clients को Live Data Send करने का Function """
    if clients:  # अगर कोई Client Connected है, तभी Data Send करें
        message = json.dumps(data)
        await asyncio.wait([ws.send(message) for ws in clients])

def on_quote_update(ws, data):
    """ जब भी Upstox से नया Price Update आए, Clients को Send करो """
    asyncio.run(send_data_to_clients(data))

def on_connect(ws):
    """ जब WebSocket Connect हो, तब Stocks Subscribe करो """
    print("✅ WebSocket Connected! Subscribing to Stocks...")
    u.set_on_quote_update(on_quote_update)
    u.subscribe(all_symbols, u.get_quote)
    print(f"✅ Subscribed to {len(all_symbols)} Stocks.")

async def websocket_handler(websocket, path):
    """ जब Android App Connect होगी, तो उसे Clients List में जोड़ो """
    clients.add(websocket)
    print(f"🔗 New Client Connected! Total Clients: {len(clients)}")
    
    try:
        async for message in websocket:
            pass  # अभी Client से कोई Request नहीं आ रही, बस Data भेज रहे हैं
    finally:
        clients.remove(websocket)
        print(f"❌ Client Disconnected! Remaining Clients: {len(clients)}")

# 🔹 WebSocket Server Run करो (Android App के लिए)
start_server = websockets.serve(websocket_handler, "0.0.0.0", 8765)

async def main():
    await start_server
    u.set_on_connect(on_connect)
    u.start_websocket(True)

asyncio.run(main())
