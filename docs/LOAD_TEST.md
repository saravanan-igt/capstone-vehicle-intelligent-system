# Load test: method, measured results, bottlenecks

**Everything below was measured locally on one machine. It is not a production capacity claim.** The capacity targets in ARCHITECTURE.md §7 remain assumptions.

## Method

- **Script:** [`loadtest/load_test.py`](../loadtest/load_test.py). This is a closed-loop test: each worker thread loops one applicant journey as fast as the server allows.
  1. `POST /v1/applications`
  2. `POST /v1/applications/{id}/evaluate`
  3. If the decision is approved, `GET /v1/decisions/{id}/vehicles` (assesses all 16 catalogue vehicles)
  4. `GET /v1/vehicles?limit=20`
- **Inputs:** randomised synthetic applicants (income, score, tenure, obligations, down payment), so the mix contains approvals, rejections and capacity-limited approvals.
- **Target:** a disposable API on port 8001 with its own SQLite database. Settings: `AI_ENABLED=false`, a single `uvicorn` process (default: 1 worker), SQLite in WAL mode with `busy_timeout=5000`. The BFF was bypassed (dev auth headers), so BFF overhead is not included.
- **Machine:** Windows 11, Intel 64 (20 logical CPUs), 31.7 GB RAM, Python 3.12.3. The load generator and the server shared the same machine.
- **Runs:** 1 worker for 15 s; 8 workers for 30 s; 16 workers for 30 s (2026-11-09). Raw results are in `loadtest/results-w1.json`, `results-w8.json` and `results-w16.json`.

Reproduce:

```powershell
# terminal 1 - disposable API (fresh DB, AI off)
cd backend
$env:DATABASE_URL="sqlite:///./data/loadtest.db"; $env:DOCUMENT_STORAGE_DIR="./data/loadtest-docs"
$env:AI_ENABLED="false"; $env:DEV_BFF_SHARED_SECRET="loadtest"
.venv\Scripts\python -m uvicorn app.main:create_app --factory --port 8001
# terminal 2
.venv\Scripts\python ..\loadtest\load_test.py --secret loadtest --workers 8 --duration 30 --out ..\loadtest\results.json
```

## Results

| Workers | Journeys | Requests | Throughput (req/s) | Evaluations/s | Errors |
| ------- | -------- | -------- | ------------------ | ------------- | ------ |
| 1       | 334      | 1,267    | 84.1               | 22.2          | 0      |
| 8       | 1,440    | 5,429    | **180.5**          | **47.9**      | 0      |
| 16      | 1,290    | 4,878    | 160.6              | 42.5          | 0      |

Latency per endpoint (ms):

| Endpoint                                               | Workers | p50  | p95   | p99     | max     |
| ------------------------------------------------------ | ------- | ---- | ----- | ------- | ------- |
| `POST /applications` (write)                           | 1       | 7.2  | 8.9   | 13.7    | 36.0    |
|                                                        | 8       | 25.0 | 162.2 | 587.8   | 1,745.7 |
|                                                        | 16      | 38.2 | 571.6 | 1,562.9 | 3,470.1 |
| `POST /evaluate` (write: decision + audit)             | 1       | 8.8  | 11.3  | 15.5    | 19.9    |
|                                                        | 8       | 27.2 | 140.9 | 457.1   | 1,972.1 |
|                                                        | 16      | 39.2 | 303.6 | 1,155.2 | 3,713.0 |
| `GET /decisions/{id}/vehicles` (read + 16 assessments) | 1       | 15.9 | 28.5  | 35.1    | 42.7    |
|                                                        | 8       | 32.4 | 72.3  | 87.4    | 117.5   |
|                                                        | 16      | 75.1 | 156.1 | 182.0   | 212.1   |
| `GET /vehicles` (read)                                 | 1       | 14.2 | 27.2  | 35.8    | 38.5    |
|                                                        | 8       | 29.0 | 65.1  | 80.9    | 102.6   |
|                                                        | 16      | 66.6 | 143.3 | 168.0   | 195.5   |

## Interpretation

1. **Saturation is between 8 and 16 workers.** Throughput fell from 180 to 161 req/s when concurrency doubled, while all latencies rose. That is the signature of a saturated single process.
2. **Writes show tail-latency spikes; reads degrade smoothly.**
   - At 16 workers, write p99 is 1.2–1.6 s and the maximum is about 3.7 s.
   - Read p99 stays under 200 ms.
   - Cause: SQLite allows **one writer at a time**, so concurrent writers wait on the lock (up to `busy_timeout`). Each evaluation writes a decision snapshot and an audit event.
   - No request failed. Writes queued instead of returning `database is locked`.
3. **Reads scale with queueing in one process.** p50 grows about linearly with workers (14 → 29 → 67 ms) because one Python process handles every request. The deterministic engine itself is cheap: single-worker p50 is 8.8 ms for evaluate.
4. **Against the assumed target** (peak 150 evaluations/s, p95 < 300 ms): this single-process SQLite setup sustains about **48 evaluations/s with p95 141 ms** (8 workers). It does **not** meet the target. That is expected and consistent with ADR-002.

## Bottlenecks and planned remedies (not yet measured)

| Bottleneck                      | Evidence                                                       | Remedy (Phase 5)                                                                      |
| ------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| SQLite single writer            | Write p99/max blow-up at 8–16 workers while reads stay bounded | PostgreSQL (row-level locking, concurrent writers) with pooling (RDS Proxy/PgBouncer) |
| One Python process              | p50 for every endpoint rises with concurrency                  | Several uvicorn workers per pod and horizontal pods (only possible once off SQLite)   |
| Per-request vehicle assessment  | `/vehicles` for a decision is the heaviest read                | Cache assessments per (decision, catalogue version), invalidated on price import      |
| Audit write on every evaluation | Two inserts per evaluation                                     | Same transaction on PostgreSQL; partition `audit_events` and `decisions` by month     |

## Limitations

- The client and server ran on the same machine, so the load generator competed for CPU.
- The runs were short (15–30 s) on a warm, small database. There was no long soak test and no growth to millions of rows.
- The BFF, TLS and network latency are excluded.
- Gemini was disabled. AI explanations and OCR are bounded by provider latency and quotas, not by this server.
- There is one run per configuration, with no repetition or variance analysis. Treat differences under about 10% as noise.
- Nothing here measures PostgreSQL, Kubernetes or AWS. Projections for those must be validated by repeating this script against that environment.
