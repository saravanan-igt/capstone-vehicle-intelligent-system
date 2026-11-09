"""Reproducible training: python -m app.ml.train  (writes data/processed/, models/eligibility_model.joblib and
models/model_card.json). Run offline; the API never trains."""

import json

from app.config import assets_dir
from app.ml.pipeline import train_and_save


def main() -> None:
    root = assets_dir()
    card = train_and_save(root / "data" / "raw" / "loan_applications.csv",
                          root / "data" / "processed" / "loan_applications_clean.csv", root / "models")
    print(json.dumps({"algorithm": card["algorithm"], "threshold": card["decision_threshold"],
                      "test": card["test_metrics"]}, indent=2))


if __name__ == "__main__":
    main()
