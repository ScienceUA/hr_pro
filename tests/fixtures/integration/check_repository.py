import sys
from pathlib import Path

from app.storage.repository import JsonlRepository
from app.parsing.models import PageType
from app.parsing.resume import ResumeParser
from app.parsing.base import BaseParser

# Временный файл для тестов (в корне проекта)
TEST_FILE = Path("test_candidates.jsonl")

# Реальные фикстуры
FIXTURES_DIR = Path("tests") / "fixtures" / "raw"
FIXTURE_RESUME_OK = FIXTURES_DIR / "resume_ok_full_profile.html"
FIXTURE_NOT_FOUND = FIXTURES_DIR / "resume_not_found_missing.html"


def cleanup():
    if TEST_FILE.exists():
        TEST_FILE.unlink()


def require_fixture(path: Path):
    if not path.exists():
        print(f"❌ Fixture not found: {path}")
        print("   Убедись, что ты запускаешь скрипт из корня проекта и фикстуры лежат в tests/fixtures/raw/")
        sys.exit(1)


def dedup_key_from_result(result) -> str:
    """
    Должно совпадать с логикой JsonlRepository:
    - если payload есть и есть resume_id -> используем resume_id
    - иначе -> 'url:' + result.url
    """
    payload = getattr(result, "payload", None)
    resume_id = getattr(payload, "resume_id", None) if payload is not None else None
    if resume_id:
        return str(resume_id)
    return "url:" + str(getattr(result, "url", ""))


def parse_real_resume_result() :
    """
    Реальный пайплайн: HTML фикстура -> ResumeParser -> ParsingResult
    """
    require_fixture(FIXTURE_RESUME_OK)
    html = FIXTURE_RESUME_OK.read_bytes()

    # URL специально "грязный" не нужен — ResumeParser сам канонизирует.
    # Но можно оставить каноничный для стабильности.
    url = "https://www.work.ua/resumes/7502793/"
    parser = ResumeParser(html, url)
    result = parser.parse()

    if result.page_type != PageType.RESUME:
        print(f"❌ Expected RESUME from fixture, got: {result.page_type}")
        sys.exit(1)
    if not result.payload or not getattr(result.payload, "resume_id", None):
        print("❌ RESUME parse returned no payload/resume_id")
        sys.exit(1)

    return result


def parse_real_not_found_result():
    """
    Реальный пайплайн: HTML фикстура -> BaseParser классификация -> ParsingResult (без payload)
    Мы не используем ResumeParser тут специально: это не RESUME-страница.
    """
    require_fixture(FIXTURE_NOT_FOUND)
    html = FIXTURE_NOT_FOUND.read_bytes()

    url = "https://www.work.ua/resumes/does-not-exist/"
    base = BaseParser(html, url)

    if base.page_type != PageType.NOT_FOUND:
        print(f"❌ Expected NOT_FOUND from fixture, got: {base.page_type}")
        sys.exit(1)

    # Формируем результат в том же контракте, который хранит репозиторий
    # (без payload, дедуп по url)
    from app.parsing.models import ParsingResult, DataQuality  # локальный импорт, чтобы не циклило

    return ParsingResult(
        url=url,
        page_type=base.page_type,
        payload=None,
        quality=DataQuality.ERROR,
        error_message="NOT_FOUND fixture"
    )


def run_tests():
    print("🛡️  Testing JsonlRepository (real pipeline fixtures)...")
    cleanup()

    # --- Test 1: Write & Exists (real RESUME result) ---
    repo = JsonlRepository(TEST_FILE)

    result1 = parse_real_resume_result()
    key1 = dedup_key_from_result(result1)

    repo.save_result(result1)

    if not repo.exists(key1):
        print(f"❌ Test 1 Failed: key '{key1}' should exist after save_result()")
        sys.exit(1)

    # Негативная проверка (несуществующий ключ)
    if repo.exists("999999999"):
        print("❌ Test 1 Failed: random id should NOT exist")
        sys.exit(1)

    print("✅ Test 1 (Write/Exists on real RESUME) OK")

    # --- Test 2: Persistence (Restart) ---
    repo2 = JsonlRepository(TEST_FILE)
    if not repo2.exists(key1):
        print(f"❌ Test 2 Failed: key '{key1}' lost after restart")
        sys.exit(1)

    print("✅ Test 2 (Persistence) OK")

    # --- Test 3: Corruption Recovery + No-payload dedup (url:...) ---
    # 1) Добавляем битую строку
    with open(TEST_FILE, "a", encoding="utf-8") as f:
        f.write("{broken_json: ...\n")

    # 2) Добавляем валидную строку в формате ParsingResult из реальной NOT_FOUND фикстуры
    result_nf = parse_real_not_found_result()
    key_nf = dedup_key_from_result(result_nf)

    with open(TEST_FILE, "a", encoding="utf-8") as f:
        f.write(result_nf.model_dump_json() + "\n")

    # 3) Новый инстанс должен восстановить оба ключа, проигнорировав мусор
    repo3 = JsonlRepository(TEST_FILE)

    if not repo3.exists(key1):
        print(f"❌ Test 3 Failed: lost RESUME key '{key1}' after corruption")
        sys.exit(1)

    if not repo3.exists(key_nf):
        print(f"❌ Test 3 Failed: failed to load no-payload key '{key_nf}' after corruption")
        sys.exit(1)

    print("✅ Test 3 (Corruption Recovery + url-dedup) OK")

    cleanup()
    print("\n🎉 JsonlRepository is solid (real fixtures, real pipeline)!")


if __name__ == "__main__":
    run_tests()
