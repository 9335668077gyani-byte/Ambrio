# docker/Dockerfile
# Multi-stage production build for Ambrio FastAPI backend
# Stage 1: builder — installs all deps, downloads MiniLM model
# Stage 2: runtime — lean final image, non-root user, no build tools

# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps needed to compile some packages (e.g. hnswlib for ChromaDB)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps into /install (isolated from system)
COPY requirements.docker.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-warn-script-location -r requirements.docker.txt

# Pre-download sentence-transformers model so runtime has zero cold start
RUN TRANSFORMERS_OFFLINE=0 python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2', cache_folder='/install/lib/python3.11/site-packages/st_cache')"

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="Ambrio" \
      version="4.0.0" \
      description="Ambrio FastAPI WebSocket backend"

# Non-root user for security
RUN groupadd -g 1001 ambrio && useradd -u 1001 -g ambrio -m -s /bin/sh ambrio

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# App source
WORKDIR /app
COPY --chown=ambrio:ambrio ambrio/ ./ambrio/
COPY --chown=ambrio:ambrio db/     ./db/

# Data directories (mounted as volumes in compose)
RUN mkdir -p /data/db /data/chroma /tmp/ambrio_uploads \
    && chown -R ambrio:ambrio /data /tmp/ambrio_uploads

USER ambrio

# Env defaults (overridden by docker-compose env_file)
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AMBRIO_DB_PATH=/data/db/ambrio.db \
    AMBRIO_CHROMA_DIR=/data/chroma \
    AMBRIO_UPLOAD_TMP=/tmp/ambrio_uploads \
    CHROMA_MODE=http \
    CHROMA_HOST=chromadb \
    CHROMA_PORT=8000 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8765 \
    UVICORN_WORKERS=2

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

CMD ["sh", "-c", "uvicorn ambrio.api.server:app \
    --host $UVICORN_HOST \
    --port $UVICORN_PORT \
    --workers $UVICORN_Workers \
    --log-level info"]
