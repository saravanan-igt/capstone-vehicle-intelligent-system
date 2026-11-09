"use client";

import type { ReactNode } from "react";

import { Icon } from "@/components/Icon";
import type { ApiError } from "@/lib/api";

export function PageHeader({
  title,
  crumbs,
  action,
}: {
  title: string;
  crumbs?: string;
  action?: ReactNode;
}) {
  const today = new Date().toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
  return (
    <div className="subheader">
      <h1>{title}</h1>
      {crumbs && <span className="crumbs">{crumbs}</span>}
      {action}
      <div className="right">
        <span className="date-chip" suppressHydrationWarning>
          Today: {today}
        </span>
      </div>
    </div>
  );
}

const TONE: Record<string, string> = {
  APPROVED: "green",
  AFFORDABLE: "green",
  PUBLISHED: "green",
  COMPLETED: "blue",
  REJECTED: "red",
  NOT_AFFORDABLE: "red",
  FAILED: "red",
  INCOMPLETE: "orange",
  UNVERIFIED: "orange",
  DRAFT: "grey",
  NEEDS_REVIEW: "purple",
  NOT_ELIGIBLE: "grey",
  PROCESSING: "blue",
  RETIRED: "grey",
  UPLOADED: "grey",
  TEXT_EXTRACTED: "blue",
  DRAFT_EXTRACTED: "purple",
  DRAFT_CREATED: "green",
  TEXT_FAILED: "red",
  EXTRACTION_FAILED: "red",
};

export function StatusBadge({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="badge grey">—</span>;
  return (
    <span className={`badge ${TONE[value] ?? "grey"}`}>
      {value.replace(/_/g, " ")}
    </span>
  );
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="skeleton"
          style={{ width: `${90 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

export function ErrorNotice({
  error,
  onRetry,
}: {
  error: ApiError;
  onRetry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <Icon name="alert" width={16} />
      <div style={{ flex: 1 }}>
        <strong>{error.message}</strong>
        <div className="small">
          {error.code}
          {error.correlationId ? ` · ref ${error.correlationId}` : ""}
        </div>
      </div>
      {onRetry && (
        <button className="btn ghost" onClick={onRetry}>
          <Icon name="refresh" width={14} />
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Cite({ id, title }: { id: string; title?: string }) {
  return (
    <span className="cite" title={title}>
      {id}
    </span>
  );
}
