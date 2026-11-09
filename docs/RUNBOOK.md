# Operating runbook (local / Docker Compose)

This runbook covers the capstone deployment: one API process with SQLite, plus the Next.js BFF. Production (AWS) procedures are design targets only (§7); nothing has been deployed.

## 1. Components and health

| Component           | Local process                                         | Compose service                 | Port | Health                                                                                                           |
| ------------------- | ----------------------------------------------------- | ------------------------------- | ---- | ---------------------------------------------------------------------------------------------------------------- |
| API (FastAPI)       | `uvicorn app.main:create_app --factory` in `backend/` | `api` (not published to host)   | 8000 | `GET /healthz` = process alive; `GET /readyz` = DB reachable, plus `ai` / `document_ai` = `gemini` or `disabled` |
| Web + BFF (Next.js) | `npm run dev` in `frontend/`                          | `web`                           | 3000 | `GET /login` returns 200                                                                                         |
| Data                | `backend/data/vla.db`, `backend/data/documents/`      | volume `api-data` → `/app/data` | —    | `python -m app.ops.backup verify` on the latest backup                                                           |

**Correlation IDs:** every API response has an `X-Correlation-Id`. The UI shows it as `ref …` in error messages. Search the API log for that ID to find the failing request. Unhandled errors are logged with `unhandled error cid=<id>`, and no stack trace reaches the client.

**Audit trail:** UI → _Audit_ (roles `loan_officer`, `policy_admin`, `tenant_admin`), or `GET /v1/audit-events`. Every create, evaluate, explain, policy and document action records the actor and the correlation ID.

## 2. Start, stop, reset

| Task               | Local                                                                       | Compose                                                          |
| ------------------ | --------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Start              | See README "Option A" (two terminals)                                       | `docker compose up -d --build`                                   |
| Stop               | Ctrl+C in each terminal                                                     | `docker compose stop`                                            |
| Logs               | Terminal output                                                             | `docker compose logs -f api web`                                 |
| Reset to seed data | Stop the API, **take a backup (§4)**, delete `backend/data/`, start the API | `docker compose down -v` (**deletes the volume; back up first**) |
| Change config      | Edit `.env` (repo root) or shell variables, then restart the API            | Edit `.env`, then `docker compose up -d`                         |

## 3. Configuration and secrets

| Variable                                           | Purpose                                                                                        | Rotation                                                                                                                                      |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `DEV_BFF_SHARED_SECRET`                            | Authenticates the BFF to the API in `AUTH_MODE=dev`. **Must be identical for both processes.** | Set a new value in `.env`, then restart **both** API and web. If they differ, every request returns 401 `Missing or invalid BFF credentials`. |
| `GEMINI_API_KEY`                                   | Gemini explanations, OCR and draft extraction                                                  | Create a new key in Google AI Studio, update `.env`, restart the API, check `/readyz` shows `"ai":"gemini"`, then revoke the old key.         |
| `GEMINI_MODEL`                                     | Model ID (default `gemini-2.5-flash`)                                                          | Before changing it, confirm the model is available to your key (docs/VERSIONS.md).                                                            |
| `GEMINI_TIMEOUT_MS` / `GEMINI_DOCUMENT_TIMEOUT_MS` | Explanation timeout and OCR/extraction timeout                                                 | The BFF waits up to 180 s for document calls, so keep the document timeout below that.                                                        |
| `MAX_UPLOAD_BYTES`                                 | Upload limit (10 MB)                                                                           | The BFF also caps uploads at 10 MB. Raise both together.                                                                                      |
| `INSECURE_COOKIES`                                 | Allows session cookies over plain http on localhost                                            | Never set it in a TLS deployment.                                                                                                             |

`.env` is git-ignored. Never paste keys into tickets, chat or logs.

## 4. Backup and restore

The tool is `backend/app/ops/backup.py` and has three subcommands:

- **`backup`** uses SQLite's online backup API, so the snapshot is consistent even while the API is writing (WAL mode). It also copies the uploaded originals and writes a `manifest.json` with SHA-256 checksums, `PRAGMA integrity_check` and table row counts.
- **`verify`** recomputes every checksum and runs the integrity check again.
- **`restore`** verifies first. It refuses to overwrite existing data without `--force`, removes stale `-wal`/`-shm` files, and swaps the database in atomically. Afterwards it re-checks integrity and that the row counts match the manifest.

### Local (run from `backend/`)

```powershell
.venv\Scripts\python -m app.ops.backup backup  --out backups               # prints {"backup": "backups\\<UTC stamp>"}
.venv\Scripts\python -m app.ops.backup verify  --from backups\<stamp>
# Restore: STOP THE API FIRST
.venv\Scripts\python -m app.ops.backup restore --from backups\<stamp> --force
```

Defaults are `--db data/vla.db` and `--docs data/documents`. Copy `backups/` off the machine; a backup on the same disk does not protect against disk loss.

**Scheduling (Windows Task Scheduler)**, for example hourly:

```powershell
schtasks /Create /SC HOURLY /TN "VLA backup" /TR "cmd /c cd /d D:\HCL_\capstone-vehicle-intelligent-system\backend && .venv\Scripts\python -m app.ops.backup backup --out backups"
```

