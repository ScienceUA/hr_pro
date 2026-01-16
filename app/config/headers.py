import random
from typing import Dict

# Базовые заголовки.
# ВАЖНО: Мы НЕ указываем "Accept-Encoding". 
# httpx сам добавит "gzip, deflate, br" и автоматически распакует ответ.
BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Список User-Agent для ротации
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

def get_headers() -> Dict[str, str]:
    """Генерирует заголовки со случайным User-Agent"""
    headers = BASE_HEADERS.copy()
    user_agent = random.choice(USER_AGENTS)
    headers["User-Agent"] = user_agent
    
    # Добавляем Client Hints (Sec-Ch-Ua) в зависимости от User-Agent
    if "Chrome" in user_agent:
        headers["Sec-Ch-Ua"] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
        headers["Sec-Ch-Ua-Mobile"] = "?0"
        if "Macintosh" in user_agent:
            headers["Sec-Ch-Ua-Platform"] = '"macOS"'
        elif "Windows" in user_agent:
            headers["Sec-Ch-Ua-Platform"] = '"Windows"'
    
    return headers