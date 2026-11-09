"""The brief's endpoints (/predict, /loan-amount, /vehicles, /vehicles/{id}, /explain, /health).
Same authentication, tenancy and audit as /v1; thin wrappers over the application layer."""

from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import correlation_id, get_principal, get_session
from app.application import advisor
from app.application import services as svc
from app.application.errors import unprocessable
from app.application.security import Principal
from app.domain.applicant import ApplicantInput
from app.infrastructure.observability import EXPLANATIONS

router = APIRouter(tags=["advisor"])
SessionDep = Annotated[Session, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]
CidDep = Annotated[str | None, Depends(correlation_id)]
Money = Annotated[Decimal, Field(ge=0, le=Decimal("100000000"), max_digits=12, decimal_places=2)]


class LoanAmountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: str | None = Field(default=None, max_length=32)
    applicant: ApplicantInput | None = None


class VehicleSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: str | None = Field(default=None, max_length=32)
    sanctioned_amount: Money | None = None
    down_payment: Money | None = None
    tenure_months: int | None = Field(default=None, ge=1, le=120)
    annual_rate: Decimal | None = Field(default=None, gt=0, lt=1, description="Nominal annual rate, e.g. 0.0975")
    region: str = Field(default="IN-MH", pattern=r"^[A-Z]{2}-[A-Z0-9]{1,3}$")
    body_type: str | None = Field(default=None, max_length=32)
    fuel_type: str | None = Field(default=None, max_length=32)
    make: str | None = Field(default=None, max_length=64)
    min_seating: int | None = Field(default=None, ge=1, le=12)
    min_price: Money | None = None
    max_price: Money | None = None
    max_emi: Money | None = None
    sort: Literal["best_fit", "price", "emi"] = "best_fit"
    limit: int = Field(default=50, ge=1, le=100)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=500)


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: str = Field(max_length=32)
    refresh: bool = False


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    state = request.app.state
    model = state.eligibility_model
    return {"status": "ok", "model": f"{model.card['name']}@{model.card['version']}" if model else None,
            "knowledge": state.knowledge.name if state.knowledge else None, "llm": state.explainer.name}


@router.post("/predict", status_code=201)
def predict(body: ApplicantInput, request: Request, p: PrincipalDep, session: SessionDep,
            cid: CidDep) -> dict[str, Any]:
    decision = advisor.predict(session, p, body, request.app.state.today(), cid, request.app.state.eligibility_model)
    session.commit()
    return advisor.predict_view(decision)


@router.post("/loan-amount")
def loan_amount(body: LoanAmountRequest, request: Request, p: PrincipalDep, session: SessionDep,
                cid: CidDep) -> dict[str, Any]:
    if (body.decision_id is None) == (body.applicant is None):
        raise unprocessable("DECISION_OR_APPLICANT", "Provide exactly one of decision_id or applicant")
    if body.applicant is not None:
        decision = advisor.predict(session, p, body.applicant, request.app.state.today(), cid,
                                   request.app.state.eligibility_model)
        session.commit()
    else:
        assert body.decision_id is not None
        decision = svc.get_decision(session, p, body.decision_id)
    return advisor.loan_amount_view(decision)


@router.post("/vehicles")
def vehicles(body: VehicleSearch, request: Request, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    filters = advisor.Filters(body.body_type, body.fuel_type, body.make, body.min_seating, body.min_price,
                              body.max_price, body.max_emi)
    return advisor.recommend_vehicles(session, p, request.app.state.today(), decision_id=body.decision_id,
                                      sanctioned_amount=body.sanctioned_amount, down_payment=body.down_payment,
                                      tenure_months=body.tenure_months, annual_rate=body.annual_rate,
                                      region=body.region, filters=filters, sort=body.sort, limit=body.limit)


@router.get("/vehicles/{vehicle_id}")
def vehicle(vehicle_id: str, p: PrincipalDep, session: SessionDep) -> dict[str, Any]:
    return advisor.vehicle_detail(session, p, vehicle_id)


@router.post("/vehicles/{vehicle_id}/ask")
def ask(vehicle_id: str, body: Question, request: Request, p: PrincipalDep, session: SessionDep,
        cid: CidDep) -> dict[str, Any]:
    state = request.app.state
    result = advisor.ask_vehicle(session, p, vehicle_id, body.question, state.knowledge, state.answerer, state.quota,
                                 cid)
    session.commit()
    return result


@router.post("/explain")
def explain(body: ExplainRequest, request: Request, p: PrincipalDep, session: SessionDep,
            cid: CidDep) -> dict[str, Any]:
    state = request.app.state
    result = svc.explain_decision(session, p, body.decision_id, state.explainer, body.refresh, cid, state.quota,
                                  state.knowledge)
    session.commit()
    EXPLANATIONS.labels(result["source"]).inc()
    decision = svc.get_decision(session, p, body.decision_id)
    return {**result, "decision": advisor.predict_view(decision)}
