import os
import json
import aiohttp
import asyncio
import firebase_admin
from firebase_admin import credentials, db, firestore

# -----------------------------
# Firebase Initialization
# -----------------------------
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

# -----------------------------
# Get Access Token from Firestore
# -----------------------------
def get_access_token():
    doc = firestore.client().collection("tokens").document("upstox").get()
    if doc.exists:
        return doc.to_dict().get("access_token")
    return None

# -----------------------------
# Fetch Batch Prices
# -----------------------------
async def fetch_prices():
    access_token = get_access_token()
    if not access_token:
        print("❌ Access token not found in Firestore.")
        return

    ref = db.reference("stocks/nifty50")
    symbols_dict = ref.get()  # {"RELIANCE": "NSE_EQ|INE002A01018", ...}

    if not symbols_dict:
        print("❌ No symbols found in Firebase Realtime DB.")
        return

    instrument_keys = list(symbols_dict.values())
    url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={','.join(instrument_keys)}"
    headers = {
        "accept": "application/json",
        "Api-Version": "2.0",
        "Authorization": f"Bearer {access_token}"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                print("✅ Status Code:", resp.status)
                if resp.status == 200:
                    data = await resp.json()
                    response_data = data.get("data", {})
                    for symbol, ikey in symbols_dict.items():
                        stock_data = response_data.get(ikey)
                        ltp = stock_data.get("last_price") if stock_data else None
                        print(f"{symbol}: {ltp}")
                else:
                    print("❌ Error Response:", await resp.text())
        except Exception as e:
            print("❌ Exception while fetching:", e)

# -----------------------------
# Run Async Test
# -----------------------------
if __name__ == "__main__":
    asyncio.run(fetch_prices())
