# Architecture Decision Record (ADR)

This document tracks all major architectural decisions made during the evolution of HR-Pro.

## ADR 001: Migration to Cloud-Native Microservices

**Date:** 2026-05-01
**Status:** Accepted

### Context
HR-Pro was initially built as a monolithic local CLI MVP. As we plan to scale the application and provide it via a web interface (`upman.group`), the system needs to be deployed to the cloud, be scalable, and support concurrent user sessions while adhering to platform usage limits (e.g., bot detection).

### Decision
We are migrating from a local MVP to a microservices architecture hosted on Google Cloud:
1. **Service Split:** The `app/` (HR-Pro Core) and `parser_service/` (Parser) modules will be split into two separate Docker containers. The Core service has been refactored from a CLI script to a FastAPI application to support synchronous/asynchronous web endpoints.
2. **Account Isolation:** `parser_service/` will run on a separate Google Cloud Account to isolate proxy/scraping activities from the main core application environment.
3. **CI/CD:** Adopt `cloudbuild.yaml` to enforce linting and tests (TDD) before deployment.

### Consequences
- Requires API contracts (REST) between the Core and Parser services.
- Requires robust Secret Management (GCP Secret Manager) for the Parser service.
- Adds deployment complexity but significantly improves scalability, maintainability, and security.

---

## ADR 002: Global Data Lake & Freshness Validation

**Date:** 2026-05-01
**Status:** Accepted

### Context
Resumes scraped from sources (Work.ua, Robota.ua, LinkedIn) cost time, proxies, and LLM tokens to parse and vectorize. Performing this for every user request is inefficient. Moreover, resumes might become inactive or hidden over time.

### Decision
1. **Global Data Lake:** ChromaDB and the JSONL storage will act as a unified, global database. Candidates are shared across all user sessions.
2. **Freshness Validator:** Before executing an expensive scrape, the Core service will query the Vector Cache. For any matched candidates, the Parser Service will perform a fast HTTP HEAD/GET request (Freshness Check) to verify if the resume URL is still active.
3. If active (HTTP 200), it's returned immediately. If hidden/deleted (HTTP 404), it's removed from the Vector Cache.

### Consequences
- Drastically reduces LLM token costs and parsing latency for frequent queries.
- Requires building `freshness_validator.py` inside `parser_service/`.
- Introduces state synchronization logic between Core and ChromaDB.

---

## ADR 003: Scraping Service Account Isolation

**Date:** 2026-05-01
**Status:** Accepted

### Context
Scraping closed platforms (like LinkedIn) requires authorized sessions (cookies/tokens). Using end-user credentials is a privacy and security violation, and risks user account bans.

### Decision
1. **Dedicated Bot Identities:** The `parser_service/` will utilize a pool of dedicated service bot accounts for authentication.
2. **Secret Manager:** All bot credentials must be stored in Google Cloud Secret Manager. No `.env` secrets in the repository.
3. **Rotation:** Implement an `AuthManager` that rotates sessions and proxies seamlessly if a bot account gets blocked.

### Consequences
- Prevents user account bans.
- Requires maintaining a pool of valid bot accounts.
- Requires integration with GCP Secret Manager in the `parser_service/`.

---

## ADR 004: API Gateway Routing

**Date:** 2026-05-01
**Status:** Accepted

### Context
With the split into microservices, we need a unified entry point for clients (like the web frontend) that abstracts the locations and scaling of underlying services.

### Decision
Implement Google Cloud API Gateway.
1. The gateway will use an OpenAPI (`api_gateway.yaml`) spec to route requests.
2. Endpoints `/preview`, `/analyze`, and `/status` will route to HR-Pro Core.
3. Internal parsing endpoints will route to Parser Service on the secondary Google Account.

### Consequences
- Centralized auth, rate-limiting, and routing.
- The web application only talks to one API host.

---

## ADR 005: Frontend Infrastructure

**Date:** 2026-05-01
**Status:** Accepted

