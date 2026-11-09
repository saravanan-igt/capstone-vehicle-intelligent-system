"""The brief's endpoints and scenarios (Capstone brief section 4), model gating, RAG Q&A and no-fit guidance."""

from typing import Any

from fastapi.testclient import TestClient

from app.domain.explanation import ExplanationDraft, ExplanationPoint
from tests.conftest import StubExplainer, StubRiskModel, as_user

ALICE = as_user("u-alice")

# Brief 4.1: income 85,000; score 745; 6 years; EMIs 12,000; 5 years; down payment 1,50,000.
SCENARIO_APPROVED: dict[str, Any] = {
    "income_amount": "85000", "income_frequency": "monthly", "credit_score": 745, "score_provider": "CIBIL",
    "employment_category": "salaried", "employment_months": 72, "existing_monthly_obligations": "12000",
    "active_loans": 1, "requested_principal": "800000", "requested_tenure_months": 60,
    "down_payment_available": "150000", "currency": "INR", "jurisdiction": "IN", "region": "IN-MH",
}
# Brief 4.2: income 22,000; score 580; 1 year; EMIs 9,000 with 2 active loans; 5 years.
SCENARIO_REJECTED: dict[str, Any] = {
    **SCENARIO_APPROVED, "income_amount": "22000", "credit_score": 580, "employment_months": 12,
    "existing_monthly_obligations": "9000", "active_loans": 2, "requested_principal": "300000",
    "down_payment_available": "50000",
}


def predict(client: TestClient, applicant: dict[str, Any]) -> dict[str, Any]:
    res = client.post("/predict", json=applicant, headers=ALICE)
    assert res.status_code == 201, res.text
    return res.json()


