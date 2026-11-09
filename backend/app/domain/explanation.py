"""Explanation contract, deterministic template, and validation of AI-drafted explanations."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

REASON_TEXT = {
    "CREDIT_SCORE_BELOW_MIN": "The credit score is below the policy minimum.",
    "INCOME_BELOW_MIN": "Qualifying monthly income is below the policy minimum.",
    "EMPLOYMENT_CATEGORY_INELIGIBLE": "The employment category is not eligible under this product.",
    "EMPLOYMENT_DURATION_BELOW_MIN": "Employment duration is below the policy minimum for this category.",
    "TENURE_OUT_OF_RANGE": "The requested tenure is outside the permitted range.",
    "REQUESTED_PRINCIPAL_BELOW_MIN": "The requested amount is below the product minimum.",
    "NO_RATE_BAND": "No interest-rate band applies to this credit score.",
    "DEBT_SERVICE_RATIO_EXCEEDED": "Existing obligations already use the maximum permitted share of income.",
    "REPAYMENT_CAPACITY_BELOW_MIN_PRINCIPAL": "Repayment capacity supports less than the product minimum loan.",
    "MISSING_REQUIRED_FIELDS": "Required information is missing, so no decision was made.",
    "POLICY_NOT_APPLICABLE": "No policy applies to the application's currency or jurisdiction.",
    "SCORE_PROVIDER_UNSUPPORTED": "The credit score provider is not accepted by the policy; manual review is needed.",
    "NO_APPLICABLE_POLICY": "No published policy is effective for this product and date.",
    "POLICY_CONFLICT": "Multiple policies conflict for this date; manual review is needed.",
    "ALL_ELIGIBILITY_RULES_PASSED": "All eligibility rules passed.",
    "ACTIVE_LOANS_ABOVE_MAX": "The applicant has more active loans than the policy allows.",
    "CREDIT_RISK_BELOW_THRESHOLD": ("The lender's validated credit-risk model scored the application below the "
                                    "approval threshold set in the policy."),
    "CREDIT_RISK_MODEL_UNAVAILABLE": ("The policy requires a credit-risk model score, but the model was unavailable; "
                                      "a credit officer must review the application."),
}
NOT_IN_POLICY = ("The policy documents do not contain a clause that justifies this; it is reported by the "
                 "system, not decided by the policy.")


class ExplanationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=600)
    citations: list[str] = Field(default_factory=list, max_length=6)


class ExplanationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str
    summary: str = Field(max_length=800)
    points: list[ExplanationPoint] = Field(max_length=12)


def template_explanation(decision: dict[str, Any]) -> ExplanationDraft:
    result = decision["result"]
    policy = decision["policy"]
    outcome = result["outcome"] or result["status"]
    clause_by_id = {c["id"]: c for c in decision.get("clauses", [])}
    points: list[ExplanationPoint] = []
    if result["status"] == "COMPLETED" and result["outcome"] == "APPROVED":
        c = result["calculations"]
        summary = (
            f"Approved under {policy['policy_code']} v{policy['version']}. Indicative eligible principal "
            f"{c['eligible_principal']} {decision['input']['currency']} over {c['tenure_months']} months at a nominal "
            f"annual rate of {c['annual_rate_nominal']}, EMI {c['emi']}."
        )
        points.append(ExplanationPoint(
            text=f"Available EMI {c['available_emi']} = qualifying income {c['qualifying_monthly_income']} x "
                 f"{c['max_debt_service_ratio']} - existing obligations {c['existing_monthly_obligations']}.",
            citations=[_rule_clause(result, "debt_service.available_emi")]))
        points.append(ExplanationPoint(
            text=f"Repayment capacity supports {c['principal_by_repayment_capacity']}; product maximum is "
                 f"{c['product_max_principal']}; requested {c['requested_principal']}.",
            citations=[_rule_clause(result, "principal.capacity_min")]))
        for flag in result["flags"]:
            points.append(ExplanationPoint(text=f"Note: {flag.replace('_', ' ').lower()}.", citations=[]))
        if "model_approval_probability" in c:
            points.append(ExplanationPoint(
                text=f"Credit-risk model approval probability {c['model_approval_probability']} meets the "
                     f"policy threshold." + _factor_text(decision),
                citations=[_rule_clause(result, "credit_risk.model")]))
    else:
        summary = f"Outcome: {outcome}. " + " ".join(REASON_TEXT.get(code, code) for code in result["reason_codes"])
        for rr in result["rule_results"]:
            if not rr["passed"]:
                extra = _factor_text(decision) if rr["rule_id"] == "credit_risk.model" else ""
                points.append(ExplanationPoint(
                    text=f"{REASON_TEXT.get(rr['reason_code'], rr['reason_code'])} Observed {rr['observed']}; "
                         f"required {rr['threshold']}.{extra}",
                    citations=[rr["clause_id"]]))
        if result["missing_fields"]:
            points.append(ExplanationPoint(text="Missing: " + ", ".join(result["missing_fields"]) + ".", citations=[]))
        failed_codes = {rr["reason_code"] for rr in result["rule_results"] if not rr["passed"]}
        for code in result["reason_codes"]:
            if code in failed_codes:
                continue
            cited = [cid for cid in result["citations"] if cid in clause_by_id]
            if cited:
                points.append(ExplanationPoint(text=REASON_TEXT.get(code, code), citations=cited))
            else:
                points.append(ExplanationPoint(text=f"{REASON_TEXT.get(code, code)} {NOT_IN_POLICY}", citations=[]))
    cited_now = {cid for point in points for cid in point.citations} | set(result["citations"])
    for clause in decision.get("clauses", []):
        if clause["id"] not in cited_now and len(points) < 11 and not _is_rule_clause(result, clause["id"]):
            points.append(ExplanationPoint(text=f"Related policy text ({clause.get('title', clause['section'])}): "
                                                f"{clause['text']}", citations=[clause["id"]]))
            cited_now.add(clause["id"])
    for point in points:
        point.citations = [cid for cid in point.citations if cid in clause_by_id]
    return ExplanationDraft(outcome=outcome, summary=summary, points=points)


def _is_rule_clause(result: dict[str, Any], clause_id: str) -> bool:
    return any(r["clause_id"] == clause_id for r in result["rule_results"])


def _rule_clause(result: dict[str, Any], rule_id: str) -> str:
    return next((r["clause_id"] for r in result["rule_results"] if r["rule_id"] == rule_id), "")


def _factor_text(decision: dict[str, Any]) -> str:
    """Names the model's strongest factors without numbers (they are model internals, not policy values)."""
    factors = (decision.get("model") or {}).get("top_factors") or []
    if not factors:
        return ""
    return " Main model factors: " + "; ".join(f"{f['label']} {f['direction']} the score" for f in factors) + "."


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _normalise(num: str) -> str:
    raw = num.replace(",", "")
    return raw.rstrip("0").rstrip(".") if "." in raw else raw


