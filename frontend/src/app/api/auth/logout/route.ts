import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { AUTH_MODE, endSession, SESSION_COOKIE } from "@/lib/server/oidc";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  if (
    !origin ||
    !host ||
    new URL(origin).host !== host ||
    req.headers.get("x-requested-with") !== "vla"
  ) {
    return NextResponse.json(
      { error: { code: "CSRF_REJECTED" } },
      { status: 403 },
    );
  }
  const jar = await cookies();
  let redirect = "/login";
  if (AUTH_MODE === "oidc") {
    redirect = await endSession(jar.get(SESSION_COOKIE)?.value).catch(
      () => "/login",
    );
    jar.delete(SESSION_COOKIE);
  } else {
    jar.delete("vla_user");
    jar.delete("vla_tenant");
  }
  return NextResponse.json({ redirect });
}
