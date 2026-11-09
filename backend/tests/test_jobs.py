"""Phase 4: transactional outbox, idempotent at-least-once job handling, retries, backpressure, quotas, metrics.
Tests marked `redis` use a real Redis (TEST_REDIS_URL) and the real BullMQ worker."""

import asyncio
import json
import os
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import worker as wk
from app.application import documents as docs
from app.config import Settings
from app.domain.documents import PageText
from app.infrastructure.db import make_engine, make_session_factory, session_scope
from app.infrastructure.document_ai import DocumentAIUnavailable
from app.infrastructure.models import OutboxEvent, PolicySourceDocument
from app.infrastructure.quota import RedisQuota, UnlimitedQuota
from app.main import create_app
from tests.conftest import GOOD_APPLICANT, TODAY, StubDocumentAI, StubExplainer, as_user

PRIYA, ALICE, LENA = as_user("u-priya"), as_user("u-alice"), as_user("u-lena")
PDF = b"%PDF-1.7\n% queued policy\n"
REDIS_URL = os.getenv("TEST_REDIS_URL")
needs_redis = pytest.mark.skipif(not REDIS_URL, reason="set TEST_REDIS_URL to run Redis/BullMQ tests")
PAGES = [PageText(page=1, text="2.1 Credit score\nApplicants must have a credit score of at least 650.")]


class DenyAll:
    def allow_ai(self, tenant_id: str) -> bool:
        return False

    def allow_upload(self, tenant_id: str) -> bool:
        return False


@pytest.fixture()
def queued(make_settings: Callable[..., Settings], explainer: StubExplainer,
           document_ai: StubDocumentAI) -> Iterator[tuple[TestClient, Settings]]:
    settings = make_settings(document_processing="queue")
    app = create_app(settings, explainer=explainer, today=lambda: TODAY, document_ai=document_ai)
    with TestClient(app) as client:
        yield client, settings
    app.state.engine.dispose()


def upload(client: TestClient, headers: dict[str, str], data: bytes = PDF) -> Any:
    return client.post("/v1/policy-documents", content=data,
                       headers={**headers, "Content-Type": "application/pdf", "X-Filename": "queued.pdf"})


def _sessions(settings: Settings, admin: bool = False):  # type: ignore[no-untyped-def]
    url = settings.database_admin_url if admin and settings.database_admin_url else settings.database_url
    return make_session_factory(make_engine(url))


def test_queue_mode_writes_outbox_in_same_transaction(queued: tuple[TestClient, Settings],
                                                      document_ai: StubDocumentAI) -> None:
    client, settings = queued
    r = upload(client, PRIYA)
    assert r.status_code == 202 and r.json()["status"] == "PROCESSING"
    assert document_ai.calls == []  # nothing ran in-request
    with session_scope(_sessions(settings, admin=True)) as s:
        events = list(s.scalars(select(OutboxEvent)))
        doc = s.get(PolicySourceDocument, r.json()["id"])
        assert len(events) == 1 and events[0].topic == docs.TOPIC_TRANSCRIBE and events[0].published_at is None
        assert doc is not None and doc.pending_job_id == events[0].id
        assert "%PDF" not in events[0].payload_json  # references only, never content
    busy = client.post(f"/v1/policy-documents/{r.json()['id']}/transcribe", headers=PRIYA)
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "DOCUMENT_BUSY"