The tool does not delete old backups. Prune them by age yourself, keeping at least the last 24 hourly and 7 daily backups.

### Docker Compose

```powershell
docker compose exec api python -m app.ops.backup backup --db /app/data/vla.db --docs /app/data/documents --out /app/data/backups
docker compose cp api:/app/data/backups ./backups
# Restore: stop the API, run the tool in a one-off container on the same volume, then start the API
docker compose stop api
docker compose run --rm --no-deps api python -m app.ops.backup restore --from /app/data/backups/<stamp> --db /app/data/vla.db --docs /app/data/documents --force
docker compose start api
```

The Compose procedure has not been executed yet, because Compose itself is still unverified (README).

### Restore drill (measured 2026-11-09, Windows 11, 20 logical CPUs, local SSD)

| Dataset                                                         | DB size | Backup  | Verify  | Restore (incl. post-checks) |
| --------------------------------------------------------------- | ------- | ------- | ------- | --------------------------- |
| Live demo DB (seed only)                                        | 4 KB    | 0.018 s | 0.003 s | 0.008 s                     |
| Disposable DB: 3,000 evaluated applications, 6,000 audit events | 20.7 MB | 0.26 s  | 0.08 s  | 0.18 s                      |

Both restores reproduced the manifest row counts and passed `integrity_check`. `tests/test_backup.py` covers two more cases:

- Data written after a backup is gone after restore.
- A tampered backup fails verification.

Run the drill at least once per release: restore into a scratch path (`--db scratch\vla.db --docs scratch\documents`) and compare the printed counts.

### PostgreSQL (full stack)

```powershell
$f = "docker-compose.full.yml"
docker compose -f $f exec -T db pg_dump -U vla_owner -d vla -Fc -f /tmp/vla.dump
docker compose -f $f cp db:/tmp/vla.dump .\backups\vla-$(Get-Date -Format yyyyMMddTHHmmss).dump
# Restore drill into a scratch database (never over the live one while the API is running)
docker compose -f $f exec -T db createdb -U vla_owner vla_restore_drill
docker compose -f $f exec -T db pg_restore -U vla_owner -d vla_restore_drill --no-owner --exit-on-error /tmp/vla.dump
```

The uploaded originals live in the `docs-data` volume. Copy them alongside the dump (`docker compose -f $f cp api:/app/data/documents .\backups\documents`).

**Drill measured 2026-11-09 on the full stack** (small dataset):

- The dump took 0.45 s and the restore 0.80 s.
- Row counts matched: 1 application, 1 decision, 8 audit events, 2 documents.
- All 9 `tenant_isolation` RLS policies and the Alembic version (`0004`) were restored.

The runtime role `vla_app` is cluster-level and is not part of the dump, but its table grants are. On a new server, create the role first (`deploy/postgres/init-app-role.sh`), then run `pg_restore`, so the grants restore with the data.

### Recovery objectives

| Environment                   | RPO (data loss)                           | RTO (downtime)                 | Basis                                                                                                                                                                                              |
| ----------------------------- | ----------------------------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Local / Compose               | Backup interval (1 h if scheduled hourly) | < 5 min (stop, restore, start) | The restore itself measured well under 1 s; the rest is operator time                                                                                                                              |
| Production target (not built) | ≤ 5 min                                   | ≤ 1 h                          | RDS/Aurora automated backups with point-in-time recovery; S3 versioning plus cross-region replication for documents; restore into a new instance, then repoint. **Targets only; never exercised.** |

## 5. Incident playbooks

