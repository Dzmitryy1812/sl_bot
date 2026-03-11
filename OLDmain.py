import os, time, requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

load_dotenv()

USER = "0xa5b97fAeD6550E590A217EC66C379CCCE3Abb83B"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
THRESHOLD = float(os.getenv("PNL_THRESHOLD", "-10"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # секунд

DATA_API = "https://data-api.polymarket.com"

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=PRIVATE_KEY
)

def get_positions():
    r = requests.get(f"{DATA_API}/positions?user={USER}")
    r.raise_for_status()
    return r.json()

def weighted_pnl(positions):
    total_val, total_size = 0, 0
    for p in positions:
        size = float(p.get("size") or p.get("tokensHeld") or 1)
        pct = float(p.get("percentPnl") or 0)
        total_val += pct * size
        total_size += size
    return (total_val / total_size) if total_size else 0

def send_tg(msg):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT_ID, "text": msg}
    )

def close_position(p):
    try:
        token_id = p.get("asset") or p.get("tokenId")
        size = float(p.get("size") or p.get("tokensHeld") or 0)

        order = client.create_and_post_order({
            "tokenID": token_id,
            "side": "SELL",
            "price": 0.01,  # market sell — минимальная цена
            "size": size
        })
        print(f"✅ {p.get('title')} — closed: {order}")
        return True
    except Exception as e:
        print(f"❌ {p.get('title')} — error: {e}")
        return False

def check_and_close():
    positions = get_positions()
    if not positions:
        return

    above = [p for p in positions if "above" in (p.get("title") or "").lower()]
    if not above:
        return

    pnl = weighted_pnl(above)
    print(f"PnL: {pnl:.2f}%")

    if pnl >= THRESHOLD:
        return

    send_tg(f"📉 PnL {pnl:.2f}% — закрываю {len(above)} поз")

    closed = 0
    for p in above:
        if close_position(p):
            closed += 1
        time.sleep(1)

    send_tg(f"✅ Закрыто {closed}/{len(above)}")

# Бесконечный цикл проверки
print(f"Bot started. Check every {CHECK_INTERVAL}s")
while True:
    try:
        check_and_close()
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(CHECK_INTERVAL)
