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

# System deps for building wheels (lxml) + TLS
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Poetry + export plugin (used only in builder stage)
RUN pip install --no-cache-dir poetry poetry-plugin-export

# Copy only dependency manifests for better layer caching
COPY pyproject.toml poetry.lock ./

# Export requirements and build wheels into /wheels
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes \
 && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


############################################
# Runtime: minimal libs + non-root user
############################################
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Runtime system libs:
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    libjpeg62-turbo \
    libfreetype6 \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Create non-root user (fixed UID/GID=1000)
RUN groupadd --gid 1000 hruser \
 && useradd  --uid 1000 --gid 1000 --create-home --shell /bin/bash hruser

WORKDIR /app

# Install python deps from wheels built in builder
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
 && rm -rf /wheels

# === ДОДАНО: Встановлення залежностей для багатомовної моделі ===
# Критично: встановлюємо легку CPU-версію PyTorch, щоб образ не важив 4 ГБ
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir sentence-transformers
# ==================================================================

# Copy only what is needed to run the agent (keep surface small)
COPY --chown=hruser:hruser app/ ./app/
COPY --chown=hruser:hruser run_agent.py ./
COPY --chown=hruser:hruser pyproject.toml ./
COPY --chown=hruser:hruser README.md ./

# === НАСТРОЙКА КЭША И ПРАВ ДО ПЕРЕХОДА НА ПОЛЬЗОВАТЕЛЯ HRUSER ===
ENV XDG_CACHE_HOME=/app/.cache \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence_transformers

# Writable dirs (only these should be RW), включая папку для кэша
RUN mkdir -p /app/out /app/logs /app/.cache \
 && chown -R hruser:hruser /app/out /app/logs /app/.cache

# Safety: make code read-only inside image (defense-in-depth)
RUN chmod -R 555 /app/app \
 && chmod 555 /app/run_agent.py

# Ensure default output file is writable even with read_only rootfs:
RUN ln -sf /app/out/result.jsonl /app/result.jsonl \
 && chown -h hruser:hruser /app/result.jsonl

# === ПЕРЕХОД НА ПОЛЬЗОВАТЕЛЯ ===
USER hruser

# === ЗАГРУЗКА МНОГОЯЗЫЧНОЙ МОДЕЛИ ===
RUN python -c "from chromadb.utils import embedding_functions; \
func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='paraphrase-multilingual-MiniLM-L12-v2'); \
func(['Тест українською', 'Тест на русском'])"

VOLUME ["/app/out"]

CMD ["python", "run_agent.py"]