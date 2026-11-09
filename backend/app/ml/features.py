"""Model features shared by training and inference, so both always compute them identically."""

from decimal import Decimal
from typing import Any

from app.domain.applicant import ApplicantInput, qualifying_monthly_income

NUMERIC_FEATURES = [
    "monthly_income", "credit_score", "employment_months", "existing_emi", "active_loans",
    "requested_amount", "tenure_months", "down_payment", "emi_to_income", "loan_to_annual_income",
    "down_payment_ratio",
]
CATEGORICAL_FEATURES = ["employment_category"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def derive(row: dict[str, Any]) -> dict[str, Any]:
    """Adds ratio features to a raw record with the base fields (monthly_income, existing_emi, ...)."""
    income = float(row["monthly_income"] or 0)
    requested = float(row["requested_amount"] or 0)
    down = float(row["down_payment"] or 0)
    row["emi_to_income"] = float(row["existing_emi"] or 0) / income if income > 0 else None
    row["loan_to_annual_income"] = requested / (income * 12) if income > 0 else None
    row["down_payment_ratio"] = down / (down + requested) if (down + requested) > 0 else None
    return row


def from_applicant(applicant: ApplicantInput) -> dict[str, Any]:
    assert applicant.income_amount is not None
    return derive({
        "monthly_income": float(qualifying_monthly_income(applicant)),
        "credit_score": applicant.credit_score,
        "employment_months": applicant.employment_months,
        "employment_category": applicant.employment_category,
        "existing_emi": float(applicant.existing_monthly_obligations or Decimal(0)),
        "active_loans": applicant.active_loans,
        "requested_amount": float(applicant.requested_principal or Decimal(0)),
        "tenure_months": applicant.requested_tenure_months,
        "down_payment": float(applicant.down_payment_available or Decimal(0)),
    })
