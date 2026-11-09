import { createHash, randomBytes } from "node:crypto";

import { createRemoteJWKSet, jwtVerify } from "jose";

import { sessionStore } from "@/lib/server/store";

// OIDC Authorization Code + PKCE for the BFF. Tokens never reach the browser; it only holds an opaque session id.
export const AUTH_MODE = process.env.AUTH_MODE ?? "dev";
export const SESSION_TTL_S = 8 * 60 * 60;
const TX_TTL_S = 10 * 60;

export const SECURE_COOKIES = process.env.INSECURE_COOKIES !== "true";
export const SESSION_COOKIE = SECURE_COOKIES ? "__Host-vla_sid" : "vla_sid";
export const TX_COOKIE = SECURE_COOKIES ? "__Host-vla_oidc" : "vla_oidc";

// Lax so the cookie survives the top-level redirect back from the IdP; CSRF relies on Origin + custom header.
export const cookieOptions = (maxAge: number) => ({
  httpOnly: true,
  secure: SECURE_COOKIES,
  sameSite: "lax" as const,
  path: "/",
  maxAge,
});

type Discovery = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  jwks_uri: string;
  end_session_endpoint?: string;
  revocation_endpoint?: string;
};

export type Session = {
  sub: string;
  accessToken: string;
  refreshToken?: string;
  idToken: string;
  expiresAt: number;
};

export type AuthTx = { verifier: string; nonce: string; returnTo: string };

type TokenResponse = {
  access_token: string;
  id_token?: string;
  refresh_token?: string;
  expires_in?: number;
};

function config() {
  const issuer = (process.env.OIDC_ISSUER ?? "").replace(/\/$/, "");
  const clientId = process.env.OIDC_CLIENT_ID ?? "";
  const baseUrl = (process.env.APP_BASE_URL ?? "").replace(/\/$/, "");
  if (!issuer || !clientId || !baseUrl)
    throw new Error(
      "OIDC_ISSUER, OIDC_CLIENT_ID and APP_BASE_URL are required",
    );
  return {
    issuer,
    clientId,
    clientSecret: process.env.OIDC_CLIENT_SECRET,
    scopes: process.env.OIDC_SCOPES ?? "openid email profile",
    redirectUri: `${baseUrl}/api/auth/callback`,
    postLogoutUri: `${baseUrl}/login`,
    logoutUrl: process.env.OIDC_LOGOUT_URL,
  };
}

const cache = globalThis as unknown as {
  __vlaDiscovery?: Discovery;
  __vlaJwks?: ReturnType<typeof createRemoteJWKSet>;
};

async function discovery(): Promise<Discovery> {
  if (!cache.__vlaDiscovery) {
    const { issuer } = config();
    const res = await fetch(`${issuer}/.well-known/openid-configuration`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) throw new Error(`OIDC discovery failed (${res.status})`);
    const doc = (await res.json()) as Discovery;
    if (doc.issuer.replace(/\/$/, "") !== issuer)
      throw new Error("OIDC discovery issuer mismatch");
    cache.__vlaDiscovery = doc;
  }
  return cache.__vlaDiscovery;
}

export const randomToken = () => randomBytes(32).toString("base64url");
const challenge = (verifier: string) =>
  createHash("sha256").update(verifier).digest("base64url");

export function safeReturnTo(value: string | null): string {
  return value &&
    value.startsWith("/") &&
    !value.startsWith("//") &&
    !value.startsWith("/\\")
    ? value
    : "/";
}

export async function authorizationUrl(
  returnTo: string,
): Promise<{ url: string; state: string }> {
  const { clientId, scopes, redirectUri } = config();
  const d = await discovery();
  const state = randomToken();
  const tx: AuthTx = {
    verifier: randomToken(),
    nonce: randomToken(),
    returnTo,
  };
  await sessionStore().set(`vla:bff:tx:${state}`, tx, TX_TTL_S);
  const url = new URL(d.authorization_endpoint);
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: scopes,
    state,
    nonce: tx.nonce,
    code_challenge: challenge(tx.verifier),
    code_challenge_method: "S256",
  }).toString();
  return { url: url.toString(), state };
}

