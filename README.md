# Intelligent Vehicle Loan Advisor — Design It, Build It, Defend It

A capstone application that checks vehicle-loan eligibility against a lender's **published lending policy**. It combines a **machine-learning model trained on historical loan data** with a **deterministic policy engine**:

- It returns Approved or Rejected, with clause-level citations.
- It calculates the sanctioned amount, shows the calculation, and shortlists the **catalogue** vehicles the applicant can afford.
- It answers questions about a vehicle from its brochure, and says "I don't know" when the brochure does not cover it.
- It explains each decision using policy text retrieved from a **vector index**, with the sources shown.

There are two frontends: **Streamlit** (the applicant journey from the brief) and a **Next.js** dashboard (applications, policy administration, audit).

> **All lenders, policies, applicants, loan history and vehicles are synthetic.** This is an eligibility simulation. An approval gives an _indicative_ amount. It is not a binding loan sanction.

## Capstone brief coverage

| Brief requirement                                                                                                             | Where                                                                                                                                                                                            |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 5.1 Model trained on historical loan data; EDA and preparation; comparison of more than one approach; business-fit evaluation | [notebooks/01_eda.ipynb](notebooks/01_eda.ipynb), [notebooks/02_model_training.ipynb](notebooks/02_model_training.ipynb), [docs/EVALUATION.md](docs/EVALUATION.md), `backend/app/ml/`, `models/` |
| 5.2 Specific sanctioned amount, within repayment capacity and policy limits, with the calculation shown                       | `POST /loan-amount`; deterministic engine `backend/app/domain/eligibility.py`                                                                                                                    |
| 5.3 Vehicles within budget, EMI estimate, filters and sorting, guidance when nothing fits                                     | `POST /vehicles`, `backend/app/application/advisor.py`                                                                                                                                           |
| 5.4 Vehicle details and grounded Q&A that says "I don't know"                                                                 | `GET /vehicles/{id}`, `POST /vehicles/{id}/ask`, `backend/app/rag/`                                                                                                                              |
| 5.5 Explanations from retrieved policy text, with sources, naming the threshold and the applicant's value                     | `POST /explain`; retrieved sources stored per explanation                                                                                                                                        |
| 6 Policy documents with sections, exceptions, documents and applicant-specific rules; 25+ vehicles with brochures             | `data/documents/policy/`, `data/documents/vehicles/`, [docs/DATA.md](docs/DATA.md)                                                                                                               |
| Endpoints `/predict`, `/loan-amount`, `/vehicles`, `/vehicles/{id}`, `/explain`, `/health`                                    | `backend/app/api/brief.py` (OpenAPI at `/docs`)                                                                                                                                                  |
| Streamlit frontend                                                                                                            | `streamlit_app/`                                                                                                                                                                                 |
| Sample scenarios 4.1 and 4.2                                                                                                  | Automated in `backend/tests/test_advisor.py`                                                                                                                                                     |

Beyond the brief, the project also provides:

- multi-tenant lenders with PostgreSQL row-level security;
- OIDC single sign-on;
- scanned-policy ingestion with human review;
- immutable decision snapshots with replay;
- outbox and BullMQ background jobs;
- metrics;
- CI with image scanning.

## API endpoints (brief)

All `/v1` endpoints need an authenticated identity. In local dev mode (`AUTH_MODE=dev`), both frontends send `X-Dev-User` and `X-Dev-Secret` from the server side; for interactive testing in `/docs` or `curl`, the brief endpoints below default to the demo applicant (`u-alice`) when those headers are omitted.

