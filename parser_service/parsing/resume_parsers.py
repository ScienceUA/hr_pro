import logging
import re
from typing import Optional, Dict, Any

from bs4 import Tag, BeautifulSoup

from parser_service.parsing.base import BaseParser
from parser_service.parsing.models import (
    ParsingResult,
    PageType,
    DataQuality,
    ResumeDetailData,
    SalaryDTO,
    ExperienceEntryDTO,
    EducationEntryDTO,
)
from parser_service.parsing.selectors import CSS

logger = logging.getLogger(__name__)


# =====================================================================
# 1. PARSER ДЛЯ WORK.UA (HTML Parsing)
# =====================================================================
class WorkUaResumeParser(BaseParser):
    """
    Парсер детальної сторінки резюме для Work.ua.
    """

    def parse(self) -> ParsingResult:
        if self.page_type != PageType.RESUME:
            return ParsingResult(
                url=self.url,
                page_type=self.page_type,
                payload=None,
                quality=DataQuality.ERROR,
                error_message="Not a resume page",
            )

        canonical_url = None
        try:
            resume_id = self._extract_resume_id()
            canonical_url = f"https://www.work.ua/resumes/{resume_id}/"

            salary_obj = self._extract_salary()
            salary_str = (
                f"{salary_obj.amount} {salary_obj.currency}"
                if salary_obj
                else None
            )

            data = ResumeDetailData(
                resume_id=str(resume_id),
                source="workua",
                url=canonical_url,
                title=self._extract_title()
                or self._get_text_safe(self.soup, CSS.RESUME_H1)
                or "Без посади",
                salary=salary_str,
                location=None,
                skills=[],
                summary=None,
                experience=[],
                education=[],
                languages=[],
            )

            resume_container = self.soup.select_one(CSS.SIGNATURE_RESUME)
            if not resume_container:
                raise ValueError(
                    "Resume signature container (div[id^='resume_']) not found in DOM"  # noqa: E501
                )

            self._scan_sections(self.soup, data)

            quality = DataQuality.COMPLETE
            if not data.title:
                quality = DataQuality.ERROR
            return ParsingResult(
                url=canonical_url,
                page_type=PageType.RESUME,
                payload=data,
                quality=quality,
            )

        except Exception as e:
            logger.error(
                f"Critical error parsing resume {self.url}: {e}", exc_info=True
            )
            final_url = canonical_url if canonical_url else self.url
            msg = str(e)
            if not canonical_url:
                msg = f"Cannot canonicalize URL (resume_id not found). source_url={self.url}. error={e}"

            return ParsingResult(
                url=final_url,
                page_type=PageType.RESUME,
                quality=DataQuality.ERROR,
                error_message=msg,
            )

    def _extract_title(self) -> Optional[str]:
        meta_tag = self.soup.select_one('meta[property="og:title"]')
        if meta_tag and meta_tag.has_attr("content"):
            content = meta_tag["content"]
            match = re.search(r"«(.*?)»", content)
            if match:
                return match.group(1).strip()

        h2_el = self.soup.select_one(CSS.RESUME_POSITION)
        if h2_el:
            for span in h2_el.select("span"):
                span.decompose()
            return self._clean_text(h2_el.get_text())

        return None

    def _extract_resume_id(self) -> str:
        match = re.search(r"/resumes/([a-zA-Z0-9]+)", self.url)
        if match:
            return match.group(1)

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
                match = re.search(
                    r"(\d[\d\s]+)\s*(грн|UAH|\$|USD|€|EUR)",
                    h2_text,
                    re.IGNORECASE,
                )
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

    def _scan_sections(
        self, container: Tag | BeautifulSoup, data: ResumeDetailData
    ):
        headers = container.find_all("h2")
        current_section = None

        SECTION_STARTERS = {
            "досвід": "exp",
            "освіта": "edu",
            "навички": "skills",
            "знання": "skills",
        }
        SECTION_TERMINATORS = [
            "контактна",
            "інші",
            "схожі",
            "додаткова",
            "кандидати",
        ]

        for h2 in headers:
            text = self._clean_text(h2.get_text()).lower()
            if not text:
                continue

            is_starter = False
            for key, val in SECTION_STARTERS.items():
                if key in text:
                    current_section = val
                    is_starter = True
                    break
            if is_starter:
                continue

            if any(term in text for term in SECTION_TERMINATORS):
                current_section = None
                continue

            if current_section == "exp":
                self._parse_experience_block(h2, data)
            elif current_section == "edu":
                self._parse_education_block(h2, data)

        self._parse_skills_tags(container, data)

    def _get_block_content(self, h2_element: Tag) -> str:
        content_parts = []
        for sibling in h2_element.next_siblings:
            if isinstance(sibling, Tag):
                if sibling.name == "h2":
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
        period_match = re.search(
            r"(\w+\s+\d{4}\s*[\—\-].*|\d+\s+(роки|років|months|years).*)",
            full_text,
        )
        if period_match:
            period = period_match.group(0)
            company_part = full_text.split(period)[0]
            if company_part:
                company = company_part.strip(" .,-")

        data.experience.append(
            ExperienceEntryDTO(
                position=position, company=company, period=period
            )
        )

    def _parse_education_block(self, h2_element: Tag, data: ResumeDetailData):
        institution = self._clean_text(h2_element.get_text())
        full_text = self._get_block_content(h2_element)

        year, specialty = None, None
        if full_text:
            match = re.search(r"\b(19|20)\d{2}\b", full_text)
            if match:
                year = match.group(0)
            if year:
                specialty_cand = full_text.split(year)[0].strip(" .,-")
                if specialty_cand:
                    specialty = specialty_cand
            else:
                specialty = full_text

        data.education.append(
            EducationEntryDTO(
                institution=institution, year=year, specialty=specialty
            )
        )

    def _parse_skills_tags(
        self, container: Tag | BeautifulSoup, data: ResumeDetailData
    ):
        tags = container.select(CSS.SKILL_TAGS)
        unique_skills = set()
        for tag in tags:
            txt = self._clean_text(tag.get_text())
            if txt:
                unique_skills.add(txt)
        data.skills = list(unique_skills)


