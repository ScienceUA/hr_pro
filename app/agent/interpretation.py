from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKUA_MAP_PATH = PROJECT_ROOT / "app" / "config" / "workua_filters_map.json"


def interpret_query(user_text: str) -> dict:
    """
    Runtime entrypoint for Stage 6.1 (Interpretation).

    MUST return:
      {
        "criteria_bundle": {...},
        "search_payload": {
            "query": str,
            "city": Optional[str],     # Work.ua city slug (e.g. "kyiv") if confidently detected
            "pages": int,
            "out": str,
            "params": dict             # raw Work.ua URL params
        }
      }

    Baseline behavior (safe, deterministic):
      - Extracts query text and (optionally) city slug from user_text.
      - Does NOT invent skills/criteria.
      - Does NOT apply filters unless explicitly detected and validated.
    """
    user_text = (user_text or "").strip()
    if not user_text:
        raise ValueError("interpret_query: empty user_text")

    # 1) Load Work.ua map if present (optional but preferred)
    workua_map = _try_load_workua_map()

    # 2) Parse (query, city)
    query_text, city_slug = _extract_query_and_city(user_text, workua_map)

    # 3) Build CriteriaBundle (baseline: only what is explicitly known)
    #    This keeps pipeline deterministic and avoids hallucination.
    criteria_bundle: Dict[str, Any] = {
        "must": [],
        "must_not": [],
        "semantic": [],
        "role_anchors": [query_text] if query_text else [],
        "uncertainties": [],
        "source_query": user_text,
    }

    if not query_text:
        criteria_bundle["uncertainties"].append("Could not extract query terms from user input.")

    # 4) Build Search payload (flat, CLI-compatible)
    #    params must be RAW Work.ua URL params.
    search_payload: Dict[str, Any] = {
        "query": query_text if query_text else user_text,
        "city": city_slug,
        "pages": 3,
        "out": "result.jsonl",
        "params": {},
    }

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
