"""Vehicle-specific affordability: LTV, on-road costs, borrower contribution, and down payment."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.domain.eligibility import processing_fee
from app.domain.money import ZERO, emi, floor_to, fmt, monthly_rate_from_nominal_annual, round_half_up
from app.domain.policy import PolicyDocument

AFFORDABLE = "AFFORDABLE"
NOT_AFFORDABLE = "NOT_AFFORDABLE"
UNVERIFIED = "UNVERIFIED"
NOT_ELIGIBLE = "NOT_ELIGIBLE"


@dataclass(frozen=True)
class PriceQuote:
    vehicle_id: str
    category: str
    region: str
    currency: str
    ex_showroom: Decimal
    registration: Decimal | None
    insurance: Decimal | None
    other_charges: Decimal | None
    price_date: date

    @property
    def on_road(self) -> Decimal | None:
        parts = (self.registration, self.insurance, self.other_charges)
        if any(p is None for p in parts):
            return None
        return self.ex_showroom + sum(parts, ZERO)  # type: ignore[arg-type]


@dataclass
class VehicleAssessment:
    vehicle_id: str
    status: str
    reasons: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    values: dict[str, str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"vehicle_id": self.vehicle_id, "status": self.status, "reasons": self.reasons,
                "citations": self.citations, "values": self.values}


def assess_vehicle(
    quote: PriceQuote,
    *,
    policy: PolicyDocument,
    borrowing_capacity: Decimal,
    down_payment: Decimal,
    annual_rate: Decimal,
    tenure_months: int,
    as_of: date,
) -> VehicleAssessment:
    r = policy.rules
    out = VehicleAssessment(vehicle_id=quote.vehicle_id, status=UNVERIFIED)
    out.values = {"price_date": quote.price_date.isoformat(), "region": quote.region, "currency": quote.currency,
                  "ex_showroom": fmt(quote.ex_showroom)}

    if quote.category in r.vehicle.excluded_categories:
        out.status, out.reasons, out.citations = NOT_ELIGIBLE, ["VEHICLE_CATEGORY_EXCLUDED"], [r.vehicle.clause]
        return out
    if quote.currency != policy.currency:
        out.reasons = ["CURRENCY_MISMATCH"]
        return out
    age_days = (as_of - quote.price_date).days
    if age_days > r.vehicle.max_price_age_days:
        out.reasons, out.citations = ["STALE_PRICE"], [r.vehicle.clause]
        out.values["price_age_days"] = str(age_days)
        return out
    on_road = quote.on_road
    if on_road is None:
        out.reasons = ["ON_ROAD_COST_INCOMPLETE"]
        return out

    ltv_limit = floor_to(on_road * r.ltv.max_ratio, r.rounding.principal_step)
    principal = min(borrowing_capacity, ltv_limit)
    contribution = on_road - principal
    fee = processing_fee(principal, r.processing_fee)
    upfront = contribution + fee
    installment = round_half_up(
        emi(principal, monthly_rate_from_nominal_annual(annual_rate), tenure_months), r.rounding.emi_step
    )
    out.values.update({
        "on_road_price": fmt(on_road),
        "ltv_max_ratio": str(r.ltv.max_ratio),
        "ltv_loan_limit": fmt(ltv_limit),
        "borrowing_capacity": fmt(borrowing_capacity),
        "loan_principal": fmt(principal),
        "required_contribution": fmt(contribution),
        "processing_fee": fmt(fee),
        "upfront_cash_required": fmt(upfront),
        "down_payment_available": fmt(down_payment),
        "emi": fmt(installment),
        "tenure_months": str(tenure_months),
    })
    out.citations = [r.ltv.clause, r.principal.clause, r.processing_fee.clause]

    reasons: list[str] = []
    if principal < r.principal.min_amount:
        reasons.append("LOAN_BELOW_MIN_PRINCIPAL")
    if upfront > down_payment:
        reasons.append("DOWN_PAYMENT_SHORTFALL")
        out.values["shortfall"] = fmt(upfront - down_payment)
    out.status = NOT_AFFORDABLE if reasons else AFFORDABLE
    out.reasons = reasons
    return out
