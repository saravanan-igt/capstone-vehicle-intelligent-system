"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Icon } from "@/components/Icon";
import { Empty, ErrorNotice, Loading, PageHeader } from "@/components/ui";
import { useApi } from "@/lib/api";
import { money } from "@/lib/format";
import type { Page, Vehicle } from "@/lib/types";

const TONES = ["pink", "purple", "green", "orange", "indigo", "blue"] as const;

function Catalogue() {
  const params = useSearchParams();
  const [make, setMake] = useState(params.get("make") ?? "");
  const [body, setBody] = useState("");
  const [fuel, setFuel] = useState("");
  const qs = new URLSearchParams({ limit: "50" });
  if (make) qs.set("make", make);
  if (body) qs.set("body_type", body);
  if (fuel) qs.set("fuel_type", fuel);
  const { data, error, loading, reload } = useApi<Page<Vehicle>>(
    `v1/vehicles?${qs}`,
  );

  return (
    <div className="content">
      <div className="notice info" style={{ marginBottom: 16 }}>
        Catalogue is synthetic: makes and models are fictional and prices are
        illustrative. To check affordability, open an approved application.
      </div>
      <div className="card">
        <div className="toolbar">
          <div className="field">
            <label htmlFor="make">Make</label>
            <select
              id="make"
              value={make}
              onChange={(e) => setMake(e.target.value)}
            >
              <option value="">Any</option>
              {["Aurora", "Kestrel", "Lumen", "Orion", "Vanta", "Zephyr"].map(
                (m) => (
                  <option key={m}>{m}</option>
                ),
              )}
            </select>
          </div>
          <div className="field">
            <label htmlFor="body">Body</label>
            <select
              id="body"
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
            <label htmlFor="fuel">Fuel</label>
            <select
              id="fuel"
              value={fuel}
              onChange={(e) => setFuel(e.target.value)}
            >
              <option value="">Any</option>
              {["petrol", "diesel", "cng", "hybrid", "electric"].map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </div>
        </div>
        {error && <ErrorNotice error={error} onRetry={reload} />}
        {loading && <Loading />}
        {data && data.items.length === 0 && (
          <Empty>No vehicles match these filters.</Empty>
        )}
      </div>
      {data && data.items.length > 0 && (
        <div className="grid g-4 mt">
          {data.items.map((v, idx) => {
            const p = v.prices[0];
            return (
              <Link key={v.id} href={`/vehicles/${v.id}`} className="card">
                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                  <span className={`tile ${TONES[idx % TONES.length]}`}>
                    <Icon name="car" />
                  </span>
                  <div>
                    <strong>
                      {v.make} {v.model}
                    </strong>
                    <div className="small muted">{v.variant}</div>
                  </div>
                </div>
                <div className="small muted" style={{ marginTop: 10 }}>
                  {v.body_type} · {v.fuel_type} · {v.seating} seats ·{" "}
                  {v.category}
                </div>
                <div style={{ marginTop: 8, fontWeight: 600 }}>
                  {p ? (
                    <>
                      Ex-showroom {money(p.ex_showroom)}{" "}
                      <span className="small muted">({p.region})</span>
                    </>
                  ) : (
                    "No price on file"
                  )}
                </div>
                {p && !p.on_road_complete && (
                  <span className="badge orange" style={{ marginTop: 6 }}>
                    On-road cost incomplete
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function VehiclesPage() {
  return (
    <>
      <PageHeader title="Vehicles" crumbs="Catalogue | Browse" />
      <Suspense
        fallback={
          <div className="content">
            <Loading />
          </div>
        }
      >
        <Catalogue />
      </Suspense>
    </>
  );
}
