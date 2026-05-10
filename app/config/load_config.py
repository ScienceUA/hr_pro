import json
from pathlib import Path
from typing import Dict, List, Set


def load_unified_filters(config_dir: str = "app/config") -> Dict[str, List[str]]:
    """
    Динамічно сканує всі файли *_filters_map.json і створює єдиний довідник
    доступних критеріїв (об'єднання унікальних значень з усіх джерел).
    """
    base_path = Path(config_dir)

    # Використовуємо множини (set) для автоматичного видалення дублікатів
    unified_filters: Dict[str, Set[str]] = {
        "cities": set(),
        "experience_years": set(),
        "employment": set(),
        "education_level": set(),
        "languages": set(),
    }

    # Знаходимо всі файли карт фільтрів (workua, robotaua і будь-які майбутні)
    for map_file in base_path.glob("*_filters_map.json"):
        try:
            with open(map_file, "r", encoding="utf-8") as f:
                data = json.load(f)

                # Об'єднуємо ключі з кожного файлу.
                # Очікувана структура JSON: {"cities": {"Київ": 115, "Львів": 116}, ...}
                for category in unified_filters.keys():
                    if category in data and isinstance(data[category], dict):
                        # Додаємо тільки текстові назви (ключі), ID нам тут не потрібні
                        unified_filters[category].update(data[category].keys())
        except Exception as e:
            print(f"Помилка читання файлу {map_file.name}: {e}")

    # Конвертуємо множини назад у відсортовані списки для стабільної видачі ШІ
    return {k: sorted(list(v)) for k, v in unified_filters.items()}


def get_prompt_filters_text() -> str:
    """
    Формує готовий текстовий блок довідника для вставки в системний промпт ШІ.
    """
    filters = load_unified_filters()
    text_lines = ["Доступні стандартизовані критерії для пошуку:"]

    for category, items in filters.items():
        if items:
            items_str = ", ".join(items)
            text_lines.append(f"- {category}: [{items_str}]")

    return "\n".join(text_lines)
