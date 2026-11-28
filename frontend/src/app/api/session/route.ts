import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

// DEV-ONLY demo sign-in. Disabled unless AUTH_MODE=dev. Production uses OIDC via the identity provider.
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const SECRET = process.env.DEV_BFF_SHARED_SECRET ?? "local-dev-only";
const DEV = (process.env.AUTH_MODE ?? "dev") === "dev";
const LENDER_DEMO_USERS = new Set([
  "u-omar",
  "u-priya",
  "u-tara",
  "u-lena",
]);

const cookieOpts = {
  httpOnly: true,
  sameSite: "strict" as const,
  secure:
    process.env.NODE_ENV === "production" &&
    process.env.INSECURE_COOKIES !== "true",
  path: "/",
  maxAge: 60 * 60 * 8,
};

export async function POST(req: NextRequest) {
  if (!DEV)
    return NextResponse.json({ error: { code: "NOT_FOUND" } }, { status: 404 });
  if (req.headers.get("x-requested-with") !== "vla") {
    return NextResponse.json(
      { error: { code: "CSRF_REJECTED" } },
      { status: 403 },
    );
  }
  const body = (await req.json().catch(() => null)) as {
    user_id?: unknown;
    tenant_id?: unknown;
  } | null;
  const userId = typeof body?.user_id === "string" ? body.user_id : "";
  const tenantId = typeof body?.tenant_id === "string" ? body.tenant_id : "";
  if (!LENDER_DEMO_USERS.has(userId)) {
    return NextResponse.json(
      { error: { code: "FORBIDDEN", message: "Applicant identities cannot sign in to the lender dashboard" } },
      { status: 403 },
    );
  }
  if (
    !/^[a-z0-9\-]{1,64}$/.test(userId) ||
    (tenantId && !/^[a-z0-9\-]{1,64}$/.test(tenantId))
  ) {
    return NextResponse.json(
      { error: { code: "VALIDATION_ERROR", message: "Invalid user" } },
      { status: 422 },
    );
  }
  const headers: Record<string, string> = {
    "X-Dev-User": userId,
    "X-Dev-Secret": SECRET,
  };
  if (tenantId) headers["X-Tenant-Id"] = tenantId;
  let res: Response;
  try {
    res = await fetch(`${BACKEND}/v1/me`, { headers, cache: "no-store" });
  } catch {
    return NextResponse.json(
      {
        error: { code: "BACKEND_UNAVAILABLE", message: "Backend unavailable" },
      },
      { status: 502 },
    );
  }
  if (!res.ok)
    return new NextResponse(await res.text(), { status: res.status });
  const jar = await cookies();
  jar.set("vla_user", userId, cookieOpts);
  if (tenantId) jar.set("vla_tenant", tenantId, cookieOpts);
  else jar.delete("vla_tenant");
  return NextResponse.json(await res.json());
}

export async function DELETE(req: NextRequest) {
  if (req.headers.get("x-requested-with") !== "vla") {
    return NextResponse.json(
      { error: { code: "CSRF_REJECTED" } },
      { status: 403 },
    );
  }
  const jar = await cookies();
  jar.delete("vla_user");
  jar.delete("vla_tenant");
  return new NextResponse(null, { status: 204 });
}
