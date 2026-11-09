"""pending job id on policy documents (idempotent background processing)

Revision ID: 0004_document_pending_job
Revises: 0003_postgres_rls
Create Date: 2026-11-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_document_pending_job"
down_revision: str | None = "0003_postgres_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("policy_source_documents") as batch:
        batch.add_column(sa.Column("pending_job_id", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("policy_source_documents") as batch:
        batch.drop_column("pending_job_id")
