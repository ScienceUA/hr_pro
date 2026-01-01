import time
import requests

import os
import sys

# Добавляем корень проекта в sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from config.user_agent import BROWSER_USER_AGENT


def fetch_resume(url: str, user_agent: str, delay_seconds: float = 1.0) -> None:
    """
    Отправляет один HTTP GET-запрос к резюме.
    Печатает:
      - URL
      - HTTP статус-код
      - первые 100 символов ответа
    Делает паузу delay_seconds после запроса.
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6,en;q=0.5",
        "Connection": "close",
    }

    print(f"\n=== Запрос к резюме: {url} ===")
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        print(f"Ошибка при запросе: {e}")
        time.sleep(delay_seconds)
        return

    print(f"Статус-код: {response.status_code}")
    print(f"Итоговый URL: {response.url}")

    text_snippet = response.text[:300].replace("\n", " ").replace("\r", " ")
    print(f"Первые 300 символов ответа:\n{text_snippet}")

    time.sleep(delay_seconds)


if __name__ == "__main__":
    # СПИСОК URL РЕЗЮМЕ ДЛЯ ТЕСТА
    RESUME_URLS = [
        # временно можно продублировать один и тот же URL,
        # потом подставишь сюда 20 разных резюме
        "https://www.work.ua/resumes/11941543/?puid=2419664",
        "https://www.work.ua/resumes/9963878/?puid=84488",
        "https://www.work.ua/resumes/15932407/?puid=84488",
        "https://www.work.ua/resumes/15830038/?puid=430727",
        "https://www.work.ua/resumes/11583780/",
        "https://www.work.ua/resumes/16579369/",
        "https://www.work.ua/resumes/1604787/?puid=430727",
        "https://www.work.ua/resumes/13993441/?puid=7448",
        "https://www.work.ua/resumes/3837563/",
        "https://www.work.ua/resumes/5362207/?puid=430727",
        "https://www.work.ua/resumes/10646650/",
        "https://www.work.ua/resumes/5979422/?puid=430727",
        "https://www.work.ua/resumes/7004588/",
        "https://www.work.ua/resumes/12461291/",
        "https://www.work.ua/resumes/5701501/",
        "https://www.work.ua/resumes/9129666/",
        "https://www.work.ua/resumes/15304186/?puid=430727",
        "https://www.work.ua/resumes/6884939/",
        "https://www.work.ua/resumes/14490772/",
        "https://www.work.ua/resumes/13677793/?puid=430727",
    ]

    # 3) ПАУЗА МЕЖДУ ЗАПРОСАМИ (можно потом уменьшать до 0.5)
    DELAY_SECONDS = 0.2

    for idx, url in enumerate(RESUME_URLS, start=1):
        print(f"\n--- Резюме {idx} из {len(RESUME_URLS)} ---")
        fetch_resume(url, BROWSER_USER_AGENT, delay_seconds=DELAY_SECONDS)