### Context
The HR-Pro system needs a user-facing landing and dashboard available on the domain `upman.group`.

### Decision
Host the frontend as a static SPA (Single Page Application).
1. Deploy built static assets (HTML/CSS/JS) to a **Google Cloud Storage Bucket**.
2. Map the bucket to a Google Cloud HTTP(S) Load Balancer.
3. Configure the Load Balancer with a managed SSL certificate for `upman.group`.

### Consequences
- Extremely low cost and high availability for the UI.
- Fast delivery globally if Cloud CDN is enabled.

---

## ADR 006: State Management (Memorystore & Persistent Volume)

**Date:** 2026-05-01
**Status:** Accepted

### Context
Cloud Run containers are stateless. We need a way to track the asynchronous tasks (job status) and store our vector embeddings.

### Decision
1. **Transport State (Redis):** Use Google Cloud Memorystore (Redis) to hold `session_id`, cache intermediate states, and bridge the gap between the asynchronous `/analyze` execution and the `/status` polling endpoints. *Note: During Phase 1 local development, a temporary in-memory dictionary is used for state tracking.*
2. **Vector DB Storage (Persistent Volume):** Mount a Google Cloud Storage FUSE or Filestore volume as a persistent mount into the Cloud Run container running Core. This ensures the ChromaDB SQLite and vector binary files survive container restarts and act as the Global Data Lake.

### Consequences
- Solves the state problem for Cloud Run.
- Introduces stateful dependencies requiring proper VPC configuration for Memorystore.
---

## ADR 011: Trio Model Evaluation & RED Candidate Filtering
**Date:** 2026-05-01
**Status:** Accepted

### Context
To improve the quality of recruitment reports, we need a clear scoring system that distinguishes between ideal matches, partial matches, and unqualified candidates. Furthermore, the final report should only contain actionable candidates to reduce noise for the user.

### Decision
1. **Trio Model:** We implement a three-tier scoring system:
   - 🟢 **GREEN**: Meets all mandatory and all desirable criteria.
   - 🟡 **YELLOW**: Meets all mandatory criteria but lacks one or more desirable criteria.
   - 🔴 **RED**: Fails to meet one or more mandatory criteria.
2. **RED Filter:** The orchestrator (`run_analysis_task`) will automatically filter out candidates with the 🔴 RED status from the final Markdown report presented to the user.
3. **Data Lake First Persistence:** ALL candidates (Green, Yellow, and Red) MUST be saved to the Data Lake (JSONL/GCS) and Vector Cache (ChromaDB) immediately after parsing/analysis. 
   - RAW data from parser adapters must be persisted even if returned in-memory.
   - The RED filtering happens ONLY at the report generation stage, not at the storage stage.
4. **Supreme Override Policy:** Current architectural instructions and ADRs have absolute priority over any legacy documentation (e.g., old prompt files).

### Consequences
- Reports become more focused and "cleaner" for recruiters.
- The system maintains a complete history of all analyzed candidates in the background.
- Data Lake remains a reliable source of truth for all processed resumes.

---

## Rollback Plan (Phase 1 & 2)

**Trigger:** Critical failure of Redis session management, GCS persistence errors, or corrupted ChromaDB vector indices.

### Strategy:
1. **Redis Failure:** If Redis becomes unavailable, production-like environments must fail explicitly instead of silently falling back to process memory. In-memory session fallback is allowed only when `ALLOW_IN_MEMORY_SESSION_FALLBACK=true` is explicitly configured for local development or single-process testing.
2. **Persistence Failure:** Disable `USE_GCS=true` and revert to local filesystem storage in the `/app/out` directory.
3. **ChromaDB Corruption:** Delete the corrupted vector directory. The system will automatically rebuild the cache from the Data Lake (JSONL files) upon the next search, albeit with higher latency.
4. **Version Rollback:** Revert to the last stable Docker image tag (e.g., `hr-pro-core:v1.0.0-stable`).
