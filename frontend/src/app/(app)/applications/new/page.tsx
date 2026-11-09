"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type FormEvent } from "react";

import { Icon } from "@/components/Icon";
import { ErrorNotice, Loading, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type {
  Application,
  ApplicantInput,
  BodyType,
  Decision,
  FuelType,
} from "@/lib/types";

type FormState = Record<
  | "income_amount"
  | "income_frequency"
  | "credit_score"
  | "score_provider"
  | "employment_category"
  | "employment_months"
  | "existing_monthly_obligations"
  | "active_loans"
  | "requested_principal"
  | "requested_tenure_months"
  | "down_payment_available"
  | "currency"
  | "jurisdiction"
  | "region",
  string
>;

const EMPTY: FormState = {
  income_amount: "",
  income_frequency: "monthly",
  credit_score: "",
  score_provider: "CIBIL",
  employment_category: "salaried",
  employment_months: "",
  existing_monthly_obligations: "0",
  active_loans: "0",
  requested_principal: "",
  requested_tenure_months: "60",
  down_payment_available: "",
  currency: "INR",
  jurisdiction: "IN",
  region: "IN-MH",
};

const BODY: BodyType[] = ["hatchback", "sedan", "suv", "mpv", "coupe"];
const FUEL: FuelType[] = ["petrol", "diesel", "cng", "hybrid", "electric"];
const MONEY = /^\d{1,12}(\.\d{1,2})?$/;
const INT = /^\d{1,4}$/;

function validate(f: FormState): Partial<Record<keyof FormState, string>> {
  const e: Partial<Record<keyof FormState, string>> = {};
  const money = (k: keyof FormState, positive = false) => {
    if (f[k] === "") return;
    if (!MONEY.test(f[k])) e[k] = "Enter an amount with up to 2 decimals";
    else if (positive && Number(f[k]) <= 0) e[k] = "Must be greater than 0";
  };
  money("income_amount");
  money("existing_monthly_obligations");
  money("requested_principal", true);
  money("down_payment_available");
  if (
    f.credit_score !== "" &&
    (!INT.test(f.credit_score) ||
      +f.credit_score < 300 ||
      +f.credit_score > 900)
  ) {
    e.credit_score = "Score must be 300–900";
  }
  if (
    f.employment_months !== "" &&
    (!INT.test(f.employment_months) || +f.employment_months > 720)
  ) {
    e.employment_months = "Months must be 0–720";
  }
  if (
    f.active_loans !== "" &&
    (!INT.test(f.active_loans) || +f.active_loans > 50)
  ) {
    e.active_loans = "Active loans must be 0–50";
  }
  if (
    f.requested_tenure_months !== "" &&
    (!INT.test(f.requested_tenure_months) ||
      +f.requested_tenure_months < 1 ||
      +f.requested_tenure_months > 480)
  ) {
    e.requested_tenure_months = "Tenure must be 1–480 months";
  }
  return e;
}

function toPayload(
  f: FormState,
  body: BodyType[],
  fuel: FuelType[],
): ApplicantInput {
  const s = (v: string) => (v === "" ? null : v);
  const n = (v: string) => (v === "" ? null : Number(v));
  return {
    income_amount: s(f.income_amount),
    income_frequency: s(
      f.income_frequency,
    ) as ApplicantInput["income_frequency"],
    credit_score: n(f.credit_score),
    score_provider: s(f.score_provider),
    employment_category: s(
      f.employment_category,
    ) as ApplicantInput["employment_category"],
    employment_months: n(f.employment_months),
    existing_monthly_obligations: s(f.existing_monthly_obligations),
    active_loans: n(f.active_loans),
    requested_principal: s(f.requested_principal),
    requested_tenure_months: n(f.requested_tenure_months),
    down_payment_available: s(f.down_payment_available),
    currency: s(f.currency),
    jurisdiction: s(f.jurisdiction),
    region: s(f.region),
    preferred_body_types: body,
    preferred_fuel_types: fuel,
  };
}

function fromInput(i: ApplicantInput): FormState {
  const v = (x: string | number | null) => (x === null ? "" : String(x));
  return {
    income_amount: v(i.income_amount),
    income_frequency: v(i.income_frequency),
    credit_score: v(i.credit_score),
    score_provider: v(i.score_provider),
    employment_category: v(i.employment_category),
    employment_months: v(i.employment_months),
    existing_monthly_obligations: v(i.existing_monthly_obligations),
    active_loans: v(i.active_loans ?? null),
    requested_principal: v(i.requested_principal),
    requested_tenure_months: v(i.requested_tenure_months),
    down_payment_available: v(i.down_payment_available),
    currency: v(i.currency),
    jurisdiction: v(i.jurisdiction),
    region: v(i.region),
  };
}

function ApplicationForm() {
  const router = useRouter();
  const params = useSearchParams();
  const resumeId = params.get("id");
  const [form, setForm] = useState<FormState>(EMPTY);
  const [body, setBody] = useState<BodyType[]>([]);
  const [fuel, setFuel] = useState<FuelType[]>([]);
  const [existing, setExisting] = useState<Application | null>(null);
  const [loading, setLoading] = useState(resumeId !== null);
  const [touched, setTouched] = useState(false);
  const [serverErrors, setServerErrors] = useState<
    Partial<Record<string, string>>
  >({});
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<"draft" | "evaluate" | null>(null);
  const idemKey = useRef<string | null>(null);

  useEffect(() => {
    if (!resumeId) return;
    api<Application>(`v1/applications/${encodeURIComponent(resumeId)}`)
      .then((a) => {
        setExisting(a);
        setForm(fromInput(a.input));
        setBody(a.input.preferred_body_types);
        setFuel(a.input.preferred_fuel_types);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e : null))
      .finally(() => setLoading(false));
  }, [resumeId]);

  const errors = { ...validate(form), ...serverErrors };
  const set = (k: keyof FormState) => (e: { target: { value: string } }) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    setServerErrors((s) => ({ ...s, [k]: undefined }));
    idemKey.current = null;
  };

  async function save(): Promise<Application> {
    const payload = toPayload(form, body, fuel);
    if (existing) {
      const updated = await api<Application>(`v1/applications/${existing.id}`, {
        method: "PATCH",
        json: payload,
        headers: { "If-Match": String(existing.row_version) },
      });
      setExisting(updated);
      return updated;
    }
    const created = await api<Application>("v1/applications", {
      method: "POST",
      json: payload,
    });
    setExisting(created);
    return created;
  }

  async function submit(mode: "draft" | "evaluate", e?: FormEvent) {
    e?.preventDefault();
    setTouched(true);
    setError(null);
    if (Object.values(validate(form)).some(Boolean)) return;
    setBusy(mode);
    try {
      const app = await save();
      if (mode === "evaluate") {
        idemKey.current ??= crypto.randomUUID();
        await api<Decision>(`v1/applications/${app.id}/evaluate`, {
          method: "POST",
          headers: { "Idempotency-Key": idemKey.current },
        });
      }
      router.push(`/applications/${app.id}`);
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.code === "VALIDATION_ERROR" &&
        Array.isArray(err.details)
      ) {
        const mapped: Record<string, string> = {};
        for (const d of err.details as {
          loc: (string | number)[];
          msg: string;
        }[]) {
          const field = d.loc[d.loc.length - 1];
          if (typeof field === "string") mapped[field] = d.msg;
        }
        setServerErrors(mapped);
      }
      setError(
        err instanceof ApiError
          ? err
          : new ApiError(0, "NETWORK", "Network error", null, null),
      );
    } finally {
      setBusy(null);
    }
  }

  const field = (
    k: keyof FormState,
    label: string,
    opts: {
      help?: string;
      type?: string;
      inputMode?: "numeric" | "decimal";
    } = {},
  ) => {
    const err = touched ? errors[k] : undefined;
    return (
      <div className="field">
        <label htmlFor={k}>{label}</label>
        <input
          id={k}
          value={form[k]}
          onChange={set(k)}
          inputMode={opts.inputMode ?? "decimal"}
          aria-invalid={err ? true : undefined}
          aria-describedby={`${k}-hint`}
        />
        <div id={`${k}-hint`} className={err ? "err" : "help"}>
          {err ?? opts.help ?? "\u00a0"}
        </div>
      </div>
    );
  };
  const select = (
    k: keyof FormState,
    label: string,
    options: [string, string][],
  ) => (
    <div className="field">
      <label htmlFor={k}>{label}</label>
      <select id={k} value={form[k]} onChange={set(k)}>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
      <div className="help">&nbsp;</div>
    </div>
  );
  const toggle = <T,>(list: T[], setList: (v: T[]) => void, item: T) =>
    setList(
      list.includes(item) ? list.filter((x) => x !== item) : [...list, item],
    );

  if (loading)
    return (
      <div className="content">
        <div className="card">
          <Loading rows={8} />
        </div>
      </div>
    );

  return (
    <div className="content">
      {existing &&
        existing.status !== "DRAFT" &&
        existing.status !== "INCOMPLETE" &&
        existing.status !== "NEEDS_REVIEW" && (
          <div className="notice warn" style={{ marginBottom: 16 }}>
            This application is {existing.status} and can no longer be edited.
          </div>
        )}
      {error && (
        <div style={{ marginBottom: 16 }}>
          <ErrorNotice error={error} />
        </div>
      )}
      <form className="card" onSubmit={(e) => submit("evaluate", e)} noValidate>
        <div className="card-title">
          <h2>
            Applicant information{" "}
            <span className="sub">
              All amounts in INR. Leave unknown fields blank to save a draft.
            </span>
          </h2>
        </div>
        <div className="form-grid">
          <div className="fieldset-title">Income &amp; credit</div>
          {field("income_amount", "Income amount", {
            help: "Gross income before tax",
          })}
          {select("income_frequency", "Income frequency", [
            ["monthly", "Monthly"],
            ["annual", "Annual"],
          ])}
          {field("credit_score", "Credit score", {
            inputMode: "numeric",
            help: "300–900",
          })}
          {select("score_provider", "Score provider", [
            ["CIBIL", "CIBIL"],
            ["EXPERIAN", "Experian"],
            ["EQUIFAX", "Equifax"],
            ["CRIF", "CRIF High Mark"],
          ])}
          {select("employment_category", "Employment category", [
            ["salaried", "Salaried"],
            ["self_employed", "Self-employed"],
            ["retired", "Retired"],
            ["student", "Student"],
            ["unemployed", "Unemployed"],
            ["other", "Other"],
          ])}
          {field("employment_months", "Months in current employment", {
            inputMode: "numeric",
          })}
          {field(
            "existing_monthly_obligations",
            "Existing monthly debt payments",
            { help: "EMIs, card minimums, etc." },
          )}
          {field("active_loans", "Active loans", {
            inputMode: "numeric",
            help: "Loans currently being repaid",
          })}

          <div className="fieldset-title">Loan request</div>
          {field("requested_principal", "Requested loan amount")}
          {field("requested_tenure_months", "Requested tenure (months)", {
            inputMode: "numeric",
          })}
          {field(
            "down_payment_available",
            "Cash available for down payment & fees",
          )}

          <div className="fieldset-title">Location</div>
          {select("currency", "Currency", [["INR", "INR – Indian Rupee"]])}
          {select("jurisdiction", "Country", [["IN", "India"]])}
          {select("region", "Registration state", [
            ["IN-MH", "Maharashtra"],
            ["IN-KA", "Karnataka"],
            ["IN-DL", "Delhi"],
          ])}

          <div className="fieldset-title">Vehicle preferences (optional)</div>
          <div className="field" style={{ gridColumn: "span 2" }}>
            <span className="small muted">Body type</span>
            <div
              className="chips"
              role="group"
              aria-label="Preferred body types"
            >
              {BODY.map((b) => (
                <button
                  type="button"
                  key={b}
                  className="chip"
                  aria-pressed={body.includes(b)}
                  onClick={() => toggle(body, setBody, b)}
                >
                  {b}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <span className="small muted">Fuel</span>
            <div
              className="chips"
              role="group"
              aria-label="Preferred fuel types"
            >
              {FUEL.map((x) => (
                <button
                  type="button"
                  key={x}
                  className="chip"
                  aria-pressed={fuel.includes(x)}
                  onClick={() => toggle(fuel, setFuel, x)}
                >
                  {x}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="btn-row" style={{ marginTop: 20 }}>
          <button
            type="submit"
            className="btn primary"
            disabled={busy !== null}
          >
            <Icon name="check" width={14} />
            {busy === "evaluate" ? "Evaluating…" : "Check eligibility"}
          </button>
          <button
            type="button"
            className="btn ghost"
            disabled={busy !== null}
            onClick={() => submit("draft")}
          >
            {busy === "draft" ? "Saving…" : "Save draft"}
          </button>
          <span className="small muted">
            Information is self-declared and unverified. Results are indicative,
            not a loan sanction.
          </span>
        </div>
      </form>
    </div>
  );
}

export default function NewApplicationPage() {
  return (
    <>
      <PageHeader title="Application" crumbs="Lending | New application" />
      <Suspense
        fallback={
          <div className="content">
            <Loading />
          </div>
        }
      >
        <ApplicationForm />
      </Suspense>
    </>
  );
}
