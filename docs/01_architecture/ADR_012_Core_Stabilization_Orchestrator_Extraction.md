# ADR 012: Core Stabilization & Orchestrator Extraction

## Status

Accepted.

## Context

Phase 2 delivered a working HITL workflow, but the API layer accumulated
business logic: crawling, cache freshness checks, deduplication, persistence,
LLM scoring and report generation were implemented inside
`app/api/endpoints.py`.

The audit also found a functional bug in ChromaDB indexing. The code attempted
to save `payload.text`, but the canonical resume payload contains structured
fields such as `title`, `skills`, `summary` and `experience`. As a result, new
analysis records could be saved with an empty document and semantic pre-search
could not reliably return matches.

## Decision

1. Move the analysis workflow into `app/services/analysis_orchestrator.py`.
2. Keep `app/api/endpoints.py` responsible only for HTTP validation, session
   persistence and background task scheduling.
3. Use `app.models.search.SearchPayload` as the public `/preview` DTO.
4. Convert public DTOs to source-specific adapter payloads only through
   `SearchPayload.to_adapter_payload()`.
5. Centralize deduplication before adapter execution with
   `should_skip(url, resume_id)`.
6. Normalize canonical resume payloads into a searchable ChromaDB document with
   `resume_to_searchable_text()`.

## ChromaDB Text Normalization

The searchable text is built from stable semantic fields:

- `payload.title`
- `payload.skills`
- `payload.summary`
- every entry in `payload.experience`, including position, company, period,
  duration and description

Empty or unsupported payload structures produce an empty string. `VectorCache`
already ignores empty text in `save_analysis()`, so invalid documents are not
indexed.

## Consequences

- API routing is thinner and easier to test.
- Parser adapters become source-specific extraction components, not owners of
  business deduplication.
- The Trio-model remains explicit at the API contract boundary and is mapped
  deterministically before reaching adapters.
- ChromaDB receives actual resume content, making semantic pre-search useful
  for cache hits and delta parsing.
