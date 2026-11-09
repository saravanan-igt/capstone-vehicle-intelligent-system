"""Phase 3: API-boundary validation of OIDC access tokens (signature, issuer, audience/client_id, expiry, token_use,
scope) and subject-to-user linking. Tokens are signed locally; no IdP is contacted."""

import time
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.infrastructure.db import make_engine, make_session_factory, session_scope
from app.infrastructure.models import UserIdentity
from app.infrastructure.oidc import OidcVerifier
from app.main import create_app
from tests.conftest import SECRET, TODAY

ISSUER = "https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_TEST"
CLIENT_ID = "vla-web-client"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StaticJwks:
    def get_signing_key_from_jwt(self, token: str) -> Any:
        return type("K", (), {"key": KEY.public_key()})()


def token(key: Any = KEY, alg: str = "RS256", **claims: Any) -> str:
    now = int(time.time())
    body = {"iss": ISSUER, "sub": "sub-alice", "client_id": CLIENT_ID, "token_use": "access",
            "scope": "openid vla/api", "iat": now, "exp": now + 300, **claims}
    return jwt.encode({k: v for k, v in body.items() if v is not None}, key, algorithm=alg)


@pytest.fixture()
def oidc_client(make_settings: Callable[..., Settings]) -> Iterator[TestClient]:
    settings = make_settings(auth_mode="oidc", oidc_issuer=ISSUER, oidc_audience=CLIENT_ID,
                             oidc_token_use="access", oidc_required_scope="vla/api")
    verifier = OidcVerifier(ISSUER, CLIENT_ID, token_use="access", required_scope="vla/api")
    verifier._jwks = _StaticJwks()  # type: ignore[assignment]
    app = create_app(settings, today=lambda: TODAY, oidc=verifier)
    engine = make_engine(settings.database_admin_url or settings.database_url)
    with session_scope(make_session_factory(engine)) as s:
        s.add(UserIdentity(issuer=ISSUER, subject="sub-alice", user_id="u-alice"))
    engine.dispose()
    with TestClient(app) as client:
        yield client
    app.state.engine.dispose()


def me(client: TestClient, bearer: str | None, **headers: str) -> Any:
    auth = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return client.get("/v1/me", headers={**auth, **headers})


def test_valid_access_token_maps_to_linked_user(oidc_client: TestClient) -> None:
    r = me(oidc_client, token())
    assert r.status_code == 200 and r.json()["user_id"] == "u-alice" and r.json()["tenant"]["id"] == "t-northwind"


@pytest.mark.parametrize("bad", [
    token(exp=int(time.time()) - 600, iat=int(time.time()) - 900),
    token(iss="https://evil.example/issuer"),
    token(client_id="another-client"),
    token(token_use="id"),
    token(scope="openid"),
    token(key=OTHER_KEY),
    token(key="algorithm-confusion-attempt-0123456789", alg="HS256"),
    token(sub=None),
    "not-a-jwt",
])
def test_invalid_tokens_are_rejected(oidc_client: TestClient, bad: str) -> None:
    r = me(oidc_client, bad)
    assert r.status_code == 401 and r.json()["error"]["code"] in {"INVALID_TOKEN", "UNAUTHENTICATED"}


def test_unlinked_subject_is_forbidden_and_dev_headers_are_ignored(oidc_client: TestClient) -> None:
    assert me(oidc_client, token(sub="someone-else")).status_code == 403
    assert me(oidc_client, None, **{"X-Dev-User": "u-alice", "X-Dev-Secret": SECRET}).status_code == 401


def test_tenant_header_cannot_escalate(oidc_client: TestClient) -> None:
    assert me(oidc_client, token(), **{"X-Tenant-Id": "t-southbay"}).status_code == 403
