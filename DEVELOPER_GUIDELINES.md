# HR-Pro Developer Guidelines

This document outlines the mandatory standards and workflows for all contributors to the HR-Pro project. Adherence to these guidelines is strictly enforced (Zero Tolerance Policy).

## 1. Architectural Integrity

- **ADR First:** Every significant architectural change or new technology adoption MUST be documented in `architecture_decision_record.md`.
- **Statelessness:** The application (specifically `app/api`) must remain stateless. All transient state must be moved to Redis (Google Cloud Memorystore).
- **Strategy Pattern:** All external infrastructure dependencies (Storage, LLM, etc.) must implement a strategy pattern to allow local development without cloud dependencies.

## 2. Project Governance & Rollback

- **Rollback Log:** Every release or phase completion MUST be documented in `rollback_log.md` with clear instructions on how to revert the system to its previous stable state.
- **Atomic Commits:** Prefer small, atomic commits that correspond to specific tasks in the `task.md`.

## 3. Data Lake & Persistence (ADR 009)

- **Raw Data First:** All parsed data from external sources MUST be saved to the Data Lake (via `BaseRepository`) BEFORE any enrichment or analysis occurs. This ensures data resilience.
- **Schema Validation:** Use Pydantic models for all data transfers between components.

## 4. CI/CD & Testing

- **Test Coverage:** All new features must include unit and integration tests.
- **Fail Fast:** Adapters must implement fail-fast logic for anti-bot blocks (Captcha, Ban) to prevent wasteful retries.
- **Linting:** Code must pass `flake8` and `black` formatting. Use `# noqa: E501` only for long URLs or CSS selectors where breaking them would hurt readability.

## 5. Security

- **Secrets Management:** Never hardcode secrets. Use environment variables.
- **Internal Endpoints:** Any administrative or maintenance endpoints (e.g., `/internal/cleanup`) must be protected by a shared secret (`SCHEDULER_SECRET`).

---

**Failure to comply with these guidelines will result in a rejected PR and mandatory refactoring.**
