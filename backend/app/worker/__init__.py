"""Background worker: relays the transactional outbox to BullMQ and processes document jobs.

    python -m app.worker

Delivery is at-least-once end to end:
- The relay uses the outbox id as the BullMQ jobId, so a relay crash between add() and marking the row
  published re-adds the same id, which BullMQ ignores.
- Handlers skip any delivery whose id is not the document's pending_job_id.

Retries use exponential backoff with jitter. The final attempt records the failure on the document instead of
raising."""

import asyncio
import json
import logging
import signal
from collections.abc import Awaitable, Callable
from typing import Any

from bullmq import Queue, UnrecoverableError, Worker
from prometheus_client import start_http_server
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application import documents as docs
from app.config import Settings
from app.infrastructure.db import bind_tenant, make_engine, make_session_factory, migrate, session_scope
from app.infrastructure.document_ai import DocumentAI, DocumentAIUnavailable, build_document_ai
from app.infrastructure.models import OutboxEvent, utcnow
from app.infrastructure.observability import (
    JOBS,
    OUTBOX_PENDING,
    QUEUE_WAITING,
    REGISTRY,
    configure_logging,
    correlation_id_var,
)
from app.infrastructure.quota import Quota, build_quota
from app.infrastructure.storage import DocumentStore, LocalDocumentStore

log = logging.getLogger("vla.worker")
QUEUE_NAME = "documents"
JOB_OPTIONS: dict[str, Any] = {
    "attempts": 4,
    "backoff": {"type": "exponential", "delay": 5000, "jitter": 0.5},
    "removeOnComplete": {"count": 1000},
    "removeOnFail": False,  # kept for inspection and controlled replay (python -m app.worker.admin)
}
MAX_WAITING = 200  # backpressure: stop relaying when this many jobs are already waiting
RELAY_BATCH = 50

AddJob = Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[Any]]


async def relay_once(admin_sessions: sessionmaker[Session], add_job: AddJob, waiting: int) -> int:
    """Publishes unpublished outbox events. Returns the number published."""
    if waiting >= MAX_WAITING:
        log.warning("queue backpressure: %s waiting, relay paused", waiting)
        return 0
    with session_scope(admin_sessions) as s:
        query = (select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
                 .order_by(OutboxEvent.created_at).limit(min(RELAY_BATCH, MAX_WAITING - waiting)))
        if s.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)  # several relays can run without double work
        events = list(s.scalars(query))
        published = 0
        for event in events:
            try:
                await add_job(event.topic, json.loads(event.payload_json), {**JOB_OPTIONS, "jobId": event.id})
            except Exception as exc:  # Redis down: keep the row, try again next tick
                event.attempts += 1
                event.last_error = type(exc).__name__
                log.warning("outbox publish failed for %s: %s", event.id, type(exc).__name__)
                break
            event.published_at = utcnow()
            published += 1
        OUTBOX_PENDING.set(s.scalar(select(func.count()).select_from(OutboxEvent)
                                    .where(OutboxEvent.published_at.is_(None))) or 0)
    return published


def handle(sessions: sessionmaker[Session], store: DocumentStore, ai: DocumentAI, quota: Quota, job_id: str,
           topic: str, payload: dict[str, Any], final_attempt: bool) -> str:
    """Runs one delivery in its own transaction, scoped to the job's tenant (RLS applies on PostgreSQL)."""
    if payload.get("v") != 1 or topic not in (docs.TOPIC_TRANSCRIBE, docs.TOPIC_EXTRACT):
        raise UnrecoverableError(f"unsupported job {topic} v{payload.get('v')}")
    with session_scope(sessions) as s:
        bind_tenant(s, payload["tenant_id"])
        return docs.run_document_job(s, store, ai, quota, job_id, topic, payload, final_attempt)


def build_processor(sessions: sessionmaker[Session], store: DocumentStore, ai: DocumentAI,
                    quota: Quota) -> Callable[[Any, str], Awaitable[str]]:
    async def process(job: Any, _token: str) -> str:
        final = job.attemptsMade + 1 >= int(job.opts.get("attempts", 1))
        token = correlation_id_var.set((job.data or {}).get("correlation_id"))
        try:
            outcome = await asyncio.to_thread(handle, sessions, store, ai, quota, str(job.id), job.name, job.data,
                                              final)
            JOBS.labels(job.name, outcome).inc()
            log.info("job done", extra={"job_id": job.id, "topic": job.name, "outcome": outcome})
            return outcome
        except DocumentAIUnavailable as exc:
            JOBS.labels(job.name, "retry").inc()
            log.warning("job %s attempt %s failed: %s", job.id, job.attemptsMade + 1, exc,
                        extra={"job_id": job.id, "topic": job.name, "outcome": "retry"})
            raise RuntimeError(str(exc)) from exc
        finally:
            correlation_id_var.reset(token)

    return process


async def run(settings: Settings) -> None:
    if not settings.redis_queue_url:
        raise SystemExit("REDIS_QUEUE_URL is required for the worker")
    admin_engine = make_engine(settings.database_admin_url or settings.database_url)
    if settings.migrate_on_startup:
        migrate(admin_engine)
    admin_sessions = make_session_factory(admin_engine)
    sessions = make_session_factory(make_engine(settings.database_url))
    store = LocalDocumentStore(settings.document_storage_dir)
    ai = build_document_ai(settings.gemini_api_key, settings.gemini_model, settings.gemini_document_timeout_ms,
                           settings.ai_enabled)
    quota = build_quota(settings.redis_cache_url, settings.ai_daily_budget_per_tenant,
                        settings.uploads_per_minute_per_tenant)
    connection = {"connection": settings.redis_queue_url}
    queue = Queue(QUEUE_NAME, connection)
    worker = Worker(QUEUE_NAME, build_processor(sessions, store, ai, quota),
                    {**connection, "concurrency": settings.worker_concurrency,
                     "lockDuration": settings.gemini_document_timeout_ms + 60_000})
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows: rely on KeyboardInterrupt
            pass
    log.info("worker started", extra={"topic": QUEUE_NAME})
    try:
        while not stop.is_set():
            try:
                waiting = int(await queue.getJobCountByTypes("waiting", "delayed"))
                QUEUE_WAITING.set(waiting)
                await relay_once(admin_sessions, queue.add, waiting)
            except Exception as exc:
                log.warning("relay tick failed: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.0)
            except TimeoutError:
                pass
    finally:
        log.info("worker stopping: waiting for the active job to finish")
        await worker.close()
        await queue.close()


def main() -> None:
    settings = Settings()
    configure_logging(settings.json_logs)
    start_http_server(settings.worker_metrics_port, registry=REGISTRY)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
