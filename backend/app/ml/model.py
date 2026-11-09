"""Loads the saved eligibility model (never trains) and scores applicants with per-feature attributions."""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.domain.applicant import ApplicantInput
from app.ml.features import FEATURES, from_applicant

log = logging.getLogger(__name__)
FEATURE_LABELS = {
    "monthly_income": "monthly income", "credit_score": "credit score", "employment_months": "employment length",
    "existing_emi": "existing EMIs", "active_loans": "number of active loans", "requested_amount": "requested amount",
    "tenure_months": "tenure", "down_payment": "down payment", "emi_to_income": "existing EMI to income ratio",
    "loan_to_annual_income": "loan to annual income ratio", "down_payment_ratio": "down payment share",
    "employment_category": "employment category",
}


@dataclass(frozen=True)
class RiskScore:
    probability: float
    prediction: str
    threshold: float
    model_version: str
    algorithm: str
    artifact_sha256: str
    factors: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"approval_probability": round(self.probability, 4), "prediction": self.prediction,
                "model_threshold": self.threshold, "model_version": self.model_version, "algorithm": self.algorithm,
                "artifact_sha256": self.artifact_sha256, "top_factors": self.factors}


class RiskModel(Protocol):
    card: dict[str, Any]

    def score(self, applicant: ApplicantInput, top: int = 4) -> RiskScore: ...


class EligibilityModel:
    def __init__(self, pipeline: Any, card: dict[str, Any]) -> None:
        self._pipeline = pipeline
        self.card = card

    @classmethod
    def load(cls, models_dir: Path) -> "EligibilityModel | None":
        path, card_path = models_dir / "eligibility_model.joblib", models_dir / "model_card.json"
        if not path.exists() or not card_path.exists():
            log.warning("eligibility model not found in %s; decisions requiring it go to manual review", models_dir)
            return None
        card = json.loads(card_path.read_text("utf-8"))
        if hashlib.sha256(path.read_bytes()).hexdigest() != card.get("artifact_sha256"):
            log.error("eligibility model hash does not match its model card; refusing to load")
            return None
        import joblib
        import pandas as pd

        model = cls(joblib.load(path), card)
        model._frame = pd.DataFrame  # type: ignore[attr-defined]
        return model

    def _proba(self, rows: list[dict[str, Any]]) -> list[float]:
        frame = self._frame(rows, columns=FEATURES)  # type: ignore[attr-defined]
        return [float(p) for p in self._pipeline.predict_proba(frame)[:, 1]]

    def score(self, applicant: ApplicantInput, top: int = 4) -> RiskScore:
        row = from_applicant(applicant)
        base = self._proba([row])[0]
        reference = self.card["reference_values"]
        # Attribution: change in probability when one input is replaced by the training median (or mode).
        variants = [{**row, feature: reference[feature]} for feature in FEATURES]
        deltas = [base - p for p in self._proba(variants)]
        factors = sorted(({"feature": f, "label": FEATURE_LABELS[f], "value": row[f], "typical_value": reference[f],
                           "effect": round(d, 4), "direction": "raises" if d > 0 else "lowers"}
                          for f, d in zip(FEATURES, deltas) if abs(d) >= 0.005),
                         key=lambda x: abs(x["effect"]), reverse=True)[:top]
        threshold = float(self.card["decision_threshold"])
        return RiskScore(probability=base, prediction="Approved" if base >= threshold else "Rejected",
                         threshold=threshold, model_version=str(self.card["version"]),
                         algorithm=str(self.card["algorithm"]), artifact_sha256=str(self.card["artifact_sha256"]),
                         factors=factors)