| Symptom                                                        | Likely cause                                                                                                                   | Action                                                                                                                                                                                                                                                                                                               |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Every page shows "Sign in required" or 401                     | BFF and API secrets differ, or the session cookie was not set over http                                                        | Make `DEV_BFF_SHARED_SECRET` identical in both processes; for local http set `INSECURE_COOKIES=true`; sign in again                                                                                                                                                                                                  |
| UI shows `BACKEND_UNAVAILABLE` (502)                           | API down, or `BACKEND_URL` is wrong                                                                                            | Check `GET /healthz`, then restart the API                                                                                                                                                                                                                                                                           |
| Explanations say _template_ with a fallback reason             | Gemini key missing, quota exhausted, timeout, or the AI draft failed validation                                                | **No action needed for correctness:** decisions and amounts are deterministic and unaffected. Check `/readyz` and the `fallback_reason`. Fix the key or quota, then click _Regenerate_ on the explanation                                                                                                            |
| Uploaded document stuck in `TEXT_FAILED`                       | Gemini unavailable, or the output failed checks (page gaps, truncation)                                                        | Open the document, read the error, then click _Retry transcription_. For very long scans, split the PDF (limit: 60 pages)                                                                                                                                                                                            |
| `EXTRACTION_FAILED`                                            | Gemini error or non-JSON output                                                                                                | Click _Extract draft rules_ again, or write the policy JSON manually and submit it through the same review form (clause grounding still applies)                                                                                                                                                                     |
| `CLAUSES_NOT_GROUNDED` (422) when creating a draft             | A clause's text is not on its cited page (OCR error, a clause spanning a page break, or an edited quote)                       | Copy the clause text exactly from the transcribed page; split clauses that span pages; fix OCR errors only by re-transcribing                                                                                                                                                                                        |
| `POLICY_CONFLICT` (409) on publish                             | Another published policy for the same product starts on the same date                                                          | Choose a different `effective_from`, or retire the old version (manual DB task for now)                                                                                                                                                                                                                              |
| Applications return `NEEDS_REVIEW` with `NO_APPLICABLE_POLICY` | No published policy is effective on the evaluation date                                                                        | Publish a policy covering today; already-evaluated decisions are unaffected                                                                                                                                                                                                                                          |
| _Verify by replay_ reports `reproducible: false`               | The policy content hash or engine version differs from the recorded one                                                        | Treat it as an incident: do not change decisions. Check whether `ENGINE_VERSION` changed in a deployment, or whether a DB row was edited outside the API (compare against the latest backup)                                                                                                                         |
| `database is locked`, or write latency spikes                  | SQLite single-writer contention (see LOAD_TEST.md)                                                                             | Expected above about 8 concurrent writers. Reduce concurrency for the demo; production uses PostgreSQL                                                                                                                                                                                                               |
| Suspected cross-tenant access                                  | —                                                                                                                              | Collect the correlation IDs and audit events, then check the user's memberships table. The API returns 404 for other tenants' objects by design. File a security incident; do not delete data                                                                                                                        |
| Document stuck in `PROCESSING` (full stack)                    | Worker down, queue Redis down, or the job is waiting for its next backoff attempt                                              | `docker compose -f docker-compose.full.yml ps worker`, then `exec worker python -m app.worker.admin counts`. The outbox keeps unpublished jobs while Redis is down and relays them once it is back. After the 4th failed attempt the document shows `TEXT_FAILED`/`EXTRACTION_FAILED` and can be retried from the UI |
| Failed jobs piling up                                          | Gemini outage or quota, or a malformed payload                                                                                 | `exec worker python -m app.worker.admin failed [--tenant <id>]`. Replay one with `retry --job <id>`; replaying a stale job is a safe no-op. Prefer the UI Retry, which creates a fresh outbox event                                                                                                                  |
| Explanations fall back with _Tenant AI budget exhausted_       | The per-tenant daily AI budget (`AI_DAILY_BUDGET_PER_TENANT`) was reached, or the cache Redis is unreachable (AI fails closed) | Decisions are unaffected. Raise the budget deliberately (financial configuration change: record it in the audit trail), or restore the cache Redis                                                                                                                                                                   |
| Uploads return 429 `RATE_LIMITED`                              | `UPLOADS_PER_MINUTE_PER_TENANT` exceeded                                                                                       | Wait one minute; raise the limit only for a known bulk import                                                                                                                                                                                                                                                        |
| SSO: `/login?error=state_mismatch`                             | Login took longer than 10 minutes, the callback was replayed, or cookies are blocked                                           | Start sign-in again. Repeated occurrences from one user can indicate a login-CSRF attempt                                                                                                                                                                                                                            |
| SSO: every API call returns 401 after sign-in                  | Token rejected by the API (issuer, audience/`client_id`, `token_use` or scope mismatch) or the identity is not linked          | Compare `OIDC_ISSUER`/`OIDC_AUDIENCE` on the API with the IdP. Run `python -m app.ops.identities list`. An unlinked subject returns 403, not 401                                                                                                                                                                     |
| SSO: users signed out when the IdP was briefly down            | By design: refresh fails closed and the session is removed                                                                     | Users sign in again once the IdP is back                                                                                                                                                                                                                                                                             |

## 6. Release and rollback (local / Compose)

1. Run the CI checks locally first: `pytest`, `npm run typecheck`, `npm run build`. CI repeats them, then builds and scans the images (`.github/workflows/ci.yml`).
2. **Take a backup (§4) before every release.** Schema changes go through Alembic migrations (`backend/migrations`). The SQLite demo applies them on API startup; the full stack applies them in the one-shot `migrate` service with the owner role. Migrations are forward-only in operation: roll back by restoring the pre-release backup, not by `alembic downgrade`.
3. **Rollback:**
   1. Check out the previous tag: `git checkout <tag>`.
   2. Rebuild: `docker compose up -d --build`.
   3. If the new release wrote data the old one cannot read, restore the pre-release backup.

Decisions are immutable snapshots, so a code rollback never changes a recorded outcome. Replay reports any engine-version mismatch.

## 7. Production reference (design only)

These are not implemented in this repository, because the Kubernetes and Terraform work was deferred.

- **Probes and scaling:** liveness on `/healthz`, readiness on `/readyz`, an HPA on CPU, and a PDB with `minAvailable: 1`.
- **Backups:** RDS PITR, S3 versioning, and AWS Backup vault lock.
- **Secrets:** Secrets Manager with rotation, mounted through IRSA.
- **Alerts:** API 5xx rate, p95 latency, AI fallback rate per tenant, and the count of documents stuck in `*_FAILED`.
