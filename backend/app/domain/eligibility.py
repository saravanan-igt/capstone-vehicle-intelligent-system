"""Deterministic eligibility and loan-amount engine. Pure: no I/O, no clock, no AI."""

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.domain.applicant import ApplicantInput, missing_fields, qualifying_monthly_income
from app.domain.money import (
    ZERO,
    emi,
    floor_to,
    fmt,
    monthly_rate_from_nominal_annual,
    principal_for_emi,
    round_half_up,
)
from app.domain.policy import CitedRule, FeeRule, PolicyDocument

ENGINE_VERSION = "1.1.0"

STATUS_COMPLETED = "COMPLETED"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
APPROVED = "APPROVED"
REJECTED = "REJECTED"


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    clause_id: str
    passed: bool
    observed: str
    threshold: str
    reason_code: str | None = None


@dataclass
class EvaluationResult:
    status: str
    outcome: str | None = None
    missing_fields: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    rule_results: list[RuleResult] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    calculations: dict[str, str | None] = field(default_factory=dict)
    eligible_principal: Decimal | None = None
    borrowing_capacity: Decimal | None = None
    annual_rate: Decimal | None = None
    tenure_months: int | None = None
    emi: Decimal | None = None
    processing_fee: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("eligible_principal", "borrowing_capacity", "emi", "processing_fee"):
            data[key] = fmt(data[key])
        data["annual_rate"] = None if self.annual_rate is None else str(self.annual_rate)
        return data


def processing_fee(principal: Decimal, rule: FeeRule) -> Decimal:
    raw = round_half_up(principal * rule.rate)
    return min(max(raw, rule.min_amount), rule.max_amount)


def select_policy(candidates: list[PolicyDocument], product: str, on: date) -> tuple[PolicyDocument | None, str | None]:
    """Precedence: effective on `on`, same product, latest effective_from wins; ties are a conflict."""
    effective = [p for p in candidates if p.product == product and p.is_effective_on(on)]
    if not effective:
        return None, "NO_APPLICABLE_POLICY"
    latest = max(p.effective_from for p in effective)
    top = [p for p in effective if p.effective_from == latest]
    if len(top) > 1:
        return None, "POLICY_CONFLICT"
    return top[0], None


class _Trace:
    def __init__(self) -> None:
        self.results: list[RuleResult] = []

    def check(self, rule_id: str, rule: CitedRule, passed: bool, observed: object, threshold: str, reason: str) -> bool:
        self.results.append(
            RuleResult(rule_id, rule.clause, passed, str(observed), threshold, None if passed else reason)
        )
        return passed


