from typing import Annotated, Any, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import correlation_id, get_principal, get_session
from app.application import documents as docs
from app.application import services as svc
from app.application.errors import AppError
from app.application.security import Principal
from app.infrastructure.observability import AI_BUDGET_DENIED, EXPLANATIONS
from app.domain.applicant import ApplicantInput
from app.infrastructure.models import Tenant, User

router = APIRouter(prefix="/v1")

SessionDep = Annotated[Session, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]
CidDep = Annotated[str | None, Depends(correlation_id)]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_\-:.]{8,128}$")]
VehicleStatus = Literal["AFFORDABLE", "NOT_AFFORDABLE", "UNVERIFIED", "NOT_ELIGIBLE"]


def _today(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.today()


@router.get("/me", tags=["identity"])
def me(p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    tenant = session.get(Tenant, p.tenant_id)
    return {"user_id": p.user_id, "email": p.email, "display_name": p.display_name,
            "tenant": {"id": p.tenant_id, "name": tenant.name if tenant else None},
            "roles": sorted(p.roles), "permissions": sorted(p.permissions),
            "available_tenants": list(p.available_tenants)}


@router.get("/dashboard", tags=["dashboard"])
def dashboard(request: Request, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    return svc.dashboard(session, p, _today(request))


@router.post("/applications", status_code=201, tags=["applications"])
def create_application(body: ApplicantInput, p: PrincipalDep, session: SessionDep, cid: CidDep) -> dict[str, Any]:
    app = svc.create_application(session, p, body, cid)
    session.commit()
    return svc.application_view(app, session.get(User, app.applicant_user_id))


@router.get("/applications", tags=["applications"])
def list_applications(p: PrincipalDep, session: SessionDep, cursor: str | None = None,
                      limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict[str, Any]:
    return svc.list_applications(session, p, cursor, limit)


@router.get("/applications/{app_id}", tags=["applications"])
def get_application(app_id: str, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    app = svc.get_application(session, p, app_id)
    return svc.application_view(app, session.get(User, app.applicant_user_id))


@router.patch("/applications/{app_id}", tags=["applications"])
def update_application(app_id: str, body: ApplicantInput, p: PrincipalDep, session: SessionDep, cid: CidDep,
                       if_match: Annotated[int, Header(alias="If-Match")]) -> dict[str, Any]:
    app = svc.update_application(session, p, app_id, body, if_match, cid)
    session.commit()
    return svc.application_view(app, session.get(User, app.applicant_user_id))


@router.post("/applications/{app_id}/evaluate", tags=["decisions"])
def evaluate(app_id: str, request: Request, response: Response, p: PrincipalDep, session: SessionDep,
             cid: CidDep, idempotency_key: IdemKey = None) -> dict[str, Any]:
    decision, created = svc.evaluate_application(session, p, app_id, idempotency_key, _today(request), cid,
                                                 request.app.state.eligibility_model)
    session.commit()
    response.status_code = 201 if created else 200
    if not created:
        response.headers["Idempotent-Replayed"] = "true"
    return svc.decision_view(decision)


@router.get("/applications/{app_id}/decision", tags=["decisions"])
def latest_decision(app_id: str, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    return svc.decision_view(svc.latest_decision(session, p, app_id))


@router.get("/decisions/{decision_id}", tags=["decisions"])
def get_decision(decision_id: str, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    return svc.decision_view(svc.get_decision(session, p, decision_id))


@router.post("/decisions/{decision_id}/replay", tags=["decisions"])
def replay(decision_id: str, request: Request, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    return svc.replay_decision(session, p, decision_id, request.app.state.eligibility_model)


@router.post("/decisions/{decision_id}/explanation", tags=["explanations"])
def explain(decision_id: str, request: Request, p: PrincipalDep, session: SessionDep, cid: CidDep,
            refresh: bool = False) -> dict[str, Any]:
    state = request.app.state
    result = svc.explain_decision(session, p, decision_id, state.explainer, refresh, cid, state.quota,
                                  state.knowledge)
    session.commit()
    EXPLANATIONS.labels(result["source"]).inc()
    if result["fallback_reason"] == svc.AI_BUDGET_EXHAUSTED:
        AI_BUDGET_DENIED.inc()
    return result


@router.get("/decisions/{decision_id}/vehicles", tags=["vehicles"])
def decision_vehicles(decision_id: str, request: Request, p: PrincipalDep, session: SessionDep,
                      body_type: str | None = None, fuel_type: str | None = None,
                      status: VehicleStatus | None = None) -> dict[str, Any]:
    return svc.affordable_vehicles(session, p, decision_id, _today(request), body_type, fuel_type, status)


@router.get("/vehicles", tags=["vehicles"])
def list_vehicles(p: PrincipalDep, session: SessionDep, cursor: str | None = None,
                  limit: Annotated[int, Query(ge=1, le=100)] = 50, body_type: str | None = None,
                  fuel_type: str | None = None, make: str | None = None) -> dict[str, Any]:
    return svc.list_vehicles(session, p, cursor, limit, body_type, fuel_type, make)


@router.get("/vehicles/{vehicle_id}", tags=["vehicles"])
def get_vehicle(vehicle_id: str, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    return svc.get_vehicle(session, p, vehicle_id)


@router.get("/policies", tags=["policies"])
def list_policies(p: PrincipalDep, session: SessionDep) -> list[dict[str, Any]]:
    return svc.list_policies(session, p)


@router.get("/policies/{version_id}", tags=["policies"])
def get_policy(version_id: str, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    view = svc.get_policy(session, p, version_id)
    view["source_document_id"] = (docs.source_document_for_policy(session, p.tenant_id, version_id)
                                  if p.has("policy_document:read") else None)
    return view


@router.post("/policies", status_code=201, tags=["policies"])
def create_policy(p: PrincipalDep, session: SessionDep, cid: CidDep,
                  document: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    p.require("policy:write")
    row = svc.create_policy_draft(session, p, svc.parse_policy(document), cid)
    session.commit()
    return svc.policy_view(row)


@router.post("/policies/{version_id}/publish", tags=["policies"])
def publish_policy(version_id: str, p: PrincipalDep, session: SessionDep, cid: CidDep) -> dict[str, Any]:
    row = svc.publish_policy(session, p, version_id, cid)
    session.commit()
    return svc.policy_view(row)


async def _read_limited(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise AppError(413, "PAYLOAD_TOO_LARGE", f"Uploads are limited to {limit // (1024 * 1024)} MB")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > limit:
            raise AppError(413, "PAYLOAD_TOO_LARGE", f"Uploads are limited to {limit // (1024 * 1024)} MB")
    return bytes(buf)


@router.post("/policy-documents", tags=["policy documents"],
             openapi_extra={"requestBody": {"required": True, "content": {
                 m: {"schema": {"type": "string", "format": "binary"}}
                 for m in ("application/pdf", "image/png", "image/jpeg")}}})
async def upload_policy_document(request: Request, response: Response, p: PrincipalDep, session: SessionDep,
                                 cid: CidDep, x_filename: Annotated[str, Header(max_length=400)] = "document"
                                 ) -> dict[str, Any]:
    """Raw-body upload (Content-Type: application/pdf | image/png | image/jpeg). Stores the original, then transcribes
    in-request (201) or, with DOCUMENT_PROCESSING=queue, queues a background job (202). Re-uploading identical
    bytes returns the existing document (200)."""
    p.require("policy:write")
    state = request.app.state
    if not state.quota.allow_upload(p.tenant_id):
        raise AppError(429, "RATE_LIMITED", "Too many uploads for this organisation; try again in a minute")
    data = await _read_limited(request, state.settings.max_upload_bytes)
    queued = state.settings.document_processing == "queue"

    def run() -> tuple[dict[str, Any], bool]:
        row, created = docs.upload_document(session, p, state.document_store, data,
                                            request.headers.get("content-type", ""), unquote(x_filename), cid)
        if created and queued:
            docs.request_processing(session, p, row.id, docs.TOPIC_TRANSCRIBE, cid)
        session.commit()
        if created and not queued:
            docs.transcribe_document(session, p, state.document_store, state.document_ai, row.id, cid, state.quota)
            session.commit()
        return docs.document_detail(session, p, row.id), created

    detail, created = await run_in_threadpool(run)
    response.status_code = (202 if queued else 201) if created else 200
    return detail


@router.get("/policy-documents", tags=["policy documents"])
def list_policy_documents(p: PrincipalDep, session: SessionDep) -> list[dict[str, Any]]:
    return docs.list_documents(session, p)


@router.get("/policy-documents/{doc_id}", tags=["policy documents"])
def get_policy_document(doc_id: str, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    return docs.document_detail(session, p, doc_id)


@router.get("/policy-documents/{doc_id}/file", tags=["policy documents"])
def get_policy_document_file(doc_id: str, request: Request, p: PrincipalDep, session: SessionDep) -> Response:
    data, mime, filename = docs.document_file(session, p, request.app.state.document_store, doc_id)
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/policy-documents/{doc_id}/search", tags=["policy documents"])
def search_policy_document(doc_id: str, p: PrincipalDep, session: SessionDep,
                           q: Annotated[str, Query(min_length=2, max_length=200)],
                           limit: Annotated[int, Query(ge=1, le=25)] = 10) -> dict[str, Any]:
    return docs.search_document(session, p, doc_id, q, limit)


@router.post("/policy-documents/{doc_id}/transcribe", tags=["policy documents"])
def transcribe_policy_document(doc_id: str, request: Request, response: Response, p: PrincipalDep,
                               session: SessionDep, cid: CidDep) -> dict[str, Any]:
    state = request.app.state
    if state.settings.document_processing == "queue":
        docs.request_processing(session, p, doc_id, docs.TOPIC_TRANSCRIBE, cid)
        response.status_code = 202
    else:
        docs.transcribe_document(session, p, state.document_store, state.document_ai, doc_id, cid, state.quota)
    session.commit()
    return docs.document_detail(session, p, doc_id)


@router.post("/policy-documents/{doc_id}/extract", tags=["policy documents"])
def extract_policy_draft(doc_id: str, request: Request, response: Response, p: PrincipalDep, session: SessionDep,
                         cid: CidDep) -> dict[str, Any]:
    state = request.app.state
    if state.settings.document_processing == "queue":
        docs.request_processing(session, p, doc_id, docs.TOPIC_EXTRACT, cid)
        session.commit()
        response.status_code = 202
        return docs.document_detail(session, p, doc_id)
    detail = docs.extract_draft(session, p, state.document_ai, doc_id, cid, state.quota)
    session.commit()
    return detail


@router.post("/policy-documents/{doc_id}/policy-drafts", status_code=201, tags=["policy documents"])
def create_policy_draft_from_document(doc_id: str, p: PrincipalDep, session: SessionDep, cid: CidDep,
                                      document: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    """Reviewer-approved draft. Schema-validated and every clause must be grounded in the source pages.
    Creates a DRAFT policy version only; publishing remains a separate authorised action."""
    row = docs.create_draft_from_document(session, p, doc_id, document, cid)
    session.commit()
    return svc.policy_view(row)


@router.get("/audit-events", tags=["audit"])
def audit_events(p: PrincipalDep, session: SessionDep, cursor: str | None = None,
                 limit: Annotated[int, Query(ge=1, le=100)] = 50) -> dict[str, Any]:
    return svc.list_audit(session, p, cursor, limit)

