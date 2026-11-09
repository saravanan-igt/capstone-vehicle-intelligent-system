"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, type ReactNode } from "react";

import { Icon, type IconName } from "@/components/Icon";
import { Logo } from "@/components/Logo";
import { useApi } from "@/lib/api";
import type { Me } from "@/lib/types";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

type NavItem = { href: string; label: string; icon: IconName; perm?: string };
const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Lending",
    items: [
      { href: "/", label: "Dashboard", icon: "dashboard" },
      {
        href: "/applications/new",
        label: "New Application",
        icon: "form",
        perm: "application:create",
      },
      { href: "/applications", label: "Applications", icon: "list" },
    ],
  },
  {
    section: "Catalogue",
    items: [
      {
        href: "/vehicles",
        label: "Vehicles",
        icon: "car",
        perm: "vehicle:read",
      },
    ],
  },
  {
    section: "Policy",
    items: [
      {
        href: "/policies",
        label: "Policies",
        icon: "policy",
        perm: "policy:read",
      },
    ],
  },
  {
    section: "Administration",
    items: [
      { href: "/audit", label: "Audit Log", icon: "audit", perm: "audit:read" },
    ],
  },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  if (href === "/applications")
    return (
      pathname === "/applications" || /^\/applications\/(?!new)/.test(pathname)
    );
  return pathname.startsWith(href);
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: me } = useApi<Me>("v1/me");

  async function logout() {
    const res = await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "X-Requested-With": "vla" },
    }).catch(() => null);
    const body = (await res?.json().catch(() => null)) as {
      redirect?: string;
    } | null;
    // The IdP logout URL (OIDC) ends the provider session too; dev mode returns /login.
    if (body?.redirect && /^(https?:\/\/|\/)/.test(body.redirect))
      window.location.assign(body.redirect);
    else router.push("/login");
  }

  const perms = new Set(me?.permissions ?? []);
  const initials = (me?.display_name ?? "?")
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2);

  return (
    <MeContext.Provider value={me}>
      <a href="#main" className="sr-only">
        Skip to content
      </a>
      <div className="shell">
        <aside className="sidebar" aria-label="Primary">
          <Logo />
          <nav>
            {NAV.map((group) => {
              const items = group.items.filter(
                (i) => !i.perm || perms.has(i.perm),
              );
              if (items.length === 0) return null;
              return (
                <div key={group.section}>
                  <div className="nav-section">{group.section}</div>
                  {items.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`nav-link${isActive(pathname, item.href) ? " active" : ""}`}
                      aria-current={
                        isActive(pathname, item.href) ? "page" : undefined
                      }
                    >
                      <Icon name={item.icon} />
                      {item.label}
                      <Icon name="chevron" className="chev" />
                    </Link>
                  ))}
                </div>
              );
            })}
          </nav>
        </aside>
        <div className="main">
          <header className="topbar">
            <div className="menu" aria-hidden="true">
              <span>
                <Icon name="menu" width={14} />
                Lending <Icon name="down" width={12} />
              </span>
              <span>
                <Icon name="settings" width={14} />
                Settings <Icon name="down" width={12} />
              </span>
            </div>
            <div className="search">
              <label htmlFor="global-search" className="sr-only">
                Search vehicles
              </label>
              <input
                id="global-search"
                placeholder="Search vehicles"
                onKeyDown={(e) => {
                  if (e.key === "Enter")
                    router.push(
                      `/vehicles?make=${encodeURIComponent(e.currentTarget.value)}`,
                    );
                }}
              />
              <Icon name="search" />
            </div>
            <div className="topbar-right">
              <span
                className="badge purple"
                title="All lenders, applicants and vehicles are synthetic"
              >
                SYNTHETIC DATA
              </span>
              <span className="icon-btn" aria-hidden="true">
                <Icon name="bell" width={18} />
                <span className="dot" />
              </span>
              <span className="icon-btn" aria-hidden="true">
                <Icon name="mail" width={18} />
              </span>
              <span className="small" aria-hidden="true">
                <Icon name="globe" width={14} /> English
              </span>
              <div className="user-menu">
                <span className="avatar" aria-hidden="true">
                  {initials}
                </span>
                <span className="who">
                  <strong>{me?.display_name ?? "…"}</strong>
                  <small>
                    {me
                      ? `${me.tenant.name ?? me.tenant.id} · ${me.roles.join(", ")}`
                      : ""}
                  </small>
                </span>
                <button
                  className="icon-btn"
                  onClick={logout}
                  title="Sign out"
                  aria-label="Sign out"
                >
                  <Icon name="logout" width={18} />
                </button>
              </div>
            </div>
          </header>
          <main
            id="main"
            style={{ display: "flex", flexDirection: "column", flex: 1 }}
          >
            {children}
          </main>
          <footer className="footer">
            © Vehicle Loan Advisor | Capstone demonstration · indicative results
            only | 2026
          </footer>
        </div>
      </div>
    </MeContext.Provider>
  );
}
