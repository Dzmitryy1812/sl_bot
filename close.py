import requests
import os
import sys
import json
import time
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

REQUEST_TIMEOUT_SECONDS = 15

DEBUG_LOG_PATH = os.path.join(os.path.dirname(__file__), "debug-7510a5.log")
DEBUG_SESSION_ID = "7510a5"

# ─── Proxy setup ───────────────────────────────────────────────
PROXY_URL = (
    os.environ.get("HTTP_PROXY")
    or os.environ.get("HTTPS_PROXY")
    or os.environ.get("http_proxy")
    or os.environ.get("https_proxy")
)
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else {}

if PROXIES:
    _original_session_init = requests.Session.__init__

    def _patched_session_init(self, *args, **kwargs):
        _original_session_init(self, *args, **kwargs)
        self.proxies.update(PROXIES)

    requests.Session.__init__ = _patched_session_init
# ────────────────────────────────────────────────────────────────

# region agent log
def _dbg(hypothesis_id: str, location: str, message: str, data: dict, run_id: str = "pre-fix") -> None:
    payload = {
        "sessionId": DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    try:
        with open(
            os.path.join(os.path.dirname(__file__), "debug-10ada1.log"),
            "a",
            encoding="utf-8",
        ) as f2:
            f2.write(line)
    except Exception:
        # отдельный debug режим, не должен ломать основную логику
        pass
# endregion agent log

WALLET = os.environ.get("WALLET")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
if not WALLET or not PRIVATE_KEY:
    _dbg(
        "H0",
        "close.py:env",
        "missing required env",
        {"hasWallet": bool(WALLET), "hasPrivateKey": bool(PRIVATE_KEY), "logPath": DEBUG_LOG_PATH},
    )
    raise RuntimeError("Missing required env: WALLET and/or PRIVATE_KEY")

SELL_PRICE = float(os.environ.get("CLOSE_SELL_PRICE", "0.01"))
USE_BEST_BID = os.environ.get("CLOSE_USE_BEST_BID", "1").strip() not in {"0", "false", "False"}
ORDER_TYPE_STR = os.environ.get("CLOSE_ORDER_TYPE", "FAK").strip().upper()

# ─── Диагностика прокси ────────────────────────────────────────
_dbg(
    "H0",
    "close.py:proxy_check",
    "proxy config",
    {"proxyUrl": PROXY_URL[:20] + "..." if PROXY_URL else "NONE", "hasProxy": bool(PROXIES)},
)

if PROXIES:
    try:
        ip_resp = requests.get("https://ifconfig.me", timeout=10)
        print(f"External IP (via proxy): {ip_resp.text.strip()}")
    except Exception as exc:  # noqa: BLE001
        print(f"Proxy connectivity test FAILED: {exc}")
        _dbg(
            "H0",
            "close.py:proxy_test",
            "proxy test failed",
            {"errorType": type(exc).__name__, "error": str(exc)},
        )
# ────────────────────────────────────────────────────────────────

client = ClobClient(
    "https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=137,
)
client.set_api_creds(client.create_or_derive_api_creds())

def _resolve_order_type(value: str) -> OrderType:
    mapping = {
        "GTC": OrderType.GTC,
        "FOK": OrderType.FOK,
        "FAK": OrderType.FAK,
    }
    if value not in mapping:
        raise ValueError(f"Unsupported CLOSE_ORDER_TYPE={value}. Use one of: {', '.join(mapping)}")
    return mapping[value]

def _best_bid_price(token_id: str) -> float | None:
    try:
        book = client.get_order_book(token_id)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch order book for {token_id}: {exc}")
        return None

    bids = getattr(book, "bids", None) or []
    if not bids:
        return None

    top = bids[0]
    price = getattr(top, "price", None)
    if price is None:
        try:
            price = top.get("price")
        except Exception:  # noqa: BLE001
            price = None
    return float(price) if price is not None else None

def close_all_positions():
    url = f"https://data-api.polymarket.com/positions?user={WALLET}"
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        positions = response.json()
    except requests.RequestException as exc:
        error = f"Failed to fetch positions: {exc}"
        print(error)
        _dbg(
            "H1",
            "close.py:close_all_positions:positions_fetch",
            "positions fetch failed",
            {"errorType": type(exc).__name__, "error": str(exc)},
        )
        raise

    closed_positions = 0
    failed_positions = 0
    order_type = _resolve_order_type(ORDER_TYPE_STR)
    order_type_label = getattr(order_type, "name", str(order_type))

    print(f"Fetched {len(positions)} positions for wallet {WALLET}")
    _dbg(
        "H2",
        "close.py:close_all_positions:config",
        "run config",
        {
            "positionsCount": len(positions),
            "useBestBid": USE_BEST_BID,
            "sellPriceFallback": SELL_PRICE,
            "orderType": order_type_label,
            "orderTypePyType": type(order_type).__name__,
        },
    )

    for p in positions:
        token = p.get("asset") or p.get("tokenId") or p.get("tokenID")
        try:
            size_raw = p.get("size", p.get("tokensHeld", 0))
            size = float(size_raw or 0)
        except Exception as exc:  # noqa: BLE001
            failed_positions += 1
            print(f"Skipping position with invalid size: {p} ({exc})")
            _dbg(
                "H3",
                "close.py:close_all_positions:parse_position",
                "invalid size field",
                {"token": token, "sizeRaw": str(size_raw), "errorType": type(exc).__name__, "error": str(exc)},
            )
            continue

        if not token:
            failed_positions += 1
            print(f"Skipping position without asset id: {p}")
            _dbg(
                "H3",
                "close.py:close_all_positions:parse_position",
                "missing token id",
                {"size": size, "keys": sorted(list(p.keys()))[:30]},
            )
            continue

        if size <= 0:
            continue

        price = SELL_PRICE
        if USE_BEST_BID:
            best_bid = _best_bid_price(token)
            if best_bid is None:
                failed_positions += 1
                print(f"No bids in order book for token {token}; can't sell now.")
                _dbg(
                    "H4",
                    "close.py:close_all_positions:orderbook",
                    "no bids / orderbook unavailable",
                    {"token": token, "size": size},
                )
                continue
            price = best_bid

        order = OrderArgs(
            token_id=token,
            price=price,
            size=size,
            side="SELL"
        )

        try:
            signed = client.create_order(order)
            res = client.post_order(signed, order_type)
            print(f"Posted SELL {size} @ {price} ({order_type_label}) for token {token}. Response: {res}")
            closed_positions += 1
            _dbg(
                "H5",
                "close.py:close_all_positions:post_order",
                "order posted",
                {"token": token, "size": size, "price": price, "orderType": order_type_label, "responseType": type(res).__name__},
            )
        except Exception as exc:  # noqa: BLE001
            failed_positions += 1
            print(f"Failed to close token {token}: {exc}")
            _dbg(
                "H5",
                "close.py:close_all_positions:post_order",
                "order post failed",
                {"token": token, "size": size, "price": price, "orderType": order_type_label, "errorType": type(exc).__name__, "error": str(exc)},
            )

    summary = (
        f"Positions close complete. Success: {closed_positions}, Failed: {failed_positions}"
    )
    print(summary)
    _dbg(
        "H6",
        "close.py:close_all_positions:summary",
        "run summary",
        {"success": closed_positions, "failed": failed_positions},
    )

    if failed_positions > 0:
        raise RuntimeError(summary)
    if len(positions) > 0 and closed_positions == 0:
        raise RuntimeError("No positions were closed (0 orders posted).")

if __name__ == "__main__":
    try:
        close_all_positions()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        sys.exit(1)
