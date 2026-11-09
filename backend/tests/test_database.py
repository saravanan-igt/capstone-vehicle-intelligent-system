"""Phase 5: migrations match the models, legacy databases upgrade in place, and PostgreSQL RLS isolates tenants
even when application code forgets a tenant filter."""

from collections.abc import Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.infrastructure.db import BACKEND_DIR, BASELINE_REVISION, make_engine, migrate, normalise_url
from app.infrastructure.models import Base
from tests.conftest import GOOD_APPLICANT, PG_ADMIN_URL, as_user

ALICE, BEN = as_user("u-alice"), as_user("u-ben")
postgres_only = pytest.mark.skipif(not PG_ADMIN_URL, reason="set TEST_POSTGRES_URL to run PostgreSQL tests")


def test_migrations_match_models(client: TestClient, make_settings: Callable[..., Settings]) -> None:
    settings = make_settings()
    engine = make_engine(settings.database_admin_url or settings.database_url)
    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diffs == []


def test_legacy_create_all_database_is_stamped_and_upgraded(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, BASELINE_REVISION)
        conn.execute(text("DROP TABLE alembic_version"))  # what a pre-Alembic create_all database looked like
    migrate(engine)
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert {"user_identities", "outbox_events"} <= tables and version == "0005_explanation_sources"


@postgres_only
def test_rls_blocks_unscoped_and_cross_tenant_access(client: TestClient,
                                                     make_settings: Callable[..., Settings]) -> None:
    app_id = client.post("/v1/applications", json=GOOD_APPLICANT, headers=ALICE).json()["id"]
    decided = client.post(f"/v1/applications/{app_id}/evaluate", headers=ALICE)
    assert decided.status_code == 201
    runtime = create_engine(normalise_url(make_settings().database_url))  # vla_app: subject to RLS
    try:
        with runtime.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM applications")).scalar_one() == 0  # no tenant set
            conn.execute(text("SELECT set_config('app.tenant_id', 't-southbay', false)"))
            assert conn.execute(text("SELECT count(*) FROM applications")).scalar_one() == 0
            conn.execute(text("SELECT set_config('app.tenant_id', 't-northwind', false)"))
            assert conn.execute(text("SELECT count(*) FROM applications")).scalar_one() == 1
            assert conn.execute(text("SELECT count(*) FROM vehicles")).scalar_one() > 0  # shared catalogue
            conn.rollback()
        with runtime.connect() as conn, pytest.raises(DBAPIError, match="row-level security"):
            conn.execute(text("SELECT set_config('app.tenant_id', 't-southbay', false)"))
            conn.execute(text("INSERT INTO audit_events (id, tenant_id, actor_user_id, action, entity_type, "
                              "entity_id, details_json, created_at) VALUES ('x', 't-northwind', 'u-ben', 'forged', "
                              "'none', 'none', '{}', now())"))
        with runtime.connect() as conn, pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text("SELECT set_config('app.tenant_id', 't-northwind', false)"))
            conn.execute(text("UPDATE decisions SET outcome = 'REJECTED'"))
    finally:
        runtime.dispose()


@postgres_only
def test_api_still_isolates_tenants_on_postgres(client: TestClient) -> None:
    app_id = client.post("/v1/applications", json=GOOD_APPLICANT, headers=ALICE).json()["id"]
    assert client.get(f"/v1/applications/{app_id}", headers=BEN).status_code == 404
    assert client.get("/v1/applications", headers=BEN).json()["items"] == []
