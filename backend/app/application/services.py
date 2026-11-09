"""Application services: orchestrate repositories, the pure domain engine, and adapters.
Every query is tenant-scoped using the authenticated principal's tenant."""

import base64
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.errors import AppError, conflict, not_found, unprocessable
from app.application.security import Principal
from app.domain import affordability, eligibility
from app.domain.applicant import ApplicantInput, missing_fields
from app.domain.explanation import REASON_TEXT, ExplanationDraft, template_explanation, validate_explanation
from app.domain.policy import PolicyDocument
from app.infrastructure.gemini import Explainer, ExplainerUnavailable
from app.infrastructure.quota import Quota
from app.ml.model import RiskModel
from app.rag.knowledge import KnowledgeBase
from app.infrastructure.models import (
    Application,
    AuditEvent,
    Decision,
    Explanation,
    PolicyVersion,
    Tenant,
    Vehicle,
    VehiclePrice,
    utcnow,
)

MAX_PAGE = 100
AI_BUDGET_EXHAUSTED = "Tenant AI budget exhausted for today"


# ---------- helpers ----------

def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def encode_cursor(*parts: str) -> str:
    return base64.urlsafe_b64encode(json.dumps(parts).encode()).decode()


def decode_cursor(cursor: str | None) -> list[str] | None:
    if not cursor:
        return None
    try:
        parts = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(parts, list) or not all(isinstance(p, str) for p in parts):
            raise ValueError
        return parts
    except ValueError as exc:
        raise unprocessable("INVALID_CURSOR", "Cursor is malformed") from exc


def _limit(limit: int) -> int:
    return max(1, min(limit, MAX_PAGE))


def audit(session: Session, p: Principal, action: str, entity_type: str, entity_id: str,
          details: dict[str, Any] | None = None, correlation_id: str | None = None) -> None:
    session.add(AuditEvent(tenant_id=p.tenant_id, actor_user_id=p.user_id, action=action, entity_type=entity_type,
                           entity_id=entity_id, correlation_id=correlation_id,
                           details_json=canonical_json(details or {})))


def _iso(dt: datetime) -> str:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


# ---------- applications ----------

def application_view(app: Application) -> dict[str, Any]:
    return {"id": app.id, "status": app.status, "applicant_user_id": app.applicant_user_id,
            "input": json.loads(app.input_json), "row_version": app.row_version,
            "created_at": _iso(app.created_at), "updated_at": _iso(app.updated_at)}


def create_application(session: Session, p: Principal, data: ApplicantInput, cid: str | None) -> Application:
    p.require("application:create")
    app = Application(tenant_id=p.tenant_id, applicant_user_id=p.user_id, status="DRAFT",
                      input_json=data.model_dump_json())
    session.add(app)
    session.flush()
    audit(session, p, "application.created", "application", app.id, correlation_id=cid)
    return app


def get_application(session: Session, p: Principal, app_id: str) -> Application:
    app = session.scalar(select(Application).where(Application.tenant_id == p.tenant_id, Application.id == app_id))
    if app is None or not p.can_read_application(app.applicant_user_id):
        raise not_found("Application")
    return app


