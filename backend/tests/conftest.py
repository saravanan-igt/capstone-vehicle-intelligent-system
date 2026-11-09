import copy
import os
import uuid
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.documents import PageText
from app.domain.explanation import ExplanationDraft
from app.domain.policy import PolicyDocument
from app.infrastructure.document_ai import DocumentAIUnavailable
from app.infrastructure.gemini import ExplainerUnavailable
from app.main import create_app
from app.ml.model import RiskScore

TODAY = date(2026, 11, 7)
SECRET = "test-secret"
POLICY_DIR = Path(__file__).resolve().parents[2] / "data" / "documents" / "policy"
# e.g. postgresql://postgres:postgres@localhost:55432/postgres (superuser; creates a database per test)
PG_ADMIN_URL = os.getenv("TEST_POSTGRES_URL")
PG_ROLES = {"vla_owner": "owner-test-pw", "vla_app": "app-test-pw"}


def _pg_url(base: str, user: str, password: str, database: str) -> str:
    parts = urlsplit(base)
    return urlunsplit((parts.scheme, f"{user}:{password}@{parts.hostname}:{parts.port or 5432}", f"/{database}",
                       "", ""))


def _pg_admin(sql: str) -> None:
    import psycopg

    with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:  # type: ignore[arg-type]
        conn.execute(sql)  # type: ignore[arg-type]


@pytest.fixture()
def db_urls(tmp_path: Path) -> Iterator[dict[str, str | None]]:
    """SQLite by default; with TEST_POSTGRES_URL, a fresh database owned by vla_owner, used at runtime as vla_app."""
    if not PG_ADMIN_URL:
        yield {"database_url": f"sqlite:///{tmp_path / 'test.db'}", "database_admin_url": None}
        return
    for role, password in PG_ROLES.items():
        _pg_admin(f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN "
                  f"CREATE ROLE {role} LOGIN PASSWORD '{password}'; END IF; END $$")
    name = f"vla_test_{uuid.uuid4().hex[:12]}"
    _pg_admin(f"CREATE DATABASE {name} OWNER vla_owner")
    try:
        yield {"database_url": _pg_url(PG_ADMIN_URL, "vla_app", PG_ROLES["vla_app"], name),
               "database_admin_url": _pg_url(PG_ADMIN_URL, "vla_owner", PG_ROLES["vla_owner"], name)}
    finally:
        _pg_admin(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def nw_policy() -> PolicyDocument:
    return PolicyDocument.model_validate_json((POLICY_DIR / "NW-AUTO-STD-2026.1.json").read_text("utf-8"))


GOOD_APPLICANT: dict[str, Any] = {
    "income_amount": "120000", "income_frequency": "monthly", "credit_score": 780, "score_provider": "CIBIL",
    "employment_category": "salaried", "employment_months": 36, "existing_monthly_obligations": "10000",
    "active_loans": 1,
    "requested_principal": "1200000", "requested_tenure_months": 60, "down_payment_available": "400000",
    "currency": "INR", "jurisdiction": "IN", "region": "IN-MH",
}


class StubExplainer:
    name = "stub"
    model = "stub-model"

    def __init__(self) -> None:
        self.behaviour: Callable[[dict[str, Any], list[dict[str, Any]]], ExplanationDraft] | None = None
        self.calls = 0

    def draft(self, facts: dict[str, Any], evidence: list[dict[str, Any]]) -> ExplanationDraft:
        self.calls += 1
        if self.behaviour is None:
            raise ExplainerUnavailable("stub outage")
        return self.behaviour(facts, evidence)


@pytest.fixture()
def explainer() -> StubExplainer:
    return StubExplainer()


class StubDocumentAI:
    name = "stub"
    model = "stub-doc-model"

    def __init__(self) -> None:
        self.pages: list[PageText] | None = None
        self.candidate: dict[str, Any] | None = None
        self.calls: list[str] = []

    def transcribe(self, data: bytes, mime_type: str) -> list[PageText]:
        self.calls.append("transcribe")
        if self.pages is None:
            raise DocumentAIUnavailable("stub outage")
        return list(self.pages)

    def extract_policy(self, pages: list[PageText]) -> dict[str, Any]:
        self.calls.append("extract")
        if self.candidate is None:
            raise DocumentAIUnavailable("stub outage")
        return copy.deepcopy(self.candidate)


@pytest.fixture()
def document_ai() -> StubDocumentAI:
    return StubDocumentAI()


class StubRiskModel:
    """Deterministic stand-in for the saved model; tests set `probability` to steer the credit-risk rule."""

    card = {"name": "vla-eligibility", "version": "test", "algorithm": "stub", "artifact_sha256": "stub-sha",
            "decision_threshold": 0.83}

    def __init__(self) -> None:
        self.probability = 0.95

    def score(self, applicant: Any, top: int = 4) -> RiskScore:
        return RiskScore(probability=self.probability,
                         prediction="Approved" if self.probability >= 0.83 else "Rejected", threshold=0.83,
                         model_version="test", algorithm="stub", artifact_sha256="stub-sha",
                         factors=[{"feature": "credit_score", "label": "credit score", "value": 780,
                                   "typical_value": 745, "effect": 0.05, "direction": "raises"}])


@pytest.fixture()
def risk_model() -> StubRiskModel:
    return StubRiskModel()


@pytest.fixture()
def make_settings(tmp_path: Path, db_urls: dict[str, str | None]) -> Callable[..., Settings]:
    def build(**overrides: Any) -> Settings:
        values: dict[str, Any] = {"database_url": db_urls["database_url"],
                                  "database_admin_url": db_urls["database_admin_url"], "dev_shared_secret": SECRET,
                                  "gemini_api_key": None, "seed_on_startup": True,
                                  "document_storage_dir": str(tmp_path / "docs"), "redis_cache_url": None,
                                  "redis_queue_url": None, "document_processing": "inline"}
        return Settings(**{**values, **overrides})

    return build


@pytest.fixture()
def client(make_settings: Callable[..., Settings], explainer: StubExplainer,
           document_ai: StubDocumentAI, risk_model: StubRiskModel) -> Iterator[TestClient]:
    app = create_app(make_settings(), explainer=explainer, today=lambda: TODAY, document_ai=document_ai,
                     eligibility_model=risk_model)
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


def as_user(user_id: str, tenant: str | None = None) -> dict[str, str]:
    headers = {"X-Dev-User": user_id, "X-Dev-Secret": SECRET}
    if tenant:
        headers["X-Tenant-Id"] = tenant
    return headers