def evaluate(applicant: ApplicantInput, policy: PolicyDocument,
             approval_probability: float | None = None) -> EvaluationResult:
    """`approval_probability` is the saved model's score, recorded in the snapshot so replay is exact."""
    missing = missing_fields(applicant)
    if missing:
        return EvaluationResult(status=STATUS_INCOMPLETE, missing_fields=missing, reason_codes=["MISSING_REQUIRED_FIELDS"])

    r = policy.rules
    if applicant.currency != policy.currency or applicant.jurisdiction != policy.jurisdiction:
        return EvaluationResult(status=STATUS_NEEDS_REVIEW, reason_codes=["POLICY_NOT_APPLICABLE"])
    if applicant.score_provider not in r.credit_score.accepted_providers:
        return EvaluationResult(
            status=STATUS_NEEDS_REVIEW,
            reason_codes=["SCORE_PROVIDER_UNSUPPORTED"],
            citations=[r.credit_score.clause],
        )

    # Narrow optionals; presence is guaranteed by missing_fields().
    score = applicant.credit_score
    months = applicant.requested_tenure_months
    requested = applicant.requested_principal
    obligations = applicant.existing_monthly_obligations
    category = applicant.employment_category
    employed_for = applicant.employment_months
    assert score is not None and months is not None and requested is not None
    assert obligations is not None and category is not None and employed_for is not None
    active = applicant.active_loans
    assert active is not None

    income = qualifying_monthly_income(applicant)
    trace = _Trace()
    calcs: dict[str, str | None] = {"qualifying_monthly_income": fmt(income)}

    trace.check("credit_score.min", r.credit_score, score >= r.credit_score.min_score, score,
                f">= {r.credit_score.min_score}", "CREDIT_SCORE_BELOW_MIN")
    trace.check("income.min_monthly", r.income, income >= r.income.min_monthly_income, fmt(income),
                f">= {fmt(r.income.min_monthly_income)}", "INCOME_BELOW_MIN")
    category_ok = trace.check("employment.category", r.employment, category in r.employment.allowed_categories,
                              category, f"in {sorted(r.employment.allowed_categories)}", "EMPLOYMENT_CATEGORY_INELIGIBLE")
    if category_ok:
        required = r.employment.min_months[category]
        trace.check("employment.duration", r.employment, employed_for >= required, f"{employed_for} months",
                    f">= {required} months", "EMPLOYMENT_DURATION_BELOW_MIN")
    if r.active_loans is not None:
        trace.check("active_loans.max", r.active_loans, active <= r.active_loans.max_active_loans, active,
                    f"<= {r.active_loans.max_active_loans}", "ACTIVE_LOANS_ABOVE_MAX")
    tenure_ok = trace.check("tenure.range", r.tenure, r.tenure.min_months <= months <= r.tenure.max_months,
                            f"{months} months", f"{r.tenure.min_months}-{r.tenure.max_months} months",
                            "TENURE_OUT_OF_RANGE")
    trace.check("principal.requested_min", r.principal, requested >= r.principal.min_amount, fmt(requested),
                f">= {fmt(r.principal.min_amount)}", "REQUESTED_PRINCIPAL_BELOW_MIN")
    band = r.interest_rate.band_for(score)
    trace.check("interest_rate.band", r.interest_rate, band is not None, score,
                "; ".join(f"{b.min_score}-{b.max_score}" for b in r.interest_rate.bands), "NO_RATE_BAND")

    capacity: Decimal | None = None
    annual_rate: Decimal | None = None
    monthly_rate: Decimal | None = None
    if band is not None and tenure_ok:
        annual_rate = band.annual_rate
        monthly_rate = monthly_rate_from_nominal_annual(annual_rate)
        max_total_emi = income * r.debt_service.max_ratio
        available_emi = max(ZERO, max_total_emi - obligations)
        calcs.update({
            "annual_rate_nominal": str(annual_rate),
            "monthly_rate": str(round_half_up(monthly_rate, Decimal("0.0000000001"))),
            "tenure_months": str(months),
            "max_debt_service_ratio": str(r.debt_service.max_ratio),
            "max_total_monthly_obligations": fmt(max_total_emi),
            "existing_monthly_obligations": fmt(obligations),
            "available_emi": fmt(available_emi),
        })
        dsr_ok = trace.check("debt_service.available_emi", r.debt_service, available_emi > 0, fmt(available_emi),
                             "> 0.00", "DEBT_SERVICE_RATIO_EXCEEDED")
        if dsr_ok:
            capacity_principal = floor_to(principal_for_emi(available_emi, monthly_rate, months),
                                          r.rounding.principal_step)
            capacity = min(capacity_principal, r.principal.max_amount)
            calcs.update({
                "principal_by_repayment_capacity": fmt(capacity_principal),
                "product_max_principal": fmt(r.principal.max_amount),
                "borrowing_capacity": fmt(capacity),
            })
            trace.check("principal.capacity_min", r.principal, capacity >= r.principal.min_amount, fmt(capacity),
                        f">= {fmt(r.principal.min_amount)}", "REPAYMENT_CAPACITY_BELOW_MIN_PRINCIPAL")

    failed = [x for x in trace.results if not x.passed]
    # The credit-risk rule only applies once every other rule has passed; it can decline, never approve.
    if not failed and r.credit_risk is not None:
        if approval_probability is None:
            return EvaluationResult(status=STATUS_NEEDS_REVIEW, reason_codes=["CREDIT_RISK_MODEL_UNAVAILABLE"],
                                    rule_results=trace.results, citations=[r.credit_risk.clause],
                                    calculations=calcs, borrowing_capacity=capacity, annual_rate=annual_rate,
                                    tenure_months=months)
        probability = Decimal(str(round(approval_probability, 4)))
        calcs["model_approval_probability"] = str(probability)
        trace.check("credit_risk.model", r.credit_risk, probability >= r.credit_risk.min_approval_probability,
                    probability, f">= {r.credit_risk.min_approval_probability}", "CREDIT_RISK_BELOW_THRESHOLD")
        failed = [x for x in trace.results if not x.passed]
    if failed:
        return EvaluationResult(
            status=STATUS_COMPLETED,
            outcome=REJECTED,
            reason_codes=[x.reason_code for x in failed if x.reason_code],
            rule_results=trace.results,
            citations=_unique(x.clause_id for x in failed),
            calculations=calcs,
            eligible_principal=ZERO,
            borrowing_capacity=capacity,
            annual_rate=annual_rate,
            tenure_months=months,
        )

    assert capacity is not None and monthly_rate is not None
    eligible = min(requested, capacity)
    flags: list[str] = []
    if eligible < requested:
        capacity_principal = Decimal(calcs["principal_by_repayment_capacity"] or "0")
        flags.append("LIMITED_BY_REPAYMENT_CAPACITY" if capacity_principal <= r.principal.max_amount
                     else "LIMITED_BY_PRODUCT_MAX_PRINCIPAL")
    installment = round_half_up(emi(eligible, monthly_rate, months), r.rounding.emi_step)
    fee = processing_fee(eligible, r.processing_fee)
    calcs.update({
        "requested_principal": fmt(requested),
        "eligible_principal": fmt(eligible),
        "emi": fmt(installment),
        "processing_fee": fmt(fee),
        "processing_fee_financed": str(r.processing_fee.financed).lower(),
        "total_repayment": fmt(installment * months),
    })
    supporting = [r.interest_rate.clause, r.tenure.clause, r.debt_service.clause, r.principal.clause,
                  r.processing_fee.clause, r.rounding.clause]
    if r.credit_risk is not None:
        supporting.append(r.credit_risk.clause)
    return EvaluationResult(
        status=STATUS_COMPLETED,
        outcome=APPROVED,
        reason_codes=["ALL_ELIGIBILITY_RULES_PASSED"],
        flags=flags,
        rule_results=trace.results,
        citations=_unique(supporting),
        calculations=calcs,
        eligible_principal=eligible,
        borrowing_capacity=capacity,
        annual_rate=annual_rate,
        tenure_months=months,
        emi=installment,
        processing_fee=fee,
    )


def _unique(items: Any) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen
