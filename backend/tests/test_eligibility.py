from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.applicant import ApplicantInput
from app.domain.eligibility import EvaluationResult, select_policy
from app.domain.eligibility import evaluate as engine_evaluate
from app.domain.money import emi, floor_to, monthly_rate_from_nominal_annual, principal_for_emi, round_half_up
from app.domain.policy import PolicyDocument
from tests.conftest import GOOD_APPLICANT, nw_policy


def evaluate(a: ApplicantInput, p: PolicyDocument, approval_probability: float | None = 0.99) -> EvaluationResult:
    """Policy-rule tests assume the credit-risk model approves; its own tests pass explicit scores."""
    return engine_evaluate(a, p, approval_probability)


def applicant(**overrides: Any) -> ApplicantInput:
    return ApplicantInput.model_validate({**GOOD_APPLICANT, **overrides})


def policy_with(mutate: Any) -> PolicyDocument:
    data = nw_policy().model_dump(mode="json")
    mutate(data)
    return PolicyDocument.model_validate(data)


def test_approved_amount_and_emi_are_deterministic() -> None:
    res = evaluate(applicant(), nw_policy())
    assert (res.status, res.outcome) == ("COMPLETED", "APPROVED")
    r = monthly_rate_from_nominal_annual(Decimal("0.0875"))
    expected_capacity = floor_to(principal_for_emi(Decimal("50000"), r, 60), Decimal("1000"))
    assert res.borrowing_capacity == expected_capacity
    assert Decimal("2400000") < expected_capacity < Decimal("2450000")
    assert res.eligible_principal == Decimal("1200000")
    assert res.emi == round_half_up(emi(Decimal("1200000"), r, 60))
    assert res.processing_fee == Decimal("12000.00")
    assert res.flags == []
    assert all(rr.passed for rr in res.rule_results)
    assert "NW-3.1" in res.citations and "NW-3.2" in res.citations


@pytest.mark.parametrize(("score", "ok"), [(650, True), (649, False), (900, True)])
def test_credit_score_boundary(score: int, ok: bool) -> None:
    res = evaluate(applicant(credit_score=score), nw_policy())
    assert (res.outcome == "APPROVED") is ok
    if not ok:
        assert "CREDIT_SCORE_BELOW_MIN" in res.reason_codes
        assert "NW-2.1" in res.citations


@pytest.mark.parametrize(("income", "ok"), [("25000", True), ("24999.99", False)])
def test_income_boundary(income: str, ok: bool) -> None:
    res = evaluate(applicant(income_amount=income, existing_monthly_obligations="0", requested_principal="100000"),
                   nw_policy())
    assert (res.outcome == "APPROVED") is ok


def test_annual_income_is_converted_to_monthly() -> None:
    res = evaluate(applicant(income_amount="1440000", income_frequency="annual"), nw_policy())
    assert res.calculations["qualifying_monthly_income"] == "120000.00"
    assert res.outcome == "APPROVED"


@pytest.mark.parametrize(("months", "ok"), [(12, True), (84, True), (11, False), (85, False)])
def test_tenure_limits(months: int, ok: bool) -> None:
    res = evaluate(applicant(requested_tenure_months=months, requested_principal="200000"), nw_policy())
    assert (res.outcome == "APPROVED") is ok
    if not ok:
        assert res.reason_codes == ["TENURE_OUT_OF_RANGE"]


@pytest.mark.parametrize(("category", "months", "reason"), [
    ("salaried", 5, "EMPLOYMENT_DURATION_BELOW_MIN"),
    ("self_employed", 23, "EMPLOYMENT_DURATION_BELOW_MIN"),
    ("student", 60, "EMPLOYMENT_CATEGORY_INELIGIBLE"),
])
def test_employment_rules(category: str, months: int, reason: str) -> None:
    res = evaluate(applicant(employment_category=category, employment_months=months), nw_policy())
    assert res.outcome == "REJECTED" and reason in res.reason_codes


def test_debt_service_exhausted_rejects_with_citation() -> None:
    res = evaluate(applicant(existing_monthly_obligations="60000"), nw_policy())
    assert res.outcome == "REJECTED"
    assert res.reason_codes == ["DEBT_SERVICE_RATIO_EXCEEDED"]
    assert res.citations == ["NW-3.1"]


def test_limited_by_repayment_capacity() -> None:
    res = evaluate(applicant(income_amount="50000", existing_monthly_obligations="5000",
                             requested_principal="1500000"), nw_policy())
    assert res.outcome == "APPROVED"
    assert res.flags == ["LIMITED_BY_REPAYMENT_CAPACITY"]
    assert res.eligible_principal == res.borrowing_capacity < Decimal("1500000")


def test_limited_by_product_cap() -> None:
    res = evaluate(applicant(income_amount="1000000", requested_principal="6000000"), nw_policy())
    assert res.outcome == "APPROVED"
    assert res.eligible_principal == Decimal("5000000")
    assert res.flags == ["LIMITED_BY_PRODUCT_MAX_PRINCIPAL"]


def test_capacity_below_minimum_principal() -> None:
    res = evaluate(applicant(income_amount="30000", existing_monthly_obligations="14500",
                             requested_tenure_months=12), nw_policy())
    assert res.outcome == "REJECTED"
    assert "REPAYMENT_CAPACITY_BELOW_MIN_PRINCIPAL" in res.reason_codes


