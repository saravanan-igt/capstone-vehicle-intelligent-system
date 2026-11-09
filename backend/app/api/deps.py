import hmac
from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.errors import AppError, forbidden
from app.application.security import Principal
from app.infrastructure.db import bind_tenant
from app.infrastructure.models import Membership, User, UserIdentity
from app.infrastructure.oidc import TokenInvalid


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


def get_principal(request: Request, session: Session = Depends(get_session)) -> Principal:
    mode = request.app.state.settings.auth_mode
    if mode == "dev":
        user = _dev_user(request, session)
    elif mode == "oidc" and getattr(request.app.state, "oidc", None) is not None:
        user = _oidc_user(request, session)
    else:
        raise AppError(401, "UNAUTHENTICATED", "Authentication is not configured")
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
