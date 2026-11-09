"use client";

import Link from "next/link";
import { useState } from "react";

import {
  Cite,
  Empty,
  ErrorNotice,
  Loading,
  StatusBadge,
} from "@/components/ui";
import { useApi } from "@/lib/api";
import { humanize, money } from "@/lib/format";
import type {
  AffordableVehicles,
  AssessmentStatus,
  VehicleAssessmentItem,
} from "@/lib/types";

const COMPARE_ROWS: [string, string][] = [
  ["on_road_price", "On-road price"],
  ["ltv_loan_limit", "LTV loan limit"],
  ["loan_principal", "Loan principal"],
  ["required_contribution", "Your contribution"],
  ["processing_fee", "Processing fee"],
  ["upfront_cash_required", "Upfront cash needed"],
  ["emi", "EMI"],
  ["shortfall", "Shortfall"],
];

export function VehicleMatches({ decisionId }: { decisionId: string }) {
  const [status, setStatus] = useState<AssessmentStatus | "">("AFFORDABLE");
  const [body, setBody] = useState("");
  const [fuel, setFuel] = useState("");
  const [compare, setCompare] = useState<string[]>([]);
  const qs = new URLSearchParams();
  if (status) qs.set("status", status);
  if (body) qs.set("body_type", body);
  if (fuel) qs.set("fuel_type", fuel);
  const { data, error, loading, reload } = useApi<AffordableVehicles>(
    `v1/decisions/${decisionId}/vehicles?${qs}`,
  );
  const all = useApi<AffordableVehicles>(`v1/decisions/${decisionId}/vehicles`);
  const compared = (all.data?.items ?? []).filter((i) =>
    compare.includes(i.vehicle.id),
  );

  return (
    <div className="card mt">
      <div className="card-title">
        <h2>
          Vehicles you can afford{" "}
          <span className="sub">
            {data ? `region ${data.region} · prices as of ${data.as_of}` : ""}
          </span>
        </h2>
        {all.data && (
          <div className="btn-row">
            {(
              [
                "AFFORDABLE",
                "NOT_AFFORDABLE",
                "UNVERIFIED",
                "NOT_ELIGIBLE",
              ] as const
            ).map((s) => (
              <span key={s} className="small">
                <StatusBadge value={s} /> {all.data?.counts[s] ?? 0}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="toolbar">
        <div className="field">
          <label htmlFor="vf-status">Status</label>
          <select
            id="vf-status"
            value={status}
            onChange={(e) => setStatus(e.target.value as AssessmentStatus | "")}
          >
            <option value="">All</option>
            <option value="AFFORDABLE">Affordable</option>
            <option value="NOT_AFFORDABLE">Not affordable</option>
            <option value="UNVERIFIED">Unverified</option>
            <option value="NOT_ELIGIBLE">Not eligible</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="vf-body">Body</label>
          <select
            id="vf-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          >
            <option value="">Any</option>
            {["hatchback", "sedan", "suv", "mpv", "coupe", "van"].map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="vf-fuel">Fuel</label>
          <select
            id="vf-fuel"
            value={fuel}
            onChange={(e) => setFuel(e.target.value)}
          >
            <option value="">Any</option>
            {["petrol", "diesel", "cng", "hybrid", "electric"].map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
        </div>
        {data && (
          <p className="small muted" style={{ flex: 1, margin: 0 }}>
            {data.basis}
          </p>
        )}
      </div>
      {error && <ErrorNotice error={error} onRetry={reload} />}
      {loading && <Loading />}
      {data && data.items.length === 0 && (
        <Empty>
          No vehicles match.{" "}
          {status === "AFFORDABLE" &&
            "Try a larger down payment, a longer tenure, or view all statuses."}
        </Empty>
      )}
      {data && data.items.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Compare</th>
              <th>Vehicle</th>
              <th>Status</th>
              <th className="num">On-road</th>
              <th className="num">Loan</th>
              <th className="num">Upfront cash</th>
              <th className="num">EMI</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((i: VehicleAssessmentItem) => {
              const v = i.assessment.values;
              return (
                <tr key={i.vehicle.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Compare ${i.vehicle.make} ${i.vehicle.model}`}
                      checked={compare.includes(i.vehicle.id)}
                      disabled={
                        !compare.includes(i.vehicle.id) && compare.length >= 3
                      }
                      onChange={() =>
                        setCompare((c) =>
                          c.includes(i.vehicle.id)
                            ? c.filter((x) => x !== i.vehicle.id)
                            : [...c, i.vehicle.id],
                        )
                      }
                    />
                  </td>
                  <td>
                    <Link href={`/vehicles/${i.vehicle.id}`}>
                      <strong>
                        {i.vehicle.make} {i.vehicle.model}
                      </strong>{" "}
                      {i.vehicle.variant}
                    </Link>
                    <div className="small muted">
                      {i.vehicle.body_type} · {i.vehicle.fuel_type} ·{" "}
                      {i.vehicle.transmission}
                    </div>
                  </td>
                  <td>
                    <StatusBadge value={i.assessment.status} />
                  </td>
                  <td className="num">
                    {v.on_road_price ? (
                      money(v.on_road_price)
                    ) : (
                      <span className="muted">Not available</span>
                    )}
                  </td>
                  <td className="num">{money(v.loan_principal)}</td>
                  <td className="num">{money(v.upfront_cash_required)}</td>
                  <td className="num">{money(v.emi)}</td>
                  <td className="small">
                    {i.assessment.reasons.map(humanize).join("; ")}
                    {v.shortfall && ` (short by ${money(v.shortfall)})`}
                    {i.assessment.citations.map((c) => (
                      <Cite key={c} id={c} />
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {compared.length > 0 && (
        <div className="mt">
          <h3 style={{ fontSize: 13, marginBottom: 8 }}>Comparison</h3>
          <table className="table">
            <thead>
              <tr>
                <th />
                {compared.map((c) => (
                  <th key={c.vehicle.id}>
                    {c.vehicle.make} {c.vehicle.model} {c.vehicle.variant}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Status</td>
                {compared.map((c) => (
                  <td key={c.vehicle.id}>
                    <StatusBadge value={c.assessment.status} />
                  </td>
                ))}
              </tr>
              {COMPARE_ROWS.map(([k, label]) => (
                <tr key={k}>
                  <td>{label}</td>
                  {compared.map((c) => (
                    <td key={c.vehicle.id} className="num">
                      {c.assessment.values[k]
                        ? money(c.assessment.values[k])
                        : "—"}
                    </td>
                  ))}
                </tr>
              ))}
              <tr>
                <td>Price date</td>
                {compared.map((c) => (
                  <td key={c.vehicle.id}>
                    {c.assessment.values.price_date ?? "—"}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