function clientAuth(body: URLSearchParams): Record<string, string> {
  const { clientId, clientSecret } = config();
  const headers: Record<string, string> = {
    "Content-Type": "application/x-www-form-urlencoded",
  };
  if (clientSecret) {
    const basic = `${encodeURIComponent(clientId)}:${encodeURIComponent(clientSecret)}`;
    headers.Authorization = `Basic ${Buffer.from(basic).toString("base64")}`;
  } else {
    body.set("client_id", clientId);
  }
  return headers;
}

async function tokenRequest(
  params: Record<string, string>,
): Promise<TokenResponse> {
  const d = await discovery();
  const body = new URLSearchParams(params);
  const res = await fetch(d.token_endpoint, {
    method: "POST",
    headers: clientAuth(body),
    body,
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) throw new Error(`token endpoint returned ${res.status}`);
  return (await res.json()) as TokenResponse;
}

async function verifyIdToken(idToken: string, nonce: string | null) {
  const { issuer, clientId } = config();
  const d = await discovery();
  cache.__vlaJwks ??= createRemoteJWKSet(new URL(d.jwks_uri));
  const { payload } = await jwtVerify(idToken, cache.__vlaJwks, {
    issuer: [issuer, `${issuer}/`],
    audience: clientId,
    algorithms: ["RS256"],
  });
  if (nonce !== null && payload.nonce !== nonce)
    throw new Error("nonce mismatch");
  if (!payload.sub) throw new Error("id_token without sub");
  return payload;
}

export async function completeLogin(
  state: string,
  code: string,
): Promise<{ sid: string; returnTo: string }> {
  const tx = await sessionStore().take<AuthTx>(`vla:bff:tx:${state}`);
  if (!tx) throw new Error("unknown or expired login transaction");
  const tokens = await tokenRequest({
    grant_type: "authorization_code",
    code,
    redirect_uri: config().redirectUri,
    code_verifier: tx.verifier,
  });
  if (!tokens.id_token) throw new Error("token response without id_token");
  const claims = await verifyIdToken(tokens.id_token, tx.nonce);
  const session: Session = {
    sub: String(claims.sub),
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    idToken: tokens.id_token,
    expiresAt: Date.now() + (tokens.expires_in ?? 300) * 1000,
  };
  const sid = randomToken();
  await sessionStore().set(`vla:bff:session:${sid}`, session, SESSION_TTL_S);
  return { sid, returnTo: tx.returnTo };
}

/** Access token for the session, refreshed shortly before expiry. Null means the session is gone. */
export async function accessTokenFor(sid: string): Promise<string | null> {
  const key = `vla:bff:session:${sid}`;
  const session = await sessionStore().get<Session>(key);
  if (!session) return null;
  if (session.expiresAt - 60_000 > Date.now()) return session.accessToken;
  if (!session.refreshToken) {
    await sessionStore().del(key);
    return null;
  }
  try {
    const tokens = await tokenRequest({
      grant_type: "refresh_token",
      refresh_token: session.refreshToken,
    });
    if (tokens.id_token) await verifyIdToken(tokens.id_token, null);
    const next: Session = {
      ...session,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token ?? session.refreshToken,
      idToken: tokens.id_token ?? session.idToken,
      expiresAt: Date.now() + (tokens.expires_in ?? 300) * 1000,
    };
    await sessionStore().set(key, next, SESSION_TTL_S);
    return next.accessToken;
  } catch {
    await sessionStore().del(key);
    return null;
  }
}

/** Ends the local session, revokes the refresh token where supported, and returns the IdP logout URL. */
export async function endSession(sid: string | undefined): Promise<string> {
  const { clientId, postLogoutUri, logoutUrl } = config();
  const session = sid
    ? await sessionStore().take<Session>(`vla:bff:session:${sid}`)
    : null;
  const d = await discovery().catch(() => null);
  if (session?.refreshToken && d?.revocation_endpoint) {
    const body = new URLSearchParams({
      token: session.refreshToken,
      token_type_hint: "refresh_token",
    });
    await fetch(d.revocation_endpoint, {
      method: "POST",
      headers: clientAuth(body),
      body,
      signal: AbortSignal.timeout(5000),
    }).catch(() => undefined);
  }
  if (logoutUrl) return logoutUrl;
  if (d?.end_session_endpoint) {
    const url = new URL(d.end_session_endpoint);
    url.search = new URLSearchParams({
      client_id: clientId,
      post_logout_redirect_uri: postLogoutUri,
      ...(session ? { id_token_hint: session.idToken } : {}),
    }).toString();
    return url.toString();
  }
  return "/login";
}
