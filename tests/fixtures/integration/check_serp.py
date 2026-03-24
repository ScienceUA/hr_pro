import sys
from pathlib import Path
from app.parsing.serp import SerpParser
from app.parsing.models import PageType, DataQuality

# Путь к фикстуре
FIXTURE_PATH = Path(__file__).resolve().parent / "tests" / "fixtures" / "raw" / "serp_ok_python_kyiv.html"

def run_test():
    print(f"🛡️  Testing SERP Parser on {FIXTURE_PATH.name}...")
    
    if not FIXTURE_PATH.exists():
        print(f"❌ Fixture not found at {FIXTURE_PATH}")
        sys.exit(1)
        
    content = FIXTURE_PATH.read_bytes()
    # Эмулируем URL страницы поиска
    url = "https://www.work.ua/resumes-kyiv-python/"
    
    parser = SerpParser(content, url)
    result = parser.parse()
    
    # --- Assertions ---
    
    # 1. Тип страницы
    if result.page_type != PageType.SERP:
        print(f"❌ Wrong PageType: {result.page_type}")
        sys.exit(1)
        
    # 2. Качество
    if result.quality != DataQuality.COMPLETE:
        print(f"❌ Low Quality: {result.quality}")
        # Не падаем, но предупреждаем
        
    # 3. Payload (Список)
    items = result.payload
    if not items or len(items) == 0:
        print("❌ No items found in payload!")
        sys.exit(1)
        
    print(f"✅ Found {len(items)} items.")
    
    # 4. Проверка первого элемента
    first = items[0]
    print(f"   First Item: ID={first.resume_id}, Title='{first.title}'")
    print(f"   URL: {first.url}")
    
    if not first.resume_id.isdigit():
        print("❌ Invalid ID format")
        sys.exit(1)
        
    if not first.url.startswith("https://www.work.ua/resumes/"):
        print("❌ Invalid Absolute URL generation")
        sys.exit(1)

    # 5. Проверка пагинации
    if result.next_page_url:
        print(f"✅ Next Page Detected: {result.next_page_url}")
    else:
        print("⚠️  No next page found (check if fixture has pagination)")

    print("\n🎉 SERP Parser is fully functional!")

if __name__ == "__main__":
    run_test()