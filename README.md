# HR-Pro: AI Recruiting Assistant

ШІ-асистент для автоматизованого пошуку, збору та семантичного аналізу резюме кандидатів із сайтів роботи. 

## 🏗 Архітектура (Microservices)
Проєкт розділений на дві незалежні частини:
1. **HR-Pro Core (`app/`)** — "Мозок". Семантичний аналіз запитів користувача, робота з OpenAI API, генерація Markdown-звітів зі скорингом кандидатів (🟢, 🟡, 🔴).
2. **Parser Service (`parser_service/`)** — "Руки". Ізольований модуль екстракції даних. Виконує HTTP/GraphQL запити до зовнішніх джерел даних, приводить отримані дані до канонічної Pydantic-моделі.

## 📚 Документація
Повна база знань розробника, опис структури файлів та контрактів даних (Pydantic схем) знаходиться у папці `/docs`.

## 🔄 Робочий процес (Stateful HITL)
Сервіс реалізує двофазний робочий процес "Human-in-the-Loop":
1. **Попередній перегляд (`/preview`)**: Синхронний пошук, який повертає URL-адреси потенційних кандидатів і налаштовує сесію в Redis.
   Якщо пошук повертає більше 50 результатів, користувачу потрібно повідомити точну кількість знайдених резюме та попросити звузити критерії пошуку.
2. **Аналіз (`/analyze`)**: Асинхронне фонове завдання, яке виконує дельта-парсинг, обов'язкове збереження сирих даних (Data Lake) та семантичний аналіз.

## 🛠 Технологічний стек
- **FastAPI**: Шар REST API
- **Redis**: Стан сесій та координація фонових завдань
- **ChromaDB**: Семантичний векторний кеш для проаналізованих результатів
- **Google Cloud Storage**: Масштабоване сховище даних (Data Lake) для сирих результатів парсингу (опціонально)
- **OpenAI/LLM**: Семантичний скоринг та аргументація

## 🚀 Запуск
Управління залежностями здійснюється через Poetry:
```bash
poetry install
poetry run uvicorn main:app --reload
```

Parser Service локально:
```bash
poetry run uvicorn parser_service.main:app --reload --port 8001
```

Docker Compose локально:
```bash
docker compose up --build
```

Порти за замовчуванням:
- Core API: `http://127.0.0.1:8000`
- Parser Service: `http://127.0.0.1:8001`
- Redis: `127.0.0.1:6379`

Мінімальна smoke-перевірка:
```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
curl -X POST http://127.0.0.1:8000/preview \
  -H 'Content-Type: application/json' \
  -d '{"query":"python","city":"kyiv","source":"workua","pages":1}'
curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<session_id_from_preview>"}'
curl http://127.0.0.1:8000/status/<session_id_from_preview>
```

## ⚙️ Змінні оточення (Environment Variables)
- `REDIS_URL`: URL для підключення до Redis (за замовчуванням: `redis://redis:6379/0`)
- `APP_ENV`: Назва середовища (`local`, `staging`, `production` тощо).
- `ALLOW_IN_MEMORY_SESSION_FALLBACK`: Явно встановіть `true` тільки для локальної розробки, якщо Redis недоступний. За замовчуванням `false`; у production Redis-помилки мають завершувати API-запити явною помилкою, а не переходити на пам'ять процесу.
- `USE_GCS`: Встановіть `true`, щоб увімкнути збереження в Google Cloud Storage
- `GCS_BUCKET_NAME`: Бакета GCS для сирих даних Data Lake
- `REDIS_TASK_TTL`: Час життя статусу завдання в Redis (за замовчуванням: 86400)
- `REDIS_PAYLOAD_TTL`: Час життя корисного навантаження сесії в Redis (за замовчуванням: 3600)
- `USE_PARSER_SERVICE_PREVIEW`: Встановіть `true`, щоб Core `/preview` використовував Parser Service HTTP `/preview`; за замовчуванням `false`.
- `PARSER_SERVICE_BASE_URL`: Base URL Parser Service для Core `ParserClient` (у Docker Compose: `http://parser-service:8000`, локально з Poetry: `http://localhost:8001`).
