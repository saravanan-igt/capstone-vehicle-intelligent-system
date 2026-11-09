"use client";

import { useParams } from "next/navigation";

import { ErrorNotice, Loading, PageHeader } from "@/components/ui";
import { useApi } from "@/lib/api";
import { humanize, money } from "@/lib/format";
import type { Vehicle } from "@/lib/types";

export default function VehicleDetailPage() {
  const { id } = useParams<{ id: string }>();
  const {
    data: v,
    error,
    loading,
    reload,
  } = useApi<Vehicle>(`v1/vehicles/${id}`);

  return (
    <>
      <PageHeader
        title="Vehicle"
        crumbs={`Catalogue | ${v ? `${v.make} ${v.model}` : id}`}
      />
      <div className="content">
        {error && <ErrorNotice error={error} onRetry={reload} />}
        {loading && (
          <div className="card">
            <Loading rows={6} />
          </div>
        )}
        {v && (
          <>
            <div className="grid g-2">
              <div className="card">
                <div className="card-title">
                  <h2>
                    {v.make} {v.model} <span className="sub">{v.variant}</span>
                  </h2>
                  <span className="badge purple">SYNTHETIC</span>
                </div>
                <dl className="dl">
                  <dt>Body</dt>
                  <dd>{v.body_type}</dd>
                  <dt>Fuel</dt>
                  <dd>{v.fuel_type}</dd>
                  <dt>Transmission</dt>
                  <dd>{v.transmission}</dd>
                  <dt>Seating</dt>
                  <dd>{v.seating}</dd>
                  <dt>Category</dt>
                  <dd>{v.category}</dd>
                  {Object.entries(v.specs).map(([k, val]) => (
                    <div key={k} style={{ display: "contents" }}>
                      <dt>{humanize(k)}</dt>
                      <dd>{String(val)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
              <div className="card">
                <div className="card-title">
                  <h2>Provenance</h2>
                </div>
                <dl className="dl small">
                  <dt>Source</dt>
                  <dd>{v.source}</dd>
                  <dt>Reference</dt>
                  <dd className="mono">{v.source_ref}</dd>
                </dl>
                <p className="small muted">
                  Only facts present in the catalogue are shown. Missing cost
                  components are displayed as “not available”, never as zero.
                </p>
              </div>
            </div>
            <div className="card mt">
              <div className="card-title">
                <h2>Regional prices</h2>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Region</th>
                    <th>Price date</th>
                    <th className="num">Ex-showroom</th>
                    <th className="num">Registration</th>
                    <th className="num">Insurance</th>
                    <th className="num">Other</th>
                    <th className="num">On-road</th>
                  </tr>
                </thead>
                <tbody>
                  {v.prices.map((p) => (
                    <tr key={`${p.region}-${p.price_date}`}>
                      <td>{p.region}</td>
                      <td>{p.price_date}</td>
                      <td className="num">{money(p.ex_showroom)}</td>
                      <td className="num">
                        {p.registration ? (
                          money(p.registration)
                        ) : (
                          <span className="badge orange">Not available</span>
                        )}
                      </td>
                      <td className="num">
                        {p.insurance ? (
                          money(p.insurance)
                        ) : (
                          <span className="badge orange">Not available</span>
                        )}
                      </td>
                      <td className="num">
                        {p.other_charges ? (
                          money(p.other_charges)
                        ) : (
                          <span className="badge orange">Not available</span>
                        )}
                      </td>
                      <td className="num">
                        {p.on_road ? (
                          money(p.on_road)
                        ) : (
                          <span className="muted">Incomplete</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </>
  );
}