| Endpoint                  | Purpose                                                                                                                                                                                                                                                                                                             |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /health`             | Status, loaded model version, active vector index, LLM availability                                                                                                                                                                                                                                                 |
| `POST /predict`           | Applicant details in; returns the model prediction and confidence, the final decision and the reasons (with the policy clause, the threshold and the applicant's value). Records an immutable decision                                                                                                              |
| `POST /loan-amount`       | `{decision_id}` or `{applicant}`; returns the sanctioned amount, EMI, rate, tenure, fee, the calculation steps and the clauses applied                                                                                                                                                                              |
| `POST /vehicles`          | `{decision_id}` or `{sanctioned_amount, down_payment, tenure_months, annual_rate}`, with filters (`body_type`, `fuel_type`, `make`, `min_seating`, `min_price`, `max_price`, `max_emi`) and `sort` (`best_fit`, `price`, `emi`). Returns the shortlist with EMI and upfront cash, plus `guidance` when nothing fits |
| `GET /vehicles/{id}`      | Specifications, features, variants, price breakdown and brochure                                                                                                                                                                                                                                                    |
| `POST /vehicles/{id}/ask` | `{question}`; returns an answer grounded in the brochure, with sources, or "I don't know"                                                                                                                                                                                                                           |
| `POST /explain`           | `{decision_id}`; returns an explanation grounded in retrieved policy text, plus the retrieved sources                                                                                                                                                                                                               |

The full tenant-aware API is under `/v1`. It covers applications, decisions, replay, policies, document ingestion and audit.

## Screenshots (Streamlit, Docker Compose stack, no Gemini key)

| Eligibility (brief 4.1)                                    | Sanctioned amount and calculation                                  |
| ---------------------------------------------------------- | ------------------------------------------------------------------ |
| ![Eligibility](docs/screenshots/streamlit-eligibility.png) | ![Loan amount](docs/screenshots/streamlit-loan-amount.png)         |
| **Vehicles within budget**                                 | **Vehicle details**                                                |
| ![Vehicles](docs/screenshots/streamlit-vehicles.png)       | ![Vehicle details](docs/screenshots/streamlit-vehicle-details.png) |
| **Vehicle Q&A: grounded answer, then "I don't know"**      | **Rejection (brief 4.2): threshold vs actual value**               |
| ![Vehicle Q&A](docs/screenshots/streamlit-vehicle-qa.png)  | ![Rejected](docs/screenshots/streamlit-rejected.png)               |
| **Explanation with retrieved policy sources**              |                                                                    |
| ![Explanation](docs/screenshots/streamlit-explanation.png) |                                                                    |

## Quick start

### One command (Python 3.12+ and Node.js 20.9+)

```powershell
python run.py            # creates .env, installs deps, checks model/index, migrates/seeds, builds, runs, opens the browser
python run.py --help     # --dev, --test, --skip-install, --no-browser, --reset-db, --no-streamlit, ports
```

This serves the Streamlit advisor at http://localhost:8501, the Next.js dashboard at http://localhost:3000 and the API docs at http://127.0.0.1:8000/docs. Ctrl+C stops everything.

If you already have a local database from an earlier version, run `python run.py --reset-db` once. Published policies are immutable, so the updated policy documents are only seeded into a fresh database.

### Reproduce the data, model, index and notebooks

```powershell
backend\.venv\Scripts\pip install -r requirements.txt        # repository root: backend + Streamlit + notebook tools
backend\.venv\Scripts\python data\generate_loans.py; backend\.venv\Scripts\python data\build_catalogue.py
cd backend; .venv\Scripts\python -m app.ml.train; .venv\Scripts\python -m app.rag.ingest; cd ..
backend\.venv\Scripts\python notebooks\build_notebooks.py
```

`app.rag.ingest` also builds a Gemini embedding index when `GEMINI_API_KEY` is set. At runtime the API uses the Gemini index if both the key and the index are present, and otherwise falls back to the local index.

### Option A: local processes (verified)

```powershell
# 0. Once, from the repo root: create .env and set GEMINI_API_KEY (optional; without it AI falls back/disabled)
Copy-Item .env.example .env

