import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes"}


def _opt(name: str) -> str | None:
    return os.getenv(name) or None


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./data/vla.db"))
    # Privileged owner connection for migrations, seed and the outbox relay; the runtime role is subject to RLS.
    database_admin_url: str | None = field(default_factory=lambda: _opt("DATABASE_ADMIN_URL"))
    migrate_on_startup: bool = field(default_factory=lambda: _bool("MIGRATE_ON_STARTUP", True))
    # "dev" trusts the X-Dev-User header from the BFF; never enable outside local demos. "oidc" validates JWTs.
    auth_mode: str = field(default_factory=lambda: os.getenv("AUTH_MODE", "dev"))
    dev_shared_secret: str = field(default_factory=lambda: os.getenv("DEV_BFF_SHARED_SECRET", "local-dev-only"))
    oidc_issuer: str | None = field(default_factory=lambda: _opt("OIDC_ISSUER"))
    oidc_audience: str | None = field(default_factory=lambda: _opt("OIDC_AUDIENCE"))
    oidc_jwks_url: str | None = field(default_factory=lambda: _opt("OIDC_JWKS_URL"))
    # Cognito access tokens carry token_use=access and client_id instead of aud.
    oidc_token_use: str | None = field(default_factory=lambda: _opt("OIDC_TOKEN_USE"))
    oidc_required_scope: str | None = field(default_factory=lambda: _opt("OIDC_REQUIRED_SCOPE"))
    redis_cache_url: str | None = field(default_factory=lambda: _opt("REDIS_CACHE_URL"))
    redis_queue_url: str | None = field(default_factory=lambda: _opt("REDIS_QUEUE_URL"))
    # "inline" runs OCR/extraction in the request (A13); "queue" uses the outbox + BullMQ worker.
    document_processing: str = field(default_factory=lambda: os.getenv("DOCUMENT_PROCESSING", "inline"))
    ai_daily_budget_per_tenant: int = field(
        default_factory=lambda: int(os.getenv("AI_DAILY_BUDGET_PER_TENANT", "500")))
    uploads_per_minute_per_tenant: int = field(
        default_factory=lambda: int(os.getenv("UPLOADS_PER_MINUTE_PER_TENANT", "10")))
    metrics_enabled: bool = field(default_factory=lambda: _bool("METRICS_ENABLED", True))
    json_logs: bool = field(default_factory=lambda: _bool("JSON_LOGS", False))
    worker_concurrency: int = field(default_factory=lambda: int(os.getenv("WORKER_CONCURRENCY", "2")))
    worker_metrics_port: int = field(default_factory=lambda: int(os.getenv("WORKER_METRICS_PORT", "9100")))
    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY") or None)
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    gemini_timeout_ms: int = field(default_factory=lambda: int(os.getenv("GEMINI_TIMEOUT_MS", "15000")))
    # Scanned-document OCR runs in-request and can take far longer than an explanation.
    gemini_document_timeout_ms: int = field(
        default_factory=lambda: int(os.getenv("GEMINI_DOCUMENT_TIMEOUT_MS", "150000")))
    document_storage_dir: str = field(default_factory=lambda: os.getenv("DOCUMENT_STORAGE_DIR", "./data/documents"))
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))))
    ai_enabled: bool = field(default_factory=lambda: _bool("AI_ENABLED", True))
    seed_on_startup: bool = field(default_factory=lambda: _bool("SEED_ON_STARTUP", True))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o for o in os.getenv("CORS_ORIGINS", "").split(",") if o)
    )
