import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

from app.parsing.base import BaseParser
from app.parsing.models import (
    ParsingResult, 
    PageType, 
    DataQuality, 
    ResumePreviewData
)
from app.parsing.selectors import CSS

logger = logging.getLogger(__name__)

class SerpParser(BaseParser):
    """
    Парсер поисковой выдачи (SERP).
    Извлекает список ResumePreviewData.
    """

    def parse(self) -> ParsingResult:
        # 1. Если страница определилась как НЕ SERP (например, Бан или Капча) — возвращаем пустой результат с ошибкой
        if self.page_type != PageType.SERP:
            # Если это легитимная ошибка (Бан/Капча), возвращаем её статус
            return ParsingResult(
                url=self.url,
                page_type=self.page_type,
                payload=None
            )

        items: List[ResumePreviewData] = []
        
        # 2. Итерация по карточкам
        # Используем селектор карточки из CSS (он учитывает .card и .card-visited)
        cards = self.soup.select(CSS.SERP_ITEM)
        
        if not cards:
            # Страница SERP, но карточек нет? Возможно, пустая выдача или смена верстки.
            logger.warning(f"SERP detected but no cards found: {self.url}")
            return ParsingResult(
                url=self.url,
                page_type=PageType.SERP,
                payload=[],
                quality=DataQuality.PARTIAL # Считаем частичным успехом (пустой список)
            )

        for card in cards:
            try:
                item = self._parse_item(card)
                if item:
                    items.append(item)
            except Exception as e:
                # Ошибка в одной карточке не должна ломать весь парсинг
                logger.warning(f"Failed to parse SERP item: {e}")
                continue

        # 3. Пагинация (строгая логика)
        next_page = None
        links = self.soup.select(CSS.SERP_NEXT_PAGE)
        if links:
            href = links[0].get("href")
            if href:
                next_page = urljoin(self.url, href)

        # 4. Формирование результата
        # Если карточки были найдены, считаем COMPLETE, иначе PARTIAL
        quality = DataQuality.COMPLETE if items else DataQuality.PARTIAL
        
        return ParsingResult(
            url=self.url,
            page_type=PageType.SERP,
            payload=items,
            next_page_url=next_page,
            quality=quality
        )

    def _parse_item(self, card_element) -> Optional[ResumePreviewData]:
        """Парсинг одной карточки внутри списка."""
        
        # 1. Ссылка и Заголовок (Mandatory)
        # Ищем ссылку внутри карточки
        link_el = card_element.select_one(CSS.SERP_LINK)
        if not link_el or not link_el.has_attr('href'):
            # Карточка без ссылки бесполезна
            return None
            
        raw_url = link_el['href']
        # Превращаем /resumes/123/ в абсолютный URL
        full_url = urljoin(self.url, raw_url)
        
        # Извлекаем ID из URL
        # Паттерн: /resumes/1234567/ -> берем цифры
        resume_id_match = re.search(r"/resumes/(\d+)", full_url)
        if not resume_id_match:
            # Если ID не найден в URL, пропускаем (это может быть реклама)
            return None
        resume_id = resume_id_match.group(1)

        title = self._clean_text(link_el.get_text())

        # 2. Мета-данные (Optional)
        # Возраст/Город часто лежат в snippet или mt-sm
        snippet_text = self._get_text_safe(card_element, CSS.SERP_SNIPPET)
        
        # В будущем здесь можно добавить RegEx для вытаскивания возраста из snippet_text,
        # но пока сохраняем сырые данные, если поля в DTO позволяют (в Preview у нас age/city отдельные поля).
        # Для простоты пока заполняем только то, что явно видим. 
        # Доработка: парсинг строки "25 років, Київ" будет в утилитах.
        
        updated_at = self._get_text_safe(card_element, "div.text-muted span.text-default") # Примерный селектор даты

        return ResumePreviewData(
            resume_id=resume_id,
            url=full_url,
            title=title,
            # age и city пока оставляем None, так как они требуют парсинга строки "25 лет, Киев"
            # Мы добавим это в утилиты нормализации позже.
            updated_at=updated_at
        )