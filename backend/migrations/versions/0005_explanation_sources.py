"""retrieved policy sources recorded with each explanation (RAG provenance)

Revision ID: 0005_explanation_sources
Revises: 0004_document_pending_job
Create Date: 2026-11-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_explanation_sources"
down_revision: str | None = "0004_document_pending_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("explanations") as batch:
        batch.add_column(sa.Column("sources_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("explanations") as batch:
        batch.drop_column("sources_json")
