"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ChangeEvent } from "react";

import { Icon } from "@/components/Icon";
import { useMe } from "@/components/Shell";
import {
  Empty,
  ErrorNotice,
  Loading,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type {
  PolicyDocumentDetail,
  PolicySourceDocument,
  PolicySummary,
} from "@/lib/types";

const MAX_BYTES = 256 * 1024;
const MAX_DOC_BYTES = 10 * 1024 * 1024;
const DOC_TYPES = ["application/pdf", "image/png", "image/jpeg"];

export default function PoliciesPage() {
  const me = useMe();
  const router = useRouter();
  const list = useApi<PolicySummary[]>("v1/policies");
  const canReadDocs = me?.permissions.includes("policy_document:read");
  const docs = useApi<PolicySourceDocument[]>(
    canReadDocs ? "v1/policy-documents" : null,
  );
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [docBusy, setDocBusy] = useState(false);
  const canWrite = me?.permissions.includes("policy:write");

  async function onDocument(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    setUploadError(null);
    setApiError(null);
    if (!file) return;
    if (!DOC_TYPES.includes(file.type) || file.size > MAX_DOC_BYTES) {
      setUploadError("Upload a PDF, PNG or JPEG up to 10 MB.");
      return;
    }
    setDocBusy(true);
    try {
      const doc = await api<PolicyDocumentDetail>("v1/policy-documents", {
        method: "POST",
        file,
      });
      router.push(`/policies/documents/${doc.id}`);
    } catch (err) {
      setApiError(err instanceof ApiError ? err : null);
    } finally {
      setDocBusy(false);
    }
  }

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    setUploadError(null);
    setApiError(null);
    if (!file) return;
    if (!file.name.endsWith(".json") || file.size > MAX_BYTES) {
      setUploadError("Upload a structured policy .json file up to 256 KB.");
      return;
    }
    let doc: unknown;
    try {
      doc = JSON.parse(await file.text());
    } catch {
      setUploadError("File is not valid JSON.");
      return;
    }
    setBusy(true);
    try {
      await api<PolicySummary>("v1/policies", { method: "POST", json: doc });
      list.reload();
    } catch (err) {
      setApiError(err instanceof ApiError ? err : null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Policies" crumbs="Policy | Versions" />
      <div className="content">
        {canWrite && (
          <div className="card" style={{ marginBottom: 22 }}>
            <div className="card-title">
              <h2>Add a policy</h2>
            </div>
            <p className="small muted" style={{ marginTop: 0 }}>
              Upload the lender&apos;s scanned policy (PDF, PNG or JPEG). Gemini
              transcribes it page by page and drafts structured rules; you
              review every rule against the source text before a draft is
              created. Drafts never affect decisions until published by an
              authorised policy administrator. Transcription runs while you wait
              and can take a minute or two.
            </p>
            <div className="btn-row">
              <label
                className="btn primary"
                style={{ cursor: docBusy ? "wait" : "pointer" }}
              >
                <Icon name="upload" width={14} />
                {docBusy
                  ? "Uploading and transcribing…"
                  : "Upload scanned policy"}
                <input
                  type="file"
                  accept="application/pdf,image/png,image/jpeg"
                  onChange={onDocument}
                  className="sr-only"
                  disabled={docBusy || busy}
                />
              </label>
              <label
                className="btn ghost"
                style={{ cursor: busy ? "wait" : "pointer" }}
              >
                <Icon name="doc" width={14} />
                {busy ? "Uploading…" : "Upload structured JSON"}
                <input
                  type="file"
                  accept="application/json,.json"
                  onChange={onFile}
                  className="sr-only"
                  disabled={busy || docBusy}
                />
              </label>
            </div>
            {uploadError && (
              <div className="notice error" style={{ marginTop: 10 }}>
                {uploadError}
              </div>
            )}
            {apiError && (
              <div style={{ marginTop: 10 }}>
                <ErrorNotice error={apiError} />
                {Array.isArray(apiError.details) && (
                  <ul className="small">
                    {(apiError.details as { loc?: unknown[]; msg?: string }[])
                      .slice(0, 8)
                      .map((d, i) => (
                        <li key={i}>
                          <span className="mono">
                            {(d.loc ?? []).join(".")}
                          </span>
                          : {d.msg}
                        </li>
                      ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}
        <div className="card">
          <div className="card-title">
            <h2>
              Policy versions <span className="sub">{me?.tenant.name}</span>
            </h2>
          </div>
          {list.error && (
            <ErrorNotice error={list.error} onRetry={list.reload} />
          )}
          {list.loading && <Loading />}
          {list.data && list.data.length === 0 && (
            <Empty>No policies for this tenant.</Empty>
          )}
          {list.data && list.data.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Policy</th>
                  <th>Status</th>
                  <th>Effective</th>
                  <th>Published</th>
                  <th>Content hash</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.data.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.policy_code}</strong> v{p.version}
                      <div className="small muted">{p.product}</div>
                    </td>
                    <td>
                      <StatusBadge value={p.status} />
                    </td>
                    <td>
                      {p.effective_from}
                      {p.effective_to ? ` → ${p.effective_to}` : " → open"}
                    </td>
                    <td className="small">
                      {p.published_at
                        ? `${dateTime(p.published_at)} by ${p.published_by}`
                        : "—"}
                    </td>
                    <td className="mono">{p.content_sha256.slice(0, 12)}</td>
                    <td>
                      <Link href={`/policies/${p.id}`} className="btn ghost">
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {canReadDocs && (
          <div className="card mt">
            <div className="card-title">
              <h2>
                Source documents <span className="sub">uploaded originals</span>
              </h2>
            </div>
            {docs.error && (
              <ErrorNotice error={docs.error} onRetry={docs.reload} />
            )}
            {docs.loading && <Loading rows={2} />}
            {docs.data && docs.data.length === 0 && (
              <Empty>No policy documents uploaded yet.</Empty>
            )}
            {docs.data && docs.data.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Status</th>
                    <th>Pages</th>
                    <th>Uploaded</th>
                    <th>SHA-256</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {docs.data.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <strong>{d.filename}</strong>
                        <div className="small muted">
                          {d.mime_type} · {(d.size_bytes / 1024).toFixed(0)} KB
                        </div>
                      </td>
                      <td>
                        <StatusBadge value={d.status} />
                      </td>
                      <td>{d.page_count ?? "—"}</td>
                      <td className="small">
                        {dateTime(d.created_at)} by {d.uploaded_by}
                      </td>
                      <td className="mono">{d.sha256.slice(0, 12)}</td>
                      <td>
                        <Link
                          href={`/policies/documents/${d.id}`}
                          className="btn ghost"
                        >
                          Review
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </>
  );
}
