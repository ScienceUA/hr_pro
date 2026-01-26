import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("hr_pro.main")

# Импорты (запускать из корня проекта: poetry run python main.py ...)
from app.transport.fetcher import SmartFetcher
from app.storage.repository import JsonlRepository
from app.services.crawler import CrawlerService


JsonValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]


def load_workua_filters_map() -> Dict[str, Any]:
    """
    Загружает справочник фильтров Work.ua для валидации params.
    Источник истины: app/config/workua_filters_map.json
    """
    map_path = Path(__file__).parent / "app" / "config" / "workua_filters_map.json"
    if not map_path.exists():
        raise FileNotFoundError(f"workua_filters_map.json not found at: {map_path}")
    return json.loads(map_path.read_text(encoding="utf-8"))


def build_allowed_params_index(filters_map: Dict[str, Any]) -> Dict[str, Set[Any]]:
    """
    Собирает индекс допустимых параметров:
      - key: param name (например "experience", "language", "language_level", "agefrom", "ageto", "student")
      - value: множество допустимых значений (id/value), если применимо
    Для agefrom/ageto значения валидируются диапазоном отдельно.
    Для language_level: допустимы пары (language_id, level_id).
    """
    allowed: Dict[str, Set[Any]] = {}

    # age (range)
    age = filters_map.get("age", {})
    if isinstance(age, dict):
        for k in ("from_min", "to_max"):
            entry = age.get(k, {})
            if isinstance(entry, dict) and "param" in entry:
                allowed.setdefault(entry["param"], set())  # значения проверим диапазоном

    # lists: experience, education, gender, languages, extra_flags, categories
    for section_name in ("experience", "education", "gender"):
        section = filters_map.get(section_name, [])
        if isinstance(section, list):
            for item in section:
                param = item.get("param")
                val = item.get("id")
                if param and val is not None:
                    allowed.setdefault(param, set()).add(val)

    # languages (language + language_level)
    languages = filters_map.get("languages", [])
    if isinstance(languages, list):
        for lang in languages:
            lang_id = lang.get("id")
            param_lang = lang.get("param")  # usually "language"
            if param_lang and lang_id is not None:
                allowed.setdefault(param_lang, set()).add(lang_id)

            # levels
            for lvl in lang.get("levels", []) or []:
                param_level = lvl.get("param_level")  # usually "language_level"
                language_id = lvl.get("language_id")
                level_id = lvl.get("level_id")
                if param_level and language_id is not None and level_id is not None:
                    allowed.setdefault(param_level, set()).add((language_id, level_id))

    # extra flags (student/photo/disability/veteran)
    extra_flags = filters_map.get("extra_flags", [])
    if isinstance(extra_flags, list):
        for f in extra_flags:
            param = f.get("param")
            val = f.get("value")
            if param and val is not None:
                allowed.setdefault(param, set()).add(val)

    # categories + location в вашем map.json выражены base_url, а не query param
    # Поэтому они НЕ добавляются в allowed для params (пока UrlBuilder их не поддерживает как params).
    # (Это честное ограничение текущего UrlBuilder.)

    return allowed


