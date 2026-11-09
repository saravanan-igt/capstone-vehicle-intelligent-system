"""The saved model and vector store are real build artefacts; these tests guard their integrity and behaviour."""

import json
from pathlib import Path

import pytest

from app.config import assets_dir
from app.domain.applicant import ApplicantInput
from app.ml.model import EligibilityModel
from app.rag.chunking import corpus
from app.rag.store import VectorStore
from tests.test_advisor import SCENARIO_APPROVED, SCENARIO_REJECTED

MODELS = assets_dir() / "models"
pytestmark = pytest.mark.skipif(not (MODELS / "eligibility_model.joblib").exists(), reason="model not built")


@pytest.fixture(scope="module")
def model() -> EligibilityModel:
    loaded = EligibilityModel.load(MODELS)
    assert loaded is not None
    return loaded


def test_model_card_documents_selection_and_cost_based_threshold() -> None:
    card = json.loads((MODELS / "model_card.json").read_text("utf-8"))
    assert card["name"] == "vla-eligibility" and len(card["comparison_cv"]) >= 2
    assert card["cost_assumption"]["false_approval"] > card["cost_assumption"]["false_rejection"]
    assert 0.5 <= card["decision_threshold"] < 1 and card["test_metrics"]["roc_auc"] > 0.9


def test_policy_threshold_matches_validated_model() -> None:
    card = json.loads((MODELS / "model_card.json").read_text("utf-8"))
    policy = json.loads((assets_dir() / "data/documents/policy/NW-AUTO-STD-2026.1.json").read_text("utf-8"))
    rule = policy["rules"]["credit_risk"]
    assert rule["model_name"] == card["name"] and float(rule["min_approval_probability"]) == card["decision_threshold"]


def test_brief_scenarios_score_as_expected(model: EligibilityModel) -> None:
    approved = model.score(ApplicantInput.model_validate(SCENARIO_APPROVED))
    rejected = model.score(ApplicantInput.model_validate(SCENARIO_REJECTED))
    assert approved.prediction == "Approved" and approved.probability >= 0.83
    assert rejected.prediction == "Rejected" and rejected.probability < 0.2
    assert {f["feature"] for f in rejected.factors} & {"credit_score", "monthly_income"}


def test_tampered_model_is_refused(tmp_path: Path) -> None:
    (tmp_path / "eligibility_model.joblib").write_bytes(b"not the model")
    (tmp_path / "model_card.json").write_text((MODELS / "model_card.json").read_text("utf-8"), "utf-8")
    assert EligibilityModel.load(tmp_path) is None


def test_vector_store_matches_documents() -> None:
    store = VectorStore.load(assets_dir() / "vectorstore" / "local")
    assert store is not None
    assert store.manifest["corpus_sha256"] == VectorStore.corpus_sha256(corpus(assets_dir())), \
        "documents changed: run `python -m app.rag.ingest`"
    kinds = {c.meta["doc_type"] for c in store.chunks}
    assert kinds == {"policy", "vehicle"}
    assert len({c.meta["model_key"] for c in store.chunks if c.meta["doc_type"] == "vehicle"}) >= 25
