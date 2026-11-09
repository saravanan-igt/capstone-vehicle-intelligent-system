"""Operator tools for failed jobs (controlled replay). Jobs carry only ids, so listing them exposes no content.

    python -m app.worker.admin failed [--tenant t-northwind]
    python -m app.worker.admin retry --job <id>          # replays one failed job
    python -m app.worker.admin counts

Replaying a job whose document is no longer waiting for it is a safe no-op (the handler skips stale ids).
Usually prefer the UI's Retry buttons, which create a fresh outbox event."""

import argparse
import asyncio
import json
import sys

from bullmq import Queue

from app.config import Settings
from app.worker import QUEUE_NAME


async def _main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.worker.admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    failed = sub.add_parser("failed")
    failed.add_argument("--tenant")
    retry = sub.add_parser("retry")
    retry.add_argument("--job", required=True)
    sub.add_parser("counts")
    args = parser.parse_args(argv)
    settings = Settings()
    if not settings.redis_queue_url:
        raise SystemExit("REDIS_QUEUE_URL is required")
    queue = Queue(QUEUE_NAME, {"connection": settings.redis_queue_url})
    try:
        if args.cmd == "counts":
            print(json.dumps(await queue.getJobCounts()))
        elif args.cmd == "failed":
            jobs = await queue.getFailed(0, 200)
            rows = [{"id": j.id, "topic": j.name, "tenant_id": j.data.get("tenant_id"),
                     "document_id": j.data.get("document_id"), "attempts": j.attemptsMade,
                     "reason": j.failedReason} for j in jobs
                    if args.tenant is None or j.data.get("tenant_id") == args.tenant]
            print(json.dumps(rows, indent=2))
        else:
            job = await queue.getJob(args.job)
            if job is None:
                raise SystemExit("job not found")
            await job.retry("failed")
            print(json.dumps({"retried": args.job}))
    finally:
        await queue.close()


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
