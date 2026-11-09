# ADR-003: BullMQ with Python workers for durable jobs

**Status:** Accepted and implemented, 2026-11-09. `bullmq` 3.5.0 (Python) with Redis 8.10. Verified with a real worker and Redis in tests and in `docker-compose.full.yml`: retries with exponential backoff and jitter, `UnrecoverableError`, failed-job listing and `job.retry`. No TypeScript worker was needed.

## Context

Several tasks need durable, retryable background processing: policy-document processing, embeddings, catalogue imports and exports. The backend is Python.

## Evidence (verified 2026-11-09, https://docs.bullmq.io/python/introduction)

- The `bullmq` pip package needs Python ≥ 3.10 and Redis ≥ 6.2, or PostgreSQL ≥ 13 with the PostgreSQL backend.
- Python queues interoperate with the other BullMQ SDKs.
- The Python docs cover `Queue`, `Worker`, `FlowProducer`, job schedulers, global concurrency and rate limits, job cancellation and `QueueEvents`.
- `QueueEvents` in Python is Redis-only.

## Decision

- Write the workers in Python (`bullmq`) so they share the domain package with the API.
- Use a transactional outbox: the API writes an `outbox` row in the same database transaction, and a relay publishes it to BullMQ. Handlers are idempotent and keyed by job ID.
- Job payloads carry record references (tenant ID and entity ID), not personal data.
- Keep the queue Redis (`noeviction`, AOF) separate from the cache Redis (`allkeys-lru`).

## Alternatives

- **TypeScript worker service:** kept as a fallback if a required feature turns out to be Node-only during Phase 4 spikes.
- **Celery, RQ or SQS:** SQS is a valid AWS-native choice. BullMQ was chosen because the brief names it.

## Revisit when

- A Phase 4 spike shows that a needed feature (for example retry/backoff options or failed-job replay) behaves differently in Python.
- ElastiCache compatibility with the chosen BullMQ configuration cannot be validated.
