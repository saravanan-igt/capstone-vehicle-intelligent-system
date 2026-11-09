import { timingSafeEqual } from "node:crypto";

import { NextRequest, NextResponse } from "next/server";

import {
  AUTH_MODE,
  completeLogin,
  cookieOptions,
  SESSION_COOKIE,
  SESSION_TTL_S,
  TX_COOKIE,
} from "@/lib/server/oidc";

export const dynamic = "force-dynamic";

function sameState(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export async function GET(req: NextRequest) {
  const fail = (code: string) => {
    const res = NextResponse.redirect(new URL(`/login?error=${code}`, req.url));
    res.cookies.delete(TX_COOKIE);
    return res;
  };
  if (AUTH_MODE !== "oidc") return fail("oidc_disabled");
  const params = req.nextUrl.searchParams;
  if (params.get("error")) return fail("idp_denied");
  const state = params.get("state") ?? "";
  const code = params.get("code") ?? "";
  const expected = req.cookies.get(TX_COOKIE)?.value ?? "";
  if (!state || !code || !expected || !sameState(state, expected))
    return fail("state_mismatch");
  try {
    const { sid, returnTo } = await completeLogin(state, code);
    const res = NextResponse.redirect(new URL(returnTo, req.url));
    res.cookies.delete(TX_COOKIE);
    res.cookies.set(SESSION_COOKIE, sid, cookieOptions(SESSION_TTL_S));
    return res;
  } catch {
    return fail("login_failed");
  }
}
