"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/Icon";
import {
  Cite,
  Empty,
  ErrorNotice,
  Loading,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { VehicleMatches } from "@/components/VehicleMatches";
import { api, ApiError, useApi } from "@/lib/api";
import { dateTime, humanize, money, percent } from "@/lib/format";
import type { Application, Decision, Explanation, Replay } from "@/lib/types";

const CALC_LABELS: [string, string, "money" | "rate" | "plain"][] = [
  ["qualifying_monthly_income", "Qualifying monthly income", "money"],
  ["max_debt_service_ratio", "Max debt-service ratio", "rate"],
  ["max_total_monthly_obligations", "Max total monthly obligations", "money"],
  ["existing_monthly_obligations", "Existing obligations", "money"],
  ["available_emi", "Available EMI", "money"],
  ["annual_rate_nominal", "Nominal annual rate (monthly compounding)", "rate"],
  ["monthly_rate", "Monthly rate", "plain"],
  ["tenure_months", "Tenure (months)", "plain"],
  [
    "principal_by_repayment_capacity",
    "Principal supported by repayment capacity",
    "money",
  ],
  ["product_max_principal", "Product maximum principal", "money"],
  ["borrowing_capacity", "Pre-vehicle borrowing capacity", "money"],
  ["requested_principal", "Requested principal", "money"],
  ["eligible_principal", "Indicative eligible principal", "money"],
  ["emi", "EMI", "money"],
  ["processing_fee", "Processing fee (upfront)", "money"],
  ["total_repayment", "Total of EMIs", "money"],
  [
    "model_approval_probability",
    "Credit-risk model approval probability",
    "plain",
  ],
];

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const app = useApi<Application>(`v1/applications/${id}`);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [decisionState, setDecisionState] = useState<
    "loading" | "none" | "ready" | "error"
  >("loading");
  const [decisionError, setDecisionError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const idem = useRef<string | null>(null);

  async function loadDecision() {
    setDecisionState("loading");
    try {
      setDecision(await api<Decision>(`v1/applications/${id}/decision`));
      setDecisionState("ready");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setDecisionState("none");
      else {
        setDecisionError(e instanceof ApiError ? e : null);
        setDecisionState("error");
      }
    }
  }

  useEffect(() => {
    void loadDecision();
  }, [id]);

  async function evaluate() {
    setBusy(true);
    setDecisionError(null);
    try {
      idem.current ??= crypto.randomUUID();
      setDecision(
        await api<Decision>(`v1/applications/${id}/evaluate`, {
          method: "POST",
          headers: { "Idempotency-Key": idem.current },
        }),
      );
      idem.current = null;
      setDecisionState("ready");
      app.reload();
    } catch (e) {
      setDecisionError(e instanceof ApiError ? e : null);
    } finally {
      setBusy(false);
    }
  }

  if (app.error) {
    return (
      <>
        <PageHeader title="Application" />
        <div className="content">
          <ErrorNotice error={app.error} onRetry={app.reload} />
        </div>
      </>
    );
  }

  const result = decision?.snapshot.result;
  const snap = decision?.snapshot;
  const clauseTitle = (cid: string) =>
    snap?.clauses.find((c) => c.id === cid)?.text;

  return (
    <>
      <PageHeader
        title="Decision"
        crumbs={`Applications | ${id.slice(0, 10)}`}
        action={app.data && <StatusBadge value={app.data.status} />}
      />
      <div className="content">
        {(app.loading || decisionState === "loading") && (
          <div className="card">
            <Loading rows={6} />
          </div>
        )}
        {decisionError && (
          <div style={{ marginBottom: 16 }}>
            <ErrorNotice error={decisionError} onRetry={loadDecision} />
          </div>
        )}

        {decisionState === "none" && app.data && (
          <div className="card">
            <Empty>
              <p>This application has not been evaluated yet.</p>
              <div className="btn-row" style={{ justifyContent: "center" }}>
                <Link className="btn ghost" href={`/applications/new?id=${id}`}>
                  Edit details
                </Link>
                <button
                  className="btn primary"
                  onClick={evaluate}
                  disabled={busy}
                >
                  {busy ? "Evaluating…" : "Check eligibility"}
                </button>
              </div>
            </Empty>
          </div>
        )}

        {decision && result && snap && (
          <>
            <div className="grid g-2-1">
              <div className="card">
                <div className="card-title">
                  <h2>
                    Result{" "}
                    <span className="sub">
                      evaluated {dateTime(decision.evaluated_at)}
                    </span>
                  </h2>
                  <StatusBadge value={decision.outcome ?? decision.status} />
                </div>

                {result.status === "INCOMPLETE" && (
                  <div className="notice warn" role="status">
                    <Icon name="alert" width={16} />
                    <div>
                      <strong>
                        More information is needed — no lending decision was
                        made.
                      </strong>
                      <div>
                        Missing:{" "}
                        {result.missing_fields.map(humanize).join(", ")}
                      </div>
                      <div className="btn-row" style={{ marginTop: 8 }}>
                        <Link
                          className="btn ghost"
                          href={`/applications/new?id=${id}`}
                        >
                          Complete application
                        </Link>
                      </div>
                    </div>
                  </div>
                )}
                {result.status === "NEEDS_REVIEW" && (
                  <div className="notice info" role="status">
                    <Icon name="alert" width={16} />
                    <div>
                      <strong>
                        Referred for manual review — this is not a rejection.
                      </strong>
                      <div>{result.reason_codes.map(humanize).join("; ")}</div>
                    </div>
                  </div>
                )}
                {result.outcome === "APPROVED" && (
                  <>
                    <div className="muted small">
                      Indicative eligible loan amount
                    </div>
                    <div className="hero-amount">
                      {money(result.eligible_principal)}
                    </div>
                    <dl className="dl" style={{ marginTop: 12 }}>
                      <dt>EMI</dt>
                      <dd>{money(result.emi)} / month</dd>
                      <dt>Tenure</dt>
                      <dd>{result.tenure_months} months</dd>
                      <dt>Interest rate</dt>
                      <dd>{percent(result.annual_rate)} p.a. nominal, fixed</dd>
                      <dt>Processing fee</dt>
                      <dd>{money(result.processing_fee)} (paid upfront)</dd>
                      <dt>Borrowing capacity</dt>
                      <dd>{money(result.borrowing_capacity)}</dd>
                    </dl>
                    {result.flags.map((f) => (
                      <div
                        key={f}
                        className="notice info"
                        style={{ marginTop: 10 }}
                      >
                        {humanize(f)} — the amount is lower than requested.
                      </div>
                    ))}
                    <p className="small muted">
                      Indicative simulation under a synthetic policy; not a
                      binding loan sanction. Inputs are self-declared and
                      unverified.
                    </p>
                  </>
                )}
                {result.outcome === "REJECTED" && (
                  <div className="notice error">
                    <Icon name="x" width={16} />
                    <div>
                      <strong>
                        Not eligible under the lender&apos;s published policy.
                      </strong>
                      <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                        {result.rule_results
                          .filter((r) => !r.passed)
                          .map((r) => (
                            <li key={r.rule_id}>
                              {humanize(r.reason_code ?? r.rule_id)}: observed{" "}
                              {r.observed}, required {r.threshold}
                              <Cite
                                id={r.clause_id}
                                title={clauseTitle(r.clause_id)}
                              />
                            </li>
                          ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>

              <div className="card">
                <div className="card-title">
                  <h2>Provenance</h2>
                </div>
                <dl className="dl small">
                  <dt>Policy</dt>
                  <dd>
                    {snap.policy.policy_code
                      ? `${snap.policy.policy_code} v${snap.policy.version}`
                      : "None applicable"}
                  </dd>
                  <dt>Lender</dt>
                  <dd>{snap.policy.lender_name ?? "—"}</dd>
                  <dt>Policy hash</dt>
                  <dd className="mono">
                    {snap.policy.content_sha256?.slice(0, 16) ?? "—"}
                  </dd>
                  <dt>Engine</dt>
                  <dd>v{decision.engine_version}</dd>
                  <dt>Result hash</dt>
                  <dd className="mono">
                    {decision.result_sha256.slice(0, 16)}
                  </dd>
                  <dt>Inputs</dt>
                  <dd>
                    {snap.input_provenance.verified
                      ? "Verified"
                      : "Self-declared, unverified"}
                  </dd>
                </dl>
                <ReplayBox decisionId={decision.id} />
                <div className="btn-row" style={{ marginTop: 12 }}>
                  <button
                    className="btn ghost"
                    onClick={evaluate}
                    disabled={busy}
                  >
                    <Icon name="refresh" width={14} />
                    Re-evaluate
                  </button>
                </div>
              </div>
            </div>

            <ExplanationBox decisionId={decision.id} />

            {result.rule_results.length > 0 && (
              <div className="grid g-2 mt">
                <div className="card">
                  <div className="card-title">
                    <h2>Rule trace</h2>
                    <span className="sub">every rule evaluated</span>
                  </div>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Rule</th>
                        <th>Observed</th>
                        <th>Requirement</th>
                        <th>Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.rule_results.map((r) => (
                        <tr key={r.rule_id}>
                          <td>
                            {humanize(r.rule_id)}
                            <Cite
                              id={r.clause_id}
                              title={clauseTitle(r.clause_id)}
                            />
                          </td>
                          <td>{r.observed}</td>
                          <td className="small">{r.threshold}</td>
                          <td>
                            {r.passed ? (
                              <span className="badge green">PASS</span>
                            ) : (
                              <span className="badge red">FAIL</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="card">
                  <div className="card-title">
                    <h2>Calculation breakdown</h2>
                  </div>
                  <dl className="dl">
                    {CALC_LABELS.filter(
                      ([k]) => result.calculations[k] != null,
                    ).map(([k, label, kind]) => (
                      <div key={k} style={{ display: "contents" }}>
                        <dt>{label}</dt>
                        <dd>
                          {kind === "money"
                            ? money(result.calculations[k])
                            : kind === "rate"
                              ? percent(result.calculations[k])
                              : result.calculations[k]}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  <p className="small muted" style={{ marginTop: 12 }}>
                    EMI = P·r·(1+r)<sup>n</sup> / ((1+r)<sup>n</sup> − 1), r =
                    annual ÷ 12. Capacity solves this for P using Available EMI
                    = income × ratio − obligations. Principal is rounded down
                    per policy.
                  </p>
                </div>
              </div>
            )}

            {snap.clauses.length > 0 && (
              <div className="card mt">
                <div className="card-title">
                  <h2>Policy sources</h2>
                  <span className="sub">{snap.policy.source_document}</span>
                </div>
                {snap.clauses.map((c) => (
                  <div key={c.id} className="clause">
                    <div className="meta">
                      {c.id} · §{c.section} · page {c.page} · {c.title}
                    </div>
                    {c.text}
                  </div>
                ))}
              </div>
            )}

            {result.outcome === "APPROVED" && (
              <VehicleMatches decisionId={decision.id} />
            )}
          </>
        )}
      </div>
    </>
  );
}

function ReplayBox({ decisionId }: { decisionId: string }) {
  const [replay, setReplay] = useState<Replay | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  return (
    <div style={{ marginTop: 12 }}>
      <button
        className="btn green"
        onClick={async () => {
          setError(null);
          try {
            setReplay(
              await api<Replay>(`v1/decisions/${decisionId}/replay`, {
                method: "POST",
              }),
            );
          } catch (e) {
            setError(e instanceof ApiError ? e : null);
          }
        }}
      >
        <Icon name="check" width={14} />
        Verify by replay
      </button>
      {replay && (
        <div
          className={`notice ${replay.reproducible ? "success" : "warn"}`}
          style={{ marginTop: 8 }}
        >
          {replay.reproducible === null
            ? replay.reason
            : replay.reproducible
              ? "Reproduced exactly with the recorded policy and engine version."
              : "Replay differs — investigate policy or engine changes."}
        </div>
      )}
      {error && <ErrorNotice error={error} />}
    </div>
  );
}

function ExplanationBox({ decisionId }: { decisionId: string }) {
  const [exp, setExp] = useState<Explanation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function load(refresh: boolean) {
    setBusy(true);
    setError(null);
    try {
      setExp(
        await api<Explanation>(
          `v1/decisions/${decisionId}/explanation${refresh ? "?refresh=true" : ""}`,
          { method: "POST" },
        ),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e : null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card mt">
      <div className="card-title">
        <h2>Explanation</h2>
        <div className="btn-row">
          {exp && (
            <span
              className={`badge ${exp.source === "ai" ? "purple" : "grey"}`}
            >
              {exp.source === "ai"
                ? `AI · validated · ${exp.model}`
                : "Deterministic template"}
            </span>
          )}
          <button
            className="btn primary"
            onClick={() => load(exp !== null)}
            disabled={busy}
          >
            <Icon name="sparkle" width={14} />
            {busy
              ? "Generating…"
              : exp
                ? "Regenerate"
                : "Explain this decision"}
          </button>
        </div>
      </div>
      {error && <ErrorNotice error={error} onRetry={() => load(false)} />}
      {!exp && !error && (
        <p className="muted small">
          Explanations are generated from the recorded decision and its cited
          clauses. They cannot change the outcome or amounts.
        </p>
      )}
      {exp && (
        <>
          <p style={{ marginTop: 0 }}>{exp.content.summary}</p>
          <ul style={{ paddingLeft: 18 }}>
            {exp.content.points.map((p, i) => (
              <li key={i}>
                {p.text}
                {p.citations.map((c) => (
                  <Cite key={c} id={c} />
                ))}
              </li>
            ))}
          </ul>
          {exp.fallback_reason && (
            <div className="notice warn small">
              AI explanation unavailable or rejected: {exp.fallback_reason}.
              Showing the deterministic explanation.
            </div>
          )}
        </>
      )}
    </div>
  );
}
