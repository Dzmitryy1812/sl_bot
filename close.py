import os
import time
import logging
import requests
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs

# Настройка логирования в файл, который ждет ваш GitHub Workflow
LOG_FILE = 'debug-7510a5.log'
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# 1. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (Берутся из Secrets вашего GitHub)
WALLET = os.getenv("WALLET")        # Ваш прокси-адрес 0x11D9...
PRIVATE_KEY = os.getenv("PRIVATE_KEY") # Приватный ключ от 0xac5E...

# 2. ИНИЦИАЛИЗАЦИЯ КЛИЕНТА (Тот самый рабочий способ)
client = ClobClient(
    host="https://clob.polymarket.com", 
    key=PRIVATE_KEY, 
    funder=WALLET, 
    signature_type=2, # Обязательно для Proxy-кошельков Polymarket
    chain_id=137
)

def main():
    log.info(f"--- ЗАПУСК ЗАКРЫТИЯ ПОЗИЦИЙ ДЛЯ {WALLET} ---")
    
    try:
        # Авторизация по API
        client.set_api_creds(client.create_or_derive_api_creds())
        log.info("Авторизация: УСПЕШНО")
    except Exception as e:
        log.error(f"Ошибка авторизации: {e}")
        return

    # Отмена всех текущих открытых ордеров (чтобы не мешали продаже)
    try:
        client.cancel_all()
        log.info("Все старые ордера отменены")
        time.sleep(1)
    except Exception as e:
        log.warning(f"Ошибка при отмене ордеров: {e}")

    # Запрос текущих позиций через Data API
    try:
        url = f"https://data-api.polymarket.com/positions?user={WALLET}"
        response = requests.get(url, timeout=20)
        positions = response.json()
    except Exception as e:
        log.error(f"Не удалось получить список позиций: {e}")
        return

    # Фильтруем только то, что реально есть на балансе
    active_positions = [p for p in positions if float(p.get("size", 0)) > 0.001]
    
    if not active_positions:
        log.info("✅ Активных позиций нет, закрывать нечего.")
        return

    log.info(f"Найдено позиций для продажи: {len(active_positions)}")

    # Цикл продажи
    for p in active_positions:
        token_id = p.get("asset")
        size = float(p.get("size"))
        title = p.get("title", "Market")

        log.info(f"Пытаюсь продать: {title} ({size} шт.)")

        try:
            order_args = OrderArgs(
                token_id=token_id,
                size=size,
                price=0.01, # Выставляем минимальную цену, чтобы продать мгновенно
                side="SELL"
            )
            # Создаем и подписываем ордер
            signed_order = client.create_order(order_args)
            # Отправляем на биржу
            resp = client.post_order(signed_order)
            
            if resp.get("success"):
                log.info(f"✅ УСПЕШНО: {title} продан.")
            else:
                log.error(f"❌ Ошибка биржи при продаже {title}: {resp}")
                
        except Exception as e:
            log.error(f"❌ Критическая ошибка при продаже {title}: {e}")

    log.info("--- ПРОЦЕСС ЗАВЕРШЕН ---")

if __name__ == "__main__":
    main()
