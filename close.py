import os
import time
import logging
import requests
# load_dotenv() не нужен на Гитхабе, так как он берет переменные из Secrets напрямую
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs

# 1. НАСТРОЙКА ПРОКСИ (Чтобы Гитхаб не забанили)
# Если ты добавишь PROXY_URL в секреты Гитхаба, он применится здесь автоматически
PROXY = os.getenv("PROXY_URL")
if PROXY:
    os.environ['HTTPS_PROXY'] = PROXY
    os.environ['HTTP_PROXY'] = PROXY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# 2. ПЕРЕМЕННЫЕ (Берутся из GitHub Secrets)
WALLET = os.getenv("WALLET")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

if not WALLET or not PRIVATE_KEY:
    log.error("Критические переменные WALLET или PRIVATE_KEY не найдены!")
    exit(1)

# Инициализация клиента
client = ClobClient(
    host="https://clob.polymarket.com", 
    key=PRIVATE_KEY, 
    funder=WALLET, 
    signature_type=2, # ТВОЙ РАБОЧИЙ РЕЖИМ PROXY
    chain_id=137
)

try:
    # Авторизация
    client.set_api_creds(client.create_or_derive_api_creds())
    log.info("Авторизация на Polymarket прошла успешно")
except Exception as e:
    log.error(f"Ошибка авторизации: {e}")
    exit(1)

def main():
    log.info(f"Запуск закрытия позиций для {WALLET}")

    # Отмена всех активных ордеров
    try:
        client.cancel_all()
        time.sleep(1)
    except:
        pass

    # Получение списка позиций
    try:
        # Важно: используем прокси для этого запроса тоже через requests
        url = f"https://data-api.polymarket.com/positions?user={WALLET}"
        response = requests.get(url, timeout=10)
        positions = response.json()
    except Exception as e:
        log.error(f"Ошибка получения позиций: {e}")
        return

    active_positions = [p for p in positions if float(p.get("size", 0)) > 0.001]
    
    if not active_positions:
        log.info("✅ Активных позиций не обнаружено.")
        return

    # Процесс продажи
    for p in active_positions:
        token_id = p.get("asset")
        size = float(p.get("size"))
        title = p.get("title", "Market")

        log.info(f"Продаю: {title} ({size} шт.)")

        try:
            order_args = OrderArgs(
                token_id=token_id,
                size=size,
                price=0.01, # Продажа "по рынку"
                side="SELL"
            )
            signed_order = client.create_order(order_args)
            resp = client.post_order(signed_order)
            log.info(f"Результат продажи {title}: {resp}")
        except Exception as e:
            log.error(f"Ошибка при продаже {title}: {e}")

if __name__ == "__main__":
    main()