def test_health_reports_components(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["model"] == "vla-eligibility@test"
    assert body["knowledge"].startswith("local:")


def test_endpoints_require_authentication(client: TestClient) -> None:
    assert client.post("/predict", json=SCENARIO_APPROVED).status_code == 401
    assert client.post("/vehicles", json={}).status_code == 401


def test_scenario_approved_end_to_end(client: TestClient) -> None:
    pred = predict(client, SCENARIO_APPROVED)
    assert pred["prediction"] == "Approved" and pred["model"]["applied_by_policy"] is True
    assert pred["model"]["prediction"] == "Approved" and pred["model"]["top_factors"]

    amount = client.post("/loan-amount", json={"decision_id": pred["decision_id"]}, headers=ALICE).json()
    assert amount["eligible"] and amount["eligible_principal"] == "800000.00" and amount["tenure_months"] == 60
    assert amount["annual_rate"] == "0.0975" and amount["emi"]
    assert [s["step"] for s in amount["calculation"]][-2:] == ["Eligible principal", "EMI"]
    cited = {c["id"] for c in amount["citations"]}
    assert {"NW-3.1", "NW-3.2", "NW-3.3", "NW-3.7"} <= cited

    shortlist = client.post("/vehicles", json={"decision_id": pred["decision_id"], "sort": "price"},
                            headers=ALICE).json()
    affordable = [i for i in shortlist["items"] if i["assessment"]["status"] == "AFFORDABLE"]
    assert len(affordable) >= 3 and shortlist["guidance"] == []
    assert shortlist["terms"]["sanctioned_amount"] == "800000.00"
    prices = [float(i["assessment"]["values"]["on_road_price"]) for i in affordable]
    assert prices == sorted(prices)
    for item in affordable:
        values = item["assessment"]["values"]
        assert float(values["loan_principal"]) <= 800000 and values["emi"]
        assert float(values["upfront_cash_required"]) <= 150000
    assert all(i["vehicle"]["id"] not in {"ori-hauler-cargo", "ori-ridgeback"} or
               i["assessment"]["status"] == "NOT_ELIGIBLE" for i in shortlist["items"])

    hatchbacks = client.post("/vehicles", json={"decision_id": pred["decision_id"], "body_type": "hatchback",
                                                "sort": "emi"}, headers=ALICE).json()
    assert hatchbacks["items"] and {i["vehicle"]["body_type"] for i in hatchbacks["items"]} == {"hatchback"}

    detail = client.get(f"/vehicles/{affordable[0]['vehicle']['id']}", headers=ALICE).json()
    assert detail["brochure"].startswith("# ") and detail["prices"] and detail["specs"]["features"]
    assert "Warranty" in detail["brochure"]

    explained = client.post("/explain", json={"decision_id": pred["decision_id"]}, headers=ALICE).json()
    assert explained["content"]["outcome"] == "APPROVED" and explained["decision"]["prediction"] == "Approved"
    assert explained["retrieval_index"].startswith("local:")
    assert explained["retrieved_sources"] and all(s["id"].startswith("NW-") for s in explained["retrieved_sources"])


def test_scenario_rejected_names_threshold_and_actual_value(client: TestClient) -> None:
    pred = predict(client, SCENARIO_REJECTED)
    assert pred["prediction"] == "Rejected"
    reasons = {r["code"]: r for r in pred["reasons"]}
    assert {"CREDIT_SCORE_BELOW_MIN", "INCOME_BELOW_MIN"} <= set(reasons)
    score = reasons["CREDIT_SCORE_BELOW_MIN"]
    assert score["observed"] == "580" and score["required"] == ">= 650" and score["clause_id"] == "NW-2.1"
    assert "at least 650" in score["clause_text"] and score["policy_supported"]

    amount = client.post("/loan-amount", json={"decision_id": pred["decision_id"]}, headers=ALICE).json()
    assert amount["eligible"] is False and amount["eligible_principal"] == "0.00"

    explained = client.post("/explain", json={"decision_id": pred["decision_id"]}, headers=ALICE).json()
    points = explained["content"]["points"]
    assert any("580" in p["text"] and "650" in p["text"] and p["citations"] == ["NW-2.1"] for p in points)

    shortlist = client.post("/vehicles", json={"decision_id": pred["decision_id"]}, headers=ALICE).json()
    assert shortlist["eligible"] is False and shortlist["items"] == []
    assert shortlist["guidance"][0]["type"] == "NOT_ELIGIBLE"


def test_model_below_policy_threshold_rejects_with_citation(client: TestClient, risk_model: StubRiskModel) -> None:
    risk_model.probability = 0.41
    pred = predict(client, SCENARIO_APPROVED)
    assert pred["prediction"] == "Rejected" and pred["model"]["prediction"] == "Rejected"
    assert [r["code"] for r in pred["reasons"]] == ["CREDIT_RISK_BELOW_THRESHOLD"]
    assert pred["reasons"][0]["clause_id"] == "NW-3.7" and pred["reasons"][0]["observed"] == "0.41"
    explained = client.post("/explain", json={"decision_id": pred["decision_id"]}, headers=ALICE).json()
    text = " ".join(p["text"] for p in explained["content"]["points"])
    assert "credit score raises the score" in text
    # Retrieval surfaces the manual-review exception tied to clause 3.7.
    assert "NW-5.1" in {s["id"] for s in explained["retrieved_sources"]}


def test_model_never_overrides_policy(client: TestClient, risk_model: StubRiskModel) -> None:
    risk_model.probability = 0.999
    pred = predict(client, {**SCENARIO_APPROVED, "active_loans": 5})
    assert pred["prediction"] == "Rejected" and [r["code"] for r in pred["reasons"]] == ["ACTIVE_LOANS_ABOVE_MAX"]


def test_missing_model_goes_to_manual_review(client: TestClient) -> None:
    client.app.state.eligibility_model = None  # type: ignore[attr-defined]
    pred = predict(client, SCENARIO_APPROVED)
    assert pred["prediction"] == "Needs review" and pred["model"] is None
    assert pred["reasons"][0]["code"] == "CREDIT_RISK_MODEL_UNAVAILABLE"


def test_reasons_without_policy_support_are_labelled(client: TestClient) -> None:
    pred = predict(client, {**SCENARIO_APPROVED, "credit_score": None})
    assert pred["prediction"] == "Incomplete" and "credit_score" in pred["missing_fields"]
    assert pred["reasons"][0]["policy_supported"] is False
    explained = client.post("/explain", json={"decision_id": pred["decision_id"]}, headers=ALICE).json()
    assert any("do not contain a clause" in p["text"] for p in explained["content"]["points"])


def test_replay_reports_model_identity(client: TestClient) -> None:
    pred = predict(client, SCENARIO_APPROVED)
    replay = client.post(f"/v1/decisions/{pred['decision_id']}/replay", headers=ALICE).json()
    assert replay["reproducible"] is True and replay["model_unchanged"] is True


def test_no_fit_guidance_for_supplied_terms(client: TestClient) -> None:
    body = {"sanctioned_amount": "300000", "down_payment": "40000", "tenure_months": 36, "annual_rate": "0.0975"}
    res = client.post("/vehicles", json=body, headers=ALICE).json()
    assert res["basis"] == "supplied_terms"
    assert not [i for i in res["items"] if i["assessment"]["status"] == "AFFORDABLE"]
    kinds = {g["type"] for g in res["guidance"]}
    assert kinds & {"INCREASE_DOWN_PAYMENT", "LOWER_PRICED_VARIANT"}
    assert all(g["text"] for g in res["guidance"])


def test_guidance_suggests_relaxing_filters_and_higher_amount(client: TestClient) -> None:
    pred = predict(client, SCENARIO_APPROVED)
    res = client.post("/vehicles", json={"decision_id": pred["decision_id"], "body_type": "mpv"},
                      headers=ALICE).json()
    assert not [i for i in res["items"] if i["assessment"]["status"] == "AFFORDABLE"]
    kinds = {g["type"] for g in res["guidance"]}
    assert "RELAX_FILTERS" in kinds or "REQUEST_HIGHER_AMOUNT" in kinds


def test_supplied_terms_are_validated_against_policy(client: TestClient) -> None:
    body = {"sanctioned_amount": "500000", "down_payment": "100000", "tenure_months": 96, "annual_rate": "0.0975"}
    res = client.post("/vehicles", json=body, headers=ALICE)
    assert res.status_code == 422 and res.json()["error"]["code"] == "TENURE_OUT_OF_RANGE"
    res = client.post("/vehicles", json={"down_payment": "100000"}, headers=ALICE)
    assert res.status_code == 422 and res.json()["error"]["code"] == "MISSING_TERMS"


def test_vehicle_questions_answered_from_brochure_or_declined(client: TestClient) -> None:
    def ask(question: str) -> dict[str, Any]:
        res = client.post("/vehicles/aur-quest-cng/ask", json={"question": question}, headers=ALICE)
        assert res.status_code == 200, res.text
        return res.json()

    known = ask("What is the ground clearance?")
    assert known["answerable"] and "200" in known["answer"] and known["sources"][0]["section"] == "Dimensions"
    warranty = ask("What warranty does the Aurora Quest come with?")
    assert warranty["answerable"] and "3 years" in warranty["answer"]
    for unknown in ("Does it have a sunroof?", "Who won the cricket world cup?", "Does it support Android Auto?"):
        reply = ask(unknown)
        assert not reply["answerable"] and reply["answer"].startswith("I don't know") and reply["sources"] == []


class FakeAnswerer:
    name = "fake"
    model = "fake"

    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply

    def answer(self, question: str, vehicle: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
        return {**self.reply, "source_ids": [s["id"] for s in sources]}


def test_llm_answers_are_checked_against_sources(client: TestClient) -> None:
    question = {"question": "What is the ground clearance?"}
    client.app.state.answerer = FakeAnswerer({"answerable": True, "answer": "It has 200 mm of ground clearance."})  # type: ignore[attr-defined]
    reply = client.post("/vehicles/aur-quest-cng/ask", json=question, headers=ALICE).json()
    assert reply["mode"] == "ai" and reply["answer"] == "It has 200 mm of ground clearance."
    client.app.state.answerer = FakeAnswerer({"answerable": True, "answer": "It has 245 mm of ground clearance."})  # type: ignore[attr-defined]
    reply = client.post("/vehicles/aur-quest-cng/ask", json=question, headers=ALICE).json()
    assert reply["mode"] == "extractive" and "245" not in reply["answer"]  # invented number rejected
    client.app.state.answerer = FakeAnswerer({"answerable": False, "answer": ""})  # type: ignore[attr-defined]
    reply = client.post("/vehicles/aur-quest-cng/ask", json=question, headers=ALICE).json()
    assert not reply["answerable"] and reply["answer"].startswith("I don't know")


def test_ai_explanation_may_cite_retrieved_clauses_only(client: TestClient, explainer: StubExplainer,
                                                       risk_model: StubRiskModel) -> None:
    risk_model.probability = 0.41
    pred = predict(client, SCENARIO_APPROVED)

    def draft(facts: dict[str, Any], evidence: list[dict[str, Any]]) -> ExplanationDraft:
        ids = {e["clause_id"] for e in evidence}
        assert {"NW-3.7", "NW-5.1"} <= ids
        return ExplanationDraft(outcome="REJECTED", summary="Declined on credit-risk grounds.", points=[
            ExplanationPoint(text="The model score 0.41 is below the policy threshold 0.83.", citations=["NW-3.7"]),
            ExplanationPoint(text="You may request a manual review by a credit officer.", citations=["NW-5.1"])])

    explainer.behaviour = draft
    explained = client.post("/explain", json={"decision_id": pred["decision_id"]}, headers=ALICE).json()
    assert explained["source"] == "ai" and explained["fallback_reason"] is None
