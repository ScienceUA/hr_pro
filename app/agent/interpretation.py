from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from app.services.llm_client import real_llm_chat # Підключаємо LLM для аналізу критеріїв

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKUA_MAP_PATH = PROJECT_ROOT / "app" / "config" / "workua_filters_map.json"


def interpret_query(user_text: str) -> dict:
    user_text = (user_text or "").strip()
    if not user_text:
        raise ValueError("interpret_query: empty user_text")

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
        "Проаналізуй повний текст вакансії та чітко розділи вимоги.\n"
        "Поверни ТІЛЬКИ валідний JSON у форматі:\n"
        "{\n"
        '  "role": "коротка назва посади для пошуку на Work.ua (1-3 слова)",\n'
        '  "must": ["список ТІЛЬКИ обов\'язкових вимог (must-have, вимагається, обов\'язково, від X років)"],\n'
        '  "semantic": ["список бажаних вимог (буде плюсом, бажано, вітається)"]\n'
        "}\n"
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
            "role": matched_category if matched_category else query_text,
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

    # 6) Build Search payload
    search_payload: Dict[str, Any] = {
        "query": search_query,
        "city": city_slug,
        "pages": 3,
        "out": "result.jsonl",
        "params": {},
    }
    
    if experience_code:
        search_payload["params"]["experience"] = experience_code

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
