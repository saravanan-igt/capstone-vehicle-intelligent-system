"""Use cases behind the brief's endpoints: predict, loan amount, vehicle recommendations with no-fit guidance,
vehicle details and grounded vehicle Q&A. Composes the services; adds no new decision logic."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application import services as svc
from app.application.errors import AppError, not_found, unprocessable
from app.application.security import Principal
from app.config import assets_dir
from app.domain import affordability, eligibility
from app.domain.applicant import ApplicantInput
from app.domain.explanation import REASON_TEXT
from app.domain.money import floor_to, fmt, monthly_rate_from_nominal_annual, principal_for_emi
from app.domain.policy import PolicyDocument
from app.infrastructure.models import Decision, Tenant, Vehicle
from app.infrastructure.quota import Quota
from app.ml.model import RiskModel
from app.rag.knowledge import KnowledgeBase
from app.rag.qa import VehicleAnswerer, answer_question

FINAL_LABEL = {"APPROVED": "Approved", "REJECTED": "Rejected", "INCOMPLETE": "Incomplete",
               "NEEDS_REVIEW": "Needs review"}


# ---------- predict & loan amount ----------

def _clauses(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in snap.get("clauses", [])}


def predict_view(d: Decision) -> dict[str, Any]:
    snap = json.loads(d.snapshot_json)
    result, clauses = snap["result"], _clauses(snap)
    failed = {rr["reason_code"]: rr for rr in result["rule_results"] if not rr["passed"]}
    reasons = []
    for code in result["reason_codes"]:
        rr = failed.get(code)
        clause_id = rr["clause_id"] if rr else next((c for c in result["citations"] if c in clauses), None)
        clause = clauses.get(clause_id or "")
        reasons.append({"code": code, "text": REASON_TEXT.get(code, code),
                        "observed": rr["observed"] if rr else None, "required": rr["threshold"] if rr else None,
                        "clause_id": clause_id, "clause_text": clause["text"] if clause else None,
                        "policy_supported": clause is not None})
    model = snap.get("model")
    model_view = None if model is None else {
        "prediction": model["prediction"], "approval_probability": model["approval_probability"],
        "confidence": round(max(model["approval_probability"], 1 - model["approval_probability"]), 4),
        "model_threshold": model["model_threshold"], "policy_threshold": model.get("policy_threshold"),
        "applied_by_policy": model["applied"], "name": model.get("name"), "version": model["model_version"],
        "algorithm": model["algorithm"], "top_factors": model["top_factors"]}
    status = result["outcome"] or result["status"]
    return {"decision_id": d.id, "application_id": d.application_id, "prediction": FINAL_LABEL.get(status, status),
            "status": result["status"], "outcome": result["outcome"], "model": model_view, "reasons": reasons,
            "missing_fields": result["missing_fields"], "flags": result["flags"],
            "policy": {k: snap["policy"].get(k) for k in ("policy_code", "version", "lender_name")} or None,
            "engine_version": d.engine_version, "evaluated_at": snap["evaluated_at"]}


def predict(session: Session, p: Principal, applicant: ApplicantInput, as_of: date, cid: str | None,
            model: RiskModel | None) -> Decision:
    app = svc.create_application(session, p, applicant, cid)
    decision, _ = svc.evaluate_application(session, p, app.id, None, as_of, cid, model)
    return decision


def loan_amount_view(d: Decision) -> dict[str, Any]:
    snap = json.loads(d.snapshot_json)
    result, clauses = snap["result"], _clauses(snap)
    c = result["calculations"]
    approved = result["outcome"] == eligibility.APPROVED
    steps = []
    if "available_emi" in c:
        steps.append({"step": "Maximum total monthly obligations",
                      "formula": f"{c['qualifying_monthly_income']} x {c['max_debt_service_ratio']}",
                      "value": c["max_total_monthly_obligations"]})
        steps.append({"step": "EMI available for the new loan",
                      "formula": f"{c['max_total_monthly_obligations']} - {c['existing_monthly_obligations']}",
                      "value": c["available_emi"]})
    if "principal_by_repayment_capacity" in c:
        steps.append({"step": "Principal that EMI repays",
                      "formula": f"PV of {c['available_emi']} at {c['annual_rate_nominal']} / 12 over "
                                 f"{c['tenure_months']} months, rounded down", "value": c["principal_by_repayment_capacity"]})
        steps.append({"step": "Borrowing capacity", "formula": f"min(that, product max {c['product_max_principal']})",
                      "value": c["borrowing_capacity"]})
    if approved:
        steps.append({"step": "Eligible principal", "formula": f"min(requested {c['requested_principal']}, capacity)",
                      "value": c["eligible_principal"]})
        steps.append({"step": "EMI", "formula": "P x r x (1+r)^n / ((1+r)^n - 1)", "value": c["emi"]})
    return {"decision_id": d.id, "eligible": approved, "status": result["status"], "outcome": result["outcome"],
            "currency": snap["input"].get("currency"),
            "eligible_principal": result["eligible_principal"] if approved else "0.00",
            "requested_principal": snap["input"].get("requested_principal"),
            "borrowing_capacity": result["borrowing_capacity"], "annual_rate": result["annual_rate"],
            "tenure_months": result["tenure_months"], "emi": result["emi"], "processing_fee": result["processing_fee"],
            "total_repayment": c.get("total_repayment"), "flags": result["flags"], "calculation": steps,
            "reasons": [REASON_TEXT.get(code, code) for code in result["reason_codes"]],
            "citations": [{"id": cid, "title": clauses[cid].get("title"), "page": clauses[cid]["page"],
                           "text": clauses[cid]["text"]} for cid in result["citations"] if cid in clauses],
            "indicative": True}


# ---------- vehicles ----------

def model_key(v: Vehicle) -> str | None:
    ref = v.source_ref or ""
    return Path(ref).stem if ref.startswith("data/documents/vehicles/") else None


def _brochure(v: Vehicle) -> str | None:
    if model_key(v) is None:
        return None
    base = (assets_dir() / "data" / "documents" / "vehicles").resolve()
    path = (assets_dir() / v.source_ref).resolve()
    if base not in path.parents or not path.is_file():
        return None
    return path.read_text("utf-8")


def vehicle_detail(session: Session, p: Principal, vehicle_id: str) -> dict[str, Any]:
    view = svc.get_vehicle(session, p, vehicle_id)
    v = session.get(Vehicle, vehicle_id)
    assert v is not None
    siblings = session.scalars(select(Vehicle).where(Vehicle.make == v.make, Vehicle.model == v.model,
                                                     Vehicle.id != v.id).order_by(Vehicle.id))
    return {**view, "model_key": model_key(v), "brochure": _brochure(v),
            "other_variants": [{"id": s.id, "variant": s.variant, "fuel_type": s.fuel_type,
                                "transmission": s.transmission} for s in siblings]}


def ask_vehicle(session: Session, p: Principal, vehicle_id: str, question: str, kb: KnowledgeBase | None,
                answerer: VehicleAnswerer | None, quota: Quota | None, cid: str | None) -> dict[str, Any]:
    p.require("vehicle:read")
    v = session.get(Vehicle, vehicle_id)
    if v is None:
        raise not_found("Vehicle")
    key = model_key(v)
    if key is None:
        raise AppError(409, "NO_VEHICLE_DOCUMENTS", "No brochure is indexed for this vehicle")
    use_ai = answerer if (answerer is not None and (quota is None or quota.allow_ai(p.tenant_id))) else None
    result = answer_question(kb, {"id": v.id, "make": v.make, "model": v.model, "model_key": key}, question, use_ai)
    svc.audit(session, p, "vehicle.question_answered", "vehicle", v.id,
              {"answerable": result["answerable"], "mode": result["mode"]}, cid)
    return result


@dataclass(frozen=True)
class Terms:
    capacity: Decimal
    down_payment: Decimal
    annual_rate: Decimal
    tenure_months: int
    region: str
    available_emi: Decimal | None  # known only for decisions; lets us model a longer tenure
    max_capacity: Decimal | None = None  # policy borrowing capacity when above the sanctioned amount


@dataclass(frozen=True)
class Filters:
    body_type: str | None = None
    fuel_type: str | None = None
    make: str | None = None
    min_seating: int | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    max_emi: Decimal | None = None

    def relaxed(self) -> "Filters":
        return Filters()

    def active(self) -> dict[str, str]:
        return {k: str(v) for k, v in self.__dict__.items() if v is not None}


SORTS = ("best_fit", "price", "emi")
_ORDER = {affordability.AFFORDABLE: 0, affordability.NOT_AFFORDABLE: 1, affordability.UNVERIFIED: 2,
          affordability.NOT_ELIGIBLE: 3}


def _price(item: dict[str, Any]) -> Decimal:
    values = item["assessment"]["values"]
    return Decimal(values.get("on_road_price") or values["ex_showroom"])


def _assess(session: Session, policy: PolicyDocument, terms: Terms, filters: Filters,
            as_of: date) -> list[dict[str, Any]]:
    q = select(Vehicle)
    if filters.body_type:
        q = q.where(Vehicle.body_type == filters.body_type)
    if filters.fuel_type:
        q = q.where(Vehicle.fuel_type == filters.fuel_type)
    if filters.make:
        q = q.where(Vehicle.make == filters.make)
    if filters.min_seating:
        q = q.where(Vehicle.seating >= filters.min_seating)
    vehicles = list(session.scalars(q.order_by(Vehicle.id)))
    prices = svc._latest_prices(session, [v.id for v in vehicles])
    items = []
    for v in vehicles:
        regional = next((pr for pr in prices.get(v.id, []) if pr.region == terms.region), None)
        if regional is None:
            assessment = affordability.VehicleAssessment(v.id, affordability.UNVERIFIED, ["NO_REGIONAL_PRICE"])
            assessment.values = {"ex_showroom": None}
        else:
            assessment = affordability.assess_vehicle(
                svc._quote(regional, v.category), policy=policy, borrowing_capacity=terms.capacity,
                down_payment=terms.down_payment, annual_rate=terms.annual_rate, tenure_months=terms.tenure_months,
                as_of=as_of)
        item = {"vehicle": {"id": v.id, "make": v.make, "model": v.model, "variant": v.variant,
                            "body_type": v.body_type, "fuel_type": v.fuel_type, "seating": v.seating,
                            "transmission": v.transmission, "model_key": model_key(v)},
                "assessment": assessment.to_dict()}
        if item["assessment"]["values"].get("ex_showroom") is None:
            continue
        price = _price(item)
        if filters.min_price is not None and price < filters.min_price:
            continue
        if filters.max_price is not None and price > filters.max_price:
            continue
        emi = item["assessment"]["values"].get("emi")
        if filters.max_emi is not None and (emi is None or Decimal(emi) > filters.max_emi):
            continue
        items.append(item)
    return items


def _sort(items: list[dict[str, Any]], sort: str) -> None:
    def emi(i: dict[str, Any]) -> Decimal:
        return Decimal(i["assessment"]["values"].get("emi") or "Infinity")

    def shortfall(i: dict[str, Any]) -> Decimal:
        return Decimal(i["assessment"]["values"].get("shortfall") or "0")

    if sort == "price":
        items.sort(key=lambda i: (_ORDER[i["assessment"]["status"]], _price(i)))
    elif sort == "emi":
        items.sort(key=lambda i: (_ORDER[i["assessment"]["status"]], emi(i)))
    else:  # best fit: the most vehicle the budget covers, then the nearest misses
        items.sort(key=lambda i: (_ORDER[i["assessment"]["status"]],
                                  -_price(i) if i["assessment"]["status"] == affordability.AFFORDABLE else shortfall(i)))


def _name(item: dict[str, Any]) -> str:
    v = item["vehicle"]
    return f"{v['make']} {v['model']} {v['variant']}"


def _affordable(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in items if i["assessment"]["status"] == affordability.AFFORDABLE]


def _guidance(session: Session, policy: PolicyDocument, terms: Terms, filters: Filters, items: list[dict[str, Any]],
              as_of: date) -> list[dict[str, Any]]:
    r = policy.rules
    out: list[dict[str, Any]] = []
    if terms.max_capacity is not None and terms.max_capacity > terms.capacity:
        more = Terms(terms.max_capacity, terms.down_payment, terms.annual_rate, terms.tenure_months, terms.region,
                     terms.available_emi)
        fits = _affordable(_assess(session, policy, more, filters, as_of))
        if fits:
            fits.sort(key=_price)
            out.append({"type": "REQUEST_HIGHER_AMOUNT",
                        "text": f"Your repayment capacity supports up to {fmt(terms.max_capacity)}, more than the "
                                f"amount you requested. A new application for a higher amount would make "
                                f"{len(fits)} vehicle(s) fit, for example the {_name(fits[0])}.",
                        "vehicle_ids": [i["vehicle"]["id"] for i in fits[:5]],
                        "citations": [r.debt_service.clause, r.principal.clause]})
    near = sorted((i for i in items if i["assessment"]["reasons"] == ["DOWN_PAYMENT_SHORTFALL"]),
                  key=lambda i: Decimal(i["assessment"]["values"]["shortfall"]))
    if near:
        best = near[0]
        out.append({"type": "INCREASE_DOWN_PAYMENT",
                    "text": f"Increase your down payment by {best['assessment']['values']['shortfall']} to afford the "
                            f"{_name(best)} (EMI {best['assessment']['values']['emi']}).",
                    "vehicle_ids": [best["vehicle"]["id"]], "citations": [r.ltv.clause, r.processing_fee.clause]})
    if terms.tenure_months < r.tenure.max_months:
        capacity = terms.capacity
        if terms.available_emi is not None:
            rate = monthly_rate_from_nominal_annual(terms.annual_rate)
            capacity = min(floor_to(principal_for_emi(terms.available_emi, rate, r.tenure.max_months),
                                    r.rounding.principal_step), r.principal.max_amount)
        longer = Terms(capacity, terms.down_payment, terms.annual_rate, r.tenure.max_months, terms.region,
                       terms.available_emi)
        fits = _affordable(_assess(session, policy, longer, filters, as_of))
        if fits:
            fits.sort(key=lambda i: Decimal(i["assessment"]["values"]["emi"]))
            out.append({"type": "LONGER_TENURE",
                        "text": f"With the policy's maximum tenure of {r.tenure.max_months} months, you could "
                                f"borrow up to {fmt(capacity)} and {len(fits)} vehicle(s) fit, for example the "
                                f"{_name(fits[0])} at EMI {fits[0]['assessment']['values']['emi']}. A longer tenure "
                                "means paying more interest overall.",
                        "vehicle_ids": [i["vehicle"]["id"] for i in fits[:5]],
                        "citations": [r.tenure.clause, r.debt_service.clause]})
    if filters.active():
        cheaper = _affordable(_assess(session, policy, terms, filters.relaxed(), as_of))
        if cheaper:
            cheaper.sort(key=_price)
            out.append({"type": "RELAX_FILTERS",
                        "text": "No vehicle matches your filters within budget. Without the filters, these fit: "
                                + "; ".join(f"{_name(i)} ({fmt(_price(i))})" for i in cheaper[:3]) + ".",
                        "vehicle_ids": [i["vehicle"]["id"] for i in cheaper[:3]], "citations": []})
    cheapest = sorted((i for i in items if i["assessment"]["status"] == affordability.NOT_AFFORDABLE), key=_price)
    if cheapest and not near:
        out.append({"type": "LOWER_PRICED_VARIANT",
                    "text": f"Consider a lower-priced variant; the least expensive option in your selection is the "
                            f"{_name(cheapest[0])} at {fmt(_price(cheapest[0]))}.",
                    "vehicle_ids": [cheapest[0]["vehicle"]["id"]], "citations": []})
    if not out:
        out.append({"type": "NO_ALTERNATIVE",
                    "text": "No catalogue vehicle fits these terms, even with the changes we can model. A credit "
                            "officer can discuss other options.", "vehicle_ids": [], "citations": []})
    return out


def recommend_vehicles(session: Session, p: Principal, as_of: date, *, decision_id: str | None,
                       sanctioned_amount: Decimal | None, down_payment: Decimal | None, tenure_months: int | None,
                       annual_rate: Decimal | None, region: str, filters: Filters, sort: str,
                       limit: int) -> dict[str, Any]:
    p.require("vehicle:read")
    if sort not in SORTS:
        raise unprocessable("INVALID_SORT", f"sort must be one of {', '.join(SORTS)}")
    if decision_id:
        d = svc.get_decision(session, p, decision_id)
        snap = json.loads(d.snapshot_json)
        result, applicant = snap["result"], snap["input"]
        if d.outcome != eligibility.APPROVED or d.policy_version_id is None:
            return {"basis": "decision", "decision_id": d.id, "eligible": False, "items": [], "counts": {},
                    "guidance": [{"type": "NOT_ELIGIBLE",
                                  "text": "The application was not approved, so no loan-funded vehicle can be "
                                          "recommended. " + " ".join(REASON_TEXT.get(c, c)
                                                                     for c in result["reason_codes"]),
                                  "vehicle_ids": [], "citations": result["citations"]}]}
        policy = PolicyDocument.model_validate_json(svc._policy_row(session, p.tenant_id,
                                                                    d.policy_version_id).document_json)
        calcs = result["calculations"]
        # The shortlist uses the sanctioned amount; unused policy capacity is offered as guidance only.
        terms = Terms(Decimal(result["eligible_principal"]), Decimal(applicant["down_payment_available"]),
                      Decimal(result["annual_rate"]), int(result["tenure_months"]), applicant["region"],
                      Decimal(calcs["available_emi"]) if calcs.get("available_emi") else None,
                      Decimal(result["borrowing_capacity"]))
        basis: dict[str, Any] = {"basis": "decision", "decision_id": d.id, "eligible": True}
    else:
        if None in (sanctioned_amount, down_payment, tenure_months, annual_rate):
            raise unprocessable("MISSING_TERMS", "Provide decision_id, or sanctioned_amount, down_payment, "
                                                 "tenure_months and annual_rate")
        assert sanctioned_amount is not None and down_payment is not None and tenure_months is not None
        assert annual_rate is not None
        tenant = session.get(Tenant, p.tenant_id)
        assert tenant is not None
        candidates = svc._published_policies(session, p.tenant_id)
        policy, issue = eligibility.select_policy([doc for _, doc in candidates], tenant.default_product, as_of)
        if policy is None:
            raise AppError(409, issue or "NO_APPLICABLE_POLICY", "No published policy applies today")
        if not policy.rules.tenure.min_months <= tenure_months <= policy.rules.tenure.max_months:
            raise unprocessable("TENURE_OUT_OF_RANGE", f"Tenure must be {policy.rules.tenure.min_months}-"
                                                       f"{policy.rules.tenure.max_months} months "
                                                       f"({policy.rules.tenure.clause})")
        terms = Terms(sanctioned_amount, down_payment, annual_rate, tenure_months, region, None)
        basis = {"basis": "supplied_terms", "decision_id": None, "eligible": None,
                 "note": "Uses the amounts you supplied; it is not a credit decision."}
    items = _assess(session, policy, terms, filters, as_of)
    _sort(items, sort)
    counts: dict[str, int] = {}
    for i in items:
        counts[i["assessment"]["status"]] = counts.get(i["assessment"]["status"], 0) + 1
    guidance = [] if _affordable(items) else _guidance(session, policy, terms, filters, items, as_of)
    return {**basis, "policy": {"policy_code": policy.policy_code, "version": policy.version},
            "terms": {"sanctioned_amount": fmt(terms.capacity), "down_payment": fmt(terms.down_payment),
                      "annual_rate": str(terms.annual_rate), "tenure_months": terms.tenure_months,
                      "region": terms.region},
            "filters": filters.active(), "sort": sort, "as_of": as_of.isoformat(), "counts": counts,
            "items": items[:limit], "total": len(items), "guidance": guidance}