# 1. Backend (Python 3.12) - terminal 1
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.in   # the .lock files are Linux/container-only
$env:DEV_BFF_SHARED_SECRET="local-dev-only"   # shell variables take precedence over .env
.venv\Scripts\python -m uvicorn app.main:create_app --factory --port 8000 --env-file ..\.env
# Health: http://127.0.0.1:8000/readyz (shows whether Gemini is enabled) | OpenAPI: http://127.0.0.1:8000/docs

# 2. Frontend (Node >= 20.9) - terminal 2, from the repo root; use npm.cmd if script execution is restricted
cd frontend
npm ci
$env:BACKEND_URL="http://127.0.0.1:8000"; $env:DEV_BFF_SHARED_SECRET="local-dev-only"; $env:INSECURE_COOKIES="true"
npm run dev        # http://localhost:3000 -> pick a demo user (Alice = applicant, Priya = policy admin)
```

The two `DEV_BFF_SHARED_SECRET` values must match. Data is stored in `backend/data/` (SQLite database and uploaded policy documents); delete that folder to reset to the seed data.

### Option B: Docker Compose, SQLite demo stack (verified 2026-11-09)

```powershell
Copy-Item .env.example .env   # set DEV_BFF_SHARED_SECRET; optionally GEMINI_API_KEY
docker compose up --build     # API http://localhost:8000/docs, Next.js http://localhost:3000, Streamlit http://localhost:8501
```

### Option C: production-like stack (verified 2026-11-09)

This stack runs PostgreSQL 18 with row-level security, separate cache and queue Redis instances, and a BullMQ worker. Uploaded documents are processed in the background.

```powershell
# .env additionally needs POSTGRES_OWNER_PASSWORD and POSTGRES_APP_PASSWORD (see .env.example)
docker compose -f docker-compose.full.yml up --build
```

The flow on startup and at runtime:

- `migrate` runs once as the owner role: it migrates and seeds.
- `api` connects as `vla_app`, which is subject to RLS.
- `worker` relays the outbox to BullMQ and processes jobs.
- **Metrics:** the API serves `/metrics` and the worker serves `:9100/metrics`. Neither is published to the host.
- **Failed jobs:** `docker compose -f docker-compose.full.yml exec worker python -m app.worker.admin failed`.

### Single sign-on (`AUTH_MODE=oidc`, Amazon Cognito or any OIDC provider)

1. Create a Cognito user pool with **MFA required**, plus an app client (confidential, Authorization Code grant, scopes `openid email profile`, callback `<APP_BASE_URL>/api/auth/callback`).
2. In `.env`, set `AUTH_MODE=oidc` and the `OIDC_*` and `APP_BASE_URL` variables (see `.env.example`). Use `OIDC_TOKEN_USE=access` for Cognito.
3. Link each IdP user to a local user. Authorisation still comes from tenant memberships, never from token claims:
   `python -m app.ops.identities link --issuer <OIDC_ISSUER> --subject <sub> --user u-alice`

Local verification without Cognito uses a mock IdP (test only):

```powershell
docker run -d -p 8080:8080 ghcr.io/navikt/mock-oauth2-server:6.1.4
# issuer http://localhost:8080/default; link demo users with: python -m app.ops.identities link-demo --issuer http://localhost:8080/default
```

The mock's tokens need `aud` = your client id and the required scope. Configure them through its `JSON_CONFIG` token callbacks.

### Regenerate hashed Linux lockfiles

```powershell
docker run --rm -v "${PWD}:/src" python:3.12-slim sh -c "pip install -q pip-tools && cd /src/backend && pip-compile -q --generate-hashes --strip-extras --allow-unsafe -o requirements.lock requirements.in && pip-compile -q --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.lock requirements-dev.in && cd /src/streamlit_app && pip-compile -q --generate-hashes --strip-extras --allow-unsafe -o requirements.lock requirements.txt"
```

The backend image is built from the repository root (`docker build -f backend/Dockerfile .`), because it bakes in `data/`, `models/` and `vectorstore/`.

### Tests

```powershell
python -m pytest                          # from repo root (or `cd backend; python -m pytest`; SQLite by default)
# Full: PostgreSQL (RLS as vla_app, one database per test) and real Redis/BullMQ
docker run -d --name vla-test-pg -e POSTGRES_PASSWORD=postgres -p 55432:5432 postgres:18.6-alpine
docker run -d --name vla-test-redis -p 56379:6379 redis:8.10.3-alpine
$env:TEST_POSTGRES_URL="postgresql://postgres:postgres@localhost:55432/postgres"; $env:TEST_REDIS_URL="redis://localhost:56379/0"
.venv\Scripts\python -m pytest
cd frontend; npm run typecheck; npm run build
```

## Demo script (capstone)

### Streamlit advisor (http://localhost:8501)

| #   | Steps                                                                                                                                                                               | What it shows                                                                                                                                                 |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1  | **Eligibility** tab with the defaults (brief scenario 4.1: income 85,000; score 745; 72 months; EMIs 12,000; 1 active loan; request 8,00,000 over 60 months; down payment 1,50,000) | Approved. Model probability and confidence, the policy threshold, and the main factors                                                                        |
| S2  | **Loan amount** tab                                                                                                                                                                 | Sanctioned INR 8,00,000, EMI, rate and tenure, the step-by-step calculation and the clauses applied                                                           |
| S3  | **Vehicles** tab: filter `suv`, sort by EMI; then filter `mpv`                                                                                                                      | The shortlist with EMI and upfront cash; for MPVs, "nothing fits" guidance (raise the down payment, take a longer tenure, request more, or relax the filters) |
| S4  | Pick a vehicle, then open **Vehicle details**; ask "What is the ground clearance?" and then "Does it have a sunroof?"                                                               | Specs, variants and price breakdown; a grounded answer with its source, then "I don't know"                                                                   |
| S5  | **Eligibility** with income 22,000, score 580, 12 months, EMIs 9,000, 2 active loans (scenario 4.2), then **Explanation**                                                           | Rejected. "Your value 580; required >= 650 (NW-2.1)", the income reason, and the retrieved policy sources                                                     |

### Next.js dashboard (http://localhost:3000)

| #   | Sign in as                   | Steps                                                                                                                                                                                                  | What it shows                                                                                                                                                                                                                                                               |
| --- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Alice (applicant, Northwind) | New Application → income 120000 monthly, CIBIL 780, salaried 36 mo, obligations 10000, 1 active loan, request 1200000 / 60 mo, cash 400000, Maharashtra → **Check eligibility**                        | Approved at ₹12,00,000, EMI, rule trace, calculation breakdown, clause texts                                                                                                                                                                                                |
| 2   |                              | On the same page, open **Vehicles you can afford**, filter SUV, compare 3 vehicles                                                                                                                     | LTV per vehicle, required contribution, fees, shortfall. A missing insurance cost shows as **Unverified**, never as zero. A stale price is flagged.                                                                                                                         |
| 3   |                              | Click **Explain this decision**                                                                                                                                                                        | Uses the AI explanation if it is validated against the recorded decision; otherwise falls back to the template                                                                                                                                                              |
| 4   |                              | Create a new application with credit score 600                                                                                                                                                         | Rejected, with citation NW‑2.1 and the clause text                                                                                                                                                                                                                          |
| 5   |                              | Request 1500000 with income 50000 / obligations 5000                                                                                                                                                   | Approved, but limited by repayment capacity                                                                                                                                                                                                                                 |
| 6   |                              | Set cash to 0                                                                                                                                                                                          | Approved, but no vehicle is affordable                                                                                                                                                                                                                                      |
| 7   |                              | Save a draft with only the credit score, then evaluate                                                                                                                                                 | INCOMPLETE status with the missing fields listed. No decision is made up.                                                                                                                                                                                                   |
| 8   | Ben (Southbay)               | Open Alice's application URL                                                                                                                                                                           | 404: tenant isolation                                                                                                                                                                                                                                                       |
| 9   | Priya (policy admin)         | Policies → upload a modified policy JSON (new version with a later effective date) → publish                                                                                                           | Drafts never affect decisions. After publishing, earlier decisions still pass **Verify by replay**.                                                                                                                                                                         |
| 10  | Priya (policy admin)         | Policies → **Upload scanned policy** (PDF/PNG/JPEG) → compare the transcribed pages with the original → **Extract draft rules** → fix any flagged issues → confirm → **Create policy draft** → publish | Gemini OCR and extraction produce untrusted drafts. A clause that is not quoted verbatim from its page is rejected (`CLAUSES_NOT_GROUNDED`). Nothing affects decisions until it is published. Without a Gemini key, the document stays in `TEXT_FAILED` and can be retried. |

## Repository layout

```
data/
  raw/                 loan_applications.csv (synthetic history), vehicles.json/.csv (catalogue)
  processed/           cleaned training data
  documents/policy/    lending policies: prose (.md) + executable rules with verbatim clauses (.json)
  documents/vehicles/  one brochure per vehicle model (26)
  generate_loans.py, build_catalogue.py   seeded generators
