"""End-to-end API scenarios (synthetic data) covering the capstone acceptance criteria."""

from typing import Any

from fastapi.testclient import TestClient

from app.domain.explanation import ExplanationDraft, ExplanationPoint
from tests.conftest import GOOD_APPLICANT, POLICY_DIR, StubExplainer, as_user

ALICE, ARJUN, OMAR, PRIYA, BEN, LENA = (as_user(u) for u in
                                        ("u-alice", "u-arjun", "u-omar", "u-priya", "u-ben", "u-lena"))


def submit(client: TestClient, headers: dict[str, str], **overrides: Any) -> tuple[str, dict[str, Any]]:
    created = client.post("/v1/applications", json={**GOOD_APPLICANT, **overrides}, headers=headers)
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]
    decided = client.post(f"/v1/applications/{app_id}/evaluate", headers=headers)
    assert decided.status_code == 201, decided.text
    return app_id, decided.json()


def test_1_approved_with_affordable_vehicles(client: TestClient) -> None:
    _, d = submit(client, ALICE)
    assert d["status"] == "COMPLETED" and d["outcome"] == "APPROVED"
    assert d["eligible_principal"] == "1200000.00"
    snap = d["snapshot"]
    assert snap["policy"]["policy_code"] == "NW-AUTO-STD" and snap["engine_version"] == "1.1.0"
    assert snap["input_provenance"]["verified"] is False
    vehicles = client.get(f"/v1/decisions/{d['id']}/vehicles", headers=ALICE).json()
    statuses = {i["vehicle"]["id"]: i["assessment"]["status"] for i in vehicles["items"]}
    assert statuses["kes-trail-s"] == "AFFORDABLE"
    assert statuses["lum-pulse"] == "UNVERIFIED"  # insurance missing
    assert statuses["lum-pulse-turbo"] == "UNVERIFIED"  # stale price
    assert statuses["ori-hauler-cargo"] == "NOT_ELIGIBLE"
    assert statuses["zep-coupe"] == "NOT_AFFORDABLE"
    only = client.get(f"/v1/decisions/{d['id']}/vehicles?status=AFFORDABLE&body_type=suv", headers=ALICE).json()
    assert only["items"] and all(i["vehicle"]["body_type"] == "suv" for i in only["items"])


def test_2_rejection_cites_policy_text(client: TestClient) -> None:
    _, d = submit(client, ALICE, credit_score=600)
    assert d["outcome"] == "REJECTED"
    result = d["snapshot"]["result"]
    assert "CREDIT_SCORE_BELOW_MIN" in result["reason_codes"]
    clause = next(c for c in d["snapshot"]["clauses"] if c["id"] == "NW-2.1")
    assert "at least 650" in clause["text"] and clause["page"] == 1
    assert client.get(f"/v1/decisions/{d['id']}/vehicles", headers=ALICE).status_code == 409


def test_3_approval_limited_by_repayment_capacity(client: TestClient) -> None:
    _, d = submit(client, ALICE, income_amount="50000", existing_monthly_obligations="5000",
                  requested_principal="1500000")
    result = d["snapshot"]["result"]
    assert d["outcome"] == "APPROVED" and result["flags"] == ["LIMITED_BY_REPAYMENT_CAPACITY"]
    assert float(d["eligible_principal"]) < 1500000


def test_4_approval_with_no_affordable_vehicles(client: TestClient) -> None:
    _, d = submit(client, ALICE, down_payment_available="0")
    assert d["outcome"] == "APPROVED"
    vehicles = client.get(f"/v1/decisions/{d['id']}/vehicles", headers=ALICE).json()
    assert vehicles["counts"].get("AFFORDABLE", 0) == 0


