FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////tmp/eleicoes2026.db \
    BACKEND_URL=http://127.0.0.1:8000 \
    DATA_MODE=official_live \
    PUBLIC_DEMO=true \
    ADMIN_ENABLED=false \
    EMBEDDING_PROVIDER=hash \
    MONTE_CARLO_SEED=42

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && useradd --create-home --uid 1000 appuser \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .
RUN chmod +x deploy/start-space.sh

USER appuser

EXPOSE 7860

CMD ["sh", "deploy/start-space.sh"]
