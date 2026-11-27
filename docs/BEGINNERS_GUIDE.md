# Beginner's Guide — Intelligent Vehicle Loan Advisor

> Read this in 10 minutes. It explains **what** the project does and **how** it is built, in plain words.

## 1. The project in one line

> "A vehicle-loan advisor that checks a lender's rules, calculates a safe loan amount, shows which cars the customer can afford, and explains *why* — with proof from the policy."

All data (lenders, customers, cars, loan history) is **synthetic**. Results are an **indicative simulation**, not a real loan.

## 2. What it does — 5 features

| # | Customer asks | App answers with |
|---|---|---|
| 1 | Am I eligible? | **Approved / Rejected** + reasons with policy clause (e.g. "Your score 580, required ≥ 650, NW-2.1") |
| 2 | How much can I borrow? | Loan amount, EMI, interest rate, fee + step-by-step calculation |
| 3 | Which cars can I buy? | Shortlist of cars from a 38-variant catalogue, with EMI and cash needed today |
| 4 | Tell me about this car | Answers from the car's brochure, or **"I don't know"** if the brochure doesn't say |
| 5 | Why this result? | Plain-language explanation with the policy text it used as evidence |

## 3. The golden rule: "AI informs, policy controls"

Three different "brains" — don't mix them up:

| Part | What it is | Job |
|---|---|---|
| **Policy engine** | Plain Python rules + maths | Makes the final decision. Exact, repeatable |
| **ML model** | Gradient Boosting trained on 12,000 old loans | Gives a risk score (0–1). Must be ≥ **0.83** to approve. Can only make approval *stricter* |
| **Gemini (LLM)** | Google's AI (optional) | Only writes nicer explanation text. **Cannot approve or reject** |

Order of checks: Missing data → **Incomplete** · Any rule fails → **Rejected** · Rules pass but ML score < 0.83 → **Rejected** · All pass → **Approved**.

## 4. The money, in one example

Income ₹85,000/month, existing EMIs ₹12,000, credit score 745, asks ₹8,00,000 for 60 months.

1. **Max debt (50% of income)** = ₹42,500 → room for new EMI = ₹42,500 − ₹12,000 = **₹30,500**
2. Score 745 → rate **9.75%**. ₹30,500/month can repay up to **₹14.43 lakh** (capacity)
3. Customer asked ₹8 lakh, so we give **₹8,00,000** (never more than asked). EMI = **₹16,899**, fee = ₹8,000
4. **Per car:** bank funds max **85%** of the car price (LTV). Customer pays rest + fee from own cash.

## 5. How it is built (tech stack)

```
 Streamlit (port 8501)     Next.js dashboard (port 3000)
   customer journey          lender: cases, audit, policies
            \                     /
             FastAPI backend (port 8000)
     Policy engine | ML model | RAG search | Gemini (optional)
                       |
             Database (SQLite / PostgreSQL)
```

| Layer | Technology | Folder |
|---|---|---|
| Customer UI | **Streamlit** (Python) | `streamlit_app/` |
| Lender dashboard | **Next.js** (React/TypeScript) | `frontend/` |
| API | **FastAPI** (Python) | `backend/app/api/` |
| Business rules | Pure Python | `backend/app/domain/` |
| Machine learning | **scikit-learn** | `backend/app/ml/`, `models/`, `notebooks/` |
| Document search (RAG) | TF-IDF vector index / Gemini embeddings | `backend/app/rag/`, `vectorstore/` |
| Data | Policies (.md + .json), 25 brochures, loan CSV | `data/` |
| Database | SQLite (local), PostgreSQL (production) | `backend/data/` |
| Deploy | Docker, Kubernetes, Terraform, GitHub Actions CI | `deploy/`, `infra/`, `.github/` |

## 6. Technical terms — simple meaning

| Term | Simple meaning |
|---|---|
| **API** | A service counter: send a request, get an answer (e.g. `POST /predict`) |
| **EMI** | Equated Monthly Instalment — fixed monthly repayment |
| **DSR** | Debt-Service Ratio — all EMIs must be ≤ 50% of income |
| **LTV** | Loan-to-Value — bank lends max 85% of car price |
| **Clause** | A numbered rule in the policy (e.g. NW-2.1 = minimum credit score) |
| **ML model** | Program that learned patterns from old loan data |
| **Features** | The 12 inputs the model uses (income, score, EMI ratio…) |
| **Threshold 0.83** | Minimum model score to approve; chosen because a bad approval costs 5× a wrong rejection |
| **ROC AUC 0.96** | How well the model ranks good vs bad applicants (1.0 = perfect) |
| **EDA** | Exploratory Data Analysis — studying the data before training |
| **RAG** | Retrieval-Augmented Generation — find the right document passage first, then answer from it |
| **Embedding / Vector index** | Text turned into numbers so similar text can be searched |
| **LLM** | Large Language Model, here Google **Gemini** (optional) |
| **Tenant** | One lender's private space (Northwind, Southbay) |
| **RLS** | Row-Level Security — database itself hides other lenders' rows |
| **OIDC / SSO** | Single sign-on login standard |
| **BFF** | Backend-for-Frontend — server proxy so secrets never reach the browser |
| **Replay** | Re-run a saved decision to prove it gives the same result |
| **Hash** | A fingerprint of data; if data changes, the fingerprint changes |
| **Docker** | Packages the app so it runs the same everywhere |

## 7. The 2 lenders and demo users

| Lender | Model threshold | Users |
|---|---|---|
| **Northwind** | 0.83 | Alice, Arjun (applicants), Omar (officer), Priya (policy admin), Tara (tenant admin) |
| **Southbay** | 0.88 (stricter) | Ben (applicant), Lena (officer + policy admin) |

## 8. How to run

```powershell
python run.py              # first time (10–20 min)
python run.py --skip-install   # later runs
```

Open: Streamlit `http://localhost:8501` · Dashboard `http://localhost:3000` · API docs `http://127.0.0.1:8000/docs`

## 9. Key numbers to remember

- 12,000 clean loan records · 4 models compared · **Gradient Boosting** chosen
- ROC AUC **0.96** · false-approval rate **5.6%** · threshold **0.83**
- 2 lenders · 25 brochures / 38 car variants · 100+ automated tests
- ~48 decisions/second measured on a single SQLite process

## 10. Never over-claim

Don't say: "real bank", "verified income", "zero hallucinations", "guaranteed fair", "production-scale proven".
Do say: "synthetic data", "indicative result", "AI informs, policy controls".

See also: [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) · [EVALUATOR_QA.md](./EVALUATOR_QA.md) · [presentation](./presentation/Vehicle_Loan_Advisor.pptx)
