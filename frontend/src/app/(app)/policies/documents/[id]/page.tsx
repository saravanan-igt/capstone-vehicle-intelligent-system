"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

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
  DocumentSearch,
  PolicyDocumentDetail,
  PolicySummary,
  ReviewProblem,
} from "@/lib/types";

const HAS_TEXT = (d: PolicyDocumentDetail) => d.text_version > 0;

function problemList(details: unknown): ReviewProblem[] {
  if (!Array.isArray(details)) return [];
  return (details as { loc?: unknown; msg?: unknown }[]).map((d) => ({
    loc: Array.isArray(d.loc) ? d.loc.join(".") : String(d.loc ?? ""),
    msg: String(d.msg ?? ""),
  }));
}

function Problems({ items }: { items: ReviewProblem[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="small" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
      {items.slice(0, 30).map((p, i) => (
        <li key={i}>
          <span className="mono">{p.loc || "document"}</span>: {p.msg}
        </li>
      ))}
    </ul>
  );
}

export default function PolicyDocumentPage() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const canWrite = me?.permissions.includes("policy:write");
  const {
    data: doc,
    error,
    loading,
    reload,
    setData,
  } = useApi<PolicyDocumentDetail>(`v1/policy-documents/${id}`);
  const [busy, setBusy] = useState<"transcribe" | "extract" | "draft" | null>(
    null,
  );
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [draftText, setDraftText] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [created, setCreated] = useState<PolicySummary | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<DocumentSearch | null>(null);

  useEffect(() => {
    setDraftText(
      doc?.extraction ? JSON.stringify(doc.extraction, null, 2) : "",
    );
    setReviewed(false);
  }, [doc?.extraction]);

  // Background (queue) mode: refresh until the worker finishes.
  useEffect(() => {
    if (doc?.status !== "PROCESSING") return;
    const timer = window.setTimeout(reload, 3000);
    return () => window.clearTimeout(timer);
  }, [doc, reload]);

  async function run(kind: "transcribe" | "extract") {
    setBusy(kind);
    setActionError(null);
    try {
      setData(
        await api<PolicyDocumentDetail>(`v1/policy-documents/${id}/${kind}`, {
          method: "POST",
        }),
      );
    } catch (e) {
      setActionError(e instanceof ApiError ? e : null);
    } finally {
      setBusy(null);
    }
  }

  async function createDraft(e: FormEvent) {
    e.preventDefault();
    setActionError(null);
    let payload: unknown;
    try {
      payload = JSON.parse(draftText);
    } catch {
      setActionError(
        new ApiError(
          0,
          "INVALID_JSON",
          "The reviewed draft is not valid JSON",
          null,
          null,
        ),
      );
      return;
    }
    setBusy("draft");
    try {
      setCreated(
        await api<PolicySummary>(`v1/policy-documents/${id}/policy-drafts`, {
          method: "POST",
          json: payload,
        }),
      );
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err : null);
    } finally {
      setBusy(null);
    }
  }

  async function onSearch(e: FormEvent) {
    e.preventDefault();
    if (query.trim().length < 2) return;
    try {
      setSearch(
        await api<DocumentSearch>(
          `v1/policy-documents/${id}/search?q=${encodeURIComponent(query.trim())}`,
        ),
      );
    } catch (err) {
      setActionError(err instanceof ApiError ? err : null);
    }
  }

  const fileUrl = `/api/bff/v1/policy-documents/${id}/file`;
  const hasText = doc ? HAS_TEXT(doc) : false;
  const processing = doc?.status === "PROCESSING";

  return (
    <>
      <PageHeader
        title="Policy document"
        crumbs={
          doc ? `Policy | Documents | ${doc.filename}` : "Policy | Documents"
        }
        action={doc && <StatusBadge value={doc.status} />}
      />
      <div className="content">
        {error && <ErrorNotice error={error} onRetry={reload} />}
        {loading && !doc && (
          <div className="card">
            <Loading rows={6} />
          </div>
        )}
        {doc && (
          <>
            <div className="grid g-2-1">
              <div className="card">
                <div className="card-title">
                  <h2>{doc.filename}</h2>
                  <a
                    className="btn ghost"
                    href={fileUrl}
                    target="_blank"
                    rel="noopener"
                  >
                    <Icon name="doc" width={14} />
                    Open original
                  </a>
                </div>
                <dl className="dl">
                  <dt>Type / size</dt>
                  <dd>
                    {doc.mime_type} · {(doc.size_bytes / 1024).toFixed(0)} KB
                  </dd>
                  <dt>SHA-256</dt>
                  <dd className="mono">{doc.sha256}</dd>
                  <dt>Uploaded</dt>
                  <dd>
                    {dateTime(doc.created_at)} by {doc.uploaded_by}
                  </dd>
                  <dt>Transcription</dt>
                  <dd>
                    {doc.text_version > 0
                      ? `v${doc.text_version} · ${doc.page_count} page(s) · ${doc.ocr_model ?? "—"}`
                      : "not available"}
                  </dd>
                  <dt>Draft extraction</dt>
                  <dd>{doc.extraction_model ?? "—"}</dd>
                  {doc.policy_version_id && (
                    <>
                      <dt>Policy draft</dt>
                      <dd>
                        <Link href={`/policies/${doc.policy_version_id}`}>
                          Open policy version
                        </Link>
                      </dd>
                    </>
                  )}
                </dl>
              </div>
              <div className="card">
                <div className="card-title">
                  <h2>Workflow</h2>
                </div>
                <ol className="small" style={{ paddingLeft: 18, marginTop: 0 }}>
                  <li>Transcribe the scanned pages (Gemini OCR).</li>
                  <li>Extract draft rules (Gemini, untrusted draft).</li>
                  <li>Review every rule and clause against the original.</li>
                  <li>Create a policy draft, then publish it separately.</li>
                </ol>
                {processing && (
                  <div className="notice info" role="status">
                    <Icon name="refresh" width={16} />
                    <div>
                      Processing in the background. This page refreshes
                      automatically.
                    </div>
                  </div>
                )}
                {doc.error && (
                  <div className="notice error" role="alert">
                    <Icon name="alert" width={16} />
                    <div>{doc.error}</div>
                  </div>
                )}
                {canWrite && (
                  <div className="btn-row" style={{ marginTop: 12 }}>
                    <button
                      className="btn ghost"
                      onClick={() => run("transcribe")}
                      disabled={busy !== null || processing}
                    >
                      <Icon name="refresh" width={14} />
                      {busy === "transcribe"
                        ? "Transcribing…"
                        : hasText
                          ? "Re-transcribe"
                          : "Retry transcription"}
                    </button>
                    <button
                      className="btn primary"
                      onClick={() => run("extract")}
                      disabled={busy !== null || !hasText || processing}
                    >
                      <Icon name="sparkle" width={14} />
                      {busy === "extract"
                        ? "Extracting…"
                        : "Extract draft rules"}
                    </button>
                  </div>
                )}
                {actionError && (
                  <div style={{ marginTop: 10 }}>
                    <ErrorNotice error={actionError} />
                    <Problems items={problemList(actionError.details)} />
                  </div>
                )}
              </div>
            </div>

            <div className="grid g-2 mt">
              <div className="card">
                <div className="card-title">
                  <h2>Original</h2>
                </div>
                {doc.mime_type === "application/pdf" ? (
                  <iframe
                    src={fileUrl}
                    title={`Original document ${doc.filename}`}
                    style={{ width: "100%", height: 640, border: 0 }}
                  />
                ) : (
                  <img
                    src={fileUrl}
                    alt={`Scanned page of ${doc.filename}`}
                    style={{ width: "100%", height: "auto" }}
                  />
                )}
              </div>
              <div className="card">
                <div className="card-title">
                  <h2>
                    Transcribed text{" "}
                    <span className="sub">verify against the original</span>
                  </h2>
                </div>
                {hasText && (
                  <form className="toolbar" onSubmit={onSearch} role="search">
                    <div className="field" style={{ flex: 1 }}>
                      <label htmlFor="doc-search">Search this document</label>
                      <input
                        id="doc-search"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="e.g. credit score, LTV, tenure"
                        maxLength={200}
                      />
                    </div>
                    <button className="btn ghost" type="submit">
                      <Icon name="search" width={14} />
                      Search
                    </button>
                  </form>
                )}
                {search && (
                  <div style={{ marginBottom: 12 }}>
                    {search.items.length === 0 ? (
                      <Empty>No passages match “{search.query}”.</Empty>
                    ) : (
                      search.items.map((c) => (
                        <div key={`${c.page}-${c.seq}`} className="clause">
                          <div className="meta">
                            page {c.page}
                            {c.section ? ` · §${c.section}` : ""}
                          </div>
                          {c.text}
                        </div>
                      ))
                    )}
                  </div>
                )}
                {doc.pages.length === 0 ? (
                  <Empty>No transcribed text yet.</Empty>
                ) : (
                  <div style={{ maxHeight: 560, overflowY: "auto" }}>
                    {doc.pages.map((pg) => (
                      <div key={pg.page} className="clause">
                        <div className="meta">page {pg.page}</div>
                        <div style={{ whiteSpace: "pre-wrap" }}>{pg.text}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {doc.extraction && (
              <div className="card mt">
                <div className="card-title">
                  <h2>
                    Review AI-drafted rules{" "}
                    <span className="sub">untrusted until you confirm</span>
                  </h2>
                </div>
                {doc.extraction_problems.length > 0 ? (
                  <div className="notice warn">
                    <Icon name="alert" width={16} />
                    <div>
                      <strong>
                        {doc.extraction_problems.length} issue(s) in the AI
                        draft.
                      </strong>{" "}
                      Missing values are left empty instead of guessed. Fill
                      them in from the document and fix every clause that is not
                      quoted verbatim.
                      <Problems items={doc.extraction_problems} />
                    </div>
                  </div>
                ) : (
                  <div className="notice info">
                    <Icon name="check" width={16} />
                    <div>
                      The draft passed schema checks and every clause was found
                      on its cited page. You still need to confirm each rule
                      value against the original.
                    </div>
                  </div>
                )}
                {canWrite && (
                  <form onSubmit={createDraft}>
                    <div className="field" style={{ marginTop: 12 }}>
                      <label htmlFor="draft-json">Reviewed policy (JSON)</label>
                      <textarea
                        id="draft-json"
                        className="mono"
                        value={draftText}
                        onChange={(e) => {
                          setDraftText(e.target.value);
                          setReviewed(false);
                        }}
                        rows={22}
                        spellCheck={false}
                      />
                      <div className="help">
                        The server re-validates the schema and checks that every
                        clause appears verbatim on its cited page. Provenance is
                        set by the server.
                      </div>
                    </div>
                    <label
                      className="small"
                      style={{ display: "flex", gap: 8, margin: "10px 0" }}
                    >
                      <input
                        type="checkbox"
                        checked={reviewed}
                        onChange={(e) => setReviewed(e.target.checked)}
                      />
                      I compared every rule value and clause with the original
                      document.
                    </label>
                    <button
                      className="btn primary"
                      type="submit"
                      disabled={!reviewed || busy !== null}
                    >
                      {busy === "draft" ? "Creating…" : "Create policy draft"}
                    </button>
                  </form>
                )}
                {created && (
                  <div className="notice success" style={{ marginTop: 12 }}>
                    <Icon name="check" width={16} />
                    <div>
                      Draft {created.policy_code} v{created.version} created. It
                      does not affect decisions until published.{" "}
                      <Link href={`/policies/${created.id}`}>
                        Review and publish
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
