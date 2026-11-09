"""Generates the SYNTHETIC historical vehicle-loan dataset (data/raw/loan_applications.csv).

    python data/generate_loans.py [--rows 12000] [--seed 2026]

No real customer data is used. Each row is a past application with the underwriting outcome (`loan_status`).
Historical underwriting is simulated as: (1) policy-style knock-outs, which mirror the current lending policy so
the model and the policy do not contradict each other, plus (2) a risk-based judgement on the remaining
applications. Realistic defects are injected on purpose for the EDA notebook: missing values, income outliers,
inconsistent category labels, duplicate submissions and a small share of historical exceptions (label noise)."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "raw" / "loan_applications.csv"
CATEGORIES = ["salaried", "self_employed", "unemployed", "retired", "student"]
CATEGORY_P = [0.68, 0.24, 0.03, 0.03, 0.02]


def generate(rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    category = rng.choice(CATEGORIES, size=rows, p=CATEGORY_P)
    income = np.round(np.exp(rng.normal(np.log(55_000), 0.55, rows)), -2)
    income = np.where(category == "student", income * 0.35, income)
    score = np.clip(np.round(rng.normal(705, 72, rows)), 300, 900).astype(int)
    months = np.where(category == "self_employed", rng.gamma(2.2, 30, rows), rng.gamma(1.6, 28, rows))
    months = np.clip(np.round(months), 0, 480).astype(int)
    months = np.where(np.isin(category, ["unemployed", "student"]), 0, months)
    active = np.clip(rng.poisson(1.1, rows), 0, 7)
    emi_share = np.clip(rng.beta(2, 7, rows) * (0.4 + 0.25 * active), 0, 0.95)
    existing_emi = np.round(np.where(active == 0, 0, income * emi_share), -2)
    requested = np.round(income * 12 * rng.uniform(0.4, 2.6, rows), -4)
    requested = np.clip(requested, 100_000, 6_000_000)
    tenure = rng.choice([24, 36, 48, 60, 72, 84], size=rows, p=[0.05, 0.15, 0.2, 0.35, 0.15, 0.1])
    down = np.round(requested * rng.uniform(0.0, 0.5, rows), -3)
    bureau = rng.choice(["CIBIL", "EXPERIAN", "EQUIFAX"], size=rows, p=[0.7, 0.22, 0.08])
    vehicle = rng.choice(["hatchback", "sedan", "suv", "mpv", "ev"], size=rows, p=[0.34, 0.2, 0.32, 0.06, 0.08])
    region = rng.choice(["IN-MH", "IN-KA", "IN-DL", "IN-TN"], size=rows, p=[0.35, 0.25, 0.25, 0.15])
    dates = pd.Timestamp("2021-01-01") + pd.to_timedelta(rng.integers(0, 5 * 365, rows), unit="D")

    emi_to_income = existing_emi / income
    lti = requested / (income * 12)
    dp_ratio = down / (down + requested)
    knockout = (
        (score < 650) | (income < 25_000) | ~np.isin(category, ["salaried", "self_employed"])
        | ((category == "salaried") & (months < 6)) | ((category == "self_employed") & (months < 24))
        | (active > 3) | (emi_to_income >= 0.5)
    )
    logit = (3.2 + 0.02 * (score - 700) - 7.0 * emi_to_income - 0.5 * active + 0.01 * np.minimum(months, 120)
             - 0.9 * np.maximum(0, lti - 1.5) + 2.0 * dp_ratio - 0.4 * (category == "self_employed")
             + rng.normal(0, 0.9, rows))
    approved = ~knockout & (rng.uniform(size=rows) < 1 / (1 + np.exp(-logit)))
    exceptions = knockout & (rng.uniform(size=rows) < 0.02)  # historical manual overrides
    approved = approved | exceptions

    df = pd.DataFrame({
        "application_id": [f"HIST-{i:06d}" for i in range(rows)],
        "application_date": dates.strftime("%Y-%m-%d"),
        "monthly_income": income, "credit_score": score.astype(float), "score_bureau": bureau,
        "employment_category": category, "employment_months": months.astype(float),
        "existing_emi": existing_emi, "active_loans": active, "requested_amount": requested,
        "tenure_months": tenure, "down_payment": down, "vehicle_type": vehicle, "region": region,
        "loan_status": np.where(approved, "Approved", "Rejected"),
    })

    def pick(frac: float) -> np.ndarray:
        return rng.uniform(size=rows) < frac

    df.loc[pick(0.025), "credit_score"] = np.nan  # thin-file applicants
    df.loc[pick(0.03), "employment_months"] = np.nan
    df.loc[pick(0.015), "down_payment"] = np.nan
    outliers = pick(0.004)
    df.loc[outliers, "monthly_income"] = df.loc[outliers, "monthly_income"] * 25  # data-entry errors
    variants = {"salaried": ["Salaried", "SALARIED", "salaried "], "self_employed": ["Self-Employed", "self employed"]}
    for canonical, spellings in variants.items():
        mask = (df["employment_category"] == canonical) & pick(0.04)
        df.loc[mask, "employment_category"] = rng.choice(spellings, size=int(mask.sum()))
    duplicates = df.sample(frac=0.01, random_state=seed)
    return pd.concat([df, duplicates], ignore_index=True).sample(frac=1, random_state=seed).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=12_000)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    df = generate(args.rows, args.seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {len(df)} rows to {OUT} (approval rate {(df['loan_status'] == 'Approved').mean():.1%})")


if __name__ == "__main__":
    main()
