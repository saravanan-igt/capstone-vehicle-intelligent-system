"""Training pipeline for the eligibility classifier. Used by the notebooks and by `python -m app.ml.train`.
Never imported by the API at startup: the API only loads the saved artefact (app.ml.model)."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from app.ml.features import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES, derive

SEED = 2026
# A wrongly approved loan (default risk, collections) costs the lender far more than a wrongly declined
# applicant (lost margin, customer friction). Assumed 5:1; see docs/EVALUATION.md.
COST_FALSE_APPROVAL = 5.0
COST_FALSE_REJECTION = 1.0
INCOME_ERROR_THRESHOLD = 1_000_000  # monthly income above this is treated as a data-entry error
CATEGORY_MAP = {"salaried": "salaried", "self_employed": "self_employed", "self-employed": "self_employed",
                "self employed": "self_employed", "unemployed": "unemployed", "retired": "retired",
                "student": "student"}


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.drop_duplicates(subset="application_id").copy()
    df["employment_category"] = (df["employment_category"].str.strip().str.lower().map(CATEGORY_MAP)
                                 .fillna("other"))
    df.loc[df["monthly_income"] > INCOME_ERROR_THRESHOLD, "monthly_income"] = np.nan
    rows = [derive(r) for r in df[["monthly_income", "existing_emi", "requested_amount", "down_payment"]]
            .to_dict("records")]
    for key in ("emi_to_income", "loan_to_annual_income", "down_payment_ratio"):
        df[key] = [r[key] for r in rows]
    df["approved"] = (df["loan_status"] == "Approved").astype(int)
    return df


def preprocessor(scale: bool) -> ColumnTransformer:
    numeric = [("impute", SimpleImputer(strategy="median"))] + ([("scale", StandardScaler())] if scale else [])
    return ColumnTransformer([
        ("num", Pipeline(numeric), NUMERIC_FEATURES),
        ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                          ("onehot", OneHotEncoder(handle_unknown="ignore"))]), CATEGORICAL_FEATURES),
    ])


def candidates() -> dict[str, tuple[Pipeline, dict[str, list[Any]]]]:
    """Model name -> (pipeline, small hyper-parameter grid tuned with 5-fold CV)."""
    return {
        "logistic_regression": (Pipeline([("prep", preprocessor(True)),
                                          ("clf", LogisticRegression(max_iter=2000))]),
                                {"clf__C": [0.1, 1.0, 10.0]}),
        "decision_tree": (Pipeline([("prep", preprocessor(False)),
                                    ("clf", DecisionTreeClassifier(random_state=SEED))]),
                          {"clf__max_depth": [4, 6, 8], "clf__min_samples_leaf": [20, 50]}),
        "random_forest": (Pipeline([("prep", preprocessor(False)),
                                    ("clf", RandomForestClassifier(n_estimators=300, random_state=SEED,
                                                                   n_jobs=-1))]),
                          {"clf__max_depth": [8, 14], "clf__min_samples_leaf": [5, 20]}),
        "gradient_boosting": (Pipeline([("prep", preprocessor(False)),
                                        ("clf", HistGradientBoostingClassifier(random_state=SEED))]),
                              {"clf__learning_rate": [0.05, 0.1], "clf__max_depth": [3, 6]}),
    }


def expected_cost(y: np.ndarray, proba: np.ndarray, threshold: float) -> float:
    pred = proba >= threshold
    false_approvals = np.sum(pred & (y == 0))
    false_rejections = np.sum(~pred & (y == 1))
    return float((COST_FALSE_APPROVAL * false_approvals + COST_FALSE_REJECTION * false_rejections) / len(y))


def best_threshold(y: np.ndarray, proba: np.ndarray) -> float:
    grid = np.round(np.arange(0.30, 0.951, 0.01), 2)
    return float(min(grid, key=lambda t: expected_cost(y, proba, t)))


def metrics(y: np.ndarray, proba: np.ndarray, threshold: float) -> dict[str, float]:
    pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {"roc_auc": round(roc_auc_score(y, proba), 4), "pr_auc": round(average_precision_score(y, proba), 4),
            "precision_approved": round(precision_score(y, pred, zero_division=0), 4),
            "recall_approved": round(recall_score(y, pred, zero_division=0), 4),
            "f1": round(f1_score(y, pred, zero_division=0), 4), "brier": round(brier_score_loss(y, proba), 4),
            "false_approval_rate": round(fp / max(1, fp + tn), 4),
            "false_rejection_rate": round(fn / max(1, fn + tp), 4),
            "expected_cost_per_application": round(expected_cost(y, proba, threshold), 4),
            "threshold": threshold, "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)}


def split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray]:
    x_train, x_test, y_train, y_test = train_test_split(df[FEATURES], df["approved"].to_numpy(), test_size=0.2,
                                                        stratify=df["approved"], random_state=SEED)
    return x_train, x_test, y_train, y_test


def compare(x_train: pd.DataFrame, y_train: np.ndarray) -> tuple[pd.DataFrame, dict[str, Pipeline]]:
    """Tunes each candidate with 5-fold CV, then scores out-of-fold probabilities with the cost metric."""
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    rows, fitted = [], {}
    for name, (pipe, grid) in candidates().items():
        search = GridSearchCV(pipe, grid, scoring="roc_auc", cv=cv, n_jobs=-1).fit(x_train, y_train)
        oof = cross_val_predict(search.best_estimator_, x_train, y_train, cv=cv, method="predict_proba")[:, 1]
        threshold = best_threshold(y_train, oof)
        rows.append({"model": name, "best_params": json.dumps(search.best_params_), "cv_roc_auc": search.best_score_,
                     **{f"cv_{k}": v for k, v in metrics(y_train, oof, threshold).items()
                        if k in ("pr_auc", "brier", "expected_cost_per_application", "threshold",
                                 "false_approval_rate", "false_rejection_rate")}})
        fitted[name] = search.best_estimator_
    table = pd.DataFrame(rows).sort_values(["cv_expected_cost_per_application", "cv_roc_auc"],
                                           ascending=[True, False]).reset_index(drop=True)
    return table, fitted


def reference_values(x_train: pd.DataFrame) -> dict[str, Any]:
    ref: dict[str, Any] = {c: float(x_train[c].median()) for c in NUMERIC_FEATURES}
    ref.update({c: str(x_train[c].mode().iloc[0]) for c in CATEGORICAL_FEATURES})
    return ref


def save(model: Pipeline, card: dict[str, Any], models_dir: Path) -> None:
    import joblib

    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / "eligibility_model.joblib"
    joblib.dump(model, path)
    card["artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (models_dir / "model_card.json").write_text(json.dumps(card, indent=2) + "\n", "utf-8")


def train_and_save(raw_csv: Path, processed_csv: Path, models_dir: Path) -> dict[str, Any]:
    raw = pd.read_csv(raw_csv)
    df = clean(raw)
    processed_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(processed_csv, index=False)
    x_train, x_test, y_train, y_test = split(df)
    table, fitted = compare(x_train, y_train)
    chosen = str(table.iloc[0]["model"])
    threshold = float(table.iloc[0]["cv_threshold"])
    model = fitted[chosen]
    test_proba = model.predict_proba(x_test)[:, 1]
    card = {
        "name": "vla-eligibility", "version": datetime.now(timezone.utc).strftime("%Y.%m.%d"),
        "algorithm": chosen, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__, "features": FEATURES, "positive_class": "Approved",
        "decision_threshold": threshold,
        "cost_assumption": {"false_approval": COST_FALSE_APPROVAL, "false_rejection": COST_FALSE_REJECTION},
        "training_data": {"file": raw_csv.name, "sha256": hashlib.sha256(raw_csv.read_bytes()).hexdigest(),
                          "rows_raw": int(len(raw)), "rows_clean": int(len(df)), "train_rows": int(len(x_train)),
                          "test_rows": int(len(x_test)), "approval_rate": round(float(df["approved"].mean()), 4)},
        "comparison_cv": table.round(4).to_dict("records"),
        "test_metrics": metrics(y_test, test_proba, threshold),
        "reference_values": reference_values(x_train),
    }
    save(model, card, models_dir)
    return card
