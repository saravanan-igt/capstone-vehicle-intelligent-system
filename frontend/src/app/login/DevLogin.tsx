"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Icon } from "@/components/Icon";

const DEMO_USERS = [
  {
    id: "u-alice",
    name: "Alice Applicant",
    role: "Applicant",
    tenant: "Northwind Auto Finance",
  },
  {
    id: "u-arjun",
    name: "Arjun Applicant",
    role: "Applicant",
    tenant: "Northwind Auto Finance",
  },
  {
    id: "u-omar",
    name: "Omar Officer",
    role: "Loan officer",
    tenant: "Northwind Auto Finance",
  },
  {
    id: "u-priya",
    name: "Priya Policy Admin",
    role: "Policy administrator",
    tenant: "Northwind Auto Finance",
  },
  {
    id: "u-tara",
    name: "Tara Tenant Admin",
    role: "Tenant administrator",
    tenant: "Northwind Auto Finance",
  },
  {
    id: "u-ben",
    name: "Ben Applicant",
    role: "Applicant",
    tenant: "Southbay Motor Credit",
  },
  {
    id: "u-lena",
    name: "Lena Officer",
    role: "Loan officer + policy admin",
    tenant: "Southbay Motor Credit",
  },
];

export default function DevLogin() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function signIn(userId: string) {
    setBusy(userId);
    setError(null);
    const res = await fetch("/api/session", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "vla",
      },
      body: JSON.stringify({ user_id: userId }),
    }).catch(() => null);
    setBusy(null);
    if (!res || !res.ok) {
      setError("Sign-in failed. Is the backend running on BACKEND_URL?");
      return;
    }
    router.push("/");
  }

  return (
    <>
      <h2 style={{ marginBottom: 6 }}>Choose a demo identity</h2>
      <p className="muted small" style={{ marginTop: 0 }}>
        Local development sign-in only (AUTH_MODE=dev). Set AUTH_MODE=oidc to
        use OIDC (Authorization Code + PKCE) with a server-side session.
      </p>
      {error && (
        <div className="notice error" role="alert" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}
      {DEMO_USERS.map((u) => (
        <button
          key={u.id}
          className="user-option"
          onClick={() => signIn(u.id)}
          disabled={busy !== null}
        >
          <span className="avatar">
            {u.name
              .split(" ")
              .map((p) => p[0])
              .join("")}
          </span>
          <span style={{ flex: 1 }}>
            <strong>{u.name}</strong>
            <span className="muted small" style={{ display: "block" }}>
              {u.role} · {u.tenant}
            </span>
          </span>
          {busy === u.id ? (
            <span className="small">Signing in…</span>
          ) : (
            <Icon name="chevron" width={16} />
          )}
        </button>
      ))}
    </>
  );
}
