import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { accessTokenFor, AUTH_MODE, SESSION_COOKIE } from "@/lib/server/oidc";

// Backend-for-frontend proxy: the browser never holds backend credentials or tokens; identity comes from an
// HttpOnly session cookie (OIDC session id, or the dev demo cookie when AUTH_MODE=dev).
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const SECRET = process.env.DEV_BFF_SHARED_SECRET ?? "local-dev-only";
const ALLOWED_PATH = /^v1(\/[A-Za-z0-9_\-]+)*$/;
const FORWARD_HEADERS = [
  "content-type",
  "idempotency-key",
  "if-match",
  "x-correlation-id",
  "x-filename",
];
const MAX_BODY_BYTES = 10 * 1024 * 1024 + 64 * 1024;
// In-request OCR/extraction of scanned policies can take minutes.
const SLOW_PATH =
  /^v1\/policy-documents(\/[A-Za-z0-9]+\/(transcribe|extract))?$/;

type Ctx = { params: Promise<{ path: string[] }> };

function error(status: number, code: string, message: string) {
  return NextResponse.json(
    { error: { code, message, correlation_id: null, details: null } },
    { status },
  );
}

async function forward(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (!ALLOWED_PATH.test(joined))
    return error(404, "NOT_FOUND", "Unknown API path");

  if (req.method !== "GET") {
    const origin = req.headers.get("origin");
    const host = req.headers.get("host");
    const sameOrigin =
      origin !== null && host !== null && new URL(origin).host === host;
    if (!sameOrigin || req.headers.get("x-requested-with") !== "vla") {
      return error(403, "CSRF_REJECTED", "Cross-site request rejected");
    }
  }

  const jar = await cookies();
  let headers: Headers;
  if (AUTH_MODE === "oidc") {
    const sid = jar.get(SESSION_COOKIE)?.value;
    const token = sid ? await accessTokenFor(sid).catch(() => null) : null;
    if (!token) return error(401, "UNAUTHENTICATED", "Sign in required");
    headers = new Headers({ Authorization: `Bearer ${token}` });
  } else {
    const user = jar.get("vla_user")?.value;
    if (!user) return error(401, "UNAUTHENTICATED", "Sign in required");
    headers = new Headers({ "X-Dev-User": user, "X-Dev-Secret": SECRET });
  }
  const tenant = jar.get("vla_tenant")?.value;
  if (tenant) headers.set("X-Tenant-Id", tenant);
  for (const name of FORWARD_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }

  let upstream: Response;
  let body: ArrayBuffer | undefined;
  if (req.method !== "GET") {
    const length = Number(req.headers.get("content-length") ?? "0");
    if (length > MAX_BODY_BYTES)
      return error(413, "PAYLOAD_TOO_LARGE", "Uploads are limited to 10 MB");
    body = await req.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES)
      return error(413, "PAYLOAD_TOO_LARGE", "Uploads are limited to 10 MB");
  }
  const slow = req.method === "POST" && SLOW_PATH.test(joined);
  try {
    upstream = await fetch(`${BACKEND}/${joined}${req.nextUrl.search}`, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(slow ? 180_000 : 30_000),
    });
  } catch {
    return error(
      502,
      "BACKEND_UNAVAILABLE",
      "The lending service is unavailable. Please retry.",
    );
  }
  const out = new NextResponse(await upstream.arrayBuffer(), {
    status: upstream.status,
  });
  for (const name of [
    "content-type",
    "content-disposition",
    "x-correlation-id",
    "idempotent-replayed",
  ]) {
    const value = upstream.headers.get(name);
    if (value) out.headers.set(name, value);
  }
  out.headers.set("Cache-Control", "no-store");
  out.headers.set("X-Content-Type-Options", "nosniff");
  return out;
}

export const dynamic = "force-dynamic";
export const GET = forward;
export const POST = forward;
export const PATCH = forward;
