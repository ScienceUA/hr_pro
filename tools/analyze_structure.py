# tools/analyze_structure.py
import sys
import re
from pathlib import Path
from typing import Optional, Iterable, Tuple, List

from bs4 import BeautifulSoup, Tag

# Определяем корень проекта (tools/ -> repo root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Входные/выходные пути
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "raw"
REPORT_PATH = PROJECT_ROOT / "tests" / "fixtures" / "structure_report.txt"

# Теги, внутри которых текст нам не нужен
SKIP_TEXT_PARENTS = {"script", "style", "meta", "noscript"}

# Ключевые слова для зарплаты
SALARY_KEYWORDS = ["грн", "uah", "$", "usd", "€", "eur"]


def _safe_get_attr(tag: Tag, attr: str) -> Optional[str]:
    """Безопасно возвращает строковый атрибут или None."""
    val = tag.get(attr)
    if val is None:
        return None
    if isinstance(val, list):
        # class обычно list[str]
        return " ".join(str(x) for x in val if x)
    return str(val)


def _pick_stable_class(classes: List[str]) -> Optional[str]:
    """
    Выбирает наиболее "стабильный" класс:
    - игнорируем слишком короткие/генерик/явно динамические
    - предпочитаем классы с буквами, без длинных чисел
    """
    if not classes:
        return None

    def score(cls: str) -> Tuple[int, int]:
        # меньше — лучше
        dynamic_penalty = 1 if re.search(r"\d{3,}", cls) else 0
        generic_penalty = 1 if cls in {"container", "row", "col", "card", "item"} else 0
        # предпочтение более "семантичным" (длиннее)
        length_penalty = -len(cls)
        return (dynamic_penalty + generic_penalty, length_penalty)

    filtered = []
    for c in classes:
        c = c.strip()
        if not c:
            continue
        if len(c) < 3:
            continue
        # отбрасываем заведомо служебные/динамические паттерны
        if c.startswith(("js-", "is-", "has-")):
            continue
        filtered.append(c)

    if not filtered:
        return None

    filtered.sort(key=score)
    return filtered[0]


def build_stable_selector(tag: Tag) -> str:
    """
    Строит стабильный селектор для одного элемента:
    приоритет: #id -> tag.stable_class -> tag
    """
    tag_name = tag.name if tag and tag.name else "*"

    tag_id = _safe_get_attr(tag, "id")
    if tag_id:
        # id обычно самый стабильный
        return f"{tag_name}#{tag_id}"

    cls_attr = tag.get("class") or []
    classes = [str(x) for x in cls_attr if x]
    stable_cls = _pick_stable_class(classes)
    if stable_cls:
        return f"{tag_name}.{stable_cls}"

    return tag_name


def build_selector_path(tag: Tag, max_depth: int = 4) -> str:
    """
    Строит путь селекторов "снизу вверх", ограничивая глубину.
    Использует стабильные селекторы на каждом уровне.
    """
    parts: List[str] = []
    cur = tag
    while cur and isinstance(cur, Tag) and cur.name != "[document]":
        parts.append(build_stable_selector(cur))
        cur = cur.parent  # type: ignore[assignment]
        if len(parts) >= max_depth:
            break
    parts.reverse()
    return " > ".join(parts)


def iter_text_nodes(soup: BeautifulSoup) -> Iterable[str]:
    """
    Итерирует текстовые ноды, исключая мусорные контейнеры.
    """
    for node in soup.find_all(string=True):
        text = str(node).strip()
        if not text:
            continue
        parent = getattr(node, "parent", None)
        if isinstance(parent, Tag) and parent.name in SKIP_TEXT_PARENTS:
            continue
        yield text