def parse_params_from_args(args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    """
    Разбирает params из --params (JSON string) или --params-file (path).
    Возвращает dict или None.
    """
    if args.params and args.params_file:
        raise ValueError("Use only one of --params or --params-file")

    if args.params:
        try:
            data = json.loads(args.params)
        except json.JSONDecodeError as e:
            raise ValueError(f"--params must be valid JSON. Error: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("--params must be a JSON object (dictionary)")
        return data

    if args.params_file:
        p = Path(args.params_file)
        if not p.exists():
            raise FileNotFoundError(f"--params-file not found: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("--params-file must contain a JSON object (dictionary)")
        return data

    return None


def validate_params(params: Dict[str, Any], filters_map: Dict[str, Any]) -> None:
    """
    Валидирует:
      - ключи params существуют в workua_filters_map.json (как query params)
      - значения имеют корректный тип и допустимы по справочникам
    """
    index = build_allowed_params_index(filters_map)

    # age range bounds
    age = filters_map.get("age", {})
    age_from_min = None
    age_to_max = None
    if isinstance(age, dict):
        if isinstance(age.get("from_min"), dict):
            age_from_min = age["from_min"].get("value")
            agefrom_param = age["from_min"].get("param", "agefrom")
        else:
            agefrom_param = "agefrom"

        if isinstance(age.get("to_max"), dict):
            age_to_max = age["to_max"].get("value")
            ageto_param = age["to_max"].get("param", "ageto")
        else:
            ageto_param = "ageto"
    else:
        agefrom_param = "agefrom"
        ageto_param = "ageto"

    allowed_keys = set(index.keys())

    # Проверка ключей
    unknown_keys = [k for k in params.keys() if k not in allowed_keys]
    if unknown_keys:
        raise ValueError(
            "Unknown params keys (not supported by workua_filters_map.json / UrlBuilder params): "
            + ", ".join(sorted(unknown_keys))
        )

    # Проверка значений
    for key, value in params.items():
        # agefrom/ageto: scalar int
        if key in (agefrom_param, ageto_param):
            if not isinstance(value, int):
                raise ValueError(f"Param '{key}' must be int, got {type(value).__name__}")
            if key == agefrom_param and age_from_min is not None and value < int(age_from_min):
                raise ValueError(f"Param '{key}' must be >= {age_from_min}, got {value}")
            if key == ageto_param and age_to_max is not None and value > int(age_to_max):
                raise ValueError(f"Param '{key}' must be <= {age_to_max}, got {value}")
            continue

        allowed_vals = index.get(key, set())

        # flags: expect scalar 1
        if all(isinstance(v, int) for v in allowed_vals) and allowed_vals == {1}:
            if value != 1:
                raise ValueError(f"Param '{key}' must be 1, got {value}")
            continue

        # language_level: list of tuples (language_id, level_id) or a single tuple
        if any(isinstance(v, tuple) for v in allowed_vals):
            tuples: List[Tuple[int, int]] = []
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(x, int) for x in item):
                        tuples.append((int(item[0]), int(item[1])))
                    else:
                        raise ValueError(
                            f"Param '{key}' must be list of [language_id, level_id] pairs. Bad item: {item}"
                        )
            elif isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(x, int) for x in value):
                tuples.append((int(value[0]), int(value[1])))
            else:
                raise ValueError(
                    f"Param '{key}' must be list of pairs or a single pair (language_id, level_id). Got: {value}"
                )

            for t in tuples:
                if t not in allowed_vals:
                    raise ValueError(f"Param '{key}' contains unsupported pair {t}")
            continue

        # standard id-based params: allow scalar int or list[int]
        if isinstance(value, int):
            if value not in allowed_vals:
                raise ValueError(f"Param '{key}' contains unsupported value {value}")
        elif isinstance(value, list):
            for item in value:
                if not isinstance(item, int):
                    raise ValueError(f"Param '{key}' must be list[int]. Bad item: {item}")
                if item not in allowed_vals:
                    raise ValueError(f"Param '{key}' contains unsupported value {item}")
        else:
            raise ValueError(
                f"Param '{key}' must be int or list[int] (or list of pairs for language_level). Got {type(value).__name__}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="HR Pro Crawler MVP (extended params support)")

    parser.add_argument("--query", type=str, required=True, help="Search query (e.g. 'Python')")
    parser.add_argument("--city", type=str, default="", help="City (e.g. 'Kyiv')")
    parser.add_argument("--pages", type=int, default=1, help="Max SERP pages to crawl")
    parser.add_argument("--out", type=str, default="candidates.jsonl", help="Output file path")

    # NEW: params support (JSON)
    parser.add_argument(
        "--params",
        type=str,
        default="",
        help='JSON object string with Work.ua params. Example: \'{"experience":[165],"language":[1]}\'',
    )
    parser.add_argument(
        "--params-file",
        type=str,
        default="",
        help="Path to JSON file with Work.ua params (same structure as --params).",
    )
    parser.add_argument(
        "--no-validate-params",
        action="store_true",
        help="Disable validation against app/config/workua_filters_map.json",
    )

    args = parser.parse_args()

    # 1) Parse params
    params: Optional[Dict[str, Any]] = None
    try:
        params = parse_params_from_args(args)
    except Exception as e:
        print(f"\n❌ Params parsing error: {e}")
        sys.exit(2)

    # 2) Validate params (optional)
    if params and not args.no_validate_params:
        try:
            filters_map = load_workua_filters_map()
            validate_params(params, filters_map)
        except Exception as e:
            print(f"\n❌ Params validation error: {e}")
            sys.exit(2)

    # 3) Init components
    print("🔧 Initializing Crawler...")
    fetcher = SmartFetcher()
    repo = JsonlRepository(args.out)
    service = CrawlerService(fetcher, repo)

    # 4) Run
    print(f"🏃 Starting crawl for query: '{args.query}' in '{args.city}'")
    if params:
        print(f"🧩 Using params: {json.dumps(params, ensure_ascii=False)}")

    try:
        stats = service.run(
            query=args.query,
            city=args.city,
            params=params,
            max_pages=args.pages,
        )

        print("\n" + "=" * 40)
        print("🏁 CRAWL FINISHED")
        print(f"   Reason: {stats.stop_reason or 'Completed'}")
        print(f"   Pages Processed:  {stats.pages_processed}")
        print(f"   Candidates Found: {stats.candidates_found}")
        print(f"   Candidates New:   {stats.candidates_new}")
        print(f"   Candidates Saved: {stats.candidates_saved}")
        print(f"   Errors (SERP):    {stats.errors_serp}")
        print(f"   Errors (Detail):  {stats.errors_detail}")
        print(f"📁 Data saved to: {args.out}")
        print("=" * 40)

    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user. Data saved safely.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
