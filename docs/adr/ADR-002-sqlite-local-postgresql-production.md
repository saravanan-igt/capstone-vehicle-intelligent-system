# ADR-002: SQLite for the local demo, PostgreSQL for production

**Status:** Accepted, 2026-11-07

## Context

The capstone needs zero-setup local execution. Production needs concurrent writers across many API pods, plus row-level security (RLS) as defence in depth.

## Decision

- **Local / Compose:** SQLite on a single API instance. Tenant isolation is enforced in the repositories through composite tenant-aware foreign keys and `tenant_id` filters.
- **Production:** RDS or Aurora PostgreSQL. Money is stored as `NUMERIC(14,2)` and JSON as `JSONB`. RLS uses `SET LOCAL app.tenant_id` per transaction, and migrations and seeds run as a separate privileged role.
- Alembic migrations replace `create_all` before the PostgreSQL work starts (Phase 5).

## Alternatives

- **PostgreSQL everywhere:** this is the most faithful option, but it adds a service to the local demo. It is still acceptable if the evaluators prefer it.
- **SQLite in production:** rejected. SQLite has a single writer and file locks, and is not a shared database for horizontally scaled pods (https://www.sqlite.org/whentouse.html).

## Limitations

- SQLite has no RLS, and its timestamps, `LIKE` behaviour and concurrency differ from PostgreSQL. The suite must therefore run against PostgreSQL in CI before production claims are made.

## Revisit when

- A demo needs more than one API replica, or the PostgreSQL CI job is in place. At that point, switch Compose to PostgreSQL.
