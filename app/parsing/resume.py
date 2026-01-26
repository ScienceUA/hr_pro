import logging
import re
from typing import Optional, List

from bs4 import Tag, BeautifulSoup

from app.parsing.base import BaseParser
from app.parsing.models import (
    ParsingResult, PageType, DataQuality, ResumeDetailData,
    SalaryDTO, ExperienceEntryDTO, EducationEntryDTO
)
from app.parsing.selectors import CSS

logger = logging.getLogger(__name__)

class ResumeParser(BaseParser):
    """
    Парсер детальной страницы резюме.
    Гарантирует канонизацию URL и строгий скоуп парсинга секций.
    """

    def parse(self) -> ParsingResult:
        # 1. Проверка типа страницы
        if self.page_type != PageType.RESUME:
            return ParsingResult(
                url=self.url,
                page_type=self.page_type,
                payload=None,
                quality=DataQuality.ERROR,
                error_message="Not a resume page"
            )

        canonical_url = None
        try:
            # 2. Извлечение ID и канонизация URL
            resume_id = self._extract_resume_id()
            canonical_url = f"https://www.work.ua/resumes/{resume_id}/"

            # 3. Сбор данных
            data = ResumeDetailData(
                resume_id=resume_id,
                url=canonical_url,
                name=self._get_text_safe(self.soup, CSS.RESUME_H1),
                title=self._get_text_safe(self.soup, CSS.RESUME_POSITION),
                salary=self._extract_salary(),
                has_hidden_contacts=bool(self.soup.select_one(CSS.RESUME_HIDDEN_ALERT)),
                skills=[],
                experience=[],
                education=[]
            )

            # 4. Сканирование секций (по всей странице), но с обязательной валидацией сигнатуры резюме
            resume_container = self.soup.select_one(CSS.SIGNATURE_RESUME)
            if not resume_container:
                raise ValueError("Resume signature container (div[id^='resume_']) not found in DOM")

            # ВАЖНО: по отчету Work.ua часть ключевых элементов (например H1) находится вне div#resume_*
            # поэтому секции сканируем по всему документу
            self._scan_sections(self.soup, data)
            # 4.1 Извлечение "монолитного текста" (часто из прикреплённого файла)
            add_info_text = self._extract_add_info_text(self.soup)
            if add_info_text:
                data.about_raw = add_info_text


            # 5. Валидация
            quality = DataQuality.COMPLETE
            if not data.name:
                quality = DataQuality.ERROR

            return ParsingResult(
                url=canonical_url, # Всегда возвращаем каноничный URL
                page_type=PageType.RESUME,
                payload=data,
                quality=quality
            )

        except Exception as e:
            logger.error(f"Critical error parsing resume {self.url}: {e}", exc_info=True)
            # Если удалось вычислить каноничный URL до ошибки — возвращаем его
            final_url = canonical_url if canonical_url else self.url
            msg = str(e)
            if not canonical_url:
                msg = f"Cannot canonicalize URL (resume_id not found). source_url={self.url}. error={e}"
            
            return ParsingResult(
                url=final_url,
                page_type=PageType.RESUME,
                quality=DataQuality.ERROR,
                error_message=msg
            )

    def _extract_resume_id(self) -> str:
        """
        Извлекает ID из URL или DOM.
        """
        # 1. Из URL (допускаем параметры после ID, но требуем совпадения паттерна)
        match = re.search(r"/resumes/([a-zA-Z0-9]+)", self.url)
        if match:
            return match.group(1)
        
        # 2. Из контейнера
        container = self.soup.select_one(CSS.SIGNATURE_RESUME)
        if container and container.has_attr("id"):
            val = container["id"].replace("resume_", "")
            if val:
                return val
            
        raise ValueError("resume_id not found")

    def _extract_salary(self) -> Optional[SalaryDTO]:
        raw_text = self._get_text_safe(self.soup, CSS.RESUME_SALARY_BLOCK)
        
        if not raw_text:
            h2_text = self._get_text_safe(self.soup, CSS.RESUME_POSITION)
            if h2_text:
                match = re.search(r"(\d[\d\s]+)\s*(грн|UAH|\$|USD|€|EUR)", h2_text, re.IGNORECASE)
                if match:
                    raw_text = match.group(0)

        if not raw_text:
            return None

        clean_str = raw_text.replace(" ", "").replace("\xa0", "")
        amount_match = re.search(r"(\d+)", clean_str)
        
        if amount_match:
            amount = int(amount_match.group(1))
            currency = "UAH"
            if "$" in raw_text or "USD" in raw_text.upper():
                currency = "USD"
            elif "€" in raw_text or "EUR" in raw_text.upper():
                currency = "EUR"
            return SalaryDTO(amount=amount, currency=currency)
        return None

    def _scan_sections(self, container: Tag | BeautifulSoup, data: ResumeDetailData):
        """
        Итерируется по H2. Переключает контекст при встрече заголовков секций.
        Если встречен "чужой" системный заголовок — сбрасывает контекст.
        """
        headers = container.find_all('h2')
        current_section = None
        
        # Заголовки, которые переключают режим парсинга
        SECTION_STARTERS = {
            "досвід": "exp",
            "освіта": "edu",
            "навички": "skills",
            "знання": "skills" # Знання і навички
        }
        
        # Заголовки, которые явно завершают любую активную секцию
        SECTION_TERMINATORS = [
            "контактна", "інші", "схожі", "додаткова", "кандидати"
        ]

        for h2 in headers:
            text = self._clean_text(h2.get_text()).lower()
            if not text:
                continue

            # 1. Проверяем, не начинается ли новая полезная секция
            is_starter = False
            for key, val in SECTION_STARTERS.items():
                if key in text:
                    current_section = val
                    is_starter = True
                    break
            if is_starter:
                continue

            # 2. Проверяем, не является ли это "терминатором" (системным блоком)
            if any(term in text for term in SECTION_TERMINATORS):
                current_section = None
                continue

            # 3. Если мы внутри активной секции — парсим контент
            if current_section == "exp":
                self._parse_experience_block(h2, data)
            elif current_section == "edu":
                self._parse_education_block(h2, data)
            
        # Навыки собираем отдельно по тегам (т.к. они часто не привязаны к H2 структуры)
        self._parse_skills_tags(container, data)

    def _get_block_content(self, h2_element: Tag) -> str:
        """
        Собирает текст между текущим H2 и следующим H2 (на том же уровне вложенности).
        Использует next_siblings, останавливаясь при встрече следующего H2.
        """
        content_parts = []
        for sibling in h2_element.next_siblings:
            if isinstance(sibling, Tag):
                if sibling.name == 'h2':
                    break 
                text = self._clean_text(sibling.get_text())
                if text:
                    content_parts.append(text)
            elif sibling.string:
                text = str(sibling).strip()
                if text:
                    content_parts.append(text)
        
        return " ".join(content_parts)

    def _parse_experience_block(self, h2_element: Tag, data: ResumeDetailData):
        position = self._clean_text(h2_element.get_text())
        full_text = self._get_block_content(h2_element)
        
        if not full_text:
            return

        company = full_text
        period = None
        
        period_match = re.search(r"(\w+\s+\d{4}\s*[\—\-].*|\d+\s+(роки|років|months|years).*)", full_text)
        if period_match:
            period = period_match.group(0)
            company_part = full_text.split(period)[0]
            if company_part:
                company = company_part.strip(' .,-')

        data.experience.append(ExperienceEntryDTO(
            position=position,
            company=company, # Возвращаем полный текст (без обрезки)
            period=period
        ))

    def _parse_education_block(self, h2_element: Tag, data: ResumeDetailData):
        institution = self._clean_text(h2_element.get_text())
        full_text = self._get_block_content(h2_element)
        
        year = None
        specialty = None

        if full_text:
            match = re.search(r"\b(19|20)\d{2}\b", full_text)
            if match:
                year = match.group(0)
            
            if year:
                specialty_cand = full_text.split(year)[0].strip(' .,-')
                if specialty_cand:
                    specialty = specialty_cand
            else:
                specialty = full_text # Возвращаем полный текст, если не смогли разбить

        data.education.append(EducationEntryDTO(
            institution=institution,
            year=year,
            specialty=specialty
        ))

    def _parse_skills_tags(self, container: Tag | BeautifulSoup, data: ResumeDetailData):

        tags = container.select(CSS.SKILL_TAGS)
        unique_skills = set()
        for tag in tags:
            txt = self._clean_text(tag.get_text())
            if txt:
                unique_skills.add(txt)
        data.skills = list(unique_skills)
    
    def _extract_add_info_text(self, container: Tag | BeautifulSoup) -> Optional[str]:
        """
        Извлекает монолитный текст резюме из блока #add_info (Work.ua часто так рендерит резюме,
        созданные на основе прикреплённого файла).

        Требования:
        - детерминированно
        - без попыток "разметить" на experience/education/skills
        - максимально чистый текст, пригодный для evidence в пункте 6
        """
        block = container.select_one(CSS.RESUME_ADD_INFO)
        if not block:
            return None

        # Удаляем "служебные" элементы, которые не несут смысловой нагрузки
        for el in block.select(".hidden-print"):
            el.decompose()

        # Берём текст с сохранением переносов
        text = block.get_text(separator="\n", strip=True)

        if not text:
            return None

        # Чистка мусора: NBSP, form-feed, множественные пустые строки
        text = text.replace("\xa0", " ").replace("\f", "\n")

        # Убираем слишком частые "відкрити контакти" (они часто встраиваются в этот блок)
        text = re.sub(r"\bвідкрити контакти\b", "", text, flags=re.IGNORECASE)

        # Нормализация пустых строк
        lines = [ln.strip() for ln in text.splitlines()]
        # Удаляем полностью пустые строки на концах, но оставляем смысловые разрывы
        cleaned: List[str] = []
        last_empty = False
        for ln in lines:
            if not ln:
                if not last_empty:
                    cleaned.append("")
                last_empty = True
                continue
            cleaned.append(ln)
            last_empty = False

        final = "\n".join(cleaned).strip()
        return final if final else None
