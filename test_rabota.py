import httpx
from bs4 import BeautifulSoup
import json
import re

def test_rabota_public():
    url = "https://robota.ua/candidates/25369704"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    print(f"Завантаження публічної сторінки: {url}...")
    response = httpx.get(url, headers=headers)
    
    soup = BeautifulSoup(response.text, 'html.parser')
    scripts = soup.find_all('script')
    
    found = False
    for i, s in enumerate(scripts):
        if not s.string:
            continue
            
        # Robota.ua часто використовує Apollo GraphQL для стейт-менеджменту
        if 'apolloState' in s.string or 'window.__INITIAL_STATE__' in s.string:
            print("✅ Знайдено вбудований JSON (Apollo/Initial State)!")
            with open("rabota_public_state.js", "w", encoding="utf-8") as f:
                f.write(s.string)
            found = True
            break
            
        # Або це може бути Next.js
        if '__NEXT_DATA__' in s.string:
            print("✅ Знайдено вбудований JSON (__NEXT_DATA__)!")
            with open("rabota_public_next.json", "w", encoding="utf-8") as f:
                f.write(s.string)
            found = True
            break

    if not found:
        print("❌ Не знайдено стандартних JSON-стейтів. Зберігаємо весь HTML для ручного аналізу.")
        with open("rabota_page.html", "w", encoding="utf-8") as f:
            f.write(response.text)

if __name__ == "__main__":
    test_rabota_public()