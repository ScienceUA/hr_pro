from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
from pydantic import BaseModel, Field
from app.services.llm_client import (
    real_llm_chat,
)  # Підключаємо LLM для аналізу критеріїв

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKUA_MAP_PATH = PROJECT_ROOT / "app" / "config" / "workua_filters_map.json"

SOURCE_MAP = {"work": "workua", "robota": "robotaua", "linkedin": "linkedin"}


class SearchPayload(BaseModel):
    """Суворий контракт даних для всіх джерел (Work, robota, LinkedIn)"""

    query: str
    city: str = "ukraine"
    allowed_sources: List[str] = ["workua", "robotaua", "linkedin"]  # Додано linkedin
    age_from: Optional[int] = None
    age_to: Optional[int] = None
    gender: Optional[str] = None  # "male", "female"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    days: Optional[int] = None  # Кількість днів пошуку
    category: Optional[str] = None  # "it", "hr" тощо
    experience_label: Optional[str] = None  # "no_experience", "1-2_years" тощо
    languages: List[str] = Field(default_factory=list)  # Список мов
    employment: Optional[str] = None  # full_time, part_time тощо
    education: Optional[str] = None  # higher, secondary тощо
    with_photo: bool = False
    with_file: bool = False
    only_disabled: bool = False
    only_students: bool = False
    # --- Обмеження видачі ---
    limit: Optional[int] = None
    limit_per_source: bool = False


NEGATION_WORDS = ["кроме", "без", "не"]


