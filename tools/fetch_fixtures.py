import argparse
import asyncio
import json
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
from typing import Dict, Any, Optional

# Импорт BS4 теперь сработает, так как мы его установили
from bs4 import BeautifulSoup
import httpx

# Добавляем корень проекта в путь для импорта модулей приложения
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings
from app.execution.http_client import HttpClientFactory
from app.execution.proxy_manager import proxy_manager

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fixture_fetcher")

# --- 0. DI Fix (Null Object Pattern) ---
class NullProxyManager:
    """Заглушка для Direct-режима, чтобы фабрика не падала при обращении к proxy_manager."""
    def get_next_proxy(self) -> Optional[str]:
        return None

# --- 1. Signature Contracts ---

class PageType(str, Enum):
    SERP = "serp"       # Список резюме
    RESUME = "resume"   # Детальная страница

class PageSignature(str, Enum):
    OK = "ok"                       # Валидная целевая страница
    PROTECTED = "protected"         # 403/401, но контент есть (скрытые контакты, логин)
    CAPTCHA = "captcha"             # Требует ввода капчи
    ACCESS_DENIED = "access_denied" # Жесткий бан (WAF)
    NOT_FOUND = "not_found"         # 404
    UNKNOWN = "unknown"             # 200, но структура не похожа на целевую

def classify_page(html: str, status_code: int, expected_type: PageType) -> PageSignature:
    """
    Классификация страницы. OK ставим только при наличии позитивных признаков.
    """
    soup = BeautifulSoup(html, "html.parser")
    lower_html = html.lower()

    # 1. Negative Checks (WAF / Captcha)
    if status_code in [403, 503] and ("cloudflare" in lower_html or "ray id" in lower_html):
        return PageSignature.ACCESS_DENIED
    
    if soup.select("#g-recaptcha-response") or soup.select("iframe[src*='captcha']"):
        return PageSignature.CAPTCHA

    # 2. Positive Checks (Structure Validation)
    if status_code == 200:
        if expected_type == PageType.RESUME:
            # Ищем признаки резюме (H1, title)
            has_h1 = bool(soup.find("h1"))
            has_resume_marker = "резюме" in soup.title.text.lower() if soup.title else False
            
            if has_h1 or has_resume_marker:
                return PageSignature.OK
        
        elif expected_type == PageType.SERP:
            # Ищем признаки списка (карточки)
            # Ищем div с классом card или ссылки на резюме
            cards = soup.select("div.card") or soup.select("a[href*='/resumes/']")
            if cards:
                return PageSignature.OK
        
        return PageSignature.UNKNOWN

    # 3. Protected / Auth
    if status_code in [401, 403]:
        return PageSignature.PROTECTED

    if status_code == 404:
        return PageSignature.NOT_FOUND

    return PageSignature.UNKNOWN

# --- 2. Security & Sanitization ---

SAFE_HEADERS = {
    "content-type", "date", "server", "last-modified", "etag", "content-encoding", "vary"
}

def sanitize_headers(headers: httpx.Headers) -> Dict[str, str]:
    """Убираем куки и токены из заголовков."""
    clean = {}
    for k, v in headers.items():
        if k.lower() in SAFE_HEADERS:
            clean[k.lower()] = v
    return clean

# --- 3. Fetch Logic ---

async def fetch_fixture(
    url: str, 
    name: str, 
    page_type: PageType,
    case_label: str,
    use_proxy: bool, 
    force: bool
):
    logger.info(f"🚀 Starting fetch: {url}")
    
    # Выбираем менеджер прокси
    pm = proxy_manager if use_proxy else NullProxyManager()
    
    # Инициализируем фабрику
    factory = HttpClientFactory(settings, pm)

    try:
        async with factory.client() as client:
            fetched_at = datetime.now(timezone.utc).isoformat()
            
            try:
                resp = await client.get(url)
            except Exception as e:
                logger.error(f"❌ Transport Error: {e}")
                return

            # --- Check 1: Content Type ---
            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" not in content_type:
                logger.error(f"❌ Invalid Content-Type: {content_type}. Expected HTML.")
                if not force:
                    return

            # --- Check 2: Signature ---
            html_text = resp.text 
            signature = classify_page(html_text, resp.status_code, page_type)
            
            logger.info(f"🔍 Signature: {signature.value.upper()} (Status: {resp.status_code})")

            # Разрешаем сохранять только понятные состояния, если нет --force
            valid_signatures = [PageSignature.OK, PageSignature.PROTECTED, PageSignature.NOT_FOUND]
            
            if signature not in valid_signatures and not force:
                logger.warning(f"⚠️ Signature '{signature.value}' rejected. Use --force to save anyway.")
                return

            # --- Saving ---
            base_dir = settings.BASE_DIR / "tests" / "fixtures" / "raw"
            base_dir.mkdir(parents=True, exist_ok=True)
            
            # Имя файла: type_case_name
            filename_base = f"{page_type.value}_{case_label}_{name}"
            html_path = base_dir / f"{filename_base}.html"
            meta_path = base_dir / f"{filename_base}.meta.json"

            # Сохраняем HTML бинарно
            with open(html_path, "wb") as f:
                f.write(resp.content)

            # Сохраняем Meta
            meta_data = {
                "url_requested": url,
                "url_final": str(resp.url),
                "status_code": resp.status_code,
                "fetched_at": fetched_at,
                "signature": signature.value,
                "type": page_type.value,
                "case": case_label,
                "fetch_mode": "proxy" if use_proxy else "direct",
                "content_type": content_type,
                "encoding_detected": resp.encoding or "utf-8",
                "headers": sanitize_headers(resp.headers)
            }
            
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2, ensure_ascii=False)

            logger.info(f"✅ Saved:\n  HTML: {html_path}\n  META: {meta_path}")

    except Exception as e:
        logger.exception(f"❌ Critical Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Fixture Fetcher (L4.1)")
    
    parser.add_argument("--url", required=True)
    parser.add_argument("--name", required=True, help="Unique suffix")
    parser.add_argument("--type", required=True, choices=["serp", "resume"], help="Page type")
    parser.add_argument("--case", required=True, default="ok", help="Scenario label")
    parser.add_argument("--proxy", action="store_true")
    parser.add_argument("--force", action="store_true")
    
    args = parser.parse_args()
    
    asyncio.run(fetch_fixture(
        url=args.url,
        name=args.name,
        page_type=PageType(args.type),
        case_label=args.case,
        use_proxy=args.proxy,
        force=args.force
    ))