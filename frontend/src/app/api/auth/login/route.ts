import { NextRequest, NextResponse } from "next/server";

import {
  AUTH_MODE,
  authorizationUrl,
  cookieOptions,
  safeReturnTo,
  TX_COOKIE,
} from "@/lib/server/oidc";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  if (AUTH_MODE !== "oidc")
    return NextResponse.redirect(new URL("/login", req.url));
  try {
    const { url, state } = await authorizationUrl(
      safeReturnTo(req.nextUrl.searchParams.get("returnTo")),
    );
    const res = NextResponse.redirect(url);
    // Binds the IdP round trip to this browser (login CSRF protection).
    res.cookies.set(TX_COOKIE, state, cookieOptions(600));
    return res;
  } catch {
    return NextResponse.redirect(
      new URL("/login?error=idp_unavailable", req.url),
    );
  }
}
