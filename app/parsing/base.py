import logging
from typing import Optional, Union
from bs4 import BeautifulSoup, Tag
from app.parsing.models import PageType
from app.parsing.selectors import CSS

logger = logging.getLogger(__name__)

class BaseParser:
    """
    Базовый класс парсера.
    Отвечает за инициализацию DOM и определение PageType по строгим сигнатурам.
    """
    
    def __init__(self, html_content: Union[str, bytes], url: str):
        self.url = url
        if isinstance(html_content, bytes):
            self.soup = BeautifulSoup(html_content, "lxml")
        else:
            self.soup = BeautifulSoup(html_content, "lxml")
            
        self._page_type = self._classify_page()

    @property
    def page_type(self) -> PageType:
        return self._page_type

    def _classify_page(self) -> PageType:
        """
        Классификация страницы.
        Приоритет: Блокировки -> Ошибки -> Логин -> Контент (Резюме/Список)
        """
        text_lower = self.soup.get_text().lower()

        # 1. BAN (WAF / Access Denied)
        if self.soup.select(CSS.SIGNATURE_WAF):
            return PageType.BAN
        # Текстовая проверка для случаев, когда CSS не ловит
        if "access denied" in text_lower or ("cloudflare" in text_lower and "ray id" in text_lower):
            return PageType.BAN
        
        # 2. CAPTCHA
        if self.soup.select(CSS.SIGNATURE_CAPTCHA):
            return PageType.CAPTCHA

        # 3. NOT FOUND (404)
        # Комбинация селектора H1 и текста (обязательно!)
        h1_404 = self.soup.select_one(CSS.SIGNATURE_404)
        if h1_404:
            h1_text = h1_404.get_text(strip=True).lower()
            if "не знайдено" in h1_text:
                return PageType.NOT_FOUND

        # 4. LOGIN
        if self.soup.select(CSS.SIGNATURE_LOGIN):
            return PageType.LOGIN

        # 5. RESUME (Строгая проверка)
        # Наличие специфичного контейнера с ID (div[id^='resume_'])
        if self.soup.select_one(CSS.SIGNATURE_RESUME):
            return PageType.RESUME
        
        # 6. SERP (Список)
        if self.soup.select(CSS.SIGNATURE_SERP):
            return PageType.SERP

        # Если есть H1, но нет контейнера резюме -> это НЕ резюме (например, главная)
        return PageType.UNKNOWN

    def _clean_text(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        text = text.replace('\xa0', ' ').replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
        cleaned = " ".join(text.split())
        return cleaned if cleaned else None

    def _get_text_safe(self, element: Union[Tag, BeautifulSoup], selector: str) -> Optional[str]:
        if not element: return None
        try:
            el = element.select_one(selector)
            if el: return self._clean_text(el.get_text())
        except Exception: pass
        return None

    def _get_attr_safe(self, element: Union[Tag, BeautifulSoup], selector: str, attr: str) -> Optional[str]:
        if not element: return None
        try:
            el = element.select_one(selector)
            if el and el.has_attr(attr):
                val = el[attr]
                if isinstance(val, list): return " ".join(val)
                return str(val).strip()
        except Exception: pass
        return None