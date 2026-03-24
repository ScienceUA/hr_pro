import time
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import Dict, Any, List

from app.transport.fetcher import SmartFetcher
from app.parsing.base import BaseParser
from app.parsing.serp import SerpParser
from app.parsing.resume import ResumeParser
from app.parsing.models import PageType, DataQuality
from app.storage.repository import JsonlRepository
from app.services.url_builder import UrlBuilder

logger = logging.getLogger(__name__)

class WorkUaAdapter:
    """
    Адаптер для джерела Work.ua.
    Інкапсулює логіку побудови URL, пагінації та парсингу HTML.
    """
    
    DELAY_SERP = 3.0    # Затримка між сторінками пошуку
    DELAY_DETAIL = 1.5  # Затримка між завантаженнями резюме

    def __init__(self, fetcher: SmartFetcher, repository: JsonlRepository):
        self.name = "workua"
        self.fetcher = fetcher
        self.repository = repository

    def preview(self, search_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 1: Проходить по сторінках SERP, рахує total_found та збирає URL.
        """
        query = str(search_payload.get("query") or "").strip()
        city = str(search_payload.get("city") or "").strip()
        params = search_payload.get("params") or {}
        max_pages = search_payload.get("pages", 5)
        direct_url = search_payload.get("direct_url")

        if not query and not direct_url:
            return {"total_found": 0, "urls": []}

        urls: List[str] = []
        seen: set[str] = set()
        real_total = None

        for page_num in range(1, int(max_pages) + 1):
            current_params = dict(params)
            if page_num > 1:
                current_params["page"] = page_num

            try:
                if direct_url:
                    current_url = self._append_page_to_url(direct_url, page_num)
                else:
                    current_url = UrlBuilder.build(query, city, current_params)
            except Exception as e:
                raise RuntimeError(f"Помилка генерації URL: {e}")

            logger.info(f"[{self.name}] 📎 Preview SERP page {page_num}: {current_url}")

            try:
                html_content = self.fetcher.get(current_url)
                if not html_content:
                    raise RuntimeError(f"Порожня відповідь від сервера на сторінці {page_num}")
            except Exception as e:
                raise RuntimeError(f"Мережева помилка: {e}")

            base_parser = BaseParser(html_content, current_url)
            self._check_page_safety(base_parser.page_type, context="SERP_PREVIEW")
            
            if base_parser.page_type != PageType.SERP:
                logger.warning(f"[{self.name}] Неочікуваний тип сторінки. Зупинка.")
                break

            serp_parser = SerpParser(html_content, current_url)
            serp_result = serp_parser.parse()
            
            if serp_result.quality == DataQuality.ERROR:
                logger.error(f"[{self.name}] Помилка парсингу SERP: {serp_result.error_message}")
                break
            
            if page_num == 1:
                try:
                    real_total = getattr(serp_result, "total_found", None)
                except Exception:
                    pass

            previews = serp_result.payload or []
            if not previews:
                break

            new_urls_found = False
            for p in previews:
                u = getattr(p, "url", None)
                if isinstance(u, str) and u and u not in seen:
                    seen.add(u)
                    urls.append(u)
                    new_urls_found = True

            if not new_urls_found:
                 break

            if page_num < int(max_pages):
                 time.sleep(self.DELAY_SERP)

        total_to_return = int(real_total) if isinstance(real_total, int) and real_total > 0 else len(urls)
        return {"total_found": total_to_return, "urls": urls}

    def run_from_urls(self, urls: List[str]) -> Dict[str, Any]:
        """
        Phase 2: Завантажує сторінки, перевіряє дублікати та обробляє помилки.
        Повертає статистику роботи адаптера.
        """
        stats = {"saved": 0, "errors": 0, "skipped": 0, "critical_error": None}
        
        if not urls:
            return stats

        for url in urls:
            # 1. Дедуплікація: витягуємо ID з URL (напр., /resumes/1234567/)
            resume_id = [p for p in url.split('/') if p.isdigit()]
            if resume_id and self.repository.exists(resume_id[-1]):
                logger.debug(f"[{self.name}] Пропуск дубля: {url}")
                stats["skipped"] += 1
                continue

            time.sleep(self.DELAY_DETAIL)

            try:
                html_content = self.fetcher.get(url)
                if not html_content:
                    logger.warning(f"[{self.name}] Порожній контент: {url}")
                    stats["errors"] += 1
                    continue
            except Exception as e:
                logger.error(f"[{self.name}] Помилка завантаження {url}: {e}")
                stats["errors"] += 1
                continue

            base_parser = BaseParser(html_content, url)

            if base_parser.page_type == PageType.NOT_FOUND:
                logger.warning(f"[{self.name}] Резюме не знайдено (404): {url}")
                stats["errors"] += 1
                continue

            # 2. Гібридний Fail Fast: ловимо RuntimeError з _check_page_safety
            try:
                self._check_page_safety(base_parser.page_type, context="DETAIL")
            except RuntimeError as e:
                logger.critical(f"[{self.name}] Збір перервано: {e}")
                stats["critical_error"] = str(e)
                break  # Зупиняємо збір, але повертаємо те, що вже зібрали

            resume_parser = ResumeParser(html_content, url)
            result = resume_parser.parse()

            if result.quality == DataQuality.ERROR:
                logger.warning(f"[{self.name}] Помилка парсингу {url}: {result.error_message}")
                stats["errors"] += 1
                continue

            try:
                self.repository.save_result(result)
                stats["saved"] += 1
                
                # Повертаємо логування name та title
                candidate_name = result.payload.name if result.payload else "Unknown"
                candidate_title = result.payload.title if result.payload else "Unknown Title"
                logger.info(f"[{self.name}] ✅ Збережено: {candidate_name} ({candidate_title})")
            except Exception as e:
                logger.error(f"[{self.name}] Помилка збереження {url}: {e}")
                stats["errors"] += 1

        logger.info(f"[{self.name}] 🏁 Збір завершено. Збережено: {stats['saved']}, Помилок: {stats['errors']}, Пропущено: {stats['skipped']}")
        return stats

    def _check_page_safety(self, page_type: PageType, context: str) -> None:
        """Перевіряє наявність блокувань. Викидає Exception для Fail Fast в Оркестраторі."""
        if page_type in [PageType.BAN, PageType.CAPTCHA, PageType.LOGIN]:
            msg = f"Блокування доступу ({page_type.value.upper()}) на етапі {context}"
            logger.critical(f"[{self.name}] 🛑 {msg}")
            raise RuntimeError(msg)

    def _append_page_to_url(self, base_url: str, page_num: int) -> str:
        if page_num <= 1:
            return base_url
        parsed = urlparse(base_url)
        qs = parse_qs(parsed.query)
        qs['page'] = [str(page_num)]
        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))