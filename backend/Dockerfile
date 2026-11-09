FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/requirements.lock ./
RUN pip install -r requirements.lock

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
# Read-only assets: policy and vehicle documents, catalogue, saved model, vector index.
# Kept outside /app/data so the runtime data volume never hides them.
COPY data/raw/vehicles.json ./assets/data/raw/vehicles.json
COPY data/documents ./assets/data/documents
COPY models ./assets/models
COPY vectorstore ./assets/vectorstore
ENV ASSETS_DIR=/app/assets
RUN useradd --uid 10001 --create-home appuser && mkdir -p /app/data/documents && chown -R appuser /app/data
USER 10001

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