def test_missing_inputs_never_produce_a_decision() -> None:
    res = evaluate(ApplicantInput(credit_score=780), nw_policy())
    assert res.status == "INCOMPLETE" and res.outcome is None
    assert "income_amount" in res.missing_fields and "region" in res.missing_fields


def test_unsupported_score_provider_needs_review_not_rejection() -> None:
    res = evaluate(applicant(score_provider="UNKNOWNCO"), nw_policy())
    assert res.status == "NEEDS_REVIEW" and res.outcome is None


def test_currency_mismatch_needs_review() -> None:
    res = evaluate(applicant(currency="USD"), nw_policy())
    assert res.status == "NEEDS_REVIEW" and res.reason_codes == ["POLICY_NOT_APPLICABLE"]


def test_zero_interest_policy() -> None:
    def zero(d: dict[str, Any]) -> None:
        d["rules"]["interest_rate"]["bands"][0]["annual_rate"] = "0"
    res = evaluate(applicant(), policy_with(zero))
    assert res.borrowing_capacity == Decimal("3000000.00")  # available EMI 50,000 x 60 months
    assert res.emi == Decimal("20000.00")


def test_engine_is_reproducible() -> None:
    a, b = evaluate(applicant(), nw_policy()), evaluate(applicant(), nw_policy())
    assert a.to_dict() == b.to_dict()


def test_policy_selection_precedence() -> None:
    base = nw_policy()
    newer = policy_with(lambda d: d.update(version="2026.2", effective_from="2026-11-01"))
    expired = policy_with(lambda d: d.update(version="2025.1", effective_from="2025-01-01",
                                             effective_to="2025-12-31"))
    chosen, issue = select_policy([base, newer, expired], "new-car-fixed", date(2026, 11, 7))
    assert issue is None and chosen is not None and chosen.version == "2026.2"
    chosen, _ = select_policy([base, newer], "new-car-fixed", date(2026, 6, 1))
    assert chosen is not None and chosen.version == "2026.1"
    assert select_policy([expired], "new-car-fixed", date(2026, 6, 1)) == (None, "NO_APPLICABLE_POLICY")
    twin = policy_with(lambda d: d.update(version="2026.1b"))
    assert select_policy([base, twin], "new-car-fixed", date(2026, 6, 1)) == (None, "POLICY_CONFLICT")


def test_policy_schema_rejects_uncited_and_overlapping_rules() -> None:
    with pytest.raises(ValidationError, match="unknown clause"):
        policy_with(lambda d: d["rules"]["income"].update(clause="NW-9.9"))
    with pytest.raises(ValidationError, match="overlap"):
        policy_with(lambda d: d["rules"]["interest_rate"]["bands"][1].update(max_score=760))
    with pytest.raises(ValidationError):
        policy_with(lambda d: d["rules"]["processing_fee"].update(financed=True))


@pytest.mark.parametrize(("loans", "ok"), [(3, True), (4, False)])
def test_active_loans_cap_is_cited(loans: int, ok: bool) -> None:
    res = evaluate(applicant(active_loans=loans), nw_policy())
    assert (res.outcome == "APPROVED") is ok
    if not ok:
        assert res.reason_codes == ["ACTIVE_LOANS_ABOVE_MAX"] and res.citations == ["NW-2.4"]


def test_active_loans_is_required() -> None:
    res = evaluate(applicant(active_loans=None), nw_policy())
    assert res.status == "INCOMPLETE" and "active_loans" in res.missing_fields


@pytest.mark.parametrize(("probability", "outcome"), [(0.83, "APPROVED"), (0.8299, "REJECTED"), (0.2, "REJECTED")])
def test_credit_risk_threshold_is_policy_defined(probability: float, outcome: str) -> None:
    res = evaluate(applicant(), nw_policy(), approval_probability=probability)
    assert res.outcome == outcome
    assert res.calculations["model_approval_probability"] == str(round(probability, 4))
    assert "NW-3.7" in res.citations
    if outcome == "REJECTED":
        assert res.reason_codes == ["CREDIT_RISK_BELOW_THRESHOLD"] and res.eligible_principal == 0


def test_model_cannot_override_a_policy_rejection() -> None:
    res = evaluate(applicant(active_loans=5), nw_policy(), approval_probability=0.999)
    assert res.outcome == "REJECTED" and res.reason_codes == ["ACTIVE_LOANS_ABOVE_MAX"]
    assert "model_approval_probability" not in res.calculations


def test_missing_model_score_needs_review_not_approval() -> None:
    res = evaluate(applicant(), nw_policy(), approval_probability=None)
    assert res.status == "NEEDS_REVIEW" and res.reason_codes == ["CREDIT_RISK_MODEL_UNAVAILABLE"]
    assert res.citations == ["NW-3.7"] and res.outcome is None


def test_policy_without_credit_risk_rule_ignores_model() -> None:
    plain = policy_with(lambda d: d["rules"].update(credit_risk=None))
    assert evaluate(applicant(), plain, approval_probability=None).outcome == "APPROVED"
    assert evaluate(applicant(), plain, approval_probability=0.01).outcome == "APPROVED"
