import re
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _safe_text(node) -> Optional[str]:
    if not node:
        return None
    return _clean_text(node.get_text(" ", strip=True))


def _find_heading(soup: BeautifulSoup, keywords: List[str]):
    keywords_lower = [kw.lower() for kw in keywords]
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = tag.get_text(" ", strip=True).lower()
        if any(keyword in text for keyword in keywords_lower):
            return tag
    return None


def _section_content(start_tag):
    if not start_tag:
        return []

    contents = []
    for sibling in start_tag.find_all_next():
        if sibling.name in {"h1", "h2", "h3", "h4"}:
            break
        if sibling.name in {"div", "article", "li", "p"}:
            text = _safe_text(sibling)
            if text:
                contents.append((sibling, text))
    return contents


def _parse_age_and_city(text: str) -> Tuple[Optional[int], Optional[str], Optional[bool]]:
    age_match = re.search(
        r"(\d{2})\s*(?:рок(?:ів|и)?|years?|лет|года?)",
        text,
        flags=re.IGNORECASE,
    )
    age = int(age_match.group(1)) if age_match else None

    relocation = None
    relocation_patterns = {
        True: [
            "готов к переезду",
            "готова к переезду",
            "готов переехать",
            "готова переехать",
            "готовий до переїзду",
            "готова до переїзду",
        ],
        False: [
            "не готов к переезду",
            "не готова к переезду",
            "не готов переехать",
            "не готова переехать",
            "не готовий до переїзду",
            "не готова до переїзду",
        ],
    }
    lowered = text.lower()
    for value, patterns in relocation_patterns.items():
        if any(pattern in lowered for pattern in patterns):
            relocation = value
            break

    city = None
    city_candidates = re.split(r"[•\|·]", text)
    if city_candidates:
        city_candidate = city_candidates[0]
        parts = [part.strip() for part in city_candidate.split(",") if part.strip()]
        if parts:
            city = parts[-1]

    return age, city if city else None, relocation


def _parse_salary(text: str) -> Tuple[Optional[int], Optional[str]]:
    salary_match = re.search(
        r"([\d\s]+)\s*(грн|uah|₴|usd|\$|eur|€|руб|₽)",
        text,
        flags=re.IGNORECASE,
    )
    if not salary_match:
        return None, None
    amount = int(salary_match.group(1).replace(" ", ""))
    currency = salary_match.group(2).upper().replace("₴", "UAH").replace("$", "USD").replace("€", "EUR")
    return amount, currency


def _parse_duration(text: str) -> Tuple[Optional[int], Optional[int]]:
    years = None
    months = None

    years_match = re.search(
        r"(\d+)\s*(?:р(?:ок(?:iв)?|okів)?|роки|years?|лет|года?)",
        text,
        flags=re.IGNORECASE,
    )
    months_match = re.search(
        r"(\d+)\s*(?:мес(?:яц)?(?:ев)?|місяц(?:і|i)?|month)",
        text,
        flags=re.IGNORECASE,
    )

    if years_match:
        years = int(years_match.group(1))
    if months_match:
        months = int(months_match.group(1))
    return years, months


def _parse_experience(section_contents):
    experiences = []
    for node, text in section_contents:
        if len(text) < 10:
            continue

        period = None
        company = None
        position = None
        description = None
        duration = None

        strong = node.find(["strong", "b"])
        if strong:
            position = _safe_text(strong)

        italic = node.find(["i", "em"])
        if italic:
            company = _safe_text(italic)

        period_match = re.search(r"\d{4}.*?\d{4}|\d{4}\s*-\s*по настоящее время|\d{4}\s*—\s*нині", text)
        if period_match:
            period = _clean_text(period_match.group(0))

        years, months = _parse_duration(text)
        duration = months
        if years is not None:
            duration = (years * 12) + (months or 0)

        description_paragraphs = [p.get_text(" ", strip=True) for p in node.find_all("p")]
        if description_paragraphs:
            description = _clean_text(" ".join(description_paragraphs))
        else:
            description = text

        experiences.append(
            {
                "period": period,
                "duration_months": duration,
                "company": company,
                "position": position,
                "description": description,
            }
        )
    return experiences


def _parse_education(section_contents):
    education = []
    for node, text in section_contents:
        if len(text) < 5:
            continue

        period = None
        institution = None
        degree = None
        description = None

        em = node.find(["strong", "b"])
        if em:
            institution = _safe_text(em)

        italic = node.find(["i", "em"])
        if italic:
            degree = _safe_text(italic)

        period_match = re.search(r"\d{4}.*?\d{4}|\d{4}\s*-\s*по настоящее время|\d{4}\s*—\s*нині", text)
        if period_match:
            period = _clean_text(period_match.group(0))

        paragraphs = [p.get_text(" ", strip=True) for p in node.find_all("p")]
        description = _clean_text(" ".join(paragraphs)) if paragraphs else text

        education.append(
            {
                "period": period,
                "institution": institution,
                "degree": degree,
                "description": description,
            }
        )
    return education


