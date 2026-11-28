"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useMe } from "@/components/Shell";
import {
  Empty,
  ErrorNotice,
  Loading,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { Application, Page } from "@/lib/types";

export default function ApplicationsPage() {
  const me = useMe();
  const [items, setItems] = useState<Application[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  async function load(next: string | null) {
    setLoading(true);
    setError(null);
    try {
      const page = await api<Page<Application>>(
        `v1/applications?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ""}`,
      );
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e
          : new ApiError(0, "NETWORK", "Network error", null, null),
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(null);
  }, []);

  return (
    <>
      <PageHeader
        title="Applications"
        crumbs="Lending | Applications"
        action={
          me?.permissions.includes("application:create") ? (
            <Link href="/applications/new" className="pill-btn">
              Add New
            </Link>
          ) : undefined
        }
      />
      <div className="content">
        <div className="card">
          <div className="card-title">
            <h2>
              {me?.permissions.includes("application:read_all")
                ? "All tenant applications"
                : "My applications"}
            </h2>
          </div>
          {error && <ErrorNotice error={error} onRetry={() => load(null)} />}
          {!loading && !error && items.length === 0 && (
            <Empty>No applications found.</Empty>
          )}
          {items.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Created</th>
                  <th>Customer</th>
                  <th>Workflow</th>
                  <th>Latest outcome</th>
                  <th className="num">Requested</th>
                  <th className="num">Eligible</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id}>
                    <td>
                      {dateTime(a.created_at)}
                      <div className="mono muted">{a.id.slice(0, 10)}</div>
                    </td>
                    <td>
                      {a.applicant?.display_name ?? "—"}
                      <div className="muted small">{a.applicant?.email ?? "—"}</div>
                    </td>
                    <td>
                      <StatusBadge value={a.status} />
                    </td>
                    <td>
                      <StatusBadge
                        value={
                          a.latest_decision?.outcome ??
                          a.latest_decision?.status
                        }
                      />
                    </td>
                    <td className="num">
                      {money(a.input.requested_principal)}
                    </td>
                    <td className="num">
                      {money(a.latest_decision?.eligible_principal)}
                    </td>
                    <td className="num">
                      {["DRAFT", "INCOMPLETE", "NEEDS_REVIEW"].includes(
                        a.status,
                      ) &&
                        a.applicant_user_id === me?.user_id && (
                          <Link
                            className="btn ghost"
                            href={`/applications/new?id=${a.id}`}
                          >
                            Resume
                          </Link>
                        )}{" "}
                      <Link
                        className="btn primary"
                        href={`/applications/${a.id}`}
                      >
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {loading && <Loading />}
          {cursor && !loading && (
            <div style={{ textAlign: "center", marginTop: 14 }}>
              <button className="btn ghost" onClick={() => load(cursor)}>
                Load more
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
