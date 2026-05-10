# Структура Файлів та Модулів Проєкту (File Structure)

Цей документ вичерпно описує ієрархію файлів системи HR-Pro після переходу до мікросервісної архітектури. 

---

## 📂 Коренева директорія (Root)
- `main.py` — Головна точка входу. На даному етапі містить монолітну логіку (потребує рефакторингу під нові сервіси).
- `pyproject.toml` / `poetry.lock` — Управління залежностями (Poetry).
- `docker-compose.yaml` / `Dockerfile` / `.dockerignore` — Інфраструктура для розгортання у контейнерах.
- `.env` / `.gitignore` — Секретні змінні та правила виключення для Git.
- `README.md` — Базовий опис проєкту.

---

## 1. 🧠 HR-Pro Core (ШІ-ядро та Оркестратор) — `app/`
Відповідає виключно за семантику, ШІ-аналіз та генерацію звітів.

### `app/models/` (Контракти Даних)
- `search.py` — «Тріо-модель» критеріїв (`search_mandatory`, `internal_mandatory`, `desirable`).
- `resume.py` — Канонічна схема резюме (єдиний стандарт для всіх сайтів).
- `agent.py` — Схеми для структурованих відповідей LLM.
- `common.py` — Базові типи даних (наприклад, моделі помилок).

### `app/agent/` (Інтерпретація NLP)
- `interpretation.py` — ШІ-агент. Розбиває запит користувача на масиви критеріїв.
- `vacancy_compressor.py` — Стискає довгі описи вакансій для економії токенів.

### `app/services/` (Бізнес-логіка)
- `analyzer.py` — ШІ-Оцінювач ("Світлофор": 🟢, 🟡, 🔴).
- `report_generator.py` — Формує Markdown-звіти.
- `llm_client.py` — Безпечний клієнт для OpenAI API.

### `app/config/` (Довідники та Налаштування)
- `load_config.py` — Динамічно генерує текст довідника фільтрів для промпту.
- `workua_filters_map.json` / `robotaua_filters_map.json` — Карти ID джерел.
- `settings.py` / `app.yaml` / `headers.py` — Системні налаштування.

### `app/core/`, `app/storage/`, `app/project/`
- `core/exceptions.py` — Кастомні помилки системи.
- `storage/repository.py` — Збереження звітів на диск.
- `storage/vector_cache.py` — Кешування семантики кандидатів.
- `project/cleanup.py` — Утиліта для очищення тимчасових файлів.

---

## 2. 🦾 Parser Service (Мікросервіс Збору) — `parser_service/`
Ізольований модуль ("Руки" системи).

### `parser_service/execution/` (Мережа та Контроль)
- `executor.py` — Асинхронний контролер запитів із підтримкою політик Resilience (Retry, Fallback).
- `http_client.py` — Фабрика клієнтів `httpx` для виконання GET/POST запитів.
- `proxy_manager.py` — Управління пулом проксі.

### `parser_service/sources/` (Адаптери Джерел)
- `workua.py` / `robotaua.py` — Перекладачі з `search_mandatory` у специфічні формати платформ (URL / GraphQL Payload).

### `parser_service/parsing/` (Екстракція та Уніфікація)
- `serp.py` — Парсер сторінок видачі (збирає ID резюме).
- `resume_parsers.py` — Парсер сторінок кандидатів (HTML/JSON -> Pydantic модель).
- `base.py` / `models.py` / `selectors.py` — Базові класи та словники селекторів.

---

## 3. 🗄 Дані, Тести та Утиліти
- `out/` — Результати роботи програми:
  - `chromadb_data/` — Векторна база даних кешу.
  - `*.jsonl` / `*.json` / `*.md` — Збережені резюме, логи аналізу та звіти.
- `tests/fixtures/` — Еталонні дані:
  - `raw/` — Збережені "сирі" HTML та JSON відповіді сайтів (для тестів).
  - `integration/` — Скрипти (`check_*.py`) для тестування окремих вузлів.
- `tools/` — Допоміжні скрипти розробника (`tools/run_agent.py`, `clean_json.py`, `analyze_structure.py`, `fetch_fixtures.py`).

---

## 🗑 Legacy-модулі (Підлягають видаленню)
*Ці файли залишаються в проєкті тимчасово, щоб не зламати старий `main.py`. Вони будуть видалені після інтеграції `main.py` з новим `parser_service`.*
- `app/transport/fetcher.py` -> *замінюється на `parser_service/execution/`*
- `app/services/crawler.py` -> *замінюється на логіку всередині `parser_service`*
- `app/services/url_builder.py` -> *замінюється на адаптери `parser_service/sources/`*