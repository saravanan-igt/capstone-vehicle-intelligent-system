# Data, documents and provenance

Everything in this repository is **synthetic**. No real applicant, lender or vehicle data is used. All generators are seeded, so running them again produces identical output.

| Asset                                                  | Path                                                        | Produced by                                                  | Used by                                         |
| ------------------------------------------------------ | ----------------------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------- |
| Historical loan applications (raw)                     | `data/raw/loan_applications.csv`                            | `python data/generate_loans.py`                              | Notebooks, `python -m app.ml.train`             |
| Cleaned training data                                  | `data/processed/loan_applications_clean.csv`                | `python -m app.ml.train` (same `clean()` the notebook shows) | Notebooks                                       |
| Vehicle catalogue (26 models, 38 variants)             | `data/raw/vehicles.json`, `data/raw/vehicles.csv`           | `python data/build_catalogue.py`                             | API seed (`vehicles`, `vehicle_prices`)         |
| Vehicle brochures (one per model)                      | `data/documents/vehicles/<model_key>.md`                    | `python data/build_catalogue.py`                             | Vector index, `GET /vehicles/{id}`, vehicle Q&A |
| Lending policies (prose)                               | `data/documents/policy/*.md`                                | Hand-written                                                 | Vector index, citations                         |
| Lending policies (executable rules + verbatim clauses) | `data/documents/policy/*.json`                              | Reviewed extraction of the prose                             | API seed (published policy versions)            |
| Eligibility model + model card                         | `models/eligibility_model.joblib`, `models/model_card.json` | `python -m app.ml.train`                                     | API (loaded read-only, hash-checked)            |
| Vector index                                           | `vectorstore/local/`, optionally `vectorstore/gemini/`      | `python -m app.rag.ingest`                                   | Explanations, vehicle Q&A                       |

Run the backend commands from `backend/`. Run the data generators from the repository root.

## 1. Historical loan applications

The file has 12,120 rows, of which 53.4% are labelled `Approved`. The columns are:

| Column                                              | Meaning                                                                                            |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `application_id`, `application_date`                | Identifier; date between 2021 and 2026 (not used as a feature)                                     |
| `monthly_income`                                    | Gross monthly income, INR                                                                          |
| `credit_score`, `score_bureau`                      | Score 300–900 and the bureau that issued it                                                        |
| `employment_category`, `employment_months`          | Salaried, self-employed, unemployed, retired or student; months in the current job or business     |
| `existing_emi`, `active_loans`                      | Existing monthly EMIs (INR) and the number of active loans                                         |
| `requested_amount`, `tenure_months`, `down_payment` | The loan request                                                                                   |
| `vehicle_type`, `region`                            | Context only; not used as features (no signal, and they could proxy for protected characteristics) |
| `loan_status`                                       | Label: `Approved` or `Rejected`                                                                    |

**How the labels are produced.** Applicants are first screened by knockout rules that mirror the written policy:

- credit score below 650;
- income below INR 25,000;
- ineligible employment category, or salaried under 6 months, or self-employed under 24 months;
- more than 3 active loans;
- existing EMIs at or above 50% of income.

Applicants who pass the knockouts are then labelled by a latent credit-risk score with noise. That score rises with credit score, income and job tenure, and falls with EMI burden, loan-to-income ratio, active loans and a small down payment. This is why a model has something to learn beyond the rules.

**Defects injected on purpose**, so that preparation can be shown:

| Defect                                                                            | Size          | Handling (`app.ml.pipeline.clean`)                                                 |
| --------------------------------------------------------------------------------- | ------------- | ---------------------------------------------------------------------------------- |
| Duplicate submissions                                                             | 120 rows (1%) | Dropped by `application_id`                                                        |
| Inconsistent category spellings (`SALARIED`, `Self-Employed`, `self employed`, …) | About 4%      | Normalised, with `other` as the fallback                                           |
| Data-entry outliers (income ×25)                                                  | 41 rows       | Incomes above INR 10,00,000/month are set to missing                               |
| Missing values (`credit_score`, `employment_months`, `down_payment`)              | 1.7–3.2%      | Median or mode imputation inside the model pipeline, fitted on training folds only |
| Label noise (manual exceptions)                                                   | About 2%      | Kept; it shows up as irreducible error in the evaluation                           |

**Derived features:** `emi_to_income`, `loan_to_annual_income` and `down_payment_ratio`.

## 2. Vehicle catalogue and brochures

The catalogue has 26 models (38 variants) from 10 synthetic makes. It covers hatchback, sedan, SUV, MPV, coupe and commercial van bodies, with petrol, diesel, CNG, hybrid and electric power. Each variant includes:

- specifications: engine, power, efficiency, airbags, boot space, dimensions;
- features, warranty, service interval and colours;
- a dated Maharashtra price, broken down into ex-showroom price, registration, insurance and other charges.

Edge cases are deliberate:

- two commercial vehicles, which are excluded by policy;
- one stale price, which needs re-verification;
- EVs with reduced registration charges.

Each model has a brochure in `data/documents/vehicles/`. The brochures are the only source the vehicle Q&A may use.

## 3. Policy documents

There are two synthetic lenders. Each policy has a prose document (`.md`), structured as pages, sections and clauses, plus an executable rules file (`.json`) whose clause texts are quoted **verbatim** from the prose. `ground_clauses()` checks every quotation against its page.

The prose covers:

- eligibility (credit score, income, employment, active loans);
- applicant-specific rules (income evidence differs for salaried and self-employed applicants);
- loan terms (debt-service limit, rate bands, tenure, amount limits, loan-to-value, fees);
- the credit-risk model threshold (NW-3.7 / SB-C7);
- vehicles and rounding;
- exceptions (manual review, co-applicants, first-time borrowers);
- required documents.

Clauses that are not executable, such as exceptions and documentation, are still indexed for retrieval. Explanations can therefore cite them. For example, a credit-risk decline points the applicant to the manual-review clause NW-5.1.

**Changing a policy.** Published policy versions are immutable. To change the rules, add a new version with a later `effective_from`, through the policy UI or as a new file pair in this folder. Then run `python -m app.rag.ingest`. The `test_vector_store_matches_documents` test fails until the index is rebuilt.

## 4. Regenerating everything

```powershell
backend\.venv\Scripts\python data\generate_loans.py
backend\.venv\Scripts\python data\build_catalogue.py
cd backend
.venv\Scripts\python -m app.ml.train            # model + card + processed data
.venv\Scripts\python -m app.rag.ingest          # local index; plus a Gemini index if GEMINI_API_KEY is set
cd ..
backend\.venv\Scripts\python notebooks\build_notebooks.py   # re-executes both notebooks
```
