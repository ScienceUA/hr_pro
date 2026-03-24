from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from app.services.llm_client import real_llm_chat # Підключаємо LLM для аналізу критеріїв

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKUA_MAP_PATH = PROJECT_ROOT / "app" / "config" / "workua_filters_map.json"

SOURCE_MAP = {
    "work": "workua",
    "rabota": "rabotaua",
    "linkedin": "linkedin"
}
NEGATION_WORDS = ["кроме", "без", "не"]

def interpret_query(user_text: str) -> dict:
    user_text = (user_text or "").strip()
    if not user_text:
        raise ValueError("interpret_query: empty user_text")

    # 0) Витягуємо direct_url, якщо користувач передав посилання на один із підтримуваних сайтів
    # Підтримуємо: work.ua, happymonday.ua, djinni.co, robota.ua, ua.jooble.org
    url_match = re.search(r"(https?://(?:www\.)?(?:work\.ua/resumes|happymonday\.ua|djinni\.co|robota\.ua|ua\.jooble\.org)[^\s]*)", user_text)
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
    experience_code = None
    experience_patterns = [
        (r"понад 5|більше 5|5\+|6\+|7\+", "166"),     # Понад 5 років
        (r"від 2 до 5|2-5|3-5|4-5", "165"),            # Від 2 до 5 років
        (r"від 1 до 2|1-2", "164"),                    # Від 1 до 2 років
        (r"до 1|менше 1|0-1", "1"),                    # До 1 року
        (r"без досвіду|немає досвіду", "0"),          # Без досвіду
    ]
    
    for pattern, code in experience_patterns:
        if re.search(pattern, user_text, re.IGNORECASE):
            experience_code = code
            query_text = re.sub(pattern, "", query_text, flags=re.IGNORECASE).strip()
            break
    
    query_text = re.sub(r"\s+", " ", query_text).strip()

    # 4) Extract role keywords for Work.ua search
    # Work.ua НЕ має фільтру "категорія резюме" — тільки ключові слова
    # Витягуємо перші 2-3 ключові слова як пошуковий запит
    
    tokens = query_text.lower().split()
    
    # Видаляємо стоп-слова (службові слова)
    stop_words = {"з", "по", "для", "та", "і", "в", "на", "у", "роботи", "досвід", "років", "роки", "рік"}
    keywords = [t for t in tokens if t not in stop_words and len(t) > 2]
    
    # Беремо перші 2-3 ключові слова для пошуку
    search_keywords = keywords[:3] if len(keywords) >= 3 else keywords[:2] if len(keywords) >= 2 else keywords
    
    # Все інше — семантичні критерії для LLM
    semantic_keywords = keywords[len(search_keywords):]
    
    search_query = " ".join(search_keywords)
    semantic_criteria = semantic_keywords

    # 5) Build CriteriaBundle: інтелектуальний поділ на обов'язкові (must) та бажані (semantic) критерії
    extraction_prompt = (
        "Проаналізуй повний текст вакансії.\n"
        "Поверни ТІЛЬКИ валідний JSON у форматі:\n"
        "{\n"
        '  "role": "коротка назва посади для пошуку (наприклад: Менеджер ЗЕД)",\n'
        '  "experience_id": 165,\n'
        '  "must": ["обов\'язкові вимоги"],\n'
        '  "semantic": ["бажані вимоги"]\n'
        "}\n"
        "ПРАВИЛА ДЛЯ experience_id: 0 (без досвіду), 1 (до 1 року), 164 (від 1 до 2 років), 165 (від 2 до 5 років), 166 (понад 5 років). Якщо не вказано, пиши null.\n"
        "Ніякого markdown чи іншого тексту."
    )
    
    try:
        llm_response = real_llm_chat([
            {"role": "system", "content": extraction_prompt},
            {"role": "user", "content": user_text}
        ])
        # Очищення від можливих markdown-тегів
        clean_json_str = llm_response.strip('` \n').replace('json\n', '')
        parsed_criteria = json.loads(clean_json_str)
    except Exception as e:
        # Fallback, якщо LLM не відповів коректно або виникла помилка
        parsed_criteria = {
            "role": query_text,
            "must": [],
            "semantic": [user_text]
        }

    criteria_bundle: Dict[str, Any] = {
        "must": parsed_criteria.get("must", []),
        "must_not": [],
        "semantic": parsed_criteria.get("semantic", []),
        "role_anchors": [parsed_criteria.get("role", "")],
        "uncertainties": [],
        "source_query": user_text,
    }

    # Оновлюємо query_text для Work.ua ТІЛЬКИ роллю, щоб краулер шукав точно
    query_text = parsed_criteria.get("role", query_text)
    search_query = query_text

    # 5.1) Фільтрація джерел на основі запиту користувача
    text_lower = user_text.lower()
    active_sources = list(SOURCE_MAP.values())
    mentioned_sources = []

    for keyword, source_id in SOURCE_MAP.items():
        if keyword in text_lower:
            start_idx = text_lower.find(keyword)
            # Перевіряємо 10 символів перед знайденим словом на наявність заперечень
            prefix = text_lower[max(0, start_idx-10):start_idx]
            is_negated = any(neg in prefix for neg in NEGATION_WORDS)
            
            if is_negated:
                if source_id in active_sources:
                    active_sources.remove(source_id)
            else:
                mentioned_sources.append(source_id)

    # Якщо користувач прямо вказав конкретні сайти (і не відмінив їх), залишаємо тільки їх
    if mentioned_sources:
        active_sources = [s for s in mentioned_sources if s in active_sources]

    # 6) Build Search payload
    search_payload: Dict[str, Any] = {
        "query": search_query,
        "city": city_slug,
        "pages": 5,
        "out": "result.jsonl",
        "params": {},
        "allowed_sources": active_sources,
    }

    exp_id = parsed_criteria.get("experience_id")
    if exp_id is not None:
        search_payload["params"]["experience"] = [int(exp_id)]

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


def _extract_query_and_city(user_text: str, workua_map: Optional[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """
    Heuristic:
      - Split into tokens
      - If last token matches a known city slug (from map) OR common city name patterns -> treat as city
      - Otherwise: no city
    """
    # Normalize whitespace
    clean = re.sub(r"\s+", " ", user_text).strip()
    tokens = clean.split(" ")
    if not tokens:
        return "", None

    # Candidate city token: last token
    last = tokens[-1].strip().lower()

    known_city_slug = _match_city_slug(last, workua_map)
    if known_city_slug:
        query_text = " ".join(tokens[:-1]).strip()
        return query_text, known_city_slug

    # Also support pattern "City:kyiv" or "city=kyiv"
    m = re.search(r"(?:city\s*[:=]\s*)([a-z0-9_-]+)$", clean, flags=re.IGNORECASE)
    if m:
        cand = m.group(1).strip().lower()
        known_city_slug = _match_city_slug(cand, workua_map)
        if known_city_slug:
            query_text = re.sub(r"(?:city\s*[:=]\s*)([a-z0-9_-]+)$", "", clean, flags=re.IGNORECASE).strip()
            return query_text, known_city_slug

    # No city detected
    return clean, None


def _match_city_slug(candidate: str, workua_map: Optional[Dict[str, Any]]) -> Optional[str]:
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
            if isinstance(item, dict) and str(item.get("slug", "")).lower() == candidate:
                return candidate

    # Case B: dict of slugs -> ...
    if isinstance(location, dict) and candidate in {str(k).lower() for k in location.keys()}:
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
