# Demo Preparation: Key Points

## 1. The project in one minute

The **Intelligent Vehicle Loan Advisor** is a demo that checks a lender's loan rules, estimates an eligible loan amount, suggests affordable vehicles and explains its results.

> **Say:** "The policy rules control the decision, the ML model adds a risk check, and AI helps explain the result. The data and lenders in this demo are synthetic."

The result is **indicative**, not a real loan approval. Income and other applicant inputs are self-declared, not independently verified.

## 2. How the pieces fit together

```text
Customer: Streamlit (8501)       Lender staff: Next.js dashboard (3000)
                    \             /
                    FastAPI backend (8000)
           /              |                 \
    Policy rules      ML risk check       RAG / optional Gemini
                           |
             Database: SQLite or PostgreSQL
```

- **Streamlit:** A Python tool for building the customer-facing forms and data screens quickly. It is convenient for a prototype; the customer UI could later be rebuilt in Next.js.
- **Next.js:** The staff dashboard for applications, policies and audit history. Its server-side BFF handles the browser session and forwards requests to FastAPI.
- **FastAPI:** The Python backend that receives requests, checks permissions where required, runs the services and returns results.
- **Modular monolith:** The backend is one application organised into separate modules. This is simpler to run and keeps related database updates together. A component could be separated later if it needs independent scaling.

### Main API endpoints

| Endpoint | Purpose |
|---|---|
| `/predict` | Evaluates an application and returns its decision and reasons. |
| `/loan-amount` | Returns the eligible amount, EMI, interest and fee using an existing decision or a new application. |
| `/vehicles` | Searches the catalogue; vehicle details and brochure questions use related endpoints. |
| `/explain` | Generates an explanation of a saved decision. |
| `/v1/*` | Staff and application endpoints, including cases, policies and audit data. |

## 3. Loan decision and calculations

- **Policy engine:** Deterministic Python rules: the same inputs and policy produce the same result. Python `Decimal` is used for money calculations and explicit rounding.
- **Possible results:** Approved, rejected, incomplete or needs review. For example, a score of **580** can fail a minimum of **650**, with clause **NW-2.1** shown as the reason.
- **ML check:** For applications that pass the other rules, the model score must meet the lender's threshold: **0.83 for Northwind**, **0.88 for Southbay**. It cannot override a failed policy rule; an unavailable required model leads to review.
- **DSR:** Debt-service ratio. In the Northwind example, total monthly EMIs must be at most **50% of income**.
- **LTV:** Loan-to-value. In the example, the amount financed against a car is capped at **85% of its on-road price**; the customer must cover the remainder and applicable fees.

### Example: how much can the customer borrow?

Income **₹85,000/month**, existing EMI **₹12,000**, credit score **745**, requested loan **₹8 lakh** over **60 months**:

1. Maximum total EMI = 50% × ₹85,000 = **₹42,500**.
2. Available new EMI = ₹42,500 − ₹12,000 = **₹30,500**.
3. At **9.75% annual interest**, the repayment-capacity calculation gives approximately **₹14.43 lakh**.
4. The eligible amount is the lowest of the **requested amount**, repayment capacity and product maximum: **₹8 lakh**.
5. EMI is approximately **₹16,899.39/month**; the example upfront processing fee is **₹8,000**. Vehicle-specific affordability is checked separately.

**EMI formula:** `EMI = P × r × (1 + r)^n / ((1 + r)^n − 1)`, where `P` is loan principal, `r` is the annual rate divided by 12, expressed as a decimal, and `n` is the number of months. The app uses the inverse formula to calculate the principal supported by an available EMI.

## 4. Machine learning: slide 9

- **scikit-learn** is the Python ML library used to train and compare models. **Pandas** helps prepare the data; **Jupyter notebooks** document exploration, experiments and results.
- Four models were compared. **Gradient Boosting**, a model combining many small decision trees, was selected for the lowest estimated business cost.
- **12,000 cleaned synthetic records:** 9,600 for training and model comparison; 2,400 held out for testing.
- **ROC AUC 0.96:** Measures how well the model ranks cases labelled eligible above those labelled ineligible. Closer to 1 is better.
- **Precision 94%:** Of the test cases the model labelled eligible, about 94% were labelled eligible in the data. **Recall 79%:** It identified about 79% of cases labelled eligible.
- **False-approval rate 5.6%:** About 5.6% of test cases labelled ineligible were incorrectly labelled eligible by the model.
- **5:1 cost ratio:** An *assumption* used in model and threshold selection: a false approval costs five times a false rejection. It is not a measured financial loss. The reported business cost is a relative score, not rupees.
- These are **model test results on synthetic data**, not proof of performance, calibration or fairness for real applicants.

## 5. RAG, Gemini and guardrails

**RAG = Retrieval-Augmented Generation:** like an open-book exam, find relevant evidence first, then use it to answer.

