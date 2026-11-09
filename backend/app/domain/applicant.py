"""Applicant input. Only lending-relevant fields are collected; all are optional so drafts can be saved."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.policy import EmploymentCategory

FuelType = Literal["petrol", "diesel", "cng", "hybrid", "electric"]
BodyType = Literal["hatchback", "sedan", "suv", "mpv", "coupe", "van"]

Money = Decimal

REQUIRED_FIELDS: tuple[str, ...] = (
    "income_amount",
    "income_frequency",
    "credit_score",
    "score_provider",
    "employment_category",
    "employment_months",
    "existing_monthly_obligations",
    "requested_principal",
    "requested_tenure_months",
    "down_payment_available",
    "currency",
    "jurisdiction",
    "region",
)


class ApplicantInput(BaseModel):
    """Units: money in `currency` major units; durations in months; income per `income_frequency`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    income_amount: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    income_frequency: Literal["monthly", "annual"] | None = None
    credit_score: int | None = Field(default=None, ge=300, le=900)
    score_provider: str | None = Field(default=None, min_length=2, max_length=32)
    employment_category: EmploymentCategory | None = None
    employment_months: int | None = Field(default=None, ge=0, le=720)
    existing_monthly_obligations: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    requested_principal: Money | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    requested_tenure_months: int | None = Field(default=None, ge=1, le=480)
    down_payment_available: Money | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    jurisdiction: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    region: str | None = Field(default=None, pattern=r"^[A-Z]{2}-[A-Z0-9]{1,3}$")
    preferred_body_types: list[BodyType] = Field(default_factory=list, max_length=6)
    preferred_fuel_types: list[FuelType] = Field(default_factory=list, max_length=5)


def missing_fields(applicant: ApplicantInput) -> list[str]:
    return [name for name in REQUIRED_FIELDS if getattr(applicant, name) is None]


def qualifying_monthly_income(applicant: ApplicantInput) -> Decimal:
    assert applicant.income_amount is not None
    if applicant.income_frequency == "annual":
        return applicant.income_amount / Decimal(12)
    return applicant.income_amount
