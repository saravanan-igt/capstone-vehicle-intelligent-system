# Dependency and version matrix

Pinned versions are in `backend/requirements.lock`, `backend/requirements-dev.lock` and `frontend/package-lock.json`. Rows marked **Pending** have not been checked against the official source yet. Do not treat them as verified.

| Component                 | Pinned                                                                               | Runtime requirement         | Verified                                | Source                                           |
| ------------------------- | ------------------------------------------------------------------------------------ | --------------------------- | --------------------------------------- | ------------------------------------------------ |
| Python                    | 3.12 (`python:3.12-slim`)                                                            | —                           | 2026-11-07 (local 3.12)                 | https://www.python.org/downloads/                |
| FastAPI                   | 0.162.0                                                                              | Python ≥ 3.9                | 2026-11-07 (PyPI)                       | https://pypi.org/project/fastapi/                |
| Starlette                 | 1.10.0 (transitive)                                                                  | —                           | from lockfile                           | https://pypi.org/project/starlette/              |
| Uvicorn                   | 0.54.0                                                                               | —                           | 2026-11-07 (PyPI)                       | https://pypi.org/project/uvicorn/                |
| Pydantic                  | 2.14.3                                                                               | —                           | 2026-11-07 (PyPI)                       | https://pypi.org/project/pydantic/               |
| SQLAlchemy                | 2.1.8                                                                                | —                           | 2026-11-07 (PyPI)                       | https://pypi.org/project/SQLAlchemy/             |
| google-genai (Gemini SDK) | 3.0.0                                                                                | —                           | 2026-11-07 (PyPI)                       | https://pypi.org/project/google-genai/           |
| Gemini model              | `gemini-2.5-flash` (default, configurable via `GEMINI_MODEL`)                        | —                           | **Pending**: confirm it is still listed | https://ai.google.dev/gemini-api/docs/models     |
| pytest / httpx            | 9.2.0 / 0.28.1                                                                       | —                           | 2026-11-07 (PyPI)                       | https://pypi.org/project/pytest/                 |
| Node.js                   | 24 (`node:24-alpine`)                                                                | Next.js needs ≥ 20.9        | 2026-11-07 (local 24)                   | https://nodejs.org/en/about/previous-releases    |
| Next.js                   | 16.4.5                                                                               | Node ≥ 20.9                 | 2026-11-07 (npm)                        | https://www.npmjs.com/package/next               |
| React / React DOM         | 19.3.1                                                                               | —                           | 2026-11-07 (npm)                        | https://www.npmjs.com/package/react              |
| TypeScript                | 5.9.3 (`strict`)                                                                     | —                           | 2026-11-07 (npm)                        | https://www.npmjs.com/package/typescript         |
| BullMQ (Python)           | 3.5.0                                                                                | Python ≥ 3.10; Redis ≥ 6.2  | 2026-11-09 (PyPI + installed API)       | https://pypi.org/project/bullmq/                 |
| redis-py                  | 8.1.0                                                                                | Python ≥ 3.10               | 2026-11-09 (PyPI)                       | https://pypi.org/project/redis/                  |
| Redis server (image)      | `redis:8.10.3-alpine`                                                                | ≥ 6.2 for BullMQ            | 2026-11-09 (Docker Hub)                 | https://hub.docker.com/_/redis                   |
| PostgreSQL (image)        | `postgres:18.6-alpine`                                                               | —                           | 2026-11-09 (Docker Hub)                 | https://hub.docker.com/_/postgres                |
| psycopg (binary)          | 3.3.8                                                                                | Python ≥ 3.10               | 2026-11-09 (PyPI)                       | https://pypi.org/project/psycopg/                |
| Alembic                   | 1.20.1                                                                               | SQLAlchemy ≥ 2.0            | 2026-11-09 (PyPI)                       | https://pypi.org/project/alembic/                |
| PyJWT (crypto)            | 2.15.1                                                                               | —                           | 2026-11-09 (PyPI)                       | https://pypi.org/project/PyJWT/                  |
| prometheus-client         | 0.26.0                                                                               | —                           | 2026-11-09 (PyPI)                       | https://pypi.org/project/prometheus-client/      |
| jose (BFF, npm)           | 6.2.16                                                                               | —                           | 2026-11-09 (npm)                        | https://www.npmjs.com/package/jose               |
| redis (BFF, npm)          | 6.3.1                                                                                | Node ≥ 20                   | 2026-11-09 (npm)                        | https://www.npmjs.com/package/redis              |
| mock-oauth2-server (test) | `ghcr.io/navikt/mock-oauth2-server:6.1.4`                                            | test only, never production | 2026-11-09 (GitHub releases)            | https://github.com/navikt/mock-oauth2-server     |
| scikit-learn              | 1.9.1                                                                                | Python ≥ 3.10               | 2026-11-09 (PyPI + training run)        | https://pypi.org/project/scikit-learn/           |
| pandas / numpy / joblib   | 3.1.1 / 2.5.4 / 1.6.0                                                                | Python ≥ 3.11               | 2026-11-09 (PyPI)                       | https://pypi.org/project/pandas/                 |
| Gemini embedding model    | `gemini-embedding-001` (768 dims, task types)                                        | —                           | 2026-11-09 (API docs)                   | https://ai.google.dev/gemini-api/docs/embeddings |
| Streamlit                 | 1.67.0 (`streamlit_app/requirements.lock`)                                           | Python ≥ 3.10               | 2026-11-09 (PyPI + local run)           | https://pypi.org/project/streamlit/              |
| Notebook tooling          | matplotlib 3.11.2, seaborn 0.13.2, nbformat 5.11.1, nbclient 0.11.0, ipykernel 7.4.0 | local only                  | 2026-11-09 (PyPI)                       | https://pypi.org/project/nbclient/               |

The model artifact is tied to the scikit-learn version recorded in `models/model_card.json`. Upgrading scikit-learn requires retraining (`python -m app.ml.train`) and re-running the notebooks.

## Open items

- **Base image tags:** the images use minor tags (`python:3.12-slim`, `node:24-alpine`). Before any production build, pin them to digests (`image@sha256:…`).
- **Backend lockfiles:** regenerated with hashes on 2026-11-09 using `pip-compile` inside `python:3.12-slim`, so they target the container platform. Installing `requirements-dev.lock` on Windows may fail, because it pins `uvloop`, which is Linux-only, and leaves out `colorama`.
