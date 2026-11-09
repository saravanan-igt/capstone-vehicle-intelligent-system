"use client";

import Link from "next/link";

import { AreaWave, Sparkline } from "@/components/Charts";
import { Icon, type IconName } from "@/components/Icon";
import { useMe } from "@/components/Shell";
import {
  Empty,
  ErrorNotice,
  Loading,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { useApi } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { Application, Dashboard, Page } from "@/lib/types";

function MiniCard({
  icon,
  tone,
  label,
  hint,
}: {
  icon: IconName;
  tone: string;
  label: string;
  hint: string;
}) {
  return (
    <div className="card mini">
      <span className={`tile ${tone}`}>
        <Icon name={icon} />
      </span>
      <div className="label">{label}</div>
      <div className="hint">{hint}</div>
      <Icon name={icon} className="ghost" />
    </div>
  );
}

export default function DashboardPage() {
  const me = useMe();
  const dash = useApi<Dashboard>("v1/dashboard");
  const recent = useApi<Page<Application>>("v1/applications?limit=6");
  const d = dash.data;
  const canCreate = me?.permissions.includes("application:create");

  return (
    <>
      <PageHeader
        title="Stats"
        crumbs="Lending overview | Dashboard"
        action={
          canCreate ? (
            <Link className="pill-btn" href="/applications/new">
              Add New
            </Link>
          ) : undefined
        }
      />
      <div className="content">
        {dash.error && <ErrorNotice error={dash.error} onRetry={dash.reload} />}
        {dash.loading && !d && (
          <div className="card">
            <Loading rows={5} />
          </div>
        )}
        {d && (
          <>
            <div className="grid g-6">
              <MiniCard
                icon="puzzle"
                tone="pink"
                label="Applications"
                hint={`${d.applications_total} in scope`}
              />
              <MiniCard
                icon="doc"
                tone="purple"
                label="Approved"
                hint={`${d.approved} decisions`}
              />
              <MiniCard
                icon="puzzle"
                tone="green"
                label="Rejected"
                hint={`${d.rejected} decisions`}
              />
              <MiniCard
                icon="cap"
                tone="orange"
                label="Incomplete"
                hint={`${d.incomplete} awaiting data`}
              />
              <MiniCard
                icon="chat"
                tone="purple"
                label="Needs review"
                hint={`${d.needs_review} for officers`}
              />
              <MiniCard
                icon="dice"
                tone="indigo"
                label="Catalogue"
                hint={`${d.vehicles_in_catalogue} vehicles · ${d.published_policies} policies`}
              />
            </div>

            <div className="grid g-4 mt">
              {(
                [
                  [
                    "Applications (7d)",
                    d.series.applications,
                    "#4b42d6",
                    "puzzle",
                    "indigo",
                  ],
                  [
                    "Decisions (7d)",
                    d.series.decisions,
                    "#a46cf0",
                    "doc",
                    "purple",
                  ],
                  [
                    "Approvals (7d)",
                    d.series.approved,
                    "#36c98b",
                    "puzzle",
                    "green",
                  ],
                  [
                    "Rejections (7d)",
                    d.series.rejected,
                    "#ff9a3c",
                    "car",
                    "orange",
                  ],
                ] as const
              ).map(([label, series, color, icon, tone]) => (
                <div key={label} className="card spark-card">
                  <div className="head">
                    <div>
                      <div className="big">
                        {series.reduce((a, b) => a + b, 0)}
                      </div>
                      <div className="hint">{label}</div>
                    </div>
                    <span className={`tile ${tone}`}>
                      <Icon name={icon} />
                    </span>
                  </div>
                  <Sparkline
                    values={[...series]}
                    color={color}
                    label={`${label} trend`}
                  />
                </div>
              ))}
            </div>

            <div className="grid g-4 mt">
              <div className="card kpi edge-blue">
                <Icon name="coin" className="kpi-icon" />
                <div>
                  <div className="value">{d.applications_total}</div>
                  <div className="caption">Total applications</div>
                </div>
              </div>
              <div className="card kpi edge-yellow">
                <Icon name="bag" className="kpi-icon" />
                <div>
                  <div className="value">
                    {money(d.total_eligible_principal)}
                  </div>
                  <div className="caption">Eligible amount (approved)</div>
                </div>
              </div>
              <div className="card kpi edge-green">
                <Icon name="wallet" className="kpi-icon" />
                <div>
                  <div className="value">
                    {money(d.average_eligible_principal)}
                  </div>
                  <div className="caption">Average eligible amount</div>
                </div>
              </div>
              <div className="card kpi edge-orange">
                <Icon name="tag" className="kpi-icon" />
                <div>
                  <div className="value">
                    {(d.approval_rate * 100).toFixed(1)}%
                  </div>
                  <div className="caption">Approval rate</div>
                </div>
              </div>
            </div>

            <div className="grid g-4 mt">
              {(
                [
                  [
                    "Approved",
                    d.approved,
                    d.series.approved,
                    "#f6607f",
                    "pink",
                    "puzzle",
                  ],
                  [
                    "Rejected",
                    d.rejected,
                    d.series.rejected,
                    "#f7b924",
                    "orange",
                    "doc",
                  ],
                  [
                    "Incomplete",
                    d.incomplete,
                    d.series.incomplete,
                    "#36c98b",
                    "green",
                    "cap",
                  ],
                  [
                    "Needs review",
                    d.needs_review,
                    d.series.needs_review,
                    "#8b7cf6",
                    "purple",
                    "puzzle",
                  ],
                ] as const
              ).map(([label, value, series, color, tone, icon]) => (
                <div key={label} className="card wave-card">
                  <div className="delta" style={{ color }}>
                    <Icon name="sparkle" width={14} />
                    last 7 days
                  </div>
                  <AreaWave
                    values={[...series]}
                    color={color}
                    label={`${label} over 7 days`}
                  />
                  <div className="foot">
                    <span className={`tile soft ${tone}`}>
                      <Icon name={icon} />
                    </span>
                    <div>
                      <div className="caption">Total {label}</div>
                      <div className="value">{value}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="grid g-2-1 mt">
          <div className="card">
            <div className="card-title">
              <h2>Recent applications</h2>
              <Link className="pill-btn" href="/applications">
                View all
              </Link>
            </div>
            {recent.error && (
              <ErrorNotice error={recent.error} onRetry={recent.reload} />
            )}
            {recent.loading && <Loading />}
            {recent.data && recent.data.items.length === 0 && (
              <Empty>
                No applications yet.{" "}
                {canCreate && (
                  <Link href="/applications/new" className="cite">
                    Start one
                  </Link>
                )}
              </Empty>
            )}
            {recent.data && recent.data.items.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Created</th>
                    <th>Workflow</th>
                    <th>Outcome</th>
                    <th className="num">Eligible amount</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.data.items.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <Link href={`/applications/${a.id}`}>
                          {dateTime(a.created_at)}
                        </Link>
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
                        {money(a.latest_decision?.eligible_principal)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="card">
            <div className="card-title">
              <h2>How decisions are made</h2>
            </div>
            <ol
              className="small"
              style={{ paddingLeft: 18, margin: 0, display: "grid", gap: 8 }}
            >
              <li>
                Your inputs are validated; missing data yields{" "}
                <StatusBadge value="INCOMPLETE" />, never a rejection.
              </li>
              <li>
                The deterministic engine evaluates every rule of the
                lender&apos;s <strong>published</strong> policy.
              </li>
              <li>
                Amounts use Decimal arithmetic and the policy&apos;s rounding
                rules.
              </li>
              <li>
                Each reason cites the exact policy clause; the snapshot can be
                replayed.
              </li>
              <li>
                AI only explains the recorded result and is checked against it.
              </li>
            </ol>
          </div>
        </div>
      </div>
    </>
  );
}