def interpret_query(user_text: str) -> dict:
    user_text = (user_text or "").strip()
    if not user_text:
        raise ValueError("interpret_query: empty user_text")

    # 0) Витягуємо direct_url, якщо користувач передав посилання на один із підтримуваних сайтів
    # Підтримуємо: work.ua, happymonday.ua, djinni.co, robota.ua, ua.jooble.org
    url_match = re.search(
        r"(https?://(?:www\.)?(?:work\.ua/resumes|happymonday\.ua|djinni\.co|robota\.ua|ua\.jooble\.org)[^\s]*)",
        user_text,
    )
    direct_url = None
    if url_match:
        direct_url = url_match.group(1).strip()
        # Видаляємо URL з тексту, щоб не заважати LLM аналізувати критерії
        user_text = user_text.replace(direct_url, "").strip()
        # Якщо крім посилання нічого не було, даємо базовий контекст
        if not user_text:
            user_text = "Аналіз кандидатів за посиланням"

    # 1) Load Work.ua map
    workua_map = _try_load_workua_map()

    # 2) Parse (query, city)
    query_text, city_slug = _extract_query_and_city(user_text, workua_map)

    # 3) Extract experience from query
    experience_label_hint = None
    experience_patterns = [
        (r"понад 10|більше 10|10\+", "more_10_years"),
        (r"від 5 до 10|5-10", "5-10_years"),
        (r"від 2 до 5|2-5|від 2 років|2\+\s*рок", "2-5_years"),
        (r"від 1 до 2|1-2", "1-2_years"),
        (r"до 1|менше 1|0-1", "under_1_year"),
        (r"без досвіду|немає досвіду", "no_experience"),
    ]

    for pattern, label in experience_patterns:
        if re.search(pattern, user_text, re.IGNORECASE):
            experience_label_hint = label
            query_text = re.sub(pattern, "", query_text, flags=re.IGNORECASE).strip()
            break

    query_text = re.sub(r"\s+", " ", query_text).strip()

    # 4) Extract role keywords for Work.ua search
    # Work.ua НЕ має фільтру "категорія резюме" — тільки ключові слова
    # Витягуємо перші 2-3 ключові слова як пошуковий запит

    tokens = query_text.lower().split()

    # Видаляємо стоп-слова (службові слова)
    stop_words = {
        "з",
        "по",
        "для",
        "та",
        "і",
        "в",
        "на",
        "у",
        "роботи",
        "досвід",
        "років",
        "роки",
        "рік",
    }
    keywords = [t for t in tokens if t not in stop_words and len(t) > 2]

    # Беремо перші 2-3 ключові слова для пошуку
    search_keywords = (
        keywords[:3]
        if len(keywords) >= 3
        else keywords[:2] if len(keywords) >= 2 else keywords
    )

    # Перші 2-3 ключових слова → пошуковий запит; решта враховується LLM через criteria_bundle
    search_query = " ".join(search_keywords)

    # 5) Build CriteriaBundle: інтелектуальний поділ на обов'язкові (must) та бажані (semantic) критерії
    extraction_prompt = (
        "Проаналізуй запит на пошук кандидатів та поверни JSON.\n"
        "Поля JSON:\n"
        "1. role: тільки назва ролі/посади для пошуку.\n"
        "2. age_from / age_to: числа або null.\n"
        "3. gender: male / female / null.\n"
        "4. salary_min / salary_max: числа або null.\n"
        "5. experience_label: one of no_experience, under_1_year, 1-2_years, 2-5_years, 5-10_years, more_10_years, null.\n"
        "6. days: число днів або null.\n"
        "7. category: коротка категорія, напр. it, hr, sales, null.\n"
        "8. employment: one of full_time, part_time, remote, project, shift, internship, seasonal, null.\n"
        "9. education: one of higher, incomplete_higher, secondary_special, secondary, null.\n"
        "10. languages: масив рядків.\n"
        "11. with_photo, with_file, only_disabled, only_students: true/false.\n"
        "12. internal_mandatory: список обов'язкових вимог (що кандидат точно повинен вміти/мати).\n"
        "13. desirable: список бажаних вимог (що буде плюсом).\n"
        "Поверни тільки JSON без markdown."
    )

    try:
        llm_response = real_llm_chat(
            [
                {"role": "system", "content": extraction_prompt},
                {"role": "user", "content": user_text},
            ]
        )
        clean_json_str = llm_response.strip("` \n").replace("json\n", "")
        parsed_criteria = json.loads(clean_json_str)
    except Exception:  # noqa: BLE001
        parsed_criteria = {
            "role": query_text,
            "internal_mandatory": [],
            "desirable": [user_text],
        }

    if experience_label_hint and not parsed_criteria.get("experience_label"):
        parsed_criteria["experience_label"] = experience_label_hint

    parsed_criteria.setdefault("category", None)
    parsed_criteria.setdefault("employment", None)
    parsed_criteria.setdefault("education", None)
    parsed_criteria.setdefault("languages", [])

    # Нова Тріо-модель
    criteria_bundle: Dict[str, Any] = {
        "internal_mandatory": parsed_criteria.get("internal_mandatory", []),
        "desirable": parsed_criteria.get("desirable", []),
        "role_anchors": [parsed_criteria.get("role", "")],
        "source_query": user_text,
    }

    # Оновлюємо query_text для Work.ua ТІЛЬКИ роллю, щоб краулер шукав точно
    query_text = parsed_criteria.get("role", query_text)
    search_query = query_text

    # 5.1) Фільтрація джерел на основі запиту користувача (Строга Формула)
    text_lower = user_text.lower()
    active_sources = list(SOURCE_MAP.values())  # За замовчуванням шукаємо скрізь

    # Шукаємо явну формулу: "шукати на [джерела]" або "джерела: [джерела]"
    formula_match = re.search(
        r"(?:шукати|пошук|джерела)[:\s]+(?:тільки\s+)?(?:на\s+)?([a-z\,\.\s]+)",
        text_lower,
    )

    if formula_match:
        formula_text = formula_match.group(1)
        explicit_sources = []
        for keyword, source_id in SOURCE_MAP.items():
            if keyword in formula_text:
                explicit_sources.append(source_id)

        if explicit_sources:
            active_sources = explicit_sources

    # Очищаємо фінальний запит (посаду) від можливого сміття з формули
    clean_query = parsed_criteria.get("role", search_query)
    for kw in SOURCE_MAP.keys():
        clean_query = re.sub(
            rf"(?i)(?:шукати|пошук|джерела)?[:\s]*(?:тільки\s+)?(?:на\s+)?{kw}(\.ua|\.com)?",
            "",
            clean_query,
        ).strip()

    # 6) Build Search payload (Валідація через Pydantic)
    payload_obj = SearchPayload(
        query=clean_query,
        city=city_slug or "ukraine",
        allowed_sources=active_sources,
        age_from=parsed_criteria.get("age_from"),
        age_to=parsed_criteria.get("age_to"),
        gender=parsed_criteria.get("gender"),
        salary_min=parsed_criteria.get("salary_min"),
        salary_max=parsed_criteria.get("salary_max"),
        days=parsed_criteria.get("days"),
        category=parsed_criteria.get("category"),
        experience_label=parsed_criteria.get("experience_label"),
        languages=parsed_criteria.get("languages", []),
        employment=parsed_criteria.get("employment"),
        education=parsed_criteria.get("education"),
        with_photo=parsed_criteria.get("with_photo", False),
        with_file=parsed_criteria.get("with_file", False),
        only_disabled=parsed_criteria.get("only_disabled", False),
        only_students=parsed_criteria.get("only_students", False),
        limit=None,
        limit_per_source=False,
    )

    # Конвертуємо в словник для адаптерів
    search_payload = payload_obj.model_dump()
    search_payload["pages"] = 100
    search_payload["out"] = "out/result.jsonl"
    search_payload["params"] = {}

    # Каскадний мапінг для Work.ua: включаємо цільовий досвід і всі вищі рівні
    # ID на Work.ua: 0 (без), 1 (до 1), 164 (1-2), 165 (2-5), 166 (5+)
    exp_cascade_work = {
        "no_experience": [0, 1, 164, 165, 166],
        "under_1_year": [1, 164, 165, 166],
        "1-2_years": [164, 165, 166],
        "2-5_years": [165, 166],
        "5-10_years": [166],
        "more_10_years": [166],
    }

    if payload_obj.experience_label in exp_cascade_work:
        search_payload["params"]["experience"] = exp_cascade_work[
            payload_obj.experience_label
        ]

    # Додаємо пряме посилання до payload, якщо воно є
    if direct_url:
        search_payload["direct_url"] = direct_url

    return {"criteria_bundle": criteria_bundle, "search_payload": search_payload}


