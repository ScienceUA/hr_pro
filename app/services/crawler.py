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
    Работает без прокси, поэтому строго соблюдает задержки и останавливается при бане.
    """

    # Задержки (в секундах) для имитации человека
    DELAY_SERP = 3.0    # Между страницами списка
    DELAY_DETAIL = 1.5  # Между резюме

    def __init__(self, fetcher: SmartFetcher, repository: JsonlRepository):
        self.fetcher = fetcher
        self.repository = repository
        self.stats = CrawlStats()

    def run(self, query: str, city: str = "", params: Dict[str, Any] = None, max_pages: int = 5) -> CrawlStats:
        """
        Запуск краулера по поисковому запросу.
        """
        # 1. Генерация стартового URL
        start_url = UrlBuilder.build(query, city, params)
        logger.info(f"🚀 Starting crawl. Query: '{query}', City: '{city}'. URL: {start_url}")
        
        current_url = start_url
        self.stats = CrawlStats()

        while current_url and self.stats.pages_processed < max_pages:
            if self.stats.critical_stop:
                break

            logger.info(f"📂 Processing SERP page {self.stats.pages_processed + 1}: {current_url}")
            
            # 2. Загрузка SERP
            # Поскольку это SERP, мы используем парсер списка внутри логики обработки
            # Но сначала нужно получить HTML и определить PageType через BaseParser (внутри fetcher)
            # SmartFetcher.get(url) возвращает сырой HTML (bytes или str). Классификация PageType выполняется через BaseParser(html, url) на стороне сервиса.
            
            try:
                html = self.fetcher.get(current_url)
            except Exception as e:
                logger.error(f"Network error fetching SERP: {e}")
                self.stats.errors_serp += 1
                break

            # Классифицируем страницу через BaseParser (контракт парсинга, а не транспорта)
            page_type = BaseParser(html, current_url).page_type

            # 3. Safety Checks
            if not self._check_page_safety(page_type, context="SERP"):
                break

            if page_type != PageType.SERP:
                logger.warning(f"Unexpected page type for SERP: {page_type}. Stopping.")
                self.stats.stop_reason = "Unexpected PageType"
                break

            # 4. Парсинг списка
            # Передаем контент в SerpParser (он наследуется от BaseParser, но нам нужно переинициализировать 
            # или использовать логику парсинга. SmartFetcher возвращает BaseParser. 
            # Эффективнее создать SerpParser из сырого HTML, который есть в base_parser.soup, 
            # но SmartFetcher не хранит raw bytes публично. 
            # Упрощение: SmartFetcher.get возвращает инстанс BaseParser. 
            # Мы пересоздадим SerpParser, передав soup.
            
            # ВАЖНО: SerpParser принимает (html_content, url). 
            # Чтобы не качать заново, берем soup.encode() или передаем soup напрямую если парсер поддерживает.
            # Наши парсеры принимают bytes/str.
            serp_result = SerpParser(html, current_url).parse()

            if serp_result.quality == DataQuality.ERROR:
                logger.error("Failed to parse SERP structure.")
                self.stats.errors_serp += 1
                break

            # payload для SERP - это список ResumePreviewData
            previews = serp_result.payload or []
            self.stats.candidates_found += len(previews)
            logger.info(f"   Found {len(previews)} candidates on page.")

            # 5. Обработка кандидатов (Detail Loop)
            for preview in previews:
                if self.stats.critical_stop:
                    break
                
                self._process_candidate(preview)

            # 6. Пагинация
            next_url = serp_result.next_page_url
            
            # Защита от зацикливания
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

    def _process_candidate(self, preview: ResumePreviewData):
        """
        Логика обработки одного кандидата: Дедупликация -> Скачивание -> Парсинг -> Сохранение.
        """
        # 1. Дедупликация (In-Memory check)
        if self.repository.exists(preview.resume_id):
            logger.debug(f"   Skipping existing ID: {preview.resume_id}")
            return

        self.stats.candidates_new += 1
        
        # 2. Throttling перед запросом деталки
        time.sleep(self.DELAY_DETAIL)

        # 3. Скачивание детальной страницы
        try:
            html = self.fetcher.get(preview.url)
        except Exception as e:
            logger.error(f"   Failed to fetch detail {preview.url}: {e}")
            self.stats.errors_detail += 1
            return

        page_type = BaseParser(html, preview.url).page_type

        # 4. Safety Checks
        if page_type == PageType.NOT_FOUND:
            logger.warning(f"   Resume not found (404): {preview.url}")
            return

        if not self._check_page_safety(page_type, context="DETAIL"):
            return

        # 5. Парсинг детальной страницы (используем raw html, без double-parsing)
        result = ResumeParser(html, preview.url).parse()

        # Сохраняем (payload здесь ResumeDetailData)
        if result.payload:
            self.repository.save_candidate(result.payload)
            self.stats.candidates_saved += 1
            logger.info(f"   ✅ Saved: {result.payload.name} ({result.payload.title})")

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