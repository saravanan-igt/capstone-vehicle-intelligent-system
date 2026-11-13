# Demo Guide: Intelligent Vehicle Loan Advisor

Use this guide in two passes:

- **Part A (learn it).** Work through it on your own first, so you can explain every screen.
- **Part B (present it).** A timed, click-by-click script for a stakeholder audience.

**How to use the numbers:** the original guide recorded a SQLite rehearsal on 2026-11-13 without Gemini, using fresh seed data (103 backend tests passed, 4 skipped). This revision follows the source code and saved model card; it is **not a new live-browser verification**. Treat probabilities and vehicle counts as rehearsal baselines, not guarantees: policy changes, model changes and ageing prices can change them. Rehearse on your demo machine before presenting.

> Companion: [DEMO.md](./DEMO.md) is a deeper, more technical script for evaluators. [Part D](#part-d--review-of-demomd-gaps-and-corrections) lists what it misses and what it gets wrong.

---

## Part A — Understand the project, from zero

Read A1–A7 first for the business story, A8–A14 for how the code delivers it, and A15–A17 before rehearsing Part B. You do not need to memorise Python to explain this application.

### A1. What problem are we solving?

Imagine someone walks into a lender's office and says: **"I want to buy a car. Will you lend me money, how much, and which cars can I buy?"**

Normally, someone must check the applicant's finances, read the lender's rulebook, calculate repayments, check car prices and explain the answer. This application brings those steps together.

| Customer's question | What the application does | Business value |
|---|---|---|
| Am I eligible? | Checks the lender's rules and a trained risk model | Consistent screening |
| How much can I borrow? | Calculates a policy-compliant amount and monthly repayment | Avoids offering more than repayment capacity supports |
| Which cars fit? | Checks catalogue prices, loan limits and cash needed today | Turns an abstract loan amount into buying options |
| What does this car offer? | Looks up its brochure to answer questions | Helps the customer research a vehicle |
| Why did I get this result? | Shows reasons, numbers and policy references | Makes the decision easier to explain and audit |

**What it is not:** a real bank connection, actual credit-bureau lookup, loan disbursement system or guarantee of approval. All lenders, people, historical loan records and vehicles are synthetic. Form inputs are self-declared, not independently verified. An approval is an **indicative simulation**, not money transferred or a binding sanction.

Your one-sentence introduction:

> "This is a vehicle-loan advisor that checks a lender's rules, calculates a safe indicative loan amount, matches cars to the customer's budget, and explains the result with evidence."

### A2. Think of it as a small lending office

| Office analogy | Software part | What it actually does |
|---|---|---|
| Reception counter | Frontend | Collects inputs and displays results |
| Service coordinator | Backend application layer | Organises identity checks, policy selection, scoring, calculations and saving |
| Rulebook and calculator | Policy engine | Applies exact rules and calculates money |
| Analyst who studied past cases | Machine-learning model, or ML | Estimates an approval score from historical examples |
| Librarian | Retrieval system | Finds relevant passages in a policy or brochure |
| Writer | Optional Gemini language model, or LLM | Turns supplied facts and passages into wording |
| Filing cabinet | Database | Keeps applications, decisions, policies and audit records |

**Most important distinction: ML is not the same thing as Gemini.** The saved ML model produces a numeric score. Gemini is an optional language/document service. The lending calculator is neither of those.

### A3. The big picture: two screens, one decision system

```text
Applicant in a browser                 Lender/user in a browser
        |                                       |
Streamlit server, port 8501             Next.js server, port 3000
        |                                       |
        |                              Server-side API proxy (BFF)
        |                                       |
        +-------------------+-------------------+
                            |
                 FastAPI backend, port 8000
                            |
           Identity + permissions + application services
                            |
          +-----------------+------------------+
          |                 |                  |
     Policy engine     Saved ML model    Document retrieval
     + money maths                       + optional Gemini
          |                                    |
          +------------ Database --------------+
                 Stored decisions and evidence
```

An **API** is a service counter that accepts a structured request and returns a structured answer. A **port** is the numbered entrance to a program on your computer. `localhost` and `127.0.0.1` mean your own computer.

Both frontends use the same backend rules; neither makes an independent lending decision. They have different presentations:

| Browser address | Purpose | Demonstrate here |
|---|---|---|
| `http://localhost:8501` | Simple Streamlit applicant journey | Five tabs: Eligibility, Loan amount, Vehicles, Vehicle details, Explanation; brochure Q&A and retrieved explanation sources |
| `http://localhost:3000` | Next.js dashboard | Saved applications, rule trace, calculations, comparison of up to 3 vehicles, replay, policy administration and audit |
| `http://127.0.0.1:8000/docs` | Automatically generated API playground | Optional technical evidence; not the main stakeholder journey |

The dashboard's vehicle details page shows catalogue specifications and prices, **not the Streamlit chat**. Its explanation card shows explanation points and citations; use Streamlit to expand the separate **Retrieved policy sources** panel.

### A4. What information goes into an application?

| Form concept | Plain-language meaning | Backend field |
|---|---|---|
| Income and frequency | Earnings entered monthly or annually; annual income is divided by 12 | `income_amount`, `income_frequency` |
| Credit score and provider | A declared credit-history score and who issued it; no bureau is contacted | `credit_score`, `score_provider` |
| Employment and duration | Salaried/self-employed/etc. and months in the current job/business | `employment_category`, `employment_months` |
| Existing monthly debt payments | Money already committed to EMIs and similar obligations | `existing_monthly_obligations` |
| Active loans | How many loans are currently being repaid | `active_loans` |
| Requested amount | Money the customer wants to borrow, not the car's total price | `requested_principal` |
| Tenure | Number of monthly repayments; 60 months = 5 years | `requested_tenure_months` |
| Down payment / available cash | Customer's own cash available for the car contribution **and upfront fees** | `down_payment_available` |
| Location | Currency INR, country India, registration region such as Maharashtra (`IN-MH`) | `currency`, `jurisdiction`, `region` |

Optional body/fuel preferences are not credit-risk features. Use the vehicle-results filters explicitly during the demo.

**Input validation and policy checking are different.** A score of `950` is invalid input because scores must be 300–900. A score of `600` is valid input but fails Northwind's minimum of 650. Missing required information produces **Incomplete**, not an assumed zero or automatic rejection.

The dashboard says "Gross income before tax", but the written policy describes qualifying income evidence differently for salaried and self-employed applicants. The code only normalises the entered income's frequency; it does **not** check salary slips, tax returns or bank statements. Say **"declared qualifying income for this simulation"**, not "verified income".

### A5. Who actually decides? "AI informs; policy controls"

The engine applies ordinary rules first. If they all pass, it applies the policy's ML-score requirement. The coordinator may calculate a model score earlier for display; that does not let the score override a failed rule.

```text
Required information missing?                   -> INCOMPLETE
Policy/context cannot support automation?        -> NEEDS_REVIEW
Any ordinary eligibility rule fails?             -> REJECTED
Rules pass, but required model unavailable?      -> NEEDS_REVIEW
Rules pass, but score below policy threshold?    -> REJECTED
Rules pass AND score meets policy threshold?     -> APPROVED
```

**Approved** means an indicative amount can be offered. **Rejected** means an evaluated rule failed. **Incomplete** means more information is needed. **Needs review** means automation cannot safely conclude; it is not a rejection.

In the database, `status=COMPLETED` means evaluation finished; `outcome=APPROVED` or `REJECTED` says what it decided. Do not mistake "Completed" for "Approved".

Northwind's executable policy:

| Clause | Rule in everyday language |
|---|---|
| NW-2.1 | Score at least 650, from CIBIL or Experian |
| NW-2.2 | Monthly qualifying income at least ₹25,000 |
| NW-2.3 | Only salaried or self-employed; at least 6 months salaried or 24 months self-employed |
| NW-2.4 | No more than 3 active loans |
| NW-3.1 | Existing debt payments plus the new EMI must fit within 50% of income |
| NW-3.2 | Score 750–900: 8.75%; 700–749: 9.75%; 650–699: 11.25% fixed nominal annual interest |
| NW-3.3 | Repay over 12–84 months |
| NW-3.4 | Loan range ₹1,00,000–₹50,00,000; a large request can be reduced rather than automatically rejected |
| NW-3.5 | For a specific vehicle, finance at most 85% of its on-road price |
| NW-3.6 | Processing fee 1% of the loan, minimum ₹2,500, maximum ₹15,000; paid upfront |
| NW-3.7 | Required model approval score at least 0.83 |
| NW-4.1 | No commercial vehicles; prices older than 120 days need re-verification |
| NW-4.2 | Capacity/LTV principal limits are rounded down in ₹1,000 steps; EMI to paise |

Source: [Northwind's written policy](../data/documents/policy/NW-AUTO-STD-2026.1.md) and its neighbouring `.json` executable rules. A **clause** is just a numbered paragraph of that rulebook.

Not every paragraph is automated. Document requirements, co-applicants and manual-review exceptions are described in the policy, but this is not a complete document-verification or officer-override workflow.

### A6. Understand the money with one worked example

Use the Streamlit defaults: monthly income ₹85,000; existing EMIs ₹12,000; score 745; request ₹8,00,000; tenure 60 months; own cash ₹1,50,000.

**Step 1 — Find the monthly repayment budget.**

```text
Maximum total monthly debt = ₹85,000 × 50% = ₹42,500
Budget for the NEW EMI     = ₹42,500 − ₹12,000 = ₹30,500
```

This is the **debt-service ratio (DSR)** rule. It does not mean we lend 50% of the person's income; it limits the monthly debt payments.

**Step 2 — Select the rate and turn the EMI budget into a loan capacity.**

A score of 745 selects 9.75% per year. The calculator asks: "What principal can ₹30,500 per month repay at this rate over 60 months?" After rounding down, that is **₹14,43,000**. This is below the ₹50 lakh product maximum.

**Step 3 — Do not lend more than requested.**

```text
Borrowing capacity = min(repayment-supported principal, ₹50,00,000)
Indicative amount = min(requested ₹8,00,000, capacity ₹14,43,000)
                  = ₹8,00,000, if eligibility and the model gate pass
Actual new EMI    = ₹16,899.39
Processing fee    = ₹8,000 upfront
```

The EMI budget is a **ceiling**, not the EMI automatically charged. Total scheduled EMIs are approximately ₹10.14 lakh over 60 months; that includes principal and interest, but not the upfront fee.

For code questions, EMI means **Equated Monthly Instalment**:

```text
EMI = P × r × (1+r)^n / ((1+r)^n − 1)
P = loan principal; r = nominal annual rate / 12; n = months
```

You need not explain the algebra on stage. Say: "It is the standard reducing-balance loan formula: each payment covers interest and some principal." The inverse formula finds the principal supported by an EMI budget.

**Step 4 — Check each car separately.**

Consider an **illustrative car**, not a promised catalogue row, with an on-road price of ₹9,00,000:

```text
On-road price             = ex-showroom + registration + insurance + other charges
85% vehicle loan ceiling  = ₹7,65,000
Loan for this car         = min(₹8,00,000 indicative amount, ₹7,65,000)
                          = ₹7,65,000
Customer's contribution   = ₹9,00,000 − ₹7,65,000 = ₹1,35,000
Processing fee on car loan= ₹7,650
Cash needed today         = ₹1,42,650
Available cash            = ₹1,50,000 -> this example fits
```

This is **loan-to-value (LTV)**: how much of the car's price the lender will finance. The car-specific loan, EMI and fee can be lower than the initial indicative loan figures.

**Loan approval does not mean every car is affordable.** A customer can pass credit screening but lack the cash contribution and fee. With zero available cash, no catalogue vehicle fits this policy even if a loan is approved.

### A7. How to read vehicle results

| Status | Meaning | What to point at |
|---|---|---|
| Affordable | Vehicle loan meets the minimum and available cash covers contribution plus fee | Loan, EMI and upfront cash |
| Not affordable | Usually a cash shortfall, or a vehicle loan below the policy minimum | Reason and shortfall |
| Unverified | Price is too old, incomplete, or otherwise cannot be confirmed | Price date / missing cost; never call a missing value zero |
| Not eligible | Vehicle category excluded, such as a commercial van | Policy reference NW-4.1 |

The recommendations assess the **fixed catalogue**, not live dealer inventory or the whole market. Filters narrow it; they do not make a failed application eligible. "Best fit" puts affordable cars first, with the highest-priced affordable options first, then the nearest misses.

When nothing fits, the Streamlit/API guidance calculates possible changes: more cash, a new request using unused capacity, a longer allowed tenure, or relaxing filters. It only offers changes its calculations support. A longer tenure can lower EMI but increase total interest; it is not an automatic approval.

**Important screen behaviour:** without an approved decision, Streamlit's Vehicles tab accepts manually supplied loan terms. This is a **what-if budget calculator**, not a reversal of a rejection. The dashboard only shows its decision-linked comparison section for approved results.

### A8. The repository: where each part lives

Paths below are relative to the repository root. Read the folder as "a team with one responsibility", not a separate deployed application.

| Location | Plain-language job | Why/when you would open it |
|---|---|---|
| `run.py` | Local startup organiser | Starts the API and both frontends; prepares dependencies/assets/database |
| `streamlit_app\app.py` | Entire five-tab applicant UI | Match a visible tab/button to its API call |
| `frontend\src\app` | Next.js pages; each page folder maps to a browser route | Find login, application, policy, vehicle or audit screens |
| `frontend\src\components` | Reusable screen pieces | `VehicleMatches.tsx` implements filtering and comparison |
| `frontend\src\lib` | Browser API helper, formatting, shared types and server auth helpers | Understand communication and display |
| `backend\app\main.py` | Creates the FastAPI application and wires its components | Startup, model/index loading, health checks and error handling |
| `backend\app\api` | API entrances | `brief.py` serves the simple advisor endpoints; `v1.py` serves the dashboard |
| `backend\app\application` | Use-case coordination | `services.py`: saved applications, policies, evaluation, replay, explanations; `advisor.py`: advisor response views, recommendations and Q&A; `documents.py`: policy ingestion |
| `backend\app\domain` | Core business rules, independent of browser/database | `eligibility.py`, `affordability.py`, `money.py`, `applicant.py`, `policy.py`, `explanation.py` |
| `backend\app\ml` | Model features, training and scoring | `features.py`, `pipeline.py`, `train.py`, `model.py` |
| `backend\app\rag` | Document splitting, indexing, search and Q&A | `chunking.py`, `ingest.py`, `embeddings.py`, `store.py`, `knowledge.py`, `qa.py` |
| `backend\app\infrastructure` | Connections to storage, databases, Gemini, login and monitoring | Adapters to outside services, not lending rules |
| `backend\app\seed`, `backend\migrations`, `backend\app\ops` | Starter records, database structure changes and operational commands | Understand how a fresh demo gets its data |
| `backend\app\worker` | Background document-processing jobs | Production-like queue mode, not a required extra process for the default local demo |
| `backend\tests` | Automated behaviour checks | Evidence for eligibility, money, permissions, documents, ML and retrieval |
| `data` | Generated loan history, catalogue and source documents | Trace where the examples and evidence come from |
| `models` | Saved trained model and its model card | The model file is loaded, not retrained on each click |
| `vectorstore` | Saved document-search indexes | Not the application database; this makes text searchable |
| `notebooks` | Step-by-step data exploration and training reports | Explain how the model was developed |
| `docs` | Architecture, evaluation, operations and this guide | Presenter/reference material |
| `deploy`, `infra`, Docker Compose files, `.github` | Packaging, deployment infrastructure and automated checks | Production/deployment discussion; do not imply all are running locally |
| `loadtest` | Scripts for measuring request throughput and latency | Discuss measured performance, not assumed production capacity |

A **layer** groups code by responsibility. This separation means a UI change need not change lending rules, and the rule calculator can be tested without running a browser or Gemini.

### A9. Follow one click through the code

Open these files in this order while studying. Search for the function names; you do not need to read every import.

| Stage | Code to find | What happens in ordinary language |
|---|---|---|
| 1. Collect | `streamlit_app\app.py` → `eligibility_tab()` | Reads the form and builds named fields |
| 2. Send | Same file → `api("POST", "/predict", json=payload)` | Sends a JSON request to FastAPI. JSON is a named-field data format, like a digital form |
| 3. Receive | `backend\app\api\brief.py` → `predict()` | Validates the request shape, obtains identity/database access and calls the use case |
| 4. Create | `backend\app\application\advisor.py` → `predict()` | Creates an application record and requests evaluation |
| 5. Coordinate | `backend\app\application\services.py` → `evaluate_application()` | Loads the applicant, selects the lender's applicable published policy, gets a model score and calls the engine |
| 6. Decide | `backend\app\domain\eligibility.py` → `evaluate()` | Checks missing data, applicability, rule thresholds, capacity and the model gate |
| 7. Record | Back in `evaluate_application()` | Saves a decision snapshot, updates application status and writes an audit event |
| 8. Present | `advisor.py` → `predict_view()`, then `eligibility_tab()` | Converts the stored decision into display fields; shows the badge, reasons, policy and score |

The dashboard follows the same core service through a different entrance:

```text
frontend\src\app\(app)\applications\new\page.tsx
  -> save application: POST /v1/applications
  -> evaluate: POST /v1/applications/{id}/evaluate
  -> backend\app\application\services.py -> evaluate_application()
  -> browser opens /applications/{id}
```

Dashboard browser requests go through `frontend\src\app\api\bff\[...path]\route.ts`. **BFF** means backend-for-frontend: a server-side intermediary which forwards requests with the user's backend identity. Backend credentials are not embedded in the browser page.

To follow the remaining buttons:

| Browser action | API entrance | Core code |
|---|---|---|
| Streamlit Loan amount | `POST /loan-amount` with `decision_id` | `advisor.loan_amount_view()` reads recorded calculations, not a new random prediction |
| Streamlit Find vehicles | `POST /vehicles` | `advisor.recommend_vehicles()` → `affordability.assess_vehicle()`; `_guidance()` computes alternatives |
| Streamlit Vehicle details | `GET /vehicles/{id}` | `advisor.vehicle_detail()` gets catalogue data and brochure |
| Ask a vehicle question | `POST /vehicles/{id}/ask` | `advisor.ask_vehicle()` → `rag.qa.answer_question()` |
| Explain this decision | `POST /explain` or dashboard's `/v1/decisions/{id}/explanation` | `services.explain_decision()` retrieves text, drafts, validates and stores |
| Verify by replay | `POST /v1/decisions/{id}/replay` | `services.replay_decision()` re-runs recorded facts through the engine |

`decision_id` is the receipt number tying the amount, explanation and vehicle budget to the same decision. Do not create a different application when you mean to explain an existing one.

### A10. Read the engine without knowing Python

The important flow in `domain\eligibility.py` is equivalent to this **simplified pseudocode**, not code to paste into the project:

```text
If required fields are missing, return Incomplete.
If the policy doesn't cover this context, return Needs review.
Record each rule's applicant value, requirement and pass/fail.
Select the score-based interest rate.
Calculate the available EMI and repayment-supported principal.
If ordinary rules failed, return Rejected with those reasons.
Otherwise require the matching model and its policy threshold.
If the model is missing, return Needs review.
If its score is too low, return Rejected.
Otherwise calculate min(request, capacity), EMI and fee; return Approved.
```

`_Trace.check()` is the checklist recorder: it stores the **observed** value, **threshold**, pass/fail and **clause_id**. These become the dashboard's Rule trace table. `EvaluationResult` is the labelled result container.

`domain\money.py` uses Python **Decimal** for lending calculations: decimal arithmetic avoids the tiny binary rounding errors common with ordinary computer floating-point numbers. ML still uses floating-point numbers for scores; that is separate from the money calculator.

`domain\policy.py` defines the expected rule structure. The policy `.json` contains machine-readable values; the `.md` is the human-readable rulebook. Publishing a JSON policy makes its rules eligible for selection. It does not teach a model new rules or retrain it.

### A11. Machine learning: what was learned, and what the score means

Think of training as giving an analyst many old example forms, each labelled Approved or Rejected, so the analyst learns patterns. **Inference** means showing the trained analyst a new form and asking for a score.

```text
data\generate_loans.py
  -> synthetic historical CSV
  -> ml\pipeline.py: clean, derive features, split, compare models
  -> models\eligibility_model.joblib + model_card.json
  -> ml\model.py: load saved file and score new applications
```

A **feature** is an input used by the model. There are 12: income, credit score, employment months, existing EMIs, active loans, requested amount, tenure, down payment, employment category and three ratios. For example, ₹12,000 existing EMIs / ₹85,000 income is about 14.1%. `ml\features.py` shares this conversion between training and live scoring.

The preparation removes duplicate applications, standardises employment spellings, marks implausible income as missing, and fills missing model inputs using training-data statistics. **This does not mean an incomplete live application is automatically filled and approved**; the live engine checks required fields separately.

Four approaches were compared:

| Model | Layman's interpretation |
|---|---|
| Logistic regression | Combines input influences into a relatively simple score |
| Decision tree | Follows a branching series of questions |
| Random forest | Combines many trees |
| Gradient boosting, chosen | Combines successive small trees, each improving on earlier errors |

The saved model card records **12,120 raw rows → 12,000 after cleaning**, split into **9,600 training** and **2,400 test** rows. Five-fold cross-validation means repeatedly training on part of the training set and checking another part. The held-out test is a separate final check. Training-fold preprocessing avoids using validation/test statistics to fill training inputs, which would leak answers into practice.

The selection favours lower expected business cost: a false approval is assumed to cost **5 times** a false rejection. The chosen model's threshold is **0.83**, rather than automatically 0.50. Southbay's policy applies a stricter **0.88** to the same named model; this does not mean a separate model was trained for each lender.

**Do not misread the statistics:**

| Number on screen/report | Meaning | What it does NOT mean |
|---|---|---|
| Approval probability about 94.9% | Model's estimated probability of the synthetic historical **Approved** label for this input | A verified 94.9% chance that a real customer will repay |
| Confidence | In this code, `max(p, 1-p)`; a summary of how far the score favours either label | A separately measured uncertainty interval |
| Test ROC AUC 0.9603 | Ability to rank approved-labelled examples above rejected-labelled ones across cutoffs | "96% accurate" or production credit performance |
| False-approval rate 5.62% | 63 of 1,120 rejected-labelled test examples were predicted Approved | 5.62% of actual loans defaulted |

The displayed "main factors" are a simple sensitivity check: replace one input with a typical training value and see how the score changes. They are **not causal proof or SHAP values**.

The API checks the saved model file's SHA-256 against its model card before loading it. This detects a file/card mismatch; it is not a digital signature proving who created it. If no usable matching model is available, a rules-passing case goes to Needs review.

Evidence: [model card](../models/model_card.json), [EVALUATION.md](./EVALUATION.md), and notebooks `01_eda.ipynb` and `02_model_training.ipynb`. EDA means **exploratory data analysis**: inspecting distributions, missing values and unusual records before modelling.

### A12. RAG and Gemini: an open-book answer, not an unrestricted chatbot

**RAG = Retrieval-Augmented Generation.** In ordinary language: "Find the relevant page first; use it as evidence when answering."

```text
Policy/brochure documents
  -> split into small passages ("chunks")
  -> turn passages into searchable numeric representations ("embeddings")
  -> save a vector index

Question
  -> search the correct policy version OR vehicle brochure
  -> keep relevant passages
  -> optional Gemini wording, otherwise template/extracted text
  -> apply output checks
  -> display answer and evidence, or "I don't know"
```

An **embedding** is a numeric representation used to compare text. A **vector index** is the saved search collection; it is not a second loan-decision model. The local index uses hashed word/phrase TF-IDF matching. With a configured Gemini key and a built Gemini index, the app can use Gemini embeddings, with local fallback if available.

There are two different grounded-answer features:

| Feature | Evidence searched | Output |
|---|---|---|
| Decision explanation | Exact policy code/version used by the decision, plus recorded facts/clauses | Summary, reasons and citations; cannot change the saved amount or outcome |
| Vehicle Q&A | Selected vehicle model's brochure only | Brochure-grounded answer, or "I don't know… Please check with the dealer." |

Without Gemini, explanation text comes from a deterministic template and vehicle answers quote relevant brochure lines. **Retrieval still works without a paid LLM call.** The saved eligibility model also works without Gemini.

Checks reduce unsupported answers: explanation outcome must match, citations must be allowed, and numbers must occur in the supplied evidence; vehicle answers need cited retrieved sources and supported numbers. Retrieval also applies relevance/key-term checks. **These are safeguards, not proof that every possible generated sentence is true.** Do not promise "zero hallucinations".

**Policy upload is a separate AI flow:** PDF/image → page transcription (OCR: reading text from an image) → proposed structured rules → human review against source pages → policy draft → explicit publication. Without the configured document AI, scanned-policy transcription fails visibly/retryably; the template fallback does not replace OCR.

Publishing a new database policy does **not** automatically add it to the saved file-based vector index. `rag\ingest.py` builds from repository documents, and the backend loads indexes at startup. New published rules can govern decisions while supplemental vector retrieval for that version is absent. Do not promise immediate indexed retrieval of an arbitrary uploaded policy.

### A13. What is saved, and why replay matters

The default local database is the file `backend\data\vla.db` (SQLite). PostgreSQL is the production-like alternative. SQLAlchemy is the Python library mapping database tables to Python objects; migrations are versioned changes to table structure.

| Stored object | Think of it as |
|---|---|
| Tenant, user, membership | Lender, person, and that person's role in the lender |
| Application | The customer's submitted form and workflow status |
| PolicyVersion | A versioned rulebook, draft or published |
| Decision | An evaluation receipt: input snapshot, policy reference/hash, clauses, recorded model score, engine version, result and result hash |
| Explanation | Wording, AI/template source, fallback reason and retrieved sources |
| Vehicle and VehiclePrice | Shared catalogue and dated regional prices |
| AuditEvent | Who performed a recorded action, on what, and when |
| Policy source/pages/chunks | Uploaded document and extracted/reviewed text |
| OutboxEvent | A saved instruction for background work in queue mode |

A **hash** is a content fingerprint: changing content changes its fingerprint. A **snapshot** is the evidence bundle as it was at decision time.

**Replay** loads the recorded applicant, referenced policy version and recorded ML probability, runs the current engine again and compares the result fingerprint and engine version. It also reports whether the loaded model artifact matches the recorded artifact. It does **not** re-ask Gemini or freshly rescore the applicant. Reproducibility and model-artifact identity are distinct reported checks.

**Re-evaluate** is different: it creates a new decision using currently applicable published policy and the current model. An old receipt is not silently rewritten.

Two technical safeguards you might be asked about: **idempotency** reuses a decision when the same evaluation request key is retried; **row version / If-Match** prevents one form update silently overwriting a concurrent update.

### A14. Who can see what?

A **tenant** is a lender's private workspace. **Authentication** means "Who are you?" **Authorisation** means "What may you do?" A role is a permission set, not just a label on the screen.

| Demo user | Workspace and role | Real capability relevant to the demo |
|---|---|---|
| Alice, Arjun | Northwind applicants | Create and view their own applications, not each other's |
| Omar | Northwind loan officer | Read all Northwind applications and audit records; cannot publish policy |
| Priya | Northwind policy admin | Upload/review/publish policies and read audit; **cannot read Alice's application** |
| Tara | Northwind tenant admin | Read tenant applications, policy documents and audit; not an unrestricted superuser or policy publisher |
| Ben | Southbay applicant | Own Southbay applications, with Southbay policy |
| Lena | Southbay officer + policy admin | Combined application-reading and policy-management permissions within Southbay |

Streamlit offers only Alice, Arjun and Ben in its sidebar. Dashboard demo login offers all these identities. The dashboard's **Sign out** icon is beside the current user at the top right; switching dashboard identity does not switch Streamlit identity.

Application queries check lender membership and record ownership. PostgreSQL adds **row-level security (RLS)**: the database also restricts tenant-owned rows. Do not claim SQLite runs PostgreSQL RLS. The vehicle catalogue is intentionally shared, unlike private applications and policy records.

Cross-tenant application access returns **404 Not found**, rather than revealing another lender's record exists. Local demo identity selection is not real bank SSO. **OIDC/SSO** is the configurable external-login alternative; authorisation still comes from local memberships.

### A15. Startup and production terms, translated

`python run.py` checks prerequisites and ports, prepares `.env`, installs dependencies unless skipped, ensures model/index assets exist, migrates/seeds the database, builds Next.js, then starts and health-checks the three programs. It does not normally retrain an existing model.

`.env` holds local configuration, including optional credentials. Do not display it during a demo. `--skip-install` skips dependency installation, **not** the Next.js production build. `--reset-db` deletes the default local demo database and reseeds it; it is not an ordinary harmless refresh.

| Term | Plain-language role in this repository |
|---|---|
| Docker / Compose | Package programs with dependencies; start a group of services |
| Redis / BullMQ worker | Support quotas and queued background document work in the production-like stack |
| Transactional outbox | Save the work instruction alongside the business change, then relay it to a queue so the instruction is not lost between those steps |
| Kubernetes | Deployment definitions for managing/scaling containers |
| Terraform | Code describing infrastructure to provision |
| CI | Automated repository checks, builds and image scanning |
| Metrics / logs | Counts, timings and request records used to understand health and failures |
| p95 latency | 95% of measured requests finished within that time |

Do not present these as extra local browser features. The documented single-process SQLite measurement is about **48 evaluations/second**, p95 **141 ms**, below the stated 150/second target. Deployment definitions are not evidence of production-scale performance. See [LOAD_TEST.md](./LOAD_TEST.md), [RUNBOOK.md](./RUNBOOK.md), [ARCHITECTURE.md](./ARCHITECTURE.md) and the [ADRs](./adr).

### A16. Your code-level study route

Do this privately; do not read source files aloud to stakeholders.

1. Read A1–A7 and manually work through ₹42,500 → ₹30,500 → ₹8,00,000 → ₹16,899.39. Be able to distinguish loan capacity from available cash.
2. Open `streamlit_app\app.py`. Find `main()` for the five tabs, `eligibility_tab()` for form submission and `loan_tab()` for the calculated result.
3. Follow A9 through `api\brief.py`, `application\advisor.py`, `application\services.py`, then `domain\eligibility.py`. Find `missing_fields`, `_Trace`, `credit_risk.model` and `eligible = min(requested, capacity)`.
4. Open `domain\affordability.py`. Find `ltv_limit`, `principal`, `contribution`, `fee`, `upfront` and `shortfall`. Explain each using A6.
5. Open `ml\features.py`, `ml\model.py` and `models\model_card.json`. Identify the inputs, saved-model load, probability, threshold and factors. Use the notebooks for training evidence, not the live API.
6. Open `rag\qa.py` and find `dont_know()`, scoped `kb.search()` and `grounded()`. Then find `explain_decision()` and `replay_decision()` in `application\services.py`.
7. Open the dashboard's application detail `page.tsx` under `frontend\src\app\(app)\applications\[id]` and `components\VehicleMatches.tsx`. Match Result, Provenance, Rule trace, Calculation breakdown and comparison to their backend data.
8. Rehearse Part B in the browser. Note your actual results before presenting; do not change policies or regenerate assets between rehearsal and demo.

Optional technical playground: in `http://127.0.0.1:8000/docs`, expand `POST /predict`, click **Try it out**, replace the request body with the JSON below and click **Execute**. Copy `decision_id` from the response. Submit `{"decision_id":"PASTE_ID_HERE"}` to `POST /loan-amount`, `POST /vehicles` and `POST /explain` in turn.

```json
{
  "income_amount": "85000",
  "income_frequency": "monthly",
  "credit_score": 745,
  "score_provider": "CIBIL",
  "employment_category": "salaried",
  "employment_months": 72,
  "existing_monthly_obligations": "12000",
  "active_loans": 1,
  "requested_principal": "800000",
  "requested_tenure_months": 60,
  "down_payment_available": "150000",
  "currency": "INR",
  "jurisdiction": "IN",
  "region": "IN-MH"
}
```

In **local dev auth mode only**, these brief endpoints default to Alice when identity headers are omitted. `/v1` does not. This is a convenience for development, not the production authentication model.

### A17. Check that you understand before presenting

| Ask yourself | Answer you should be able to give |
|---|---|
| Can Gemini approve a loan? | No. The engine enforces rules, including a separate ML-score gate |
| Can a high model score rescue a score-600 applicant? | No. The minimum-credit-score rule still fails |
| Why is the EMI not ₹30,500 in the default case? | ₹30,500 is the ceiling; the requested ₹8 lakh needs only ₹16,899.39 |
| Why can an approved customer see no affordable cars? | The customer's upfront cash may not cover contribution plus fees |
| Why two frontends? | Streamlit demonstrates the simple advisor journey; Next.js adds persisted workflows and lender administration |
| What works without Gemini? | Eligibility, money calculations, matching, replay, template explanations and local extractive Q&A, given the saved model/index |
| Does replay prove today's model made the old score? | No. It reuses the recorded score; artifact identity is reported separately |
| What should I never overclaim? | Real-world lending validity, verified income, zero hallucinations, guaranteed fairness, or unmeasured production scale |

---

## Part B — The stakeholder demo (20–25 min + Q&A)

### B0. What to show, in what order

Follow one story: **customer asks → lender checks → customer sees a budget and cars → system explains → lender can inspect the evidence**.

Use Streamlit for the complete customer story, then the dashboard for the audit/governance story. Keep source code, API docs, OCR and policy changes out of the main demo unless asked. If you have only 10 minutes, do B2, B3 steps 1–3 and 5–7, then dashboard replay in B4 step 3.

### B1. Setup (do it the day before, then again 15 min before)

```powershell
cd C:\Bright_Star_Projects\HCL_FDE\capstone-vehicle-intelligent-system
python run.py                     # initial setup: installs and builds; allow 10–20 min or more
```

For a later start, first stop the existing run with **Ctrl+C** in its terminal, then use `python run.py --skip-install`. Leave the new terminal running during the demo. This still builds Next.js; allow time for it.

**Only if you intentionally want to erase the default local demo records**, use `python run.py --reset-db --skip-install` instead. It removes the SQLite applications, decisions, policy changes and audit history. Save any needed evidence first; do not reset a shared demo environment without agreement.

1. Confirm Python 3.12+, Node 20.9+ and free ports 8000, 3000 and 8501. Wait until startup reports all three services ready.
2. Visit `http://127.0.0.1:8000/health`. For the checked-in model and local index, a normal no-Gemini response is `{"status":"ok","model":"vla-eligibility@2026.11.09","knowledge":"local:hashing-tfidf-v1","llm":"disabled"}`. Model/knowledge must not be missing for the planned journey. `/readyz` additionally checks database access.
3. If `llm` is `disabled`, use the template/extractive explanation described here. This can mean no Gemini key or AI being disabled in configuration; do not promise live Gemini. Do not expose `.env` on screen.
4. Open Streamlit at `http://localhost:8501` and dashboard login at `http://localhost:3000/login`. Keep API docs in a third, optional tab. Use the same hostname consistently for dashboard pages so its login cookie is retained.
5. In Streamlit, confirm **Alice (applicant, Northwind)** in the sidebar and the default inputs below. In the dashboard, sign in as **Alice Applicant**. These sessions are independent.
6. Rehearse B3 and B4. Keep Alice's successful dashboard application URL handy for replay and isolation. Prepare saved screenshots from [screenshots](./screenshots) as a fallback and label them as recorded evidence, not live output.

Do not regenerate the catalogue, retrain the model, publish policies or reset the database after your final rehearsal. Vehicle counts can drift as price dates age beyond 120 days.

### B2. Opening (2 min)

> "Banks need lending decisions that are fast **and** defensible. This advisor tells an applicant whether they're eligible, how much they can borrow, which cars they can afford, and *why*. Every reason points to a clause in the lender's written policy. AI helps with risk scoring and plain-language explanations, but it never overrules the policy."

### B3. Streamlit: the applicant journey (about 10 min)

#### Step 1 — Submit a customer who passes

Open `http://localhost:8501`. In the sidebar choose **Alice (applicant, Northwind)**, then open **Eligibility**. Check these values rather than assuming an earlier rehearsal left the form unchanged:

| Field | Enter/select |
|---|---|
| Monthly income (INR) | `85000` |
| Credit score / Credit bureau | `745` / `CIBIL` |
| Employment / Employment experience (months) | `salaried` / `72` |
| Active loans / Existing EMIs per month (INR) | `1` / `12000` |
| Loan amount requested (INR) / Tenure (months) | `800000` / `60` |
| Down payment available (INR) / Region | `150000` / `IN-MH` |

Click **Check eligibility** once. Point to **Approved**, the Northwind policy/version, approval probability (baseline about **94.9%**) and policy threshold **0.83**.

**Say:** "This customer meets the lender's ordinary rules, and the model score also clears the lender's required threshold. This is an indicative result, not a real sanction."

Do not read "Confidence" as a separate assurance that the person will repay.

#### Step 2 — Show the amount and its calculation

Click **Loan amount**. Point to **₹8,00,000**, **₹16,899 EMI** (rounded display), **9.75%**, **60 months**, and **₹8,000 processing fee**. Read the calculation table: ₹42,500 maximum total obligations minus ₹12,000 existing obligations leaves ₹30,500 EMI capacity. Expand **Policy clauses applied**.

**Say:** "The amount is calculated, not invented by a chatbot. The customer asked for ₹8 lakh, so we do not offer the full ₹14.43 lakh capacity. The fee is paid separately upfront."

#### Step 3 — Turn the loan into car options

Click **Vehicles**. Set **Body type = Any**, **Fuel = Any**, **Max on-road price = 0**, **Max EMI = 0**, **Sort by = best_fit**. Zero in these two filter controls means "no filter", not a free car. Click **Find vehicles**.

Baseline: **7 of 38 vehicles fit**. Point to one affordable row's **On-road price**, **Loan**, **EMI** and **Upfront cash**. Then point to Lumen Pulse rows marked **Unverified**, and Orion Hauler/Ridgeback marked **Not eligible**. Scroll the table as necessary.

**Say:** "We check both the monthly repayment and the cash needed today. A missing or stale price is not treated as zero, and commercial vehicles are excluded."

#### Step 4 — Demonstrate useful guidance when nothing fits

Still in **Vehicles**, set **Body type = suv**, leave the other filters unrestricted, choose **Sort by = emi**, and click **Find vehicles** again.

Baseline: 15 SUV variants, none affordable (13 not affordable, 2 unverified). Read one displayed guidance message and its actual cash figure; do not memorise a shortfall that may change.

**Say:** "Rather than leave the customer at a dead end, we calculate what change could help, such as more upfront cash or a broader selection. These suggestions do not override the lending rules."

#### Step 5 — Ask a supported and an unsupported question

Below the results, open the **Open vehicle details** selector and choose an **Aurora Quest** variant (prefer the CNG variant). Then click the **Vehicle details** tab. If no vehicle has been selected yet, that tab also offers **Choose a vehicle**. If it is showing a previous choice, select Quest back in the Vehicles tab.

Point to specifications and **Price breakdown**, then expand **Brochure**. Explain that this is a fictional catalogue car. In **Ask about this vehicle**, type `What is the ground clearance?` and press **Enter**.

Expected: an answer containing **200 mm**, with **Dimensions** as evidence. Next type `Does it have a sunroof?` and press **Enter**.

Expected for this brochure: **"I don't know… Please check with the dealer."** with no sources.

**Say:** "The answer is restricted to this model's brochure. Not finding a feature does not prove the car lacks it; the system admits that its documents do not answer the question."

#### Step 6 — Show a rule-based rejection

Return to **Eligibility**. Change income to `22000`, credit score to `580`, employment months to `12`, existing EMIs to `9000`, active loans to `2`, requested amount to `300000`, and down payment to `50000`. Keep salaried, CIBIL, 60 months and Maharashtra. Click **Check eligibility**.

Expected: **Rejected**. Point to **580 vs minimum 650 (NW-2.1)**, **₹22,000 vs minimum ₹25,000 (NW-2.2)**, and **no supported rate band (NW-3.2)**. The model score may also be low; the ordinary rule failures already determine rejection.

**Say:** "We show the customer's actual value beside the requirement and its source clause. A high AI score could not rescue a failed mandatory rule."

Click **Loan amount** briefly to show no sanction. Do not use the now-manual Vehicles calculator as evidence that the rejection was reversed.

#### Step 7 — Explain the rejection with evidence

Click **Explanation**, then **Explain this decision**. Read one short reason and its clause citation. Point to **Written by: template** or **Gemini (validated against the decision)**, whichever actually appears.

Expand **Retrieved policy sources**. The baseline includes relevant Northwind clauses; the exact top retrieved set can vary by index. Distinguish the recorded rejection reasons from the extra passages retrieved to help explain them.

**Say:** "The explanation describes a recorded decision; it cannot change it. With no language service we use a template. Generated drafts are checked for outcome, citations and supported numbers, with template fallback if checks fail."

**Optional multi-lender example:** choose **Ben (applicant, Southbay)** in the sidebar, restore all Step 1 inputs and submit again. Show the Southbay policy and **0.88** threshold. Switching identity clears saved result state; it does not guarantee all form fields reset. Return to Alice if continuing the customer story.

### B4. Next.js dashboard: the lender's view (about 7 min)

Do steps 1–5 for the core lender demo. The later scenarios are optional: choose them instead of extending the meeting without warning.

#### Step 1 — Sign in and create a saved application

Open `http://localhost:3000/login` and click **Alice Applicant**. The top right should show Northwind and the applicant role. Click **New Application** in the left sidebar.

Enter this complete baseline. Do not enter commas or the rupee symbol in amount fields:

| Field | Value |
|---|---|
| Income amount / Income frequency | `120000` / Monthly |
| Credit score / Score provider | `780` / CIBIL |
| Employment category / Months in current employment | Salaried / `36` |
| Existing monthly debt payments / Active loans | `10000` / `1` |
| Requested loan amount / Requested tenure (months) | `1200000` / `60` |
| Cash available for down payment & fees | `400000` |
| Currency / Country / Registration state | INR / India / Maharashtra |
| Vehicle preferences | Leave unselected; use results filters later |

Click **Check eligibility**. The browser opens `/applications/{id}`. Copy this full URL somewhere private for replay and the isolation example.

Expected: **Approved ₹12,00,000**, **8.75%**, EMI **₹24,764.68**, processing fee **₹12,000**.

**Say:** "This is a saved case. Unlike a transient chat, the decision carries the applicant's inputs and the policy/model evidence used."

#### Step 2 — Show evidence and compare cars

Scroll to **Rule trace**. Point to one observed value, requirement, PASS and clause. Point to **Calculation breakdown**, then **Policy sources**. You can also click **Explain this decision** in the Explanation card; show whether the result is AI or **Deterministic template**.

Scroll down to **Vehicles you can afford**. It starts with **Status = Affordable**. Set **Body = suv**, **Fuel = Any**. Baseline: 22 affordable variants overall, 7 affordable SUVs. The status-count badges refer to the unfiltered assessment; do not confuse them with the current filtered rows.

Tick **Compare** for two or three vehicles, then scroll to **Comparison** below the list. Point to on-road price, LTV limit, loan principal, contribution, fee, upfront cash and EMI.

To show why other cars fail, change **Status** to **All** (and **Body** to **Any**), or choose **Unverified** / **Not eligible** specifically.

**Say:** "An approval is only the first step. We show exactly how each car changes the loan and cash requirement."

#### Step 3 — Prove the saved result can be reproduced

Return to **Provenance** near the top. Point to the policy/version, policy hash, engine version, result hash and self-declared inputs. Click **Verify by replay**.

Expected with unchanged assets/engine: **"Reproduced exactly with the recorded policy and engine version."**

**Say:** "We rerun the recorded facts and score against the referenced policy and compare the calculation result. This checks reproducibility; it is different from making a new decision under today's policy."

Do not click **Re-evaluate** when you mean replay.

#### Step 4 — Show the officer's oversight

Click the **Sign out** icon beside the user at the top right. At `/login`, click **Omar Officer**. Click **Applications** in the sidebar and open Alice's saved case. Then click **Audit Log**.

Point to events such as application creation, evaluation and explanation, including actor/action/time.

**Say:** "Applicants see their own cases. A loan officer sees the lender's cases, and important state-changing actions are recorded." Do not claim every page view is audited.

#### Step 5 — Show governed policy, without changing your baseline

Sign out and sign in as **Priya Policy Admin**. Click **Policies**, then **View** beside the published Northwind version. Point to **Executable rules**, **Source clauses**, effective dates, published status and content hash.

**Say:** "The lending thresholds are governed policy values linked to written clauses. A draft cannot affect decisions until an authorised administrator publishes it."

Priya manages policy but cannot read Alice's application. Return as Alice or Omar for any later replay. If time remains, show **Dashboard** (the charts home page) and **Vehicles** in the sidebar. Do not look for a separate navigation item named "Stats".

#### Optional scenarios — rehearse separately

For each application scenario, create a **New Application** and use every Step 1 baseline value except the changes listed. Completed applications cannot simply be edited in place.

| Scenario | Exact change/action | What to show and say |
|---|---|---|
| Valid input, policy rejection | Credit score `600` | Rejected under NW-2.1 and NW-3.2; invalid-format errors are not needed to demonstrate policy rejection |
| Amount reduced safely | Income `50000`, score `745`, existing payments `5000`, request `1500000`; keep other baseline fields | Approved at **₹9,46,000**, **9.75%**, EMI **₹19,983.53**, with the repayment-capacity flag. The ₹20,000 EMI ceiling limits the amount, not the requested ₹15 lakh |
| Approved, but no affordable cars | Cash `0`, all other baseline fields unchanged | Credit approval can coexist with zero affordable cars because contribution and fees need cash |
| Missing information | Start a new blank form, enter only score `780`, click **Save draft**, then **Check eligibility** on its detail page | **Incomplete**, missing fields listed; use **Complete application** to return to the form |
| Tenant isolation | Sign out as Alice, sign in as Ben, paste Alice's saved application URL | Application not found / API 404, not Alice's details. Sign back in as Alice or Omar afterwards |
| Same-tenant ownership | As Arjun, paste Alice's URL | Also not found: lender membership alone does not let an applicant read another applicant's case |

**Optional policy publication, only after the core demo:** prepare a reviewed copy of the complete Northwind structured JSON outside the repository. Use a unique `version` and an `effective_from` later than the existing version's start; use a date on or before demo day only if you intend it to govern new decisions now. Keep thresholds and source clauses consistent. Do not upload the unchanged seeded JSON: its code/version already exists.

As Priya, choose **Policies → Upload structured JSON**, select that prepared file, **View** the resulting draft, inspect its rules and click **Review complete — publish**, then confirm the dialog. A second published policy for the same product and start date is blocked. Sign out, return as Alice/Omar, reopen the saved **older** case and click **Verify by replay**. Publication does not rewrite it. This demonstrates versioning; it does not demonstrate automatic vector-index refresh.

**Optional scanned-policy flow:** only show **Upload scanned policy** if its Gemini transcription/extraction path has been rehearsed successfully. Review page text and extracted rules before creating a draft and publishing. Without document AI, expect visible `TEXT_FAILED` and retry behaviour, not a finished policy. Keep this out of a no-key demo.

### B5. How it was built and why you can trust it (3 min)

Show [EVALUATION.md](./EVALUATION.md) or `notebooks/02_model_training.ipynb`, and mention `01_eda.ipynb` for the data exploration. Make three points:

1. **The data was deliberately messy** (duplicates, typos, outliers, gaps, label noise). Duplicates and category errors are handled; model imputation is fitted inside training folds, not using held-out test statistics.
2. **Four models were compared on expected business cost**, not accuracy alone. The 0.83 threshold reflects an assumed 5:1 cost ratio; a score is not a real-world repayment guarantee.
3. **Safety nets:** a missing/hash-mismatched model sends an otherwise rules-passing case to Needs review; rules still reject ordinary failures. Region and vehicle type are excluded from model features. Automated checks cover money, rules, access control, retrieval and document workflows; the original rehearsal reported 100+ tests.

### B6. Honest limitations and close (2 min)

- Synthetic data. Real data would need fresh EDA, bias testing and drift monitoring.
- The 5:1 cost ratio is an assumption, to be agreed with the lender's credit-risk team.
- Prices exist only for Maharashtra. Missing regional prices cannot be confirmed; some recommendation views omit those rows rather than showing a complete unverified list.
- The documented SQLite load test measured about 48 evaluations/s, not a throughput guarantee for this demo machine. Production scale (Postgres plus horizontal pods) is designed but not yet load-tested. Do not claim live Gemini OCR or Cognito verification without a successful rehearsal in that environment.

> **Close:** "The policy engine calculates the result and records its evidence. The ML gate can make approval stricter, never bypass a failed rule. Document-grounded explanations make the result understandable, and missing evidence is not a licence to guess."

---

## Part C — Stakeholder Q&A crib

| Question | Short answer |
|---|---|
| Why not let AI decide? | A language model does not set lending thresholds. The engine enforces the published policy, including a separate trained model's score gate; optional Gemini only drafts explanations/answers or policy extractions for review. |
| Isn't ML plus rules redundant? | They serve different jobs. In the documented 364 synthetic cases, the model declined 55 of 217 rules-passing cases and approved none of the 147 rule failures. That is additional screening, not proof of prevented real defaults. |
| What if the saved model is missing or changed? | Missing files or a file/card hash mismatch prevent loading. Otherwise rules-passing cases need review; ordinary rule failures still reject. |
| Fairness? | Excluding age, gender, religion, region and vehicle type from model features is not proof of fairness; other inputs may act as proxies. Real-data bias assessment is still required. |
| Policy changed. What about old decisions? | Published versions are immutable through the application. Replay uses recorded inputs/score and the referenced version, checks result/engine consistency, and reports model-artifact identity separately. |
| Can one lender see another's private cases? | Membership and ownership checks restrict access; PostgreSQL adds RLS when that stack is used. Cross-tenant application access returns 404. The vehicle catalogue is intentionally shared. |
| Does it scale? | It's measured at about 48 evaluations/s on one SQLite process. The documented path is Postgres with pooling and horizontal pods. |
| Gemini cost or outage? | Core decisions, money, matching and replay do not require Gemini. Given a local index, template explanations and extractive Q&A remain available. Scanned-policy OCR/extraction needs document AI and fails visibly without it. |

For deeper technical questions, see §8 of [DEMO.md](./DEMO.md).

---

## Part D — Review of DEMO.md: gaps and corrections

**Context:** this section preserves the original guide's comparison with DEMO.md, with source-based clarifications. It is not a new browser test report. DEMO.md targets technical evaluators; use Parts A and B here for a first-time presenter and stakeholder audience.

### Corrections and rehearsal cautions

| DEMO.md says | Actual | Fix |
|---|---|---|
| S3: "filter `suv` and sort by EMI" (implies affordable SUVs) | **No SUV is affordable** for scenario 4.1: 13 are `NOT_AFFORDABLE` and 2 are `UNVERIFIED`, and guidance appears | Run **unfiltered first** (7 affordable, plus the Unverified and Not eligible examples), then SUV or MPV for no-fit guidance |
| S3: "The MPV filter returns nothing" | It returns 2 MPVs, both not affordable, plus guidance (increase down payment, relax filters) | Reword to "nothing *fits*" |
| S3: the statuses `UNVERIFIED` and `NOT_ELIGIBLE` are listed under the SUV/MPV filters | They appear only with **no filter**, or with filter `suv` (Lumen Pulse, unverified) and `van` (commercial, not eligible) | Point at them on the unfiltered list |
| S5: model probability ≈ 0.003 | The complete rejected payload in B3 (request ₹3 lakh, cash ₹50,000) scores **0.0030** with the checked-in model; changing these inputs can change it | Specify every field; say "under 1%" rather than treating a score from a different payload as a correction |
| S5: two reasons | **Three**: NW-2.1, NW-2.2 **and NW-3.2** (no rate band for a score of 580) | Mention the third |
| S2: no EMI or fee figure | EMI **₹16,899.39**, fee **₹8,000**. Clauses cited: NW-3.1, 3.2, 3.3, 3.4, 3.6, 4.2, 3.7 | Add the figures |
| Pre-demo: "do this 15 minutes before" | The first `run.py` installs dependencies and builds Next.js, which takes 10–20 min or more | Do a full run the day before, then use `--skip-install` |
| "About 115 tests" | 107 collected locally (103 pass, 4 skip without Postgres/Redis). The README says 115 | Say "100+ tests" |
| A policy admin can publish, then open Alice's decision | Priya lacks application-reading permissions | Publish as Priya; replay Alice's existing case as Alice or Omar |
| ₹9,46,000 capacity example without a credit score | The rate depends on score; B4's full scenario uses score **745**, rate **9.75%** | Enter all baseline fields and the specified changes |

### Features DEMO.md doesn't cover

- **Next.js README rows 2–6:**
  - vehicle comparison with LTV and shortfall;
  - Explain in the dashboard;
  - a score-600 rejection;
  - an approval **limited by repayment capacity** (₹9,46,000);
  - cash 0 → 0 affordable vehicles.
- **Roles:** the loan officer (Omar), tenant admin (Tara) and Lena, and the **Audit log** page.
- The dashboard charts home page (navigation label **Dashboard**) and the **Vehicles** catalogue page.
- The Streamlit **Demo identity** switch (Ben → Southbay policy, threshold 0.88).
- The Streamlit Vehicles tab's **"supplied terms" mode** (no approved decision: enter your own loan, rate and tenure).
- **`notebooks/01_eda.ipynb`** (EDA is a brief 5.1 requirement), plus [DATA.md](./DATA.md).
- **Ops artefacts:** the RUNBOOK's measured backup and restore drill, the ADRs, and the Kubernetes, Terraform and CI pipeline (mention only).
- **Audience fit:** stakeholders need plain-language framing and a glossary. Parts A and B above provide them.