def update_application(session: Session, p: Principal, app_id: str, data: ApplicantInput,
                       expected_version: int, cid: str | None) -> Application:
    app = get_application(session, p, app_id)
    if app.applicant_user_id != p.user_id and not p.has("application:read_all"):
        raise not_found("Application")
    if app.status not in {"DRAFT", "INCOMPLETE", "NEEDS_REVIEW"}:
        raise conflict("APPLICATION_LOCKED", f"Application in status {app.status} cannot be edited")
    result = session.execute(
        update(Application)
        .where(Application.tenant_id == p.tenant_id, Application.id == app_id,
               Application.row_version == expected_version)
        .values(input_json=data.model_dump_json(), row_version=Application.row_version + 1, updated_at=utcnow())
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise conflict("VERSION_CONFLICT", "Application was modified by another request; reload and retry")
    audit(session, p, "application.updated", "application", app_id, correlation_id=cid)
    session.refresh(app)
    return app


def list_applications(session: Session, p: Principal, cursor: str | None, limit: int) -> dict[str, Any]:
    limit = _limit(limit)
    q = select(Application).where(Application.tenant_id == p.tenant_id)
    if not p.has("application:read_all"):
        p.require("application:read_own")
        q = q.where(Application.applicant_user_id == p.user_id)
    after = decode_cursor(cursor)
    if after:
        ts = datetime.fromisoformat(after[0])
        q = q.where((Application.created_at < ts) | ((Application.created_at == ts) & (Application.id < after[1])))
    rows = list(session.scalars(q.order_by(Application.created_at.desc(), Application.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    latest = _latest_decisions(session, p.tenant_id, [a.id for a in page])
    items = []
    for app in page:
        view = application_view(app)
        d = latest.get(app.id)
        view["latest_decision"] = None if d is None else {
            "id": d.id, "status": d.status, "outcome": d.outcome, "eligible_principal": d.eligible_principal,
            "evaluated_at": _iso(d.evaluated_at)}
        items.append(view)
    next_cursor = encode_cursor(page[-1].created_at.isoformat(), page[-1].id) if len(rows) > limit else None
    return {"items": items, "next_cursor": next_cursor}


def _latest_decisions(session: Session, tenant_id: str, app_ids: list[str]) -> dict[str, Decision]:
    if not app_ids:
        return {}
    rows = session.scalars(select(Decision).where(Decision.tenant_id == tenant_id,
                                                  Decision.application_id.in_(app_ids))
                           .order_by(Decision.evaluated_at.asc()))
    return {d.application_id: d for d in rows}


# ---------- policies ----------

def _published_policies(session: Session, tenant_id: str) -> list[tuple[PolicyVersion, PolicyDocument]]:
    rows = session.scalars(select(PolicyVersion).where(PolicyVersion.tenant_id == tenant_id,
                                                       PolicyVersion.status == "PUBLISHED"))
    return [(row, PolicyDocument.model_validate_json(row.document_json)) for row in rows]


def _policy_row(session: Session, tenant_id: str, version_id: str) -> PolicyVersion:
    row = session.scalar(select(PolicyVersion).where(PolicyVersion.tenant_id == tenant_id,
                                                     PolicyVersion.id == version_id))
    if row is None:
        raise not_found("Policy version")
    return row


def policy_view(row: PolicyVersion, include_document: bool = False) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": row.id, "policy_code": row.policy_code, "version": row.version, "product": row.product,
        "status": row.status, "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "content_sha256": row.content_sha256, "created_by": row.created_by, "created_at": _iso(row.created_at),
        "published_by": row.published_by, "published_at": _iso(row.published_at) if row.published_at else None,
    }
    if include_document:
        view["document"] = json.loads(row.document_json)
    return view


def list_policies(session: Session, p: Principal) -> list[dict[str, Any]]:
    p.require("policy:read")
    rows = session.scalars(select(PolicyVersion).where(PolicyVersion.tenant_id == p.tenant_id)
                           .order_by(PolicyVersion.effective_from.desc(), PolicyVersion.created_at.desc()))
    return [policy_view(r) for r in rows]


def get_policy(session: Session, p: Principal, version_id: str) -> dict[str, Any]:
    p.require("policy:read")
    return policy_view(_policy_row(session, p.tenant_id, version_id), include_document=True)


def create_policy_draft(session: Session, p: Principal, doc: PolicyDocument, cid: str | None) -> PolicyVersion:
    p.require("policy:write")
    body = canonical_json(doc.model_dump(mode="json"))
    row = PolicyVersion(tenant_id=p.tenant_id, policy_code=doc.policy_code, version=doc.version, product=doc.product,
                        status="DRAFT", document_json=body, content_sha256=sha256(body),
                        effective_from=doc.effective_from, effective_to=doc.effective_to, created_by=p.user_id)
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        raise conflict("POLICY_VERSION_EXISTS", "This policy code and version already exist") from exc
    audit(session, p, "policy.draft_created", "policy_version", row.id,
          {"policy_code": doc.policy_code, "version": doc.version, "sha256": row.content_sha256}, cid)
    return row


def publish_policy(session: Session, p: Principal, version_id: str, cid: str | None) -> PolicyVersion:
    p.require("policy:publish")
    row = _policy_row(session, p.tenant_id, version_id)
    if row.status != "DRAFT":
        raise conflict("POLICY_NOT_DRAFT", f"Only drafts can be published (status {row.status})")
    clash = session.scalar(select(PolicyVersion.id).where(
        PolicyVersion.tenant_id == p.tenant_id, PolicyVersion.product == row.product,
        PolicyVersion.status == "PUBLISHED", PolicyVersion.effective_from == row.effective_from))
    if clash:
        raise conflict("POLICY_CONFLICT", "A published policy already starts on this date for this product")
    result = session.execute(update(PolicyVersion)
                             .where(PolicyVersion.id == row.id, PolicyVersion.status == "DRAFT")
                             .values(status="PUBLISHED", published_by=p.user_id, published_at=utcnow()))
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise conflict("POLICY_NOT_DRAFT", "Policy was published concurrently")
    audit(session, p, "policy.published", "policy_version", row.id, {"sha256": row.content_sha256}, cid)
    session.refresh(row)
    return row


# ---------- evaluation ----------

def decision_view(d: Decision) -> dict[str, Any]:
    return {"id": d.id, "application_id": d.application_id, "status": d.status, "outcome": d.outcome,
            "eligible_principal": d.eligible_principal, "engine_version": d.engine_version,
            "policy_version_id": d.policy_version_id, "result_sha256": d.result_sha256,
            "evaluated_at": _iso(d.evaluated_at), "snapshot": json.loads(d.snapshot_json)}


def score_applicant(model: RiskModel | None, applicant: ApplicantInput,
                    policy: PolicyDocument | None) -> dict[str, Any] | None:
    """Model output for the snapshot. `applied` is true only when the policy cites this exact model."""
    if model is None or missing_fields(applicant):
        return None
    score = model.score(applicant).to_dict()
    rule = policy.rules.credit_risk if policy is not None else None
    score["name"] = model.card.get("name")
    score["applied"] = rule is not None and rule.model_name == score["name"]
    if rule is not None:
        score["policy_threshold"] = str(rule.min_approval_probability)
    return score


def evaluate_application(session: Session, p: Principal, app_id: str, idempotency_key: str | None,
                         as_of: date, cid: str | None, model: RiskModel | None = None) -> tuple[Decision, bool]:
    """Returns (decision, created). Replays with the same Idempotency-Key return the original decision."""
    app = get_application(session, p, app_id)
    if app.applicant_user_id != p.user_id and not p.has("application:read_all"):
        raise not_found("Application")
    p.require("application:create")
    if idempotency_key:
        existing = session.scalar(select(Decision).where(Decision.tenant_id == p.tenant_id,
                                                         Decision.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.application_id != app_id:
                raise conflict("IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was used for a different application")
            return existing, False

    applicant = ApplicantInput.model_validate_json(app.input_json)
    tenant = session.get(Tenant, p.tenant_id)
    assert tenant is not None
    candidates = _published_policies(session, p.tenant_id)
    policy, issue = eligibility.select_policy([doc for _, doc in candidates], tenant.default_product, as_of)

    policy_meta: dict[str, Any] = {}
    clauses: list[dict[str, Any]] = []
    policy_row: PolicyVersion | None = None
    model_output = score_applicant(model, applicant, policy)
    if policy is None:
        # Missing data still reported as INCOMPLETE; an absent policy never becomes a rejection.
        missing = missing_fields(applicant)
        result = (eligibility.EvaluationResult(status=eligibility.STATUS_INCOMPLETE, missing_fields=missing,
                                               reason_codes=["MISSING_REQUIRED_FIELDS"]) if missing else
                  eligibility.EvaluationResult(status=eligibility.STATUS_NEEDS_REVIEW, reason_codes=[issue or ""]))
    else:
        policy_row = next(row for row, doc in candidates if doc is policy)
        probability = model_output["approval_probability"] if model_output and model_output["applied"] else None
        result = eligibility.evaluate(applicant, policy, probability)
        policy_meta = {"version_id": policy_row.id, "policy_code": policy.policy_code, "version": policy.version,
                       "lender_name": policy.lender_name, "product": policy.product,
                       "content_sha256": policy_row.content_sha256, "synthetic": policy.synthetic,
                       "source_document": policy.source_document}
        referenced = set(result.citations) | {r.clause_id for r in result.rule_results}
        clauses = [c.model_dump() for c in policy.clauses if c.id in referenced]

    result_dict = result.to_dict()
    now = utcnow()
    snapshot = {
        "engine_version": eligibility.ENGINE_VERSION,
        "evaluated_at": now.isoformat(),
        "as_of": as_of.isoformat(),
        "tenant_id": p.tenant_id,
        "application_id": app.id,
        "product": tenant.default_product,
        "input": applicant.model_dump(mode="json"),
        "input_provenance": {"source": "applicant_self_declared", "captured_for": app.applicant_user_id,
                             "application_row_version": app.row_version, "verified": False},
        "policy": policy_meta,
        "clauses": clauses,
        "model": model_output,
        "result": result_dict,
    }
    decision = Decision(tenant_id=p.tenant_id, application_id=app.id,
                        policy_version_id=policy_row.id if policy_row else None, status=result.status,
                        outcome=result.outcome, eligible_principal=result_dict["eligible_principal"],
                        snapshot_json=canonical_json(snapshot), result_sha256=sha256(canonical_json(result_dict)),
                        engine_version=eligibility.ENGINE_VERSION, idempotency_key=idempotency_key,
                        evaluated_by=p.user_id, evaluated_at=now)
    session.add(decision)
    app.status = {"INCOMPLETE": "INCOMPLETE", "NEEDS_REVIEW": "NEEDS_REVIEW"}.get(result.status, "COMPLETED")
    app.updated_at = now
    try:
        session.flush()
    except IntegrityError as exc:
        raise conflict("IDEMPOTENCY_IN_PROGRESS", "A request with this Idempotency-Key is being processed") from exc
    audit(session, p, "application.evaluated", "decision", decision.id,
          {"status": result.status, "outcome": result.outcome, "policy_version_id": decision.policy_version_id}, cid)
    return decision, True


def get_decision(session: Session, p: Principal, decision_id: str) -> Decision:
    d = session.scalar(select(Decision).where(Decision.tenant_id == p.tenant_id, Decision.id == decision_id))
    if d is None:
        raise not_found("Decision")
    get_application(session, p, d.application_id)  # object-level authorization via the owning application
    return d


def latest_decision(session: Session, p: Principal, app_id: str) -> Decision:
    get_application(session, p, app_id)
    d = session.scalar(select(Decision).where(Decision.tenant_id == p.tenant_id, Decision.application_id == app_id)
                       .order_by(Decision.evaluated_at.desc()).limit(1))
    if d is None:
        raise not_found("Decision")
    return d


def replay_decision(session: Session, p: Principal, decision_id: str,
                    model: RiskModel | None = None) -> dict[str, Any]:
    d = get_decision(session, p, decision_id)
    snap = json.loads(d.snapshot_json)
    applicant = ApplicantInput.model_validate(snap["input"])
    if d.policy_version_id is None:
        return {"decision_id": d.id, "reproducible": None, "reason": "Decision had no applicable policy",
                "missing_fields": missing_fields(applicant)}
    row = _policy_row(session, p.tenant_id, d.policy_version_id)
    policy_hash_ok = row.content_sha256 == snap["policy"]["content_sha256"]
    policy = PolicyDocument.model_validate_json(row.document_json)
    # The engine is replayed with the recorded model score; the model itself is checked by artifact hash.
    recorded = snap.get("model")
    probability = recorded["approval_probability"] if recorded and recorded.get("applied") else None
    replay = eligibility.evaluate(applicant, policy, probability).to_dict()
    replay_hash = sha256(canonical_json(replay))
    model_unchanged = None if not recorded else (model is not None and
                                                 model.card.get("artifact_sha256") == recorded["artifact_sha256"])
    return {
        "decision_id": d.id,
        "reproducible": policy_hash_ok and replay_hash == d.result_sha256 and
        d.engine_version == eligibility.ENGINE_VERSION,
        "policy_unchanged": policy_hash_ok,
        "model_unchanged": model_unchanged,
        "engine_version_recorded": d.engine_version,
        "engine_version_current": eligibility.ENGINE_VERSION,
        "recorded_result_sha256": d.result_sha256,
        "replayed_result_sha256": replay_hash,
    }


# ---------- explanations ----------

def _retrieve_policy_context(session: Session, p: Principal, d: Decision, snap: dict[str, Any],
                             kb: KnowledgeBase | None) -> tuple[list[dict[str, Any]], str | None]:
    """Policy clauses from the vector store, restricted to the exact policy version the decision used."""
    if kb is None or d.policy_version_id is None:
        return [], None
    policy = PolicyDocument.model_validate_json(_policy_row(session, p.tenant_id, d.policy_version_id).document_json)
    by_id = {c.id: c for c in policy.clauses}
    result = snap["result"]
    cited = set(result["citations"])
    query = " ".join([REASON_TEXT.get(code, code) for code in result["reason_codes"]] +
                     [c["title"] for c in snap["clauses"] if c["id"] in cited] +
                     [f.replace("_", " ").lower() for f in result["flags"]])
    hits, threshold, index = kb.search(query, 5, {"doc_type": "policy", "policy_code": policy.policy_code,
                                                 "version": policy.version})
    sources = []
    for hit in hits:
        clause = by_id.get(hit.chunk.meta["clause_id"])
        if clause is not None and hit.score >= threshold:
            sources.append({**clause.model_dump(), "score": round(hit.score, 4), "chunk_id": hit.chunk.id,
                            "source": hit.chunk.meta.get("source")})
    return sources, index


def explain_decision(session: Session, p: Principal, decision_id: str, explainer: Explainer,
                     refresh: bool, cid: str | None, quota: Quota | None = None,
                     kb: KnowledgeBase | None = None) -> dict[str, Any]:
    d = get_decision(session, p, decision_id)
    if not refresh:
        cached = session.scalar(select(Explanation).where(Explanation.tenant_id == p.tenant_id,
                                                          Explanation.decision_id == d.id)
                                .order_by(Explanation.created_at.desc()).limit(1))
        if cached is not None:
            return explanation_view(cached)
    snap = json.loads(d.snapshot_json)
    retrieved, index = _retrieve_policy_context(session, p, d, snap, kb)
    recorded_ids = {c["id"] for c in snap["clauses"]}
    # Retrieved clauses join the evidence (and become citable); the recorded decision itself is unchanged.
    snap["clauses"] = snap["clauses"] + [{k: c[k] for k in ("id", "section", "page", "title", "text")}
                                         for c in retrieved if c["id"] not in recorded_ids]
    result = snap["result"]
    # Minimised facts: no identity, no free text from the applicant.
    facts = {"status": result["status"], "outcome": result["outcome"] or result["status"],
             "reason_codes": result["reason_codes"], "flags": result["flags"],
             "missing_fields": result["missing_fields"], "calculations": result["calculations"],
             "rule_results": result["rule_results"], "currency": snap["input"].get("currency"),
             "policy": {k: snap["policy"].get(k) for k in ("policy_code", "version", "lender_name")}}
    evidence = [{"clause_id": c["id"], "section": c["section"], "page": c["page"], "text": c["text"]}
                for c in snap["clauses"]]
    source, fallback_reason, model = "template", None, None
    try:
        if quota is not None and not quota.allow_ai(p.tenant_id):
            raise ExplainerUnavailable(AI_BUDGET_EXHAUSTED)
        draft = explainer.draft(facts, evidence)
        problems = validate_explanation(draft, snap)
        if problems:
            fallback_reason = "AI draft rejected: " + "; ".join(problems[:5])
            draft = template_explanation(snap)
        else:
            source, model = "ai", explainer.model
    except ExplainerUnavailable as exc:
        fallback_reason = str(exc)
        draft = template_explanation(snap)
    row = Explanation(tenant_id=p.tenant_id, decision_id=d.id, source=source, model=model,
                      content_json=draft.model_dump_json(), fallback_reason=fallback_reason,
                      sources_json=canonical_json({"index": index, "items": retrieved}))
    session.add(row)
    session.flush()
    audit(session, p, "decision.explained", "decision", d.id, {"source": source}, cid)
    return explanation_view(row)


def explanation_view(row: Explanation) -> dict[str, Any]:
    sources = json.loads(row.sources_json) if row.sources_json else {"index": None, "items": []}
    return {"id": row.id, "decision_id": row.decision_id, "source": row.source, "model": row.model,
            "fallback_reason": row.fallback_reason, "created_at": _iso(row.created_at),
            "content": ExplanationDraft.model_validate_json(row.content_json).model_dump(),
            "retrieval_index": sources["index"], "retrieved_sources": sources["items"]}


# ---------- vehicles ----------

def _price_view(price: VehiclePrice) -> dict[str, Any]:
    quote = _quote(price, "")
    return {"region": price.region, "currency": price.currency, "ex_showroom": price.ex_showroom,
            "registration": price.registration, "insurance": price.insurance, "other_charges": price.other_charges,
            "on_road": str(quote.on_road) if quote.on_road is not None else None,
            "on_road_complete": quote.on_road is not None, "price_date": price.price_date.isoformat(),
            "source": price.source}


def _quote(price: VehiclePrice, category: str) -> affordability.PriceQuote:
    def dec(v: str | None) -> Decimal | None:
        return None if v is None else Decimal(v)

    return affordability.PriceQuote(vehicle_id=price.vehicle_id, category=category, region=price.region,
                                    currency=price.currency, ex_showroom=Decimal(price.ex_showroom),
                                    registration=dec(price.registration), insurance=dec(price.insurance),
                                    other_charges=dec(price.other_charges), price_date=price.price_date)


def vehicle_view(v: Vehicle, prices: list[VehiclePrice]) -> dict[str, Any]:
    return {"id": v.id, "make": v.make, "model": v.model, "variant": v.variant, "body_type": v.body_type,
            "fuel_type": v.fuel_type, "category": v.category, "transmission": v.transmission, "seating": v.seating,
            "specs": json.loads(v.specs_json), "source": v.source, "source_ref": v.source_ref,
            "prices": [_price_view(pr) for pr in sorted(prices, key=lambda x: (x.region, x.price_date))]}


def _latest_prices(session: Session, vehicle_ids: list[str]) -> dict[str, list[VehiclePrice]]:
    out: dict[str, dict[str, VehiclePrice]] = {}
    for pr in session.scalars(select(VehiclePrice).where(VehiclePrice.vehicle_id.in_(vehicle_ids))):
        current = out.setdefault(pr.vehicle_id, {}).get(pr.region)
        if current is None or pr.price_date > current.price_date:
            out[pr.vehicle_id][pr.region] = pr
    return {vid: list(by_region.values()) for vid, by_region in out.items()}


def list_vehicles(session: Session, p: Principal, cursor: str | None, limit: int, body_type: str | None,
                  fuel_type: str | None, make: str | None) -> dict[str, Any]:
    p.require("vehicle:read")
    limit = _limit(limit)
    q = select(Vehicle)
    if body_type:
        q = q.where(Vehicle.body_type == body_type)
    if fuel_type:
        q = q.where(Vehicle.fuel_type == fuel_type)
    if make:
        q = q.where(Vehicle.make == make)
    after = decode_cursor(cursor)
    if after:
        q = q.where(Vehicle.id > after[0])
    rows = list(session.scalars(q.order_by(Vehicle.id).limit(limit + 1)))
    page = rows[:limit]
    prices = _latest_prices(session, [v.id for v in page])
    return {"items": [vehicle_view(v, prices.get(v.id, [])) for v in page],
            "next_cursor": encode_cursor(page[-1].id) if len(rows) > limit else None}


def get_vehicle(session: Session, p: Principal, vehicle_id: str) -> dict[str, Any]:
    p.require("vehicle:read")
    v = session.get(Vehicle, vehicle_id)
    if v is None:
        raise not_found("Vehicle")
    all_prices = list(session.scalars(select(VehiclePrice).where(VehiclePrice.vehicle_id == v.id)))
    return vehicle_view(v, all_prices)


def affordable_vehicles(session: Session, p: Principal, decision_id: str, as_of: date, body_type: str | None,
                        fuel_type: str | None, status: str | None) -> dict[str, Any]:
    d = get_decision(session, p, decision_id)
    if d.outcome != eligibility.APPROVED or d.policy_version_id is None:
        raise AppError(409, "DECISION_NOT_APPROVED", "Vehicle affordability requires an approved decision")
    snap = json.loads(d.snapshot_json)
    result, applicant = snap["result"], snap["input"]
    policy = PolicyDocument.model_validate_json(_policy_row(session, p.tenant_id, d.policy_version_id).document_json)
    region = applicant["region"]
    q = select(Vehicle)
    if body_type:
        q = q.where(Vehicle.body_type == body_type)
    if fuel_type:
        q = q.where(Vehicle.fuel_type == fuel_type)
    vehicles = list(session.scalars(q.order_by(Vehicle.id)))
    prices = _latest_prices(session, [v.id for v in vehicles])
    items = []
    for v in vehicles:
        regional = next((pr for pr in prices.get(v.id, []) if pr.region == region), None)
        if regional is None:
            assessment = affordability.VehicleAssessment(v.id, affordability.UNVERIFIED, ["NO_REGIONAL_PRICE"])
        else:
            assessment = affordability.assess_vehicle(
                _quote(regional, v.category), policy=policy,
                borrowing_capacity=Decimal(result["borrowing_capacity"]),
                down_payment=Decimal(applicant["down_payment_available"]),
                annual_rate=Decimal(result["annual_rate"]), tenure_months=int(result["tenure_months"]), as_of=as_of)
        if status and assessment.status != status:
            continue
        items.append({"vehicle": {"id": v.id, "make": v.make, "model": v.model, "variant": v.variant,
                                  "body_type": v.body_type, "fuel_type": v.fuel_type, "seating": v.seating,
                                  "transmission": v.transmission},
                      "assessment": assessment.to_dict()})
    order = {affordability.AFFORDABLE: 0, affordability.NOT_AFFORDABLE: 1, affordability.UNVERIFIED: 2,
             affordability.NOT_ELIGIBLE: 3}
    items.sort(key=lambda i: (order[i["assessment"]["status"]],
                              Decimal(i["assessment"]["values"].get("emi") or "0")))
    counts = Counter(i["assessment"]["status"] for i in items)
    return {"decision_id": d.id, "region": region, "as_of": as_of.isoformat(),
            "basis": "Pre-vehicle borrowing capacity, capped per vehicle by LTV on on-road price; "
                     "affordable only if upfront cash (contribution + fees) <= available down payment.",
            "counts": dict(counts), "items": items}


# ---------- dashboard & audit ----------

def dashboard(session: Session, p: Principal, today: date) -> dict[str, Any]:
    apps_q = select(Application).where(Application.tenant_id == p.tenant_id)
    if not p.has("application:read_all"):
        apps_q = apps_q.where(Application.applicant_user_id == p.user_id)
    apps = list(session.scalars(apps_q)) if (p.has("application:read_all") or p.has("application:read_own")) else []
    latest = _latest_decisions(session, p.tenant_id, [a.id for a in apps])
    outcomes = Counter((d.outcome or d.status) for d in latest.values())
    approved = [Decimal(d.eligible_principal) for d in latest.values()
                if d.outcome == eligibility.APPROVED and d.eligible_principal]
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    created = Counter(a.created_at.date() for a in apps)
    decided = Counter(d.evaluated_at.date() for d in latest.values())
    approved_daily = Counter(d.evaluated_at.date() for d in latest.values() if d.outcome == eligibility.APPROVED)
    by_kind = {kind: Counter(d.evaluated_at.date() for d in latest.values() if (d.outcome or d.status) == kind)
               for kind in ("REJECTED", "INCOMPLETE", "NEEDS_REVIEW")}
    vehicles = session.scalar(select(func.count()).select_from(Vehicle)) or 0
    policies = session.scalar(select(func.count()).select_from(PolicyVersion).where(
        PolicyVersion.tenant_id == p.tenant_id, PolicyVersion.status == "PUBLISHED")) or 0
    return {
        "applications_total": len(apps),
        "approved": outcomes.get("APPROVED", 0),
        "rejected": outcomes.get("REJECTED", 0),
        "incomplete": outcomes.get("INCOMPLETE", 0) + sum(1 for a in apps if a.id not in latest),
        "needs_review": outcomes.get("NEEDS_REVIEW", 0),
        "approval_rate": round(outcomes.get("APPROVED", 0) / max(1, len(latest)), 4),
        "total_eligible_principal": str(sum(approved, Decimal(0))),
        "average_eligible_principal": str((sum(approved, Decimal(0)) / len(approved)).quantize(Decimal("0.01")))
        if approved else "0.00",
        "vehicles_in_catalogue": vehicles,
        "published_policies": policies,
        "series": {"days": [d.isoformat() for d in days],
                   "applications": [created.get(d, 0) for d in days],
                   "decisions": [decided.get(d, 0) for d in days],
                   "approved": [approved_daily.get(d, 0) for d in days],
                   "rejected": [by_kind["REJECTED"].get(d, 0) for d in days],
                   "incomplete": [by_kind["INCOMPLETE"].get(d, 0) for d in days],
                   "needs_review": [by_kind["NEEDS_REVIEW"].get(d, 0) for d in days]},
    }


def list_audit(session: Session, p: Principal, cursor: str | None, limit: int) -> dict[str, Any]:
    p.require("audit:read")
    limit = _limit(limit)
    q = select(AuditEvent).where(AuditEvent.tenant_id == p.tenant_id)
    after = decode_cursor(cursor)
    if after:
        ts = datetime.fromisoformat(after[0])
        q = q.where((AuditEvent.created_at < ts) | ((AuditEvent.created_at == ts) & (AuditEvent.id < after[1])))
    rows = list(session.scalars(q.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    return {"items": [{"id": e.id, "actor_user_id": e.actor_user_id, "action": e.action,
                       "entity_type": e.entity_type, "entity_id": e.entity_id, "correlation_id": e.correlation_id,
                       "details": json.loads(e.details_json), "created_at": _iso(e.created_at)} for e in page],
            "next_cursor": encode_cursor(page[-1].created_at.isoformat(), page[-1].id) if len(rows) > limit else None}


def parse_policy(payload: dict[str, Any]) -> PolicyDocument:
    try:
        return PolicyDocument.model_validate(payload)
    except ValidationError as exc:
        raise unprocessable("INVALID_POLICY", "Policy document failed validation",
                            exc.errors(include_url=False, include_context=False)) from exc