def test_relay_is_idempotent_and_applies_backpressure(queued: tuple[TestClient, Settings]) -> None:
    client, settings = queued
    upload(client, PRIYA)
    added: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    async def add(name: str, data: dict[str, Any], opts: dict[str, Any]) -> None:
        added.append((name, data, opts))

    async def broken(name: str, data: dict[str, Any], opts: dict[str, Any]) -> None:
        raise ConnectionError("redis down")

    admin = _sessions(settings, admin=True)
    assert asyncio.run(wk.relay_once(admin, add, waiting=wk.MAX_WAITING)) == 0  # backpressure
    assert asyncio.run(wk.relay_once(admin, broken, waiting=0)) == 0
    with session_scope(admin) as s:
        event = s.scalars(select(OutboxEvent)).one()
        assert event.published_at is None and event.attempts == 1  # kept for the next tick
    assert asyncio.run(wk.relay_once(admin, add, waiting=0)) == 1
    assert asyncio.run(wk.relay_once(admin, add, waiting=0)) == 0
    name, data, opts = added[0]
    assert opts["jobId"] == event.id and opts["attempts"] == 4 and opts["backoff"]["jitter"] == 0.5
    assert name == docs.TOPIC_TRANSCRIBE and set(data) == {"v", "document_id", "tenant_id", "requested_by",
                                                           "correlation_id"}


def test_handler_retries_then_records_failure_and_skips_duplicates(queued: tuple[TestClient, Settings],
                                                                   document_ai: StubDocumentAI) -> None:
    client, settings = queued
    doc_id = upload(client, PRIYA).json()["id"]
    sessions = _sessions(settings)
    with session_scope(_sessions(settings, admin=True)) as s:
        event = s.scalars(select(OutboxEvent)).one()
        job_id, payload = event.id, json.loads(event.payload_json)
    quota = UnlimitedQuota()
    store = client.app.state.document_store  # type: ignore[attr-defined]

    with pytest.raises(DocumentAIUnavailable):  # non-final attempt: propagate so BullMQ retries
        wk.handle(sessions, store, document_ai, quota, job_id, docs.TOPIC_TRANSCRIBE, payload, final_attempt=False)
    assert client.get(f"/v1/policy-documents/{doc_id}", headers=PRIYA).json()["status"] == "PROCESSING"
    assert wk.handle(sessions, store, document_ai, quota, "some-other-id", docs.TOPIC_TRANSCRIBE, payload,
                     final_attempt=True) == "skipped"
    wk.handle(sessions, store, document_ai, quota, job_id, docs.TOPIC_TRANSCRIBE, payload, final_attempt=True)
    failed = client.get(f"/v1/policy-documents/{doc_id}", headers=PRIYA).json()
    assert failed["status"] == "TEXT_FAILED" and "stub outage" in failed["error"]

    assert client.post(f"/v1/policy-documents/{doc_id}/transcribe", headers=PRIYA).status_code == 202
    with session_scope(_sessions(settings, admin=True)) as s:
        retry = s.scalars(select(OutboxEvent).where(OutboxEvent.id != job_id)).one()
        retry_id = retry.id
    document_ai.pages = PAGES
    assert wk.handle(sessions, store, document_ai, quota, retry_id, docs.TOPIC_TRANSCRIBE, payload, True) == "completed"
    assert wk.handle(sessions, store, document_ai, quota, retry_id, docs.TOPIC_TRANSCRIBE, payload, True) == "skipped"
    done = client.get(f"/v1/policy-documents/{doc_id}", headers=PRIYA).json()
    assert done["status"] == "TEXT_EXTRACTED" and done["text_version"] == 1  # duplicate delivery did not re-run


def test_job_for_another_tenant_cannot_touch_document(queued: tuple[TestClient, Settings],
                                                      document_ai: StubDocumentAI) -> None:
    client, settings = queued
    doc_id = upload(client, PRIYA).json()["id"]
    with session_scope(_sessions(settings, admin=True)) as s:
        job_id = s.scalars(select(OutboxEvent)).one().id
    forged = {"v": 1, "document_id": doc_id, "tenant_id": "t-southbay", "requested_by": "u-lena"}
    document_ai.pages = PAGES
    quota = UnlimitedQuota()
    outcome = wk.handle(_sessions(settings), client.app.state.document_store, document_ai, quota,  # type: ignore[attr-defined]
                        job_id, docs.TOPIC_TRANSCRIBE, forged, True)
    assert outcome == "skipped" and document_ai.calls == []


