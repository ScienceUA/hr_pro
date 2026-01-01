import time
from typing import Optional

import requests


def fetch_html(
    url: str,
    user_agent: str,
    delay_seconds: float = 1.0,
    timeout_seconds: float = 15.0,
) -> Optional[str]:
    """
    Делает один HTTP GET-запрос к URL с заданным User-Agent.
    Возвращает текст HTML или None в случае ошибки.
    Делает паузу delay_seconds после запроса.
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6,en;q=0.5",
        "Connection": "close",
    }

    print(f"\n[fetch_html] GET {url}")
    try:
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
    except Exception as e:
        print(f"[fetch_html] Ошибка при запросе: {e}")
        time.sleep(delay_seconds)
        return None

    print(f"[fetch_html] Статус-код: {response.status_code}")
    print(f"[fetch_html] Итоговый URL: {response.url}")

    if response.status_code != 200:
        # Здесь позже можно добавить особую обработку 403/429
        time.sleep(delay_seconds)
        return None

    html = response.text
    time.sleep(delay_seconds)
    return html
