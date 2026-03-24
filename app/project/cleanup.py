import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "out"

def cleanup_project(role_slug: str = None):
    if not OUT_DIR.exists():
        print(f"Папка {OUT_DIR} не існує. Немає файлів для очищення.")
        return

    patterns = []
    if role_slug:
        patterns.append(f"result_*{role_slug}*.jsonl")
        patterns.append(f"result_llm_*{role_slug}*.json")
        patterns.append(f"result_llm_*{role_slug}*.md")
    else:
        patterns.append("result_*.jsonl")
        patterns.append("result_llm_*.json")
        patterns.append("result_llm_*.md")

    deleted_count = 0
    for pattern in patterns:
        for filepath in OUT_DIR.glob(pattern):
            try:
                filepath.unlink()
                print(f"Видалено: {filepath.name}")
                deleted_count += 1
            except Exception as e:
                print(f"Помилка видалення {filepath.name}: {e}")
    
    print(f"Очищення завершено. Всього видалено файлів: {deleted_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Очищення результатів проєкту")
    parser.add_argument("--role", type=str, default=None, help="Назва вакансії (наприклад 'sales-director') для видалення")
    args = parser.parse_args()
    
    cleanup_project(args.role)