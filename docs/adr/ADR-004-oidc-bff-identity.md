# ADR-004: OIDC through a backend-for-frontend; Amazon Cognito selected

**Status:** Accepted and implemented, 2026-11-09 (`AUTH_MODE=oidc`), and verified end to end against a standards-based mock IdP. **Not yet verified against a real Cognito user pool.** `AUTH_MODE=dev` remains for the local demo.

## Context

Tokens must not sit in browser storage. Admins need MFA, and the target deployment is AWS.

## Decision

- The Next.js server acts as a backend-for-frontend (BFF). It runs the Authorization Code + PKCE flow, keeps tokens server-side, and gives the browser only an HttpOnly, Secure, SameSite=Strict session cookie. Non-GET requests also need a same-Origin check and a custom header.
- The API validates the JWT signature (JWKS), issuer, audience, expiry and scopes. It derives the tenant from membership, not from client input.
- **Identity provider:** Amazon Cognito user pools. Cognito is AWS-native, supports MFA and integrates with IAM. Requiring MFA for admin groups is planned.

## Alternatives

- **Auth0 / Okta:** richer B2B organisation features, but higher cost and an extra vendor.
- **Keycloak:** self-hosted, so we would have to operate and patch it ourselves.

## Limitations

- Dev mode trusts a demo identity cookie plus a BFF shared secret. It must never be exposed outside local development.

## Revisit when

- A target lender mandates its own workforce IdP, which would mean federating into Cognito or switching.
