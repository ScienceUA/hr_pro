What this repo is (1 абзац)

Current milestone: “Completed L1.1–L1.5, next is L6 (proxy-aware orchestration)”

Invariant rules (короткий список):

Local MVP transport = SmartFetcher (requests), sync.

Local MVP: stop on BAN/CAPTCHA/LOGIN (current behavior) until proxy stage.

No long-term storage requirement is cloud/agent level, not enforced in local MVP.

How to run (smoke test) — одна команда + ожидаемый результат

Where the truth lives: ссылки на docs/00_context/*, docs/01_protocols/*

Do not do (критично): “Do not refactor Local MVP to httpx/async in L6; extend transport with proxies later.”