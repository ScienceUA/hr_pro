# Interface Testing

## Parser Service

Run Core locally from the repository root:

```bash
poetry run uvicorn main:app --reload --port 8000
```

Run the Parser Service locally from the repository root:

```bash
poetry run uvicorn parser_service.main:app --reload --port 8001
```

Or run Core, Parser Service, and Redis together:

```bash
docker compose up --build
```

Health checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
```

Expected Core response:

```json
{"status":"ok"}
```

Expected Parser response:

```json
{"status":"ok","service":"parser","version":"0.1.0"}
```

Core workflow smoke test:

```bash
curl -X POST http://127.0.0.1:8000/preview \
  -H 'Content-Type: application/json' \
  -d '{"query":"python","city":"kyiv","source":"workua","pages":1}'

curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<session_id_from_preview>"}'

curl http://127.0.0.1:8000/status/<session_id_from_preview>
```

The Parser Service also exposes contract-only HTTP endpoints for `/preview`,
`/parse`, and `/freshness`. These endpoints validate request DTOs and return
stable placeholder response envelopes with `implemented: false` until adapter
execution is migrated behind the HTTP boundary.

`/preview` responses expose unambiguous count fields:
`total_found` is the total number of source results for the query, while
`returned_count` is the number of preview `items` included in the response.

Core `/preview` preserves `session_id`, `preview.total_found`, and
`preview.urls`, and adds `preview.requires_refinement` plus `preview.message`.
When `preview.total_found > 50`, `requires_refinement` is `true` and
`message` includes the concrete result count and asks the user to narrow the
search criteria before analysis.

Core `/analyze` refuses sessions whose stored preview metadata has
`requires_refinement: true`. It returns HTTP 409 with
`code: preview_refinement_required`, a user-facing message, and `total_found`
when available. Older sessions without this metadata remain compatible.

Core `/status/{session_id}` returns a stable task status envelope for known
sessions:
`session_id`, `status`, `step`, `progress`, `message`, `error`, `report`, and
`counters`. Legacy/minimal Redis status payloads are normalized into this
shape, with unknown numeric or diagnostic fields moved under `counters`.
Unknown sessions return HTTP 404.

Redis session fallback is explicit. `ALLOW_IN_MEMORY_SESSION_FALLBACK=false`
by default, so Redis connection failures return HTTP 503 with
`code: redis_unavailable`. Set `ALLOW_IN_MEMORY_SESSION_FALLBACK=true` only
for local development or tests where single-process in-memory session state is
acceptable.

Run interface contract tests:

```bash
poetry run pytest tests/test_parser_service_health.py tests/test_parser_service_contract.py -q
```