def allowed_numbers(decision: dict[str, Any]) -> set[str]:
    """Every number an explanation may state: decision values, thresholds, clause text and section ids."""
    texts: list[str] = []
    result = decision["result"]
    texts += [str(v) for v in result["calculations"].values() if v is not None]
    for rr in result["rule_results"]:
        texts += [rr["observed"], rr["threshold"]]
    for clause in decision.get("clauses", []):
        texts += [clause["id"], clause["section"], clause["text"]]
    policy = decision.get("policy") or {}
    texts += [str(policy.get("version", "")), str(policy.get("policy_code", ""))]
    allowed = {_normalise(m) for t in texts for m in _NUMBER.findall(t)}
    # Percent forms of rates/ratios, e.g. 0.0875 -> 8.75
    for value in list(allowed):
        try:
            if "." in value and float(value) < 1:
                allowed.add(_normalise(f"{float(value) * 100:.4f}"))
        except ValueError:
            pass
    return allowed


def validate_explanation(draft: ExplanationDraft, decision: dict[str, Any]) -> list[str]:
    """Returns violations; empty list means the draft is consistent with the recorded decision."""
    result = decision["result"]
    expected_outcome = result["outcome"] or result["status"]
    authorised = (set(result["citations"]) | {r["clause_id"] for r in result["rule_results"]} |
                  {c["id"] for c in decision.get("clauses", [])})
    problems: list[str] = []
    if draft.outcome != expected_outcome:
        problems.append(f"outcome '{draft.outcome}' disagrees with recorded '{expected_outcome}'")
    for point in draft.points:
        for cid in point.citations:
            if cid not in authorised:
                problems.append(f"citation '{cid}' is not an authorised clause for this decision")
    allowed = allowed_numbers(decision)
    text = draft.summary + " " + " ".join(p.text for p in draft.points)
    for num in _NUMBER.findall(text):
        if _normalise(num) not in allowed:
            problems.append(f"unsupported number '{num}'")
    return problems