def analyze_one_file(filepath: Path, out) -> None:
    out.write(f"\n{'='*72}\nANALYZING: {filepath.name}\n{'='*72}\n")

    raw = filepath.read_bytes()

    try:
        soup = BeautifulSoup(raw, "lxml")
    except Exception as e:
        out.write(f"❌ PARSE ERROR (lxml): {e}\n")
        return

    # --- H1 ---
    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        out.write("[H1] Found: True\n")
        out.write(f"     Path: {build_selector_path(h1)}\n")
        out.write(f"     Text: {h1.get_text(strip=True)[:80]}\n")
    else:
        out.write("[H1] Found: False\n")

    # --- H2 ---
    h2s = soup.find_all("h2")
    out.write(f"[H2] Headers count: {len(h2s)}\n")
    for i, h2 in enumerate(h2s[:30], start=1):  # ограничение для отчёта
        if not isinstance(h2, Tag):
            continue
        text = h2.get_text(strip=True)
        if not text:
            continue
        out.write(f"     #{i}: '{text[:80]}'\n")
        out.write(f"         Path: {build_selector_path(h2)}\n")

    # --- Salary candidates ---
    out.write("[SALARY] Candidates:\n")
    found_any = False
    for text in iter_text_nodes(soup):
        low = text.lower()
        if any(k in low for k in SALARY_KEYWORDS):
            # найдём ближайший "смысловой" родитель-тег
            # пытаемся подняться до ближайшего блочного контейнера
            found_any = True
            # восстановим Tag из текста через поиск: берём первый match в дереве
            node = soup.find(string=lambda s: s and str(s).strip() == text)
            parent = getattr(node, "parent", None)
            if not isinstance(parent, Tag):
                continue

            # поднимаемся на 1-2 уровня, если попали в span/i
            container = parent
            for _ in range(2):
                if isinstance(container, Tag) and container.name in {"span", "i", "b", "strong"} and isinstance(container.parent, Tag):
                    container = container.parent
            out.write(f"     Text: {text[:120]}\n")
            out.write(f"     Path: {build_selector_path(container)}\n")

    if not found_any:
        out.write("     NOT FOUND\n")

    # --- SERP links ---
    links = soup.select("a[href*='/resumes/']")
    # фильтр: href может отсутствовать, поэтому безопасно
    valid_links = []
    for a in links:
        if not isinstance(a, Tag):
            continue
        href = a.get("href")
        if not href:
            continue
        href_str = str(href)
        if "/resumes/" in href_str:
            valid_links.append(a)

    out.write(f"[SERP] Resume links count: {len(valid_links)}\n")
    if valid_links:
        sample = valid_links[0]
        out.write(f"     Sample HREF: {sample.get('href')}\n")
        out.write(f"     Sample Path: {build_selector_path(sample)}\n")

    # --- Generic "card-like" containers ---
    # Вместо предположения .card — ищем контейнеры, которые содержат ссылки на резюме
    out.write("[SERP] Card-like containers (first 5):\n")
    card_candidates = []
    for a in valid_links[:50]:
        # поднимемся до первого div/section/article/li
        cur = a
        for _ in range(6):
            if isinstance(cur, Tag) and cur.name in {"div", "section", "article", "li"}:
                card_candidates.append(cur)
                break
            cur = cur.parent if isinstance(cur.parent, Tag) else None
            if cur is None:
                break

    # дедуп по пути
    seen = set()
    shown = 0
    for c in card_candidates:
        path = build_selector_path(c)
        if path in seen:
            continue
        seen.add(path)
        out.write(f"     - {path}\n")
        shown += 1
        if shown >= 5:
            break

    if shown == 0:
        out.write("     (none)\n")


def main() -> None:
    if not FIXTURES_DIR.exists():
        print(f"❌ Fixtures directory not found: {FIXTURES_DIR}")
        print("   Ensure fixtures exist under tests/fixtures/raw/*.html")
        sys.exit(1)

    files = sorted(FIXTURES_DIR.glob("*.html"))
    if not files:
        print(f"❌ No .html files found in: {FIXTURES_DIR}")
        sys.exit(1)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Analyzing {len(files)} fixture(s)...")
    with REPORT_PATH.open("w", encoding="utf-8") as out:
        out.write("STRUCTURE REPORT\n")
        out.write(f"Fixtures dir: {FIXTURES_DIR}\n")
        out.write(f"Count: {len(files)}\n")
        out.write("=" * 72 + "\n")
        for f in files:
            analyze_one_file(f, out)

    print("✅ Analysis complete.")
    print(f"📄 Report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
