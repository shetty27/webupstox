import json
import firebase_admin
from firebase_admin import credentials, firestore
from upstox_api.api import Upstox
import websocket
import asyncio
import websockets  # WebSocket Server के लिए

# 🔹 Firebase Setup (Firestore Authentication)
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()


# ✅ Firestore से Access Token लेना
def get_access_token():
    doc_ref = db.collection("tokens").document("upstox")
    token_data = doc_ref.get().to_dict()
    if token_data:
        return token_data.get("access_token")
    else:
        return None
        
# 🔹 Upstox API Credentials
API_KEY = "your-upstox-api-key"
ACCESS_TOKEN = get_access_token()  # Firestore से Access Token लाओ

if not ACCESS_TOKEN:
    print("❌ Access Token not found in Firestore!")
    exit()

# 🔹 Upstox Object Create करें
u = Upstox(API_KEY, ACCESS_TOKEN)
u.get_master_contract('NSE_EQ')  # NSE के लिए Master Contract लोड करें

# 🔹 Firebase Firestore से Stock List Load करें
def get_stock_list():
    stock_list_ref = db.collection("StockLists").document("stocks")
    stock_data = stock_list_ref.get()
    if stock_data.exists:
        return stock_data.to_dict()
    return {}

stock_data = get_stock_list()

all_symbols = []
if stock_data:
    all_symbols = stock_data.get("Nifty50", []) + stock_data.get("NiftySmallcap50", []) + stock_data.get("NiftyMidcap50", [])

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