def test_5_incomplete_application_has_no_decision_outcome(client: TestClient) -> None:
    created = client.post("/v1/applications", json={"credit_score": 780, "currency": "INR"}, headers=ALICE)
    app_id = created.json()["id"]
    d = client.post(f"/v1/applications/{app_id}/evaluate", headers=ALICE).json()
    assert d["status"] == "INCOMPLETE" and d["outcome"] is None
    assert "income_amount" in d["snapshot"]["result"]["missing_fields"]
    assert client.get(f"/v1/applications/{app_id}", headers=ALICE).json()["status"] == "INCOMPLETE"


def test_6_ai_outage_keeps_deterministic_results(client: TestClient, explainer: StubExplainer) -> None:
    _, d = submit(client, ALICE)
    e = client.post(f"/v1/decisions/{d['id']}/explanation", headers=ALICE).json()
    assert e["source"] == "template" and "stub outage" in e["fallback_reason"]
    assert e["content"]["outcome"] == "APPROVED" and "1200000.00" in e["content"]["summary"]
    assert client.get(f"/v1/decisions/{d['id']}", headers=ALICE).json()["outcome"] == "APPROVED"


def test_6b_ai_claims_are_validated(client: TestClient, explainer: StubExplainer) -> None:
    _, d = submit(client, ALICE, credit_score=600)

    def lying(facts: dict[str, Any], evidence: list[dict[str, Any]]) -> ExplanationDraft:
        # Simulates a model that followed an injected instruction in policy text.
        return ExplanationDraft(outcome="APPROVED", summary="Approved for 9999999.",
                                points=[ExplanationPoint(text="See clause", citations=["SB-B1"])])

    explainer.behaviour = lying
    e = client.post(f"/v1/decisions/{d['id']}/explanation", headers=ALICE).json()
    assert e["source"] == "template"
    assert "disagrees" in e["fallback_reason"]
    assert e["content"]["outcome"] == "REJECTED"

    def faithful(facts: dict[str, Any], evidence: list[dict[str, Any]]) -> ExplanationDraft:
        assert "u-alice" not in str(facts)  # identity is not sent to the model
        return ExplanationDraft(outcome=facts["outcome"], summary="The credit score of 600 is below 650.",
                                points=[ExplanationPoint(text="Minimum score rule.", citations=["NW-2.1"])])

    explainer.behaviour = faithful
    e2 = client.post(f"/v1/decisions/{d['id']}/explanation?refresh=true", headers=ALICE).json()
    assert e2["source"] == "ai" and e2["fallback_reason"] is None


def test_7_cross_tenant_and_object_level_access_denied(client: TestClient) -> None:
    app_id, d = submit(client, ALICE)
    for headers in (BEN, LENA, ARJUN):
        assert client.get(f"/v1/applications/{app_id}", headers=headers).status_code == 404
        assert client.get(f"/v1/decisions/{d['id']}", headers=headers).status_code == 404
        assert client.get(f"/v1/decisions/{d['id']}/vehicles", headers=headers).status_code == 404
        assert client.post(f"/v1/decisions/{d['id']}/explanation", headers=headers).status_code == 404
    assert client.get("/v1/applications", headers=as_user("u-ben", "t-northwind")).status_code == 403
    assert client.get(f"/v1/applications/{app_id}", headers=OMAR).status_code == 200
    assert all(a["id"] != app_id for a in client.get("/v1/applications", headers=LENA).json()["items"])
    assert client.get("/v1/applications", headers={"X-Dev-User": "u-alice"}).status_code == 401


