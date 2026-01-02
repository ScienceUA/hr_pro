# CONTRACT (не менять):
# parse_resume_html(html: str, url: str) -> dict
# Возвращает словарь с ключами:
#   source_url: str
#   workua_id: str | None
#   full_name: str | None
#   position: str | None
#   location: str | None
#   age: int | None
#   gender: str | None
#   salary: dict {amount: int | None, currency: str | None, period: str | None}
#   experience_years: int | None
#   experience_items: list[dict]
#   education: list[dict]
#   skills: list[str]
#   about: str | None
#   raw_sections: dict[str, str]
# При ошибках парсинга возвращает значения None/пустые коллекции, не делает HTTP запросов и ничего не печатает.

import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _safe_text(node) -> Optional[str]:
    if not node:
        return None
    return _clean_text(node.get_text(" ", strip=True))


def _extract_workua_id(url: str) -> Optional[str]:
    match = re.search(r"/resumes/(\d+)", url)
    return match.group(1) if match else None


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


def _parse_age_and_gender(text: str) -> Tuple[Optional[int], Optional[str]]:
    age_match = re.search(
        r"(\d{2})\s*(?:рок(?:ів|и)?|years?|лет|года?)",
        text,
        flags=re.IGNORECASE,
    )
    age = int(age_match.group(1)) if age_match else None

    gender = None
    gender_map = {
        "мужчина": "male",
        "чоловік": "male",
        "женщина": "female",
        "жінка": "female",
    }
    lowered = text.lower()
    for marker, normalized in gender_map.items():
        if marker in lowered:
            gender = normalized
            break

    return age, gender


def _parse_salary(text: str) -> Dict[str, Optional[str]]:
    amount = None
    currency = None
    period = None

    salary_match = re.search(
        r"([\d\s]+)\s*(грн|uah|₴|usd|\$|eur|€|руб|₽)",
        text,
        flags=re.IGNORECASE,
    )
    if salary_match:
        raw_amount = salary_match.group(1).replace(" ", "")
        try:
            amount = int(raw_amount)
        except Exception:
            amount = None
        currency = (
            salary_match.group(2)
            .upper()
            .replace("₴", "UAH")
            .replace("$", "USD")
            .replace("€", "EUR")
        )

    period_match = re.search(r"(час|день|мес|мiсяц|month|год|year)", text, flags=re.IGNORECASE)
    if period_match:
        token = period_match.group(1).lower()
        if token.startswith(("мес", "мiсяц", "month")):
            period = "month"
        elif token.startswith(("год", "year")):
            period = "year"
        elif token.startswith(("день", "day")):
            period = "day"
        elif token.startswith("час"):
            period = "hour"

    return {"amount": amount, "currency": currency, "period": period}


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
        if len(text) < 3:
            continue

        period = None
        company = None
        position = None
        description = None
        duration_months = None

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
        if years is not None or months is not None:
            duration_months = (years or 0) * 12 + (months or 0)

        description_paragraphs = [p.get_text(" ", strip=True) for p in node.find_all("p")]
        if description_paragraphs:
            description = _clean_text(" ".join(description_paragraphs))
        else:
            description = text

        experiences.append(
            {
                "period": period,
                "company": company,
                "position": position,
                "duration_months": duration_months,
                "description": description,
            }
        )
    return experiences


def _parse_education(section_contents):
    education = []
    for node, text in section_contents:
        if len(text) < 3:
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


def _collect_raw_sections(soup: BeautifulSoup) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    for heading in soup.find_all(["h2", "h3"]):
        title = _safe_text(heading)
        if not title:
            continue
        content_parts = []
        for sibling in heading.find_all_next():
            if sibling.name in {"h1", "h2", "h3"}:
                break
            text = _safe_text(sibling)
            if text:
                content_parts.append(text)
        sections[title] = _clean_text(" ".join(content_parts)) if content_parts else ""
    return sections


def _parse_location(text: str) -> Optional[str]:
    parts = [part.strip() for part in re.split(r"[•\|·]", text) if part.strip()]
    if parts:
        return parts[-1]
    return None


def parse_resume_html(html: str, url: str) -> dict:
    """
    Возвращает словарь со структурой, описанной в контракте выше:
    source_url, workua_id, full_name, position, location, age, gender, salary (amount, currency, period),
    experience_years, experience_items, education, skills, about, raw_sections.
    При любых ошибках парсинга значения остаются None или пустыми коллекциями.
    """
    result = {
        "source_url": url,
        "workua_id": _extract_workua_id(url),
        "full_name": None,
        "position": None,
        "location": None,
        "age": None,
        "gender": None,
        "salary": {"amount": None, "currency": None, "period": None},
        "experience_years": None,
        "experience_items": [],
        "education": [],
        "skills": [],
        "about": None,
        "raw_sections": {},
    }

    try:
        if not html:
            return result

        soup = BeautifulSoup(html, "html.parser")

        position_tag = soup.find("h1")
        if position_tag:
            result["position"] = _safe_text(position_tag)

        name_tag = soup.find(attrs={"itemprop": "name"}) or soup.find("h2")
        if name_tag:
            result["full_name"] = _safe_text(name_tag)

        meta_title = soup.find("title")
        header_candidates = []
        if meta_title and meta_title.text:
            header_candidates.append(meta_title.text)
        header_candidates.extend(
            [_safe_text(tag) for tag in soup.find_all(["h1", "h2", "p", "span"], limit=20) if _safe_text(tag)]
        )
        header_text = " • ".join([part for part in header_candidates if part])

        age, gender = _parse_age_and_gender(header_text)
        result["age"] = age
        result["gender"] = gender
        result["location"] = _parse_location(header_text)

        salary_texts = []
        if meta_title and meta_title.text:
            salary_texts.append(meta_title.text)
        for cls in ["salary", "resume-salary", "expected-salary", "js-resume-salary"]:
            tag = soup.find(attrs={"class": lambda c: c and cls in c})
            if tag:
                salary_texts.append(tag.get_text(" ", strip=True))
        for text in salary_texts:
            parsed_salary = _parse_salary(text)
            if any(parsed_salary.values()):
                result["salary"] = parsed_salary
                break

        experience_header = _find_heading(soup, ["опыт работы", "досвід роботи", "experience"])
        experience_content = _section_content(experience_header)
        result["experience_items"] = _parse_experience(experience_content)

        total_years, _ = _parse_duration(header_text)
        result["experience_years"] = total_years

        education_header = _find_heading(soup, ["образование", "освіта", "education"])
        education_content = _section_content(education_header)
        result["education"] = _parse_education(education_content)

        skills_header = _find_heading(soup, ["навыки", "навички", "skills"])
        skills_content = _section_content(skills_header)
        result["skills"] = _parse_list_section(skills_content)

        about_header = _find_heading(soup, ["о себе", "про себе", "about"])
        about_content = _section_content(about_header)
        if about_content:
            about_texts = [text for _, text in about_content]
            result["about"] = _clean_text(" ".join(about_texts)) if about_texts else None

        result["raw_sections"] = _collect_raw_sections(soup)

    except Exception:
        return result

    return result
