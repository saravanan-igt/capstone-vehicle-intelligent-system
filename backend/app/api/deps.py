import hmac
from collections.abc import Iterator

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errors import AppError, forbidden
from app.application.security import Principal
from app.infrastructure.db import bind_tenant
from app.infrastructure.models import Membership, User, UserIdentity
from app.infrastructure.oidc import TokenInvalid

_dev_user_header = APIKeyHeader(name="X-Dev-User", auto_error=False, description="Demo user id in AUTH_MODE=dev (e.g. u-alice)")
_dev_secret_header = APIKeyHeader(name="X-Dev-Secret", auto_error=False, description="Shared secret in AUTH_MODE=dev")
_tenant_header = APIKeyHeader(name="X-Tenant-Id", auto_error=False, description="Optional tenant id override")
_bearer_scheme = HTTPBearer(auto_error=False, description="OIDC Bearer token in AUTH_MODE=oidc")


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.rollback()  # no-op after an explicit commit; discards partial work on errors
        session.close()


def correlation_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


def _dev_user(request: Request, session: Session) -> User:
    secret = request.headers.get("X-Dev-Secret", "")
    if not hmac.compare_digest(secret.encode(), request.app.state.settings.dev_shared_secret.encode()):
        raise AppError(401, "UNAUTHENTICATED", "Missing or invalid BFF credentials")
    user_id = request.headers.get("X-Dev-User", "")
    user = session.get(User, user_id) if user_id else None
    if user is None:
        raise AppError(401, "UNAUTHENTICATED", "Unknown user")
    return user


def _oidc_user(request: Request, session: Session) -> User:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AppError(401, "UNAUTHENTICATED", "Bearer token required")
    try:
        claims = request.app.state.oidc.verify(header[7:].strip())
    except TokenInvalid as exc:
        raise AppError(401, "INVALID_TOKEN", "Access token is invalid or expired") from exc
    identity = session.scalar(select(UserIdentity).where(UserIdentity.issuer == claims["iss"].rstrip("/"),
                                                         UserIdentity.subject == claims["sub"]))
    user = session.get(User, identity.user_id) if identity else None
    if user is None:
        raise forbidden("This sign-in is not linked to a user account; ask an administrator")
    return user


def _resolve_principal(request: Request, session: Session, user: User) -> Principal:
    memberships = list(session.scalars(select(Membership).where(Membership.user_id == user.id)))
    tenants = tuple(sorted({m.tenant_id for m in memberships}))
    if not tenants:
        raise forbidden("User has no tenant membership")
    requested = request.headers.get("X-Tenant-Id")
    if requested and requested not in tenants:
        raise forbidden("Not a member of the requested tenant")
    tenant_id = requested or tenants[0]
    bind_tenant(session, tenant_id)
    roles = frozenset(m.role for m in memberships if m.tenant_id == tenant_id)
    return Principal(user_id=user.id, email=user.email, display_name=user.display_name, tenant_id=tenant_id,
                     roles=roles, available_tenants=tenants)


def get_principal(
    request: Request,
    session: Session = Depends(get_session),
    _u: str | None = Depends(_dev_user_header),
    _s: str | None = Depends(_dev_secret_header),
    _t: str | None = Depends(_tenant_header),
    _b: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> Principal:
    mode = request.app.state.settings.auth_mode
    if mode == "dev":
        user = _dev_user(request, session)
    elif mode == "oidc" and getattr(request.app.state, "oidc", None) is not None:
        user = _oidc_user(request, session)
    else:
        raise AppError(401, "UNAUTHENTICATED", "Authentication is not configured")
    return _resolve_principal(request, session, user)


def get_brief_principal(
    request: Request,
    session: Session = Depends(get_session),
    _u: str | None = Depends(_dev_user_header),
    _s: str | None = Depends(_dev_secret_header),
    _t: str | None = Depends(_tenant_header),
    _b: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> Principal:
    """For the capstone brief endpoints: in dev mode, defaults to demo applicant `u-alice` when no auth headers are sent."""
    mode = request.app.state.settings.auth_mode
    if mode == "dev" and not request.headers.get("X-Dev-User") and not request.headers.get("X-Dev-Secret"):
        user = session.get(User, "u-alice")
        if user is None:
            raise AppError(401, "UNAUTHENTICATED", "Default demo user not found")
        return _resolve_principal(request, session, user)
    return get_principal(request, session)
