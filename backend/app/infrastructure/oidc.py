"""OIDC access-token validation for the API boundary (Cognito or any standards-based IdP)."""

import json
import logging
import urllib.request
from typing import Any

import jwt

log = logging.getLogger(__name__)
ALGORITHMS = ["RS256"]


class TokenInvalid(Exception):
    pass


class OidcVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str | None = None, token_use: str | None = None,
                 required_scope: str | None = None, leeway_s: int = 30) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.token_use = token_use
        self.required_scope = required_scope
        self.leeway_s = leeway_s
        self._jwks_url = jwks_url
        self._jwks: jwt.PyJWKClient | None = None

    def _client(self) -> jwt.PyJWKClient:
        if self._jwks is None:
            url = self._jwks_url or self._discover_jwks()
            self._jwks = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=5)
        return self._jwks

    def _discover_jwks(self) -> str:
        with urllib.request.urlopen(f"{self.issuer}/.well-known/openid-configuration", timeout=5) as resp:  # noqa: S310
            config = json.loads(resp.read())
        if config.get("issuer", "").rstrip("/") != self.issuer:
            raise TokenInvalid("discovery issuer mismatch")
        return str(config["jwks_uri"])

    def verify(self, token: str) -> dict[str, Any]:
        try:
            key = self._client().get_signing_key_from_jwt(token).key
            claims: dict[str, Any] = jwt.decode(
                token, key, algorithms=ALGORITHMS, issuer=self.issuer, leeway=self.leeway_s,
                options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": False})
        except (jwt.PyJWTError, OSError, KeyError, ValueError) as exc:
            log.info("token rejected: %s", type(exc).__name__)
            raise TokenInvalid(type(exc).__name__) from exc
        aud = claims.get("aud")
        audiences = aud if isinstance(aud, list) else [aud] if aud else []
        if self.audience not in audiences and claims.get("client_id") != self.audience:
            raise TokenInvalid("audience")
        if self.token_use and claims.get("token_use") != self.token_use:
            raise TokenInvalid("token_use")
        if self.required_scope and self.required_scope not in str(claims.get("scope", "")).split():
            raise TokenInvalid("scope")
        return claims
