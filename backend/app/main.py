import logging
import re
import time
import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.api.v1 import router
from app.application.errors import AppError
from app.config import Settings
from app.infrastructure.db import init_schema, make_engine, make_session_factory, session_scope
from app.infrastructure.document_ai import DocumentAI, build_document_ai
from app.infrastructure.gemini import Explainer, build_explainer
from app.infrastructure.observability import (
    HTTP_LATENCY,
    HTTP_REQUESTS,
    REGISTRY,
    configure_logging,
    correlation_id_var,
)
from app.infrastructure.oidc import OidcVerifier
from app.infrastructure.quota import Quota, RedisQuota, build_quota
from app.infrastructure.storage import DocumentStore, LocalDocumentStore
from app.seed.seed import seed

log = logging.getLogger("vla")
_CID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


def _error(status: int, code: str, message: str, cid: str | None, details: object = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "error": {"code": code, "message": message, "correlation_id": cid, "details": details}})


def create_app(settings: Settings | None = None, explainer: Explainer | None = None,
               today: Callable[[], date] | None = None, document_ai: DocumentAI | None = None,
               document_store: DocumentStore | None = None, oidc: OidcVerifier | None = None,
               quota: Quota | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.json_logs)
    engine = make_engine(settings.database_url)
    admin_engine = make_engine(settings.database_admin_url) if settings.database_admin_url else engine
    if settings.migrate_on_startup:
        init_schema(admin_engine)
    if settings.seed_on_startup:
        with session_scope(make_session_factory(admin_engine)) as s:
            seed(s)
    if admin_engine is not engine:
        admin_engine.dispose()
    session_factory = make_session_factory(engine)

    app = FastAPI(title="Intelligent Vehicle Loan Advisor API", version="0.1.0",
                  description="Deterministic, policy-grounded vehicle-loan eligibility (capstone; synthetic data).")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.explainer = explainer or build_explainer(settings.gemini_api_key, settings.gemini_model,
                                                       settings.gemini_timeout_ms, settings.ai_enabled)
    app.state.document_ai = document_ai or build_document_ai(
        settings.gemini_api_key, settings.gemini_model, settings.gemini_document_timeout_ms, settings.ai_enabled)
    app.state.document_store = document_store or LocalDocumentStore(settings.document_storage_dir)
    app.state.today = today or (lambda: datetime.now(timezone.utc).date())
    app.state.oidc = oidc or (OidcVerifier(settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url,
                                           settings.oidc_token_use, settings.oidc_required_scope)
                              if settings.auth_mode == "oidc" and settings.oidc_issuer and settings.oidc_audience
                              else None)
    if settings.auth_mode == "oidc" and app.state.oidc is None:
        raise RuntimeError("AUTH_MODE=oidc requires OIDC_ISSUER and OIDC_AUDIENCE")
    app.state.quota = quota or build_quota(settings.redis_cache_url, settings.ai_daily_budget_per_tenant,
                                           settings.uploads_per_minute_per_tenant)

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                           allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])

    @app.middleware("http")
    async def correlation(request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get("X-Correlation-Id", "")
        cid = incoming if _CID.match(incoming) else uuid.uuid4().hex
        request.state.correlation_id = cid
        token = correlation_id_var.set(cid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error cid=%s", cid)
            response = _error(500, "INTERNAL_ERROR", "Unexpected server error", cid)
        finally:
            correlation_id_var.reset(token)
        route = getattr(request.scope.get("route"), "path", "unmatched")
        elapsed = time.perf_counter() - started
        HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, route).observe(elapsed)
        log.info("request", extra={"method": request.method, "route": route, "status": response.status_code,
                                   "duration_ms": round(elapsed * 1000, 1)})
        response.headers["X-Correlation-Id"] = cid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, getattr(request.state, "correlation_id", None), exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return _error(422, "VALIDATION_ERROR", "Request validation failed",
                      getattr(request.state, "correlation_id", None), details)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz() -> dict[str, str]:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        quota_state = app.state.quota
        cache = ("ok" if quota_state.ping() else "degraded") if isinstance(quota_state, RedisQuota) else "disabled"
        return {"status": "ready", "ai": app.state.explainer.name, "document_ai": app.state.document_ai.name,
                "cache": cache, "document_processing": settings.document_processing}

    if settings.metrics_enabled:
        # Scraped inside the cluster only; the BFF proxies nothing outside /v1.
        @app.get("/metrics", include_in_schema=False)
        def metrics() -> Response:
            return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    app.include_router(router)
    return app