def _parse_list_section(section_contents):
    values = []
    for node, _ in section_contents:
        items = node.find_all(["li", "span", "a"])
        if items:
            for item in items:
                text = _safe_text(item)
                if text:
                    values.append(text)
        else:
            text = _safe_text(node)
            if text:
                values.append(text)
    return values


def parse_resume_html(html: str, url: str) -> dict:
    """
    CONTRACT (не менять):
      - На вход подается HTML страницы резюме (строка) и исходный URL.
      - Функция возвращает словарь с фиксированными ключами:
        {
            "url": str,                         # входной URL резюме
            "title": str | None,                # заголовок/позиция
            "full_name": str | None,            # имя кандидата
            "age_years": int | None,            # возраст в годах
            "city": str | None,                 # город проживания
            "ready_to_relocate": bool | None,   # готовность к переезду
            "salary_amount": int | None,        # ожидаемая зарплата числом
            "salary_currency": str | None,      # валюта зарплаты (UAH/USD/EUR/...)
            "summary": str | None,              # блок "О себе"/summary
            "skills": list[str],                # навыки/скиллы
            "languages": list[str],             # знание языков
            "experience_years": int | None,     # общий опыт в годах
            "experience_months": int | None,    # оставшиеся месяцы опыта
            "experience": list[dict],           # подробные записи опыта
            "education": list[dict],            # образование/курсы
        }
      - experience каждый элемент:
        {
            "period": str | None,           # период работы (как в тексте)
            "duration_months": int | None,  # длительность в месяцах если удалось вычислить
            "company": str | None,          # компания
            "position": str | None,         # должность
            "description": str | None,      # описание обязанностей
        }
      - education каждый элемент:
        {
            "period": str | None,        # период обучения
            "institution": str | None,   # учебное заведение
            "degree": str | None,        # специальность/степень
            "description": str | None,   # дополнительное описание
        }
      - Если что-то не удалось распарсить, соответствующее значение None/пустой список.
      - Функция не должна выбрасывать исключения при ошибках парсинга.
    """
    result = {
        "url": url,
        "title": None,
        "full_name": None,
        "age_years": None,
        "city": None,
        "ready_to_relocate": None,
        "salary_amount": None,
        "salary_currency": None,
        "summary": None,
        "skills": [],
        "languages": [],
        "experience_years": None,
        "experience_months": None,
        "experience": [],
        "education": [],
    }

    try:
        if not html:
            return result

        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.find("h1")
        if title_tag:
            result["title"] = _safe_text(title_tag)

        name_tag = soup.find(attrs={"itemprop": "name"}) or soup.find("h2")
        if name_tag:
            result["full_name"] = _safe_text(name_tag)

        meta_title = soup.find("title")
        salary_amount = None
        salary_currency = None
        if meta_title and meta_title.text:
            salary_amount, salary_currency = _parse_salary(meta_title.text)
        if salary_amount is None or salary_currency is None:
            salary_text_candidates = []
            for cls in ["salary", "resume-salary", "expected-salary"]:
                tag = soup.find(attrs={"class": lambda c: c and cls in c})
                if tag:
                    salary_text_candidates.append(tag.get_text(" ", strip=True))
            for text in salary_text_candidates:
                amount, currency = _parse_salary(text)
                if amount is not None:
                    salary_amount = amount
                    salary_currency = currency
                    break
        result["salary_amount"] = salary_amount
        result["salary_currency"] = salary_currency

        header_text_parts = []
        for tag in soup.find_all(["h1", "h2", "p", "span"], limit=20):
            text = _safe_text(tag)
            if text:
                header_text_parts.append(text)
        header_text = " • ".join(header_text_parts)

        age, city, relocation = _parse_age_and_city(header_text)
        result["age_years"] = age
        result["city"] = city
        result["ready_to_relocate"] = relocation

        experience_header = _find_heading(soup, ["опыт работы", "досвід роботи", "experience"])
        experience_content = _section_content(experience_header)
        result["experience"] = _parse_experience(experience_content)

        education_header = _find_heading(soup, ["образование", "освіта", "education"])
        education_content = _section_content(education_header)
        result["education"] = _parse_education(education_content)

        skills_header = _find_heading(soup, ["навыки", "навички", "skills"])
        skills_content = _section_content(skills_header)
        result["skills"] = _parse_list_section(skills_content)

        languages_header = _find_heading(soup, ["языки", "мови", "languages"])
        languages_content = _section_content(languages_header)
        result["languages"] = _parse_list_section(languages_content)

        summary_header = _find_heading(soup, ["о себе", "про себе", "about"])
        summary_content = _section_content(summary_header)
        if summary_content:
            summary_texts = [text for _, text in summary_content]
            result["summary"] = _clean_text(" ".join(summary_texts)) if summary_texts else None

        experience_years, experience_months = _parse_duration(header_text)
        result["experience_years"] = experience_years
        result["experience_months"] = experience_months

    except Exception:
        return result

    return result
