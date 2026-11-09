# Intelligent Vehicle Loan Advisor — Design It, Build It, Defend It

A capstone application that checks vehicle-loan eligibility against a lender's **published lending policy** using a **deterministic engine**. It returns Approved/Rejected with clause-level citations, works out an indicative eligible amount, shows which **catalogue** vehicles the applicant can afford, and explains each decision. The explanation comes from Gemini when it is available and passes validation; otherwise it comes from a deterministic template.

> **All lenders, policies, applicants and vehicles are synthetic.** This is an eligibility simulation. An approval gives an _indicative_ amount. It is not a binding loan sanction.

## Quick start

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
docker compose up --build     # http://localhost:3000
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
docker run --rm -v "${PWD}\backend:/w" -w /w python:3.12-slim sh -c "pip install -q pip-tools && pip-compile -q --generate-hashes --strip-extras --allow-unsafe -o requirements.lock requirements.in && pip-compile -q --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.lock requirements-dev.in"
```

### Tests

```powershell
cd backend; .venv\Scripts\python -m pytest            # SQLite; PostgreSQL/Redis tests are skipped
# Full: PostgreSQL (RLS as vla_app, one database per test) and real Redis/BullMQ
docker run -d --name vla-test-pg -e POSTGRES_PASSWORD=postgres -p 55432:5432 postgres:18.6-alpine
docker run -d --name vla-test-redis -p 56379:6379 redis:8.10.3-alpine
$env:TEST_POSTGRES_URL="postgresql://postgres:postgres@localhost:55432/postgres"; $env:TEST_REDIS_URL="redis://localhost:56379/0"
.venv\Scripts\python -m pytest
cd frontend; npm run typecheck; npm run build
```

## Demo script (capstone)

| #   | Sign in as                   | Steps                                                                                                                                                                                                  | What it shows                                                                                                                                                                                                                                                               |
| --- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Alice (applicant, Northwind) | New Application → income 120000 monthly, CIBIL 780, salaried 36 mo, obligations 10000, request 1200000 / 60 mo, cash 400000, Maharashtra → **Check eligibility**                                       | Approved at ₹12,00,000, EMI, rule trace, calculation breakdown, clause texts                                                                                                                                                                                                |
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
backend/
  app/domain/          pure rules: money (Decimal), policy schema, eligibility engine, affordability, explanation validation
  app/application/     use cases, authorization (roles + ownership + tenant), errors
  app/infrastructure/  SQLAlchemy models/DB, Gemini adapter
  app/api/             FastAPI routes (/v1), auth dependency, error contract
  app/seed/            synthetic policies (JSON with clause text) and vehicle catalogue
  app/ops/             backup / verify / restore tool for the SQLite DB and uploaded documents
  tests/               unit + end-to-end scenarios (63 tests)
frontend/
  src/app/(app)/       dashboard, applications, decision detail, vehicles, policies (incl. document review), audit
  src/app/api/bff/     backend-for-frontend proxy (HttpOnly session, CSRF checks)
  src/app/api/session/ DEV-ONLY demo sign-in
loadtest/              closed-loop load-test script and raw results
docs/                  architecture, assumptions, ADRs, versions, runbook, load-test report
.github/workflows/     CI: tests, type-check, build, image scan, compose smoke test
```

## Documentation

| Document                                     | Contents                                                                                                                                  |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Product understanding, assumptions register, diagrams, engine maths, AI boundaries, security, capacity model, phase status, defense notes |
| [docs/adr](docs/adr)                         | Architecture decision records                                                                                                             |
| [docs/VERSIONS.md](docs/VERSIONS.md)         | Verified dependency/version matrix                                                                                                        |
| [docs/RUNBOOK.md](docs/RUNBOOK.md)           | Operations, secrets rotation, backup/restore with measured drill, RPO/RTO, incident playbooks, rollback                                   |
| [docs/LOAD_TEST.md](docs/LOAD_TEST.md)       | Load-test method, measured results, bottlenecks, limitations                                                                              |