```text
Policy clauses / vehicle brochures → text chunks → vectors → searchable index
Question or decision reasons → relevant chunks → explanation or answer
```

- **Chunking:** Custom Python code creates one chunk per policy clause and one per vehicle brochure section; Python's `re` finds brochure headings.
- **Embeddings:** Text is converted into numbers for searching. The local option uses a custom TF-IDF implementation with **NumPy**; an optional Gemini index uses `google-genai` and `gemini-embedding-001`.
- **Gemini:** The optional LLM writes an explanation or vehicle answer; it does not approve loans, calculate EMI or change the saved decision.
- **Retrieval scope:** Decision explanations search the same policy version used for the decision. Vehicle questions search the selected vehicle's brochure.
- **Checks and fallback:** Explanation checks compare the outcome, citations and numbers with the decision and evidence; a template is used if checks fail or the explainer is unavailable. Vehicle Q&A can use brochure text directly or say **"I don't know"** when relevant evidence is missing.
- **Human review:** AI-extracted policy drafts require review and grounding against the source before a draft policy version is created.
- These checks **reduce** errors; they do not prove every generated statement is correct.

> **Say:** "AI explains the decision; it does not make or change it. We retrieve relevant evidence and check the response, but we do not claim zero hallucinations."

## 6. Where information is stored

| Location | Purpose |
|---|---|
| `models\` | Saved trained model and model card. |
| `data\` | Synthetic loan and vehicle data, lender policies and brochures. |
| `vectorstore\local\` | `vectors.npy` contains embeddings; `chunks.json` holds text and sources; `manifest.json` describes the index. A Gemini index, if built, is separate. |
| SQLite / PostgreSQL | Applications, decisions, policy versions, explanations, audit events and vehicle records. |

**Saved decision:** The FastAPI backend automatically stores a snapshot of the evaluation in the database's `decisions` table: the inputs, result, relevant rules and clauses, calculations, policy version and model output. An audit event records the action. The explanation later reads this saved record.

**Audit Log screen:** An activity history for authorised staff, showing important actions such as evaluations and policy changes, who performed them and when.

**Vehicle catalogue:** The cars are preloaded synthetic data, not a live dealer feed. `data\build_catalogue.py` generates the catalogue and brochures, and the backend seed process loads new vehicle IDs into the database. The screen has no add/upload feature, and the seed process does not automatically update existing vehicles.

## 7. Security and lenders

- **Authentication** asks *who are you?* **OIDC** is a sign-in standard supported by the project; a configured identity provider such as Cognito handles login.
- **Authorization** asks *what may you do?* Roles, lender membership and record ownership control access.
- **Demo mode is different:** The dashboard uses demo identities; some unprefixed endpoints default to a demo applicant without headers. This shortcut is not for production. OIDC has been tested with a mock provider, not a real Cognito setup.
- **Multi-tenant** means the same application serves multiple lenders. Demo lenders and memberships are seeded in `backend\app\seed\seed.py`. The backend selects a tenant from the user's verified membership.
- **RLS (Row-Level Security):** PostgreSQL adds database-level tenant isolation to tenant-owned tables. SQLite does not provide this RLS layer; application-level access checks still apply.
- **BFF (Backend for Frontend):** A server-side layer between the browser and FastAPI. With OIDC configured, it manages the session and keeps tokens out of browser JavaScript.

## 8. Other technical terms

| Term | Simple explanation |
|---|---|
| **SQLAlchemy** | Python library used to read and save database records. |
| **Alembic migrations** | Versioned instructions for changing database tables and columns. |
| **Redis + BullMQ** | Queue and job-management tools for background work. When queue mode is enabled, a worker processes tasks such as policy-document transcription and can retry failures. The basic setup processes documents during the request. |
| **Terraform** | Infrastructure-as-code tool. This repo has reference AWS files; they are not required for the local demo or proof of a deployed production system. |
| **Hash** | A digital fingerprint used to help detect changes to saved data or model files. |

## 9. Limitations to state confidently

- **Synthetic data and policies:** Not a real lender, real loan history or verified customer information.
- **Model assumptions:** The 5:1 cost ratio is assumed; real data, bias checks and calibration are needed before production use.
- **Performance:** About **48 evaluations/second**, with evaluation **p95 ~141 ms**, was measured on one local SQLite process at eight concurrent clients. The assumed target was 150 evaluations/second; PostgreSQL and production scale have not yet been load-tested.
- **Authentication:** Local demo shortcuts must not be exposed as production login. Real identity-provider deployment still needs verification.
- **Vehicle administration:** The catalogue is preloaded; there is no screen for uploading new cars.
- **AI:** Evidence and checks help, but generated text can still be wrong.

**Related materials:** [Beginner's guide](BEGINNERS_GUIDE.md) · [Short demo script](DEMO_SCRIPT.md) · [Evaluator questions](EVALUATOR_QA.md) · [Presentation](presentation/Vehicle_Loan_Advisor.pptx)
