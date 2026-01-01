import time
import requests
from config.user_agent import BROWSER_USER_AGENT


def test_url(url: str, user_agent: str, times: int = 3, delay_seconds: float = 2.0) -> None:
    """
    Отправляет HTTP GET-запрос к заданному URL с указанным User-Agent.
    Повторяет запрос `times` раз с паузой `delay_seconds` секунд.
    Печатает:
      - номер попытки
      - HTTP статус-код
      - итоговый URL (после редиректов)
      - первые 200 символов ответа (как текст)
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6,en;q=0.5",
        "Connection": "close",
    }

    for i in range(1, times + 1):
        print(f"\n=== Запрос {i} к {url} ===")
        try:
            response = requests.get(url, headers=headers, timeout=15)
        except Exception as e:
            print(f"Ошибка при запросе: {e}")
            time.sleep(delay_seconds)
            continue

        print(f"Статус-код: {response.status_code}")
        print(f"Итоговый URL: {response.url}")

        # Печатаем первые 200 символов текста ответа
        text_snippet = response.text[:200].replace("\n", " ").replace("\r", " ")
        print(f"Первые 200 символов ответа:\n{text_snippet}")

        # Пауза перед следующим запросом
        if i != times:
            time.sleep(delay_seconds)


if __name__ == "__main__":
   
    # ВЫБЕРИ URL для теста: раскомментируй нужную строку
    URL_RESUME = "https://www.work.ua/resumes/16462621/?puid=2419664"
    URL_BASE_SEARCH = "https://www.work.ua/resumes-kyiv-marketing+director/"
    URL_FILTERED_SEARCH = "https://www.work.ua/resumes-kyiv-administration-industry-it-marketing+director/?experience=166"

    # Пример: сначала тестируем страницу резюме с браузерным User-Agent
    test_url(
    url=URL_RESUME,
    user_agent=BROWSER_USER_AGENT,
    times=3,
    delay_seconds=2.0,
    )

    # Чтобы протестировать "ботоподобный" User-Agent, после этого
    # измени вызов на:
    #
    # test_url(
    #     url=URL_RESUME,
    #     user_agent="Python-requests/2.31.0",
    #     times=3,
    #     delay_seconds=2.0,
    # )
