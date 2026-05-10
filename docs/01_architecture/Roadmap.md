# План доопрацювань (Roadmap) проекту HR-Pro

## Поточний статус
Локальний додаток (CLI) із реалізованим алгоритмом Human-in-the-Loop, парсингом Work.ua/Robota.ua та AI-скорингом.

## Реалізовано (Done)
- [x] Впроваджено "Тріо-модель" критеріїв (`search_mandatory`, `internal_mandatory`, `desirable`).
- [x] Налаштовано парсинг Work.ua та Robota.ua.
- [x] Реалізовано генерацію звітів (Світлофор: 🟢, 🟡, 🔴) у Markdown.
- [x] Кешування через Vector Database (ChromaDB).
- [x] Впроваджено базовий Anti-bot захист (Jitter, Proxy Manager, Semaphore).

## Backlog: Підготовка до Cloud-Native (Google Cloud)
- [ ] **Рефакторинг асинхронності:** Замінити всі синхронні виклики `asyncio.run()` в адаптерах на нативні `await` для сумісності з FastAPI та уникнення блокування Event Loop.
- [ ] **Transport State (Redis):** Інтегрувати Redis для збереження проміжних результатів (URL) між `/preview` та `/analyze` (короткий TTL).
- [ ] **Адаптація Business State під Хмару:** Налаштувати Persistent Volume (або Cloud Storage) для вже існуючого `JsonlRepository` та `VectorCache` (ChromaDB) для збереження історії проєктів.
- [ ] **Централізація Дедуплікації:** Винести існуючу логіку перевірки дублікатів з індивідуальних адаптерів у загальний рівень Оркестратора, щоб єдині правила діяли для всіх джерел.
- [ ] **Автоматизація Cleanup:** Налаштувати запуск існуючого скрипта `app/project/cleanup.py` (через Cloud Scheduler) для автоматичного видалення старих даних.
- [ ] **Universal LLM Connector:** Спроєктувати REST API за стандартом OpenAPI (Swagger) таким чином, щоб він був LLM-agnostic (підтримував інтеграцію як з OpenAI GPTs, так і з Anthropic Claude чи Google Gemini).
- [ ] **FastAPI & Long Polling API:** Реалізувати ендпоінти `/preview`, `/analyze` (Background Tasks) та `/status/{session_id}` для обходу таймаутів Custom GPT.
- [ ] **Парсер LinkedIn:** Розробити та інтегрувати адаптер.