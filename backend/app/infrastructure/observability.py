"""Prometheus metrics and structured JSON logs with correlation ids. Labels never include tenant or user ids."""

import contextvars
import json
import logging
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

REGISTRY = CollectorRegistry(auto_describe=True)
HTTP_REQUESTS = Counter("vla_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=REGISTRY)
HTTP_LATENCY = Histogram("vla_http_request_duration_seconds", "HTTP request latency", ["method", "route"],
                         buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 15, 60, 180), registry=REGISTRY)
EXPLANATIONS = Counter("vla_explanations_total", "Explanations by source", ["source"], registry=REGISTRY)
AI_BUDGET_DENIED = Counter("vla_ai_budget_denied_total", "AI calls skipped because a tenant budget was exhausted",
                           registry=REGISTRY)
JOBS = Counter("vla_jobs_total", "Background jobs by topic and outcome", ["topic", "outcome"], registry=REGISTRY)
OUTBOX_PENDING = Gauge("vla_outbox_pending", "Unpublished outbox events", registry=REGISTRY)
QUEUE_WAITING = Gauge("vla_queue_waiting", "Jobs waiting in the documents queue", registry=REGISTRY)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)), "level": record.levelname,
                 "logger": record.name, "msg": record.getMessage(), "correlation_id": correlation_id_var.get()}
        for key in ("method", "route", "status", "duration_ms", "job_id", "topic", "outcome"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging(json_logs: bool) -> None:
    root = logging.getLogger()
    if json_logs and not any(isinstance(h.formatter, _JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        root.handlers = [handler]
        root.setLevel(logging.INFO)
