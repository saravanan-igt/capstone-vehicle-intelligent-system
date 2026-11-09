"""Declarative, versioned lending policy schema. Every executable rule cites a source clause."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EmploymentCategory = Literal["salaried", "self_employed", "unemployed", "retired", "student", "other"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Clause(_Strict):
    id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,31}$")
    section: str
    page: int = Field(ge=1)
    title: str
    text: str = Field(min_length=1, max_length=4000)


class CitedRule(_Strict):
    clause: str


class CreditScoreRule(CitedRule):
    min_score: int = Field(ge=300, le=900)
    accepted_providers: list[str] = Field(min_length=1)


class IncomeRule(CitedRule):
    min_monthly_income: Decimal = Field(ge=0)


class EmploymentRule(CitedRule):
    allowed_categories: list[EmploymentCategory] = Field(min_length=1)
    min_months: dict[EmploymentCategory, int]

    @model_validator(mode="after")
    def _durations_cover_categories(self) -> "EmploymentRule":
        missing = [c for c in self.allowed_categories if c not in self.min_months]
        if missing:
            raise ValueError(f"min_months missing for categories: {missing}")
        return self


class DebtServiceRule(CitedRule):
    max_ratio: Decimal = Field(gt=0, le=1)


class RateBand(_Strict):
    min_score: int = Field(ge=300, le=900)
    max_score: int = Field(ge=300, le=900)
    annual_rate: Decimal = Field(ge=0, le=1)


class InterestRateRule(CitedRule):
    basis: Literal["nominal_annual_monthly_compounding"]
    bands: list[RateBand] = Field(min_length=1)

    @model_validator(mode="after")
    def _bands_do_not_overlap(self) -> "InterestRateRule":
        ordered = sorted(self.bands, key=lambda b: b.min_score)
        for band in ordered:
            if band.min_score > band.max_score:
                raise ValueError("rate band min_score > max_score")
        for left, right in zip(ordered, ordered[1:]):
            if right.min_score <= left.max_score:
                raise ValueError("rate bands overlap")
        return self

    def band_for(self, score: int) -> RateBand | None:
        return next((b for b in self.bands if b.min_score <= score <= b.max_score), None)


class TenureRule(CitedRule):
    min_months: int = Field(ge=1)
    max_months: int = Field(ge=1, le=480)


class PrincipalRule(CitedRule):
    min_amount: Decimal = Field(gt=0)
    max_amount: Decimal = Field(gt=0)


class LtvRule(CitedRule):
    max_ratio: Decimal = Field(gt=0, le=1)
    basis: Literal["on_road_price"]


class FeeRule(CitedRule):
    rate: Decimal = Field(ge=0, le=Decimal("0.1"))
    min_amount: Decimal = Field(ge=0)
    max_amount: Decimal = Field(ge=0)
    # Engine v1 only supports fees paid upfront; financed fees would need capacity/LTV re-solving.
    financed: Literal[False] = False


class VehicleRule(CitedRule):
    excluded_categories: list[str] = Field(default_factory=list)
    max_price_age_days: int = Field(ge=1)


class RoundingRule(CitedRule):
    emi_step: Decimal = Decimal("0.01")
    principal_step: Decimal = Decimal("1000")


class PolicyRules(_Strict):
    credit_score: CreditScoreRule
    income: IncomeRule
    employment: EmploymentRule
    debt_service: DebtServiceRule
    interest_rate: InterestRateRule
    tenure: TenureRule
    principal: PrincipalRule
    ltv: LtvRule
    processing_fee: FeeRule
    vehicle: VehicleRule
    rounding: RoundingRule


class PolicyDocument(_Strict):
    schema_version: Literal["1"] = "1"
    policy_code: str = Field(pattern=r"^[A-Z0-9\-]{3,40}$")
    version: str = Field(pattern=r"^[0-9A-Za-z.\-]{1,20}$")
    lender_name: str
    product: str = Field(pattern=r"^[a-z0-9\-]{3,40}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    jurisdiction: str = Field(pattern=r"^[A-Z]{2}$")
    effective_from: date
    effective_to: date | None = None
    source_document: str
    synthetic: bool = True
    clauses: list[Clause] = Field(min_length=1)
    rules: PolicyRules

    @model_validator(mode="after")
    def _consistency(self) -> "PolicyDocument":
        clause_ids = [c.id for c in self.clauses]
        if len(set(clause_ids)) != len(clause_ids):
            raise ValueError("duplicate clause ids")
        known = set(clause_ids)
        for name in PolicyRules.model_fields:
            rule = getattr(self.rules, name)
            if rule.clause not in known:
                raise ValueError(f"rule '{name}' cites unknown clause '{rule.clause}'")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        r = self.rules
        if r.tenure.min_months > r.tenure.max_months:
            raise ValueError("tenure min exceeds max")
        if r.principal.min_amount > r.principal.max_amount:
            raise ValueError("principal min exceeds max")
        if r.processing_fee.min_amount > r.processing_fee.max_amount:
            raise ValueError("fee min exceeds max")
        return self

    def clause(self, clause_id: str) -> Clause:
        return next(c for c in self.clauses if c.id == clause_id)

    def is_effective_on(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on <= self.effective_to)