def test_8_policy_update_keeps_history_reproducible(client: TestClient) -> None:
    _, old = submit(client, ALICE)
    doc = __import__("json").loads((POLICY_DIR / "NW-AUTO-STD-2026.1.json").read_text("utf-8"))
    doc.update(version="2026.2", effective_from="2026-11-01")
    doc["rules"]["credit_score"]["min_score"] = 800
    doc["rules"]["interest_rate"]["bands"] = [{"min_score": 800, "max_score": 900, "annual_rate": "0.085"}]
    doc["clauses"][1]["text"] = "Applicants must have a credit score of at least 800 from CIBIL or EXPERIAN."

    assert client.post("/v1/policies", json=doc, headers=ALICE).status_code == 403
    draft = client.post("/v1/policies", json=doc, headers=PRIYA)
    assert draft.status_code == 201 and draft.json()["status"] == "DRAFT"
    _, still_old = submit(client, ALICE)
    assert still_old["outcome"] == "APPROVED"  # drafts never affect decisions
    published = client.post(f"/v1/policies/{draft.json()['id']}/publish", headers=PRIYA)
    assert published.status_code == 200 and published.json()["status"] == "PUBLISHED"
    assert client.post(f"/v1/policies/{draft.json()['id']}/publish", headers=PRIYA).status_code == 409

    _, new = submit(client, ALICE)
    assert new["outcome"] == "REJECTED" and new["snapshot"]["policy"]["version"] == "2026.2"
    replay = client.post(f"/v1/decisions/{old['id']}/replay", headers=ALICE).json()
    assert replay["reproducible"] is True and replay["policy_unchanged"] is True
    audit = client.get("/v1/audit-events", headers=PRIYA).json()["items"]
    assert {"policy.published", "policy.draft_created"} <= {e["action"] for e in audit}


def test_invalid_policy_is_rejected_with_details(client: TestClient) -> None:
    r = client.post("/v1/policies", json={"policy_code": "X"}, headers=PRIYA)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_POLICY"


def test_idempotent_evaluation(client: TestClient) -> None:
    app_id = client.post("/v1/applications", json=GOOD_APPLICANT, headers=ALICE).json()["id"]
    key = {**ALICE, "Idempotency-Key": "eval-key-0001"}
    first = client.post(f"/v1/applications/{app_id}/evaluate", headers=key)
    second = client.post(f"/v1/applications/{app_id}/evaluate", headers=key)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    other = client.post("/v1/applications", json=GOOD_APPLICANT, headers=ALICE).json()["id"]
    assert client.post(f"/v1/applications/{other}/evaluate", headers=key).status_code == 409


def test_optimistic_concurrency_on_update(client: TestClient) -> None:
    created = client.post("/v1/applications", json={"credit_score": 700}, headers=ALICE).json()
    ok = client.patch(f"/v1/applications/{created['id']}", json=GOOD_APPLICANT,
                      headers={**ALICE, "If-Match": "1"})
    assert ok.status_code == 200 and ok.json()["row_version"] == 2
    stale = client.patch(f"/v1/applications/{created['id']}", json=GOOD_APPLICANT,
                         headers={**ALICE, "If-Match": "1"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_validation_errors_are_consistent(client: TestClient) -> None:
    r = client.post("/v1/applications", json={"credit_score": 1200, "religion": "x"}, headers=ALICE)
    body = r.json()
    assert r.status_code == 422 and body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["correlation_id"] == r.headers["X-Correlation-Id"]


def test_pagination_and_dashboard(client: TestClient) -> None:
    for _ in range(3):
        submit(client, ALICE)
    page1 = client.get("/v1/applications?limit=2", headers=OMAR).json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    page2 = client.get(f"/v1/applications?limit=2&cursor={page1['next_cursor']}", headers=OMAR).json()
    ids = {a["id"] for a in page1["items"]} | {a["id"] for a in page2["items"]}
    assert len(ids) == 3
    dash = client.get("/v1/dashboard", headers=OMAR).json()
    assert dash["approved"] == 3 and dash["vehicles_in_catalogue"] == 38
    assert client.get("/v1/dashboard", headers=BEN).json()["applications_total"] == 0


def test_southbay_tenant_uses_its_own_policy(client: TestClient) -> None:
    _, d = submit(client, BEN, score_provider="EXPERIAN")
    assert d["status"] == "NEEDS_REVIEW"  # Southbay accepts CIBIL only
    _, d2 = submit(client, BEN)
    assert d2["snapshot"]["policy"]["policy_code"] == "SB-AUTO-PRIME" and d2["outcome"] == "APPROVED"
