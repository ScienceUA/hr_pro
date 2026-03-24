import sys
from pathlib import Path
from app.parsing.resume import ResumeParser
from app.parsing.models import PageType, DataQuality

# Устойчивое вычисление корня
try:
    PROJECT_ROOT = Path(__file__).resolve().parent
    FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "raw" / "resume_ok_full_profile.html"
    if not FIXTURE_PATH.exists():
        PROJECT_ROOT = Path(__file__).resolve().parents[1]
        FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "raw" / "resume_ok_full_profile.html"
except IndexError:
    pass

def run_test():
    print(f"🛡️  Testing Resume Parser on {FIXTURE_PATH.name}...")
    
    if not FIXTURE_PATH.exists():
        print(f"❌ Fixture not found at {FIXTURE_PATH}")
        sys.exit(1)
        
    content = FIXTURE_PATH.read_bytes()
    
    # 1. Тест с "грязным" URL (параметры, отсутствие слэша)
    # ID из файла отчета: 7502793
    dirty_url = "https://work.ua/resumes/7502793?utm_source=test"
    
    parser = ResumeParser(content, dirty_url)
    result = parser.parse()
    
    # --- Assertions ---
    
    # 1. Quality
    if result.quality != DataQuality.COMPLETE:
        print(f"❌ Low Quality: {result.quality} | Msg: {result.error_message}")
        sys.exit(1)
    
    # 2. Canonical URL Check (Critical)
    expected_url = "https://www.work.ua/resumes/7502793/"
    
    if result.url != expected_url:
        print(f"❌ ParsingResult.url NOT canonical: {result.url}")
        sys.exit(1)
    if result.payload.url != expected_url:
        print(f"❌ Payload.url NOT canonical: {result.payload.url}")
        sys.exit(1)
        
    print(f"✅ URL Canonicalized: {result.url}")

    data = result.payload
    
    # 3. Experience & Garbage Check
    print(f"✅ Experience Entries: {len(data.experience)}")
    if len(data.experience) == 0:
        print("❌ No experience entries parsed from resume_ok_full_profile.html (regression).")
        sys.exit(1)

    for exp in data.experience:
        # Проверяем, что не захватили заголовки "Схожие кандидаты" и т.п.
        pos_lower = (exp.position or "").lower()
        if any(x in pos_lower for x in ["кандидат", "кандидати", "інші", "схожі", "додаткова", "контактна"]):
            print(f"❌ Garbage in Experience: Found '{exp.position}'")
            sys.exit(1)
        
        # Проверка отсутствия обрезки (длина > 100 для длинных названий)
        if exp.company and len(exp.company) > 99:
             print(f"   ℹ️  Long company name preserved ({len(exp.company)} chars)")

    if len(data.experience) > 0:
        first = data.experience[0]
        print(f"   Sample Job: '{first.position}' @ '{first.company}'")

    print(f"✅ Education Entries: {len(data.education)}")
    print(f"✅ Skills Found: {len(data.skills)}")
    # Минимальная наполненность: на полноценном профиле ожидаем хотя бы 1 образование и хотя бы 1 навык.
    # Если одно из них пустое — вероятно, сломались селекторы/сканирование.
    if len(data.education) == 0:
        print("❌ No education entries parsed (regression).")
        sys.exit(1)

    if len(data.skills) == 0:
        print("❌ No skills parsed (regression). Check CSS.SKILL_TAGS or page scope.")
        sys.exit(1)

    print("\n🎉 Resume Parser is functional!")

if __name__ == "__main__":
    run_test()