notebooks/             01_eda, 02_model_training (executed, with outputs) + build_notebooks.py
models/                eligibility_model.joblib + model_card.json (metrics, threshold, hash)
vectorstore/           embedding index (local TF-IDF; Gemini when built with a key)
backend/
  app/domain/          pure rules: money (Decimal), policy schema, eligibility engine, affordability, explanation validation
  app/application/     use cases (services, advisor), authorization (roles + ownership + tenant), errors
  app/ml/              features, training pipeline, model loading and scoring
  app/rag/             chunking, embeddings, vector store, knowledge base, ingest, vehicle Q&A
  app/infrastructure/  SQLAlchemy models/DB, Gemini adapters (explain, answer, OCR), storage, OIDC, quotas, metrics
  app/api/             FastAPI routes: brief endpoints (brief.py) and /v1, auth dependency, error contract
  app/seed/            loads the synthetic tenants, users, policies and catalogue
  app/ops/ app/worker/ migrations, backup/restore, identity linking; BullMQ worker
  tests/               unit, end-to-end, brief scenarios, ML/RAG integrity (115 tests)
streamlit_app/         Streamlit frontend (applicant journey)
frontend/
  src/app/(app)/       dashboard, applications, decision detail, vehicles, policies (incl. document review), audit
  src/app/api/bff/     backend-for-frontend proxy (HttpOnly session, CSRF checks)
  src/app/api/session/ DEV-ONLY demo sign-in