# -------------------------
# Helpers
# -------------------------


def _try_load_workua_map() -> Optional[Dict[str, Any]]:
    if not WORKUA_MAP_PATH.exists():
        return None
    try:
        with WORKUA_MAP_PATH.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _extract_query_and_city(
    user_text: str, workua_map: Optional[Dict[str, Any]]
) -> Tuple[str, Optional[str]]:
    clean = re.sub(r"\s+", " ", user_text).strip()
    if not clean:
        return "", None

    city_aliases = {
        "київ": "kyiv",
        "києві": "kyiv",
        "киев": "kyiv",
        "львів": "lviv",
        "львові": "lviv",
        "львов": "lviv",
        "одеса": "odesa",
        "одесі": "odesa",
        "одесса": "odesa",
        "харків": "kharkiv",
        "харков": "kharkiv",
        "дніпро": "dnipro",
        "днепр": "dnipro",
    }

    text_lower = clean.lower()
    for alias, slug in city_aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", text_lower):
            query_text = re.sub(
                rf"\bу\s+{re.escape(alias)}\b|\bв\s+{re.escape(alias)}\b|\b{re.escape(alias)}\b",
                "",
                clean,
                flags=re.IGNORECASE,
            ).strip()
            query_text = re.sub(r"\s+", " ", query_text).strip()
            return query_text, slug

    tokens = clean.split(" ")
    last = tokens[-1].strip().lower()

    known_city_slug = _match_city_slug(last, workua_map)
    if known_city_slug:
        query_text = " ".join(tokens[:-1]).strip()
        return query_text, known_city_slug

    m = re.search(r"(?:city\s*[:=]\s*)([a-z0-9_-]+)$", clean, flags=re.IGNORECASE)
    if m:
        cand = m.group(1).strip().lower()
        known_city_slug = _match_city_slug(cand, workua_map)
        if known_city_slug:
            query_text = re.sub(
                r"(?:city\s*[:=]\s*)([a-z0-9_-]+)$", "", clean, flags=re.IGNORECASE
            ).strip()
            return query_text, known_city_slug

    return clean, None


def _match_city_slug(
    candidate: str, workua_map: Optional[Dict[str, Any]]
) -> Optional[str]:
    """
    Validate city slug against workua_filters_map.json if available.
    We only accept a city if it exists in map; otherwise return None.
    """
    if not candidate:
        return None

    if workua_map is None:
        # Without map we cannot validate slugs safely.
        # Return None to avoid inventing city slugs.
        return None

    # Try common structures:
    # - workua_map["location"]["values"]...
    # - workua_map["location"]...
    # We search any dict/list for {"slug": candidate} or direct key match.
    location = workua_map.get("location") if isinstance(workua_map, dict) else None
    if location is None:
        return None

    # Case A: dict with "values": [...]
    if isinstance(location, dict) and isinstance(location.get("values"), list):
        for item in location["values"]:
            if (
                isinstance(item, dict)
                and str(item.get("slug", "")).lower() == candidate
            ):
                return candidate

    # Case B: dict of slugs -> ...
    if isinstance(location, dict) and candidate in {
        str(k).lower() for k in location.keys()
    }:
        return candidate

    # Case C: nested search (best-effort)
    if _deep_contains_slug(location, candidate):
        return candidate

    return None


def _deep_contains_slug(obj: Any, slug: str) -> bool:
    if isinstance(obj, dict):
        if str(obj.get("slug", "")).lower() == slug:
            return True
        for v in obj.values():
            if _deep_contains_slug(v, slug):
                return True
    elif isinstance(obj, list):
        for x in obj:
            if _deep_contains_slug(x, slug):
                return True
    return False
