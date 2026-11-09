"""PostgreSQL row-level security on tenant-owned tables (no-op on SQLite)

Policies compare tenant_id with the transaction-local setting app.tenant_id, which the API sets from the
authenticated membership. An unset value matches no rows (default deny). The table owner (migrations, seed,
outbox relay) bypasses RLS; the runtime role (DB_APP_ROLE, default vla_app) does not.

Revision ID: 0003_postgres_rls
Revises: 0002_identities_outbox
Create Date: 2026-11-09
"""
import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0003_postgres_rls"
down_revision: str | None = "0002_identities_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("policy_versions", "applications", "decisions", "explanations", "audit_events",
                 "policy_source_documents", "policy_document_pages", "policy_chunks", "outbox_events")
SHARED_READ_TABLES = ("tenants", "users", "memberships", "user_identities", "vehicles", "vehicle_prices")


def _app_role() -> str:
    role = os.getenv("DB_APP_ROLE", "vla_app")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise ValueError("DB_APP_ROLE must be a simple lowercase identifier")
    return role


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} "
                   "USING (tenant_id = current_setting('app.tenant_id', true)) "
                   "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")
    role = _app_role()
    # Grants only if the runtime role was provisioned (deploy/postgres/init-app-role.sh or the platform).
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            GRANT USAGE ON SCHEMA public TO {role};
            GRANT SELECT ON {", ".join(SHARED_READ_TABLES)} TO {role};
            GRANT SELECT, INSERT ON {", ".join(TENANT_TABLES)} TO {role};
            -- Decisions, explanations, audit events, pages and chunks stay append-only for the runtime role.
            GRANT UPDATE ON applications, policy_versions, policy_source_documents, outbox_events TO {role};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
