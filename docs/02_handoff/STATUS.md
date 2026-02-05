# STATUS.md

## 1. Сводка

Проект HR-Pro завершил стадию **Local Agent MVP**.
Система полностью функциональна локально: от ввода запроса до генерации PDF-отчета.
Текущая разрешённая зона работ — **пункт 7** (Контейнеризация и Облако).

## 2. Статус по пунктам плана (SOURCE OF TRUTH: Development_Plan.md)

1. Инициализация окружения — ✅ завершено
2. Контракты данных — ✅ завершено
3. Транспорт и подготовительный Resilient HTTP — ✅ завершено
4. Парсинг резюме и тестирование — ✅ завершено
5. Локальный оркестратор (Service Layer). Local MVP — ✅ завершено
6. Логика Агента и AI-анализ — ✅ завершено (CLOSED)
7. Контейнеризация и миграция в облако — ⏳ активный пункт
8. Proxy-aware Orchestration — ⏸ запланировано

## 3. Детализация закрытого этапа 6 (Agent Intelligence)

**Дата закрытия:** [Текущая дата]
**Результат:** Реализован полный локальный пайплайн (`run_agent.py`).

**Реализованные модули:**
1. **Interpretation (6.1):** Baseline-интерпретатор (`app/agent/interpretation.py`). Преобразует текст в `CriteriaBundle` и `SearchPayload`.
2. **Search Integration (6.2):** `CrawlerService` интегрирован и управляется через единый контракт.
3. **Analysis (6.3):** `ResumeAnalyzer` с поддержкой Mock-режима и безопасного промптинга. Traffic Light Protocol (MATCH/CONDITIONAL/REJECT).
4. **Reporting (6.4):** `ReportGenerator` создает Markdown-отчеты без PII в заголовках.
5. **Orchestration (6.5):** Скрипт `run_agent.py` объединяет все шаги в единый процесс (Interactive CLI).

**Известные ограничения (Technical Debt):**
- Интерпретация (6.1) использует эвристику (Regex/Tokens), а не LLM.
- Режим Real LLM требует API Key (инфраструктура `llm_client.py` готова).

## Legacy artifacts (execution/*_page.py)

В репозитории присутствуют файлы:
- `app/execution/resume_page.py` — legacy парсер.
- `app/execution/search_page.py` — legacy placeholder.

Оба файла **не участвуют** в активном runtime Local MVP.
Активный детерминированный слой парсинга (SOURCE OF TRUTH для runtime):
- `app/parsing/resume.py`
- `app/parsing/serp.py`
