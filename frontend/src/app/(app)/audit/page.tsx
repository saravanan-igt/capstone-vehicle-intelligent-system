"use client";

import { useEffect, useState } from "react";

import { Empty, ErrorNotice, Loading, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { AuditEvent, Page } from "@/lib/types";

export default function AuditPage() {
  const [items, setItems] = useState<AuditEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  async function load(next: string | null) {
    setLoading(true);
    setError(null);
    try {
      const page = await api<Page<AuditEvent>>(
        `v1/audit-events?limit=50${next ? `&cursor=${encodeURIComponent(next)}` : ""}`,
      );
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e instanceof ApiError ? e : null);
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
        title="Audit Log"
        crumbs="Administration | Audit events (tenant-scoped)"
      />
      <div className="content">
        <div className="card">
          {error && <ErrorNotice error={error} onRetry={() => load(null)} />}
          {!loading && !error && items.length === 0 && (
            <Empty>No audit events.</Empty>
          )}
          {items.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Entity</th>
                  <th>Details</th>
                  <th>Correlation</th>
                </tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.id}>
                    <td>{dateTime(e.created_at)}</td>
                    <td>{e.actor_user_id}</td>
                    <td>
                      <span className="badge blue">{e.action}</span>
                    </td>
                    <td className="mono">
                      {e.entity_type}:{e.entity_id.slice(0, 10)}
                    </td>
                    <td className="mono">{JSON.stringify(e.details)}</td>
                    <td className="mono">
                      {e.correlation_id?.slice(0, 12) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {loading && <Loading />}
          {cursor && !loading && (
            <div style={{ textAlign: "center", marginTop: 12 }}>
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
