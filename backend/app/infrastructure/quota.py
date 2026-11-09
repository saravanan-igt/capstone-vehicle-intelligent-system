"""Per-tenant quotas on the cache Redis (disposable data; eviction only resets counters early).

Keys are always prefixed with the tenant id, so one tenant's counters can never be read or reset by another."""

import logging
import time
from datetime import datetime, timezone
from typing import Protocol

log = logging.getLogger(__name__)


class Quota(Protocol):
    def allow_ai(self, tenant_id: str) -> bool: ...

    def allow_upload(self, tenant_id: str) -> bool: ...


class UnlimitedQuota:
    """Used when no cache Redis is configured (single-process local demo)."""

    def allow_ai(self, tenant_id: str) -> bool:
        return True

    def allow_upload(self, tenant_id: str) -> bool:
        return True


class RedisQuota:
    def __init__(self, url: str, ai_per_day: int, uploads_per_minute: int) -> None:
        import redis

        self._redis = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
        self.ai_per_day = ai_per_day
        self.uploads_per_minute = uploads_per_minute

    def _hit(self, key: str, limit: int, ttl_s: int, fail_open: bool) -> bool:
        try:
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl_s, nx=True)
            count = int(pipe.execute()[0])
        except Exception as exc:  # cache outage must not take the lending flow down
            log.warning("quota store unavailable (%s); fail_open=%s", type(exc).__name__, fail_open)
            return fail_open
        return count <= limit

    def allow_ai(self, tenant_id: str) -> bool:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        # Fail closed: without a working budget the AI path is skipped and deterministic templates are used.
        return self._hit(f"vla:{tenant_id}:ai:{day}", self.ai_per_day, 2 * 86400, fail_open=False)

    def allow_upload(self, tenant_id: str) -> bool:
        minute = int(time.time() // 60)
        return self._hit(f"vla:{tenant_id}:upload:{minute}", self.uploads_per_minute, 120, fail_open=True)

    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except Exception:
            return False


def build_quota(url: str | None, ai_per_day: int, uploads_per_minute: int) -> Quota:
    return RedisQuota(url, ai_per_day, uploads_per_minute) if url else UnlimitedQuota()
