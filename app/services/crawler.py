import time
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from app.transport.fetcher import SmartFetcher
from app.parsing.base import BaseParser
from app.parsing.serp import SerpParser
from app.parsing.resume import ResumeParser
from app.parsing.models import PageType, DataQuality, ResumePreviewData
from app.storage.repository import JsonlRepository
from app.services.url_builder import UrlBuilder

logger = logging.getLogger(__name__)

@dataclass
class CrawlStats:
    """Статистика текущего прогона."""
    pages_processed: int = 0
    candidates_found: int = 0
    candidates_new: int = 0
    candidates_saved: int = 0
    errors_serp: int = 0
    errors_detail: int = 0
    critical_stop: bool = False
    stop_reason: Optional[str] = None

class CrawlerService:
    """
    Оркестратор процесса сбора данных.
    Реализует цикл: SERP -> Links -> Dedup -> Detail -> Save.
    Строго соблюдает задержки и останавливается при блокировках.
    """
    
    # Задержки (в секундах) для имитации человека
    DELAY_SERP = 3.0    # Между страницами списка
    DELAY_DETAIL = 1.5  # Между резюме

    def __init__(self, fetcher: SmartFetcher, repository: JsonlRepository):
        self.fetcher = fetcher
        self.repository = repository
        self.stats = CrawlStats()

    def run(
        self,
        query: str,
        city: str = "",
        params: Optional[Dict[str, Any]] = None,
        max_pages: Optional[int] = None,
    ) -> CrawlStats:

        """
        Запуск краулера по поисковому запросу.
        """
        # 1. Генерация стартового URL (с учетом параметров фильтрации)
        try:
            start_url = UrlBuilder.build(query, city, params)
        except Exception as e:
            logger.error(f"Failed to build URL: {e}")
            self.stats.critical_stop = True
            self.stats.stop_reason = "URL Build Error"
            return self.stats

        logger.info(f"🚀 Starting crawl. Query: '{query}', City: '{city}'. URL: {start_url}")
        
        current_url = start_url
        self.stats = CrawlStats()

        while current_url and (max_pages is None or self.stats.pages_processed < max_pages):
            if self.stats.critical_stop:
                break

            logger.info(f"📂 Processing SERP page {self.stats.pages_processed + 1}: {current_url}")
            
            # --- 1. Fetching ---
            try:
                html_content = self.fetcher.get(current_url)
                if not html_content:
                    logger.error("Empty response from fetcher for SERP.")
                    self.stats.errors_serp += 1
                    break
            except Exception as e:
                logger.error(f"Network error fetching SERP: {e}")
                self.stats.errors_serp += 1
                break

            # --- 2. Safety Check (Base Parser) ---
            # Создаем легкий парсер только для проверки типа страницы
            base_parser = BaseParser(html_content, current_url)
            
            if not self._check_page_safety(base_parser.page_type, context="SERP"):
                break

            if base_parser.page_type != PageType.SERP:
                logger.warning(f"Unexpected page type for SERP: {base_parser.page_type}. Stopping.")
                self.stats.stop_reason = f"Unexpected PageType: {base_parser.page_type}"
                break

            # --- 3. Parsing (Serp Parser) ---
            # Передаем ТОТ ЖЕ html_content напрямую
            serp_parser = SerpParser(html_content, current_url)
            serp_result = serp_parser.parse()

            if serp_result.quality == DataQuality.ERROR:
                logger.error("Failed to parse SERP structure.")
                self.stats.errors_serp += 1
                break

            previews = serp_result.payload or []
            self.stats.candidates_found += len(previews)
            logger.info(f"   Found {len(previews)} candidates on page.")

            # --- 4. Detail Loop (Candidates) ---
            for preview in previews:
                if self.stats.critical_stop:
                    break
                self._process_candidate(preview)

            # --- 5. Pagination ---
            next_url = serp_result.next_page_url
            
            # Защита от зацикливания (если next_url ведет на ту же страницу)
            if next_url == current_url:
                logger.warning("Next page URL matches current. Loop detected.")
                break
            
            current_url = next_url
            self.stats.pages_processed += 1

            if current_url:
                logger.debug(f"💤 Sleeping {self.DELAY_SERP}s before next page...")
                time.sleep(self.DELAY_SERP)
        
        logger.info(f"🏁 Crawl finished. Stats: {self.stats}")
        return self.stats
    
    def preview(self, search_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 1 (Preview/Count):
        - НЕ скачивает детали резюме
        - НЕ сохраняет JSONL
        - Только: проходит SERP пагинацию, собирает URL резюме сверху вниз
        и возвращает {total_found, urls}.
        """
        query = str(search_payload.get("query") or "").strip()
        city = str(search_payload.get("city") or "").strip()
        params = search_payload.get("params") or {}
        max_pages = search_payload.get("max_pages", None)

        if not query:
            return {"total_found": 0, "urls": []}

        try:
            start_url = UrlBuilder.build(query, city, params)
        except Exception as e:
            logger.error(f"Failed to build URL (preview): {e}")
            return {"total_found": 0, "urls": []}

        current_url = start_url
        pages_processed = 0

        urls: list[str] = []
        seen: set[str] = set()

        while current_url and (max_pages is None or pages_processed < int(max_pages)):
            logger.info(f"📎 Preview SERP page {pages_processed + 1}: {current_url}")

            # --- Fetch ---
            try:
                html_content = self.fetcher.get(current_url)
                if not html_content:
                    logger.error("Empty response from fetcher for SERP (preview).")
                    break
            except Exception as e:
                logger.error(f"Network error fetching SERP (preview): {e}")
                break

            # --- Safety ---
            base_parser = BaseParser(html_content, current_url)
            if not self._check_page_safety(base_parser.page_type, context="SERP_PREVIEW"):
                break
            if base_parser.page_type != PageType.SERP:
                logger.warning(f"Unexpected page type for SERP preview: {base_parser.page_type}. Stopping.")
                break

            # --- Parse SERP ---
            serp_parser = SerpParser(html_content, current_url)
            serp_result = serp_parser.parse()
            if serp_result.quality == DataQuality.ERROR:
                logger.error("Failed to parse SERP structure (preview).")
                break

            previews = serp_result.payload or []
            for p in previews:
                u = getattr(p, "url", None)
                if isinstance(u, str) and u and u not in seen:
                    seen.add(u)
                    urls.append(u)

            next_url = serp_result.next_page_url
            if next_url == current_url:
                logger.warning("Next page URL matches current (preview). Loop detected.")
                break

            current_url = next_url
            pages_processed += 1

            if current_url:
                time.sleep(self.DELAY_SERP)

        # Если SerpParser смог вытащить реальное total_found — используем его.
        # Иначе fallback: len(urls)
        real_total = None
        try:
            real_total = getattr(serp_result, "total_found", None)
        except Exception:
            real_total = None

        return {"total_found": int(real_total) if isinstance(real_total, int) and real_total > 0 else len(urls), "urls": urls}

    def run_from_urls(self, urls: list[str], out: str) -> str:
        """
        Phase 2 (Full crawl by URLs):
        - скачивает ТОЛЬКО детали по переданным URL
        - парсит ResumeParser
        - сохраняет через repository.save_result()
        - возвращает путь out (для совместимости с run_agent.py)
        """
        # Мы не переинициализируем repository здесь, потому что он уже создан с нужным out_path
        # в load_crawler_service(out_path). out используем как контроль/лог.
        if not urls:
            return out

        self.stats = CrawlStats()

        for url in urls:
            if self.stats.critical_stop:
                break

            time.sleep(self.DELAY_DETAIL)

            try:
                html_content = self.fetcher.get(url)
                if not html_content:
                    logger.warning(f"Empty content for detail {url}")
                    self.stats.errors_detail += 1
                    continue
            except Exception as e:
                logger.error(f"Failed to fetch detail {url}: {e}")
                self.stats.errors_detail += 1
                continue

            base_parser = BaseParser(html_content, url)

            if base_parser.page_type == PageType.NOT_FOUND:
                logger.warning(f"Resume not found (404): {url}")
                continue

            if not self._check_page_safety(base_parser.page_type, context="DETAIL"):
                break

            resume_parser = ResumeParser(html_content, url)
            result = resume_parser.parse()

            if result.quality == DataQuality.ERROR:
                logger.warning(f"Parser Error for {url}: {result.error_message}")
                self.stats.errors_detail += 1
                continue

            try:
                self.repository.save_result(result)
                self.stats.candidates_saved += 1

                candidate_name = result.payload.name if result.payload else "Unknown"
                candidate_title = result.payload.title if result.payload else "Unknown Title"
                logger.info(f"✅ Saved: {candidate_name} ({candidate_title})")

            except Exception as e:
                logger.error(f"Failed to save result for {url}: {e}")
                self.stats.errors_detail += 1

        logger.info(f"🏁 run_from_urls finished. Stats: {self.stats}")
        return out

    
    def _process_candidate(self, preview: ResumePreviewData):
        """
        Логика обработки одного кандидата: Дедупликация -> Скачивание -> Парсинг -> Сохранение.
        """
        # 1. Дедупликация (In-Memory check)
        # Проверяем по resume_id (ключевой инвариант)
        if self.repository.exists(preview.resume_id):
            logger.debug(f"   Skipping existing ID: {preview.resume_id}")
            return

        self.stats.candidates_new += 1
        
        # 2. Throttling перед запросом деталки
        time.sleep(self.DELAY_DETAIL)

        # 3. Скачивание детальной страницы
        try:
            html_content = self.fetcher.get(preview.url)
            if not html_content:
                logger.warning(f"   Empty content for detail {preview.url}")
                self.stats.errors_detail += 1
                return
        except Exception as e:
            logger.error(f"   Failed to fetch detail {preview.url}: {e}")
            self.stats.errors_detail += 1
            return

        # 4. Проверка статуса (Safety Checks)
        base_parser = BaseParser(html_content, preview.url)
        
        # Если 404 - это не критично, просто пропускаем кандидата
        if base_parser.page_type == PageType.NOT_FOUND:
            logger.warning(f"   Resume not found (404): {preview.url}")
            return
            
        # Если Бан/Капча - это критично для всей сессии
        if not self._check_page_safety(base_parser.page_type, context="DETAIL"):
            return

        # 5. Парсинг детальной страницы
        resume_parser = ResumeParser(html_content, preview.url)
        result = resume_parser.parse()

        if result.quality == DataQuality.ERROR:
            logger.warning(f"   Parser Error for {preview.resume_id}: {result.error_message}")
            self.stats.errors_detail += 1
            return

        # 6. Сохранение результата
        try:
            # Используем актуальный метод репозитория save_result(ParsingResult)
            self.repository.save_result(result)
            self.stats.candidates_saved += 1
            
            # Логируем имя для наглядности (если распарсилось)
            candidate_name = result.payload.name if result.payload else "Unknown"
            candidate_title = result.payload.title if result.payload else "Unknown Title"
            logger.info(f"   ✅ Saved: {candidate_name} ({candidate_title})")
            
        except Exception as e:
            logger.error(f"   Failed to save result for {preview.resume_id}: {e}")

    def _check_page_safety(self, page_type: PageType, context: str) -> bool:
        """
        Проверяет, можно ли продолжать работу.
        При BAN/CAPTCHA/LOGIN выставляет флаг critical_stop.
        """
        if page_type in [PageType.BAN, PageType.CAPTCHA, PageType.LOGIN]:
            logger.critical(f"🛑 CRITICAL: Detected {page_type.value.upper()} on {context}. Stopping session.")
            self.stats.critical_stop = True
            self.stats.stop_reason = f"Blocked: {page_type.value}"
            return False
        return True