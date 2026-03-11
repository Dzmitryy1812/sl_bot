import requests
import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

WALLET = os.environ["WALLET"]
PRIVATE_KEY = os.environ["PRIVATE_KEY"]

client = ClobClient(
    "https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=137
)
client.set_api_creds(client.create_or_derive_api_creds())

def close_all_positions():
    url = f"https://data-api.polymarket.com/positions?user={WALLET}"
    positions = requests.get(url).json()

    for p in positions:
        size = float(p.get("size", p.get("tokensHeld", 0)))
        token = p["asset"]

        if size <= 0:
            continue

        order = OrderArgs(
            token_id=token,
            price=0.01,
            size=size,
            side="SELL"
        )

        signed = client.create_order(order)
        client.post_order(signed, OrderType.GTC)

    print("Positions closed")
    # уведомление в Telegram
    tg_token = os.environ.get("TG_TOKEN")
    tg_chat = os.environ.get("TG_CHAT_ID")
    if tg_token and tg_chat:
        requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            json={"chat_id": tg_chat, "text": "🚨 All positions closed"}
        )

if __name__ == "__main__":
    close_all_positions()
