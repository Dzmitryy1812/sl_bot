import requests
import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

WALLET = os.environ["WALLET"]
PRIVATE_KEY = os.environ["PRIVATE_KEY"]
SELL_PRICE = float(os.environ.get("CLOSE_SELL_PRICE", "0.01"))
REQUEST_TIMEOUT_SECONDS = 15

client = ClobClient(
    "https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=137
)
client.set_api_creds(client.create_or_derive_api_creds())


def send_telegram_message(text):
    tg_token = os.environ.get("TG_TOKEN")
    tg_chat = os.environ.get("TG_CHAT_ID")

    if not tg_token or not tg_chat:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            json={"chat_id": tg_chat, "text": text},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        print(f"Failed to send Telegram notification: {exc}")


def close_all_positions():
    url = f"https://data-api.polymarket.com/positions?user={WALLET}"
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        positions = response.json()
    except requests.RequestException as exc:
        error = f"Failed to fetch positions: {exc}"
        print(error)
        send_telegram_message(f"⚠️ {error}")
        return

    closed_positions = 0
    failed_positions = 0

    for p in positions:
        size = float(p.get("size", p.get("tokensHeld", 0)) or 0)
        token = p.get("asset")

        if not token:
            failed_positions += 1
            print(f"Skipping position without asset id: {p}")
            continue

        if size <= 0:
            continue

        order = OrderArgs(
            token_id=token,
            price=SELL_PRICE,
            size=size,
            side="SELL"
        )

        try:
            signed = client.create_order(order)
            client.post_order(signed, OrderType.GTC)
            closed_positions += 1
        except Exception as exc:  # noqa: BLE001
            failed_positions += 1
            print(f"Failed to close token {token}: {exc}")

    summary = (
        f"Positions close complete. Success: {closed_positions}, Failed: {failed_positions}"
    )
    print(summary)
    send_telegram_message(f"🚨 {summary}")

if __name__ == "__main__":
    close_all_positions()
