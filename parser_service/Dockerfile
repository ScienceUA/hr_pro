# syntax=docker/dockerfile:1

############################################
# Builder: export deps via Poetry + install
############################################
FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /build

# System deps for building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry poetry-plugin-export

# Copy poetry files from build context root
COPY pyproject.toml poetry.lock ./

RUN poetry export -f requirements.txt --output requirements.txt --without-hashes \
 && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


############################################
# Runtime: minimal libs + non-root user
############################################
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 parseruser \
 && useradd  --uid 1000 --gid 1000 --create-home --shell /bin/bash parseruser

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
 && rm -rf /wheels

# Copy only parser_service.
COPY --chown=parseruser:parseruser parser_service/ ./parser_service/

RUN chmod -R 555 /app/parser_service

USER parseruser

# Entrypoint will be updated to FastAPI app or Celery worker later
CMD ["python", "-m", "parser_service.main"]