loadtest/              closed-loop load-test script and raw results
docs/                  architecture, data, evaluation, ADRs, versions, runbook, load-test report
requirements.txt       one-environment install (backend + Streamlit + notebooks)
.github/workflows/     CI: tests (SQLite + PostgreSQL/Redis), type-check, build, image scan, compose smoke tests
```

## Documentation

| Document                                     | Contents                                                                                                                                  |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Product understanding, assumptions register, diagrams, engine maths, AI boundaries, security, capacity model, phase status, defense notes |
| [docs/EVALUATION.md](docs/EVALUATION.md)     | Error costs, model comparison and choice, test metrics, policy interplay, sanctioned-amount method, retrieval thresholds, brief scenarios |
| [docs/DATA.md](docs/DATA.md)                 | Datasets, documents, injected data defects and how they are handled, provenance, regeneration                                             |
| [docs/adr](docs/adr)                         | Architecture decision records                                                                                                             |
| [docs/VERSIONS.md](docs/VERSIONS.md)         | Verified dependency/version matrix                                                                                                        |
| [docs/RUNBOOK.md](docs/RUNBOOK.md)           | Operations, secrets rotation, backup/restore with measured drill, RPO/RTO, incident playbooks, rollback                                   |
| [docs/LOAD_TEST.md](docs/LOAD_TEST.md)       | Load-test method, measured results, bottlenecks, limitations                                                                              |
