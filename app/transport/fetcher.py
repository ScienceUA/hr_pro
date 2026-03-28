import time
import random
import logging
import requests
from app.config.headers import get_headers

logger = logging.getLogger(__name__)

class SmartFetcher:
    """
    Транспортный слой на базе requests (синхронный).
    """
    def __init__(self):
        self.session = requests.Session()

    def get(self, url: str) -> str:
        # Ротация заголовков из конфига
        self.session.headers.update(get_headers())
        
        # Jitter
        time.sleep(random.uniform(0.5, 1.5))

        try:
            logger.debug(f"Fetching {url}...")
            response = self.session.get(url, timeout=15)
            # raise_for_status вызываем, но помним, что 403/404 Work.ua отдает как 200 в некоторых случаях,
            # поэтому BaseParser всё равно нужен.
            # Но если будет реальная 500 ошибка сервера, мы хотим об этом знать.
            if response.status_code not in [404, 403]: 
                 response.raise_for_status()
            
            # Явная защита: возвращаем строку, даже если тело пустое
            return response.text or ""
            
        except requests.RequestException as e:
            logger.error(f"HTTP Request failed: {e}")
            # Для MVP краулера возвращаем пустую строку, чтобы парсер выдал ERROR/UNKNOWN,
            # а не валил весь процесс.
            return ""
    def post_json(self, url: str, json: dict) -> dict: # Змінено json_data на json
        """
        Відправляє POST-запит із JSON-тілом.
        Необхідно для отримання списку резюме через API Rabota.ua.
        """
        self.session.headers.update(get_headers())
        time.sleep(random.uniform(0.5, 1.5))
        
        try:
            logger.debug(f"Posting JSON to {url}...")
            # Тепер назва параметра у визначенні (json) збігається з назвою у виклику
            response = self.session.post(url, json=json, timeout=30) 
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"POST JSON request failed: {e}")
            # Викидаємо помилку, оскільки без результатів пошуку ми не можемо продовжувати
            raise RuntimeError(f"Не вдалося отримати дані з API: {e}")