def test_ai_budget_and_upload_rate_limits(make_settings: Callable[..., Settings], explainer: StubExplainer,
                                          document_ai: StubDocumentAI) -> None:
    app = create_app(make_settings(), explainer=explainer, today=lambda: TODAY, document_ai=document_ai,
                     quota=DenyAll())
    with TestClient(app) as client:
        assert upload(client, PRIYA).status_code == 429
        app_id = client.post("/v1/applications", json=GOOD_APPLICANT, headers=ALICE).json()["id"]
        decision = client.post(f"/v1/applications/{app_id}/evaluate", headers=ALICE).json()
        explained = client.post(f"/v1/decisions/{decision['id']}/explanation", headers=ALICE).json()
        assert explained["source"] == "template" and "budget" in explained["fallback_reason"]
        assert explainer.calls == 0 and decision["outcome"] == "APPROVED"  # budget never affects the decision
        metrics = client.get("/metrics").text
        assert 'vla_explanations_total{source="template"}' in metrics and "vla_ai_budget_denied_total" in metrics
        assert 'route="/v1/applications/{app_id}/evaluate"' in metrics  # templated routes, no ids in labels
    app.state.engine.dispose()


@needs_redis
def test_redis_quota_is_tenant_scoped_and_fails_closed_for_ai() -> None:
    prefix = uuid.uuid4().hex[:8]
    quota = RedisQuota(REDIS_URL, ai_per_day=2, uploads_per_minute=1)  # type: ignore[arg-type]
    a, b = f"t-a-{prefix}", f"t-b-{prefix}"
    assert [quota.allow_ai(a) for _ in range(3)] == [True, True, False]
    assert quota.allow_ai(b)  # independent counter
    assert quota.allow_upload(a) and not quota.allow_upload(a)
    down = RedisQuota("redis://127.0.0.1:1/0", ai_per_day=10, uploads_per_minute=10)
    assert down.allow_ai(a) is False and down.allow_upload(a) is True


@needs_redis
def test_end_to_end_with_real_bullmq_worker(queued: tuple[TestClient, Settings],
                                            document_ai: StubDocumentAI) -> None:
    client, settings = queued
    document_ai.pages = PAGES
    queue_name = f"documents-test-{uuid.uuid4().hex[:8]}"
    doc_id = upload(client, PRIYA).json()["id"]
    sessions, admin = _sessions(settings), _sessions(settings, admin=True)
    quota = UnlimitedQuota()
    store = client.app.state.document_store  # type: ignore[attr-defined]

    async def scenario() -> None:
        from bullmq import Queue, Worker

        queue = Queue(queue_name, {"connection": REDIS_URL})
        worker = Worker(queue_name, wk.build_processor(sessions, store, document_ai, quota),
                        {"connection": REDIS_URL})
        try:
            assert await wk.relay_once(admin, queue.add, 0) == 1
            await queue.add(docs.TOPIC_TRANSCRIBE, {}, {"jobId": "dup"})  # unrelated id, payload rejected
            for _ in range(100):
                status = client.get(f"/v1/policy-documents/{doc_id}", headers=PRIYA).json()["status"]
                if status == "TEXT_EXTRACTED":
                    break
                await asyncio.sleep(0.1)
            assert status == "TEXT_EXTRACTED"
            for _ in range(50):
                if await queue.getFailedCount() >= 1:
                    break
                await asyncio.sleep(0.1)
            failed = await queue.getFailed()
            assert [j.id for j in failed] == ["dup"]  # unsupported payload is unrecoverable, not retried
        finally:
            await worker.close(force=True)
            await queue.obliterate(force=True)
            await queue.close()

    asyncio.run(scenario())
    assert document_ai.calls == ["transcribe"]
    assert client.get(f"/v1/policy-documents/{doc_id}", headers=LENA).status_code == 404