# =====================================================================
# 2. PARSER ДЛЯ ROBOTA.UA (GraphQL JSON Parsing)
# =====================================================================
class RobotaUaResumeParser:
    """
    Парсер для обробки чистого GraphQL JSON від Robota.ua.
    """

    def __init__(self, json_data: Dict[str, Any], url: str):
        self.json_data = json_data
        self.url = url

    def _clean_html(self, raw_html: str) -> str:
        """Очищає HTML-теги з тексту навичок та досвіду"""
        if not raw_html:
            return ""
        clean_text = re.sub(r"<[^>]+>", " ", raw_html)
        clean_text = clean_text.replace("&nbsp;", " ")
        return re.sub(r"\s+", " ", clean_text).strip()

    def parse(self) -> ParsingResult:
        try:
            resume_data = self.json_data.get("data", {}).get("employerResume")

            if not resume_data:
                return ParsingResult(
                    url=self.url,
                    page_type=PageType.RESUME,
                    quality=DataQuality.ERROR,
                    error_message="Резюме не знайдено або доступ закрито",
                )

            title = resume_data.get("title", "Без посади")
            resume_id = str(resume_data.get("id", ""))

            # Зарплата
            salary_str = None
            salary_obj = resume_data.get("salary")
            if salary_obj:
                amount = salary_obj.get('amount', '')
                currency = salary_obj.get('currency', 'UAH')
                salary_str = f"{amount} {currency}"

            # Місто
            city_node = resume_data.get("city") or {}
            location = city_node.get("name")

            # 1. Навички (Skills)
            skills_text = self._clean_html(resume_data.get("skills", ""))
            skills_list = [skills_text] if skills_text else []

            # Файл резюме
            file_node = resume_data.get("file")
            summary_text = None
            if file_node and isinstance(file_node, dict):
                summary_text = file_node.get("summary", "")
                if summary_text:
                    skills_list.append(f"[ФАЙЛ РЕЗЮМЕ]: {summary_text}")

            # 2. Досвід роботи
            exp_items = []
            for exp in resume_data.get("experiences") or []:
                exp_items.append(
                    ExperienceEntryDTO(
                        company=exp.get("companyName") or "Невідома компанія",
                        position=exp.get("position") or "Без посади",
                        period=f"{exp.get('startWork', '')} - {exp.get('endWork') or 'Нині'}",  # noqa: E501
                        description=self._clean_html(
                            exp.get("description", "")
                        ),
                        # Зберігаємо опис в DTO (можливо в company чи summary,
                        # залежно від вашої логіки LLM)
                    )
                )

            # 3. Освіта
            edu_items = []
            for edu in resume_data.get("educations") or []:
                edu_items.append(
                    EducationEntryDTO(
                        institution=edu.get("institutionTitle") or "",
                        specialty=edu.get("speciality") or "",
                        year=str(edu.get("yearOfGraduation") or ""),
                    )
                )

            # Формуємо єдину канонічну модель ResumeDetailData
            data = ResumeDetailData(
                resume_id=resume_id,
                source="robotaua",
                url=self.url,
                title=title,
                salary=salary_str,
                location=location,
                skills=skills_list,
                summary=summary_text,
                experience=exp_items,
                education=edu_items,
                languages=[],  # Можна додати обробку languageSkills, якщо потрібно  # noqa: E501
            )

            return ParsingResult(
                url=self.url,
                page_type=PageType.RESUME,
                payload=data,
                quality=DataQuality.COMPLETE,
            )

        except Exception as e:
            logger.error(f"Error parsing Robota JSON {self.url}: {e}")
            return ParsingResult(
                url=self.url,
                page_type=PageType.RESUME,
                quality=DataQuality.ERROR,
                error_message=str(e),
            )
