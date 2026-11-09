"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { useMe } from "@/components/Shell";
import {
  Cite,
  ErrorNotice,
  Loading,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { humanize } from "@/lib/format";
import type { PolicyDetail } from "@/lib/types";

export default function PolicyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const {
    data: p,
    error,
    loading,
    reload,
  } = useApi<PolicyDetail>(`v1/policies/${id}`);
  const [publishError, setPublishError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function publish() {
    if (
      !window.confirm(
        "Publish this policy? It will govern new decisions from its effective date.",
      )
    )
      return;
    setBusy(true);
    setPublishError(null);
    try {
      await api(`v1/policies/${id}/publish`, { method: "POST" });
      reload();
    } catch (e) {
      setPublishError(e instanceof ApiError ? e : null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Policy"
        crumbs={p ? `Policy | ${p.policy_code} v${p.version}` : "Policy"}
        action={p && <StatusBadge value={p.status} />}
      />
      <div className="content">
        {error && <ErrorNotice error={error} onRetry={reload} />}
        {loading && (
          <div className="card">
            <Loading rows={6} />
          </div>
        )}
        {p && (
          <>
            <div className="grid g-2-1">
              <div className="card">
                <div className="card-title">
                  <h2>{p.document.lender_name}</h2>
                  {p.document.synthetic && (
                    <span className="badge purple">SYNTHETIC</span>
                  )}
                </div>
                <dl className="dl">
                  <dt>Product</dt>
                  <dd>{p.product}</dd>
                  <dt>Currency / jurisdiction</dt>
                  <dd>
                    {p.document.currency} / {p.document.jurisdiction}
                  </dd>
                  <dt>Effective</dt>
                  <dd>
                    {p.effective_from} → {p.effective_to ?? "open"}
                  </dd>
                  <dt>Source document</dt>
                  <dd>{p.document.source_document}</dd>
                  <dt>SHA-256</dt>
                  <dd className="mono">{p.content_sha256}</dd>
                </dl>
              </div>
              <div className="card">
                <div className="card-title">
                  <h2>Lifecycle</h2>
                </div>
                <dl className="dl small">
                  <dt>Created by</dt>
                  <dd>{p.created_by}</dd>
                  <dt>Published by</dt>
                  <dd>{p.published_by ?? "—"}</dd>
                  {p.source_document_id && (
                    <>
                      <dt>Source document</dt>
                      <dd>
                        <Link
                          href={`/policies/documents/${p.source_document_id}`}
                        >
                          Compare with original
                        </Link>
                      </dd>
                    </>
                  )}
                </dl>
                {p.status === "DRAFT" &&
                  me?.permissions.includes("policy:publish") && (
                    <button
                      className="btn primary"
                      style={{ marginTop: 12 }}
                      onClick={publish}
                      disabled={busy}
                    >
                      {busy ? "Publishing…" : "Review complete — publish"}
                    </button>
                  )}
                {publishError && (
                  <div style={{ marginTop: 10 }}>
                    <ErrorNotice error={publishError} />
                  </div>
                )}
              </div>
            </div>
            <div className="grid g-2 mt">
              <div className="card">
                <div className="card-title">
                  <h2>Executable rules</h2>
                </div>
                <table className="table">
                  <tbody>
                    {Object.entries(p.document.rules).flatMap(
                      ([name, rule]) => {
                        if (!rule) return [];
                        const { clause, ...params } = rule;
                        return [
                          <tr key={name}>
                            <td>
                              <strong>{humanize(name)}</strong>
                              <Cite id={clause} />
                            </td>
                            <td className="mono">{JSON.stringify(params)}</td>
                          </tr>,
                        ];
                      },
                    )}
                  </tbody>
                </table>
              </div>
              <div className="card">
                <div className="card-title">
                  <h2>Source clauses</h2>
                </div>
                {p.document.clauses.map((c) => (
                  <div key={c.id} className="clause">
                    <div className="meta">
                      {c.id} · §{c.section} · page {c.page} · {c.title}
                    </div>
                    {c.text}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
