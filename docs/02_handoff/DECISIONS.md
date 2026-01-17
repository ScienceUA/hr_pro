Decision: A — SmartFetcher is the Local MVP transport

Scope: Local MVP (L1.5) работает синхронно, без прокси, с троттлингом.

Non-goal: L1.3 Resilient HTTP не обязан быть подключён в runtime L1.5.

Migration note: L1.3 будет подключаться на фазе cloud/scale и/или L6 proxy-aware orchestration.