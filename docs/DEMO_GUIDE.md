# Demo Guide: Intelligent Vehicle Loan Advisor

Use this guide in two passes:

- **Part A (learn it).** Work through it on your own first, so you can explain every screen.
- **Part B (present it).** A timed, click-by-click script for a stakeholder audience.

Every expected value in this guide was **re-checked against the running system on 2026-11-13**. That check used SQLite, no Gemini key, and seed data from `python run.py --reset-db`. The backend tests passed: 103 passed, 4 skipped (Postgres/Redis-only), 0 failed.

> Companion: [DEMO.md](./DEMO.md) is a deeper, more technical script for evaluators. [Part D](#part-d--review-of-demomd-gaps-and-corrections) lists what it misses and what it gets wrong.

---

## Part A — Understand the project (allow 60–90 minutes)

### A1. The story in one paragraph

An applicant enters their finances. The system:

1. decides **Approved, Rejected, Incomplete or Needs review** under a lender's published lending policy;
2. calculates **how much they can borrow** and shows the maths;
3. lists the **catalogue vehicles they can actually afford**, with EMI and the cash needed upfront;
4. answers **questions about a vehicle** from its brochure, and says "I don't know" when the brochure doesn't cover it;
5. **explains** the decision in plain language, citing policy clauses.

Everything is **synthetic**: the lenders, applicants, loan history and vehicles. Approvals are *indicative*.

### A2. The one idea to remember: "AI informs, rules decide"

| Component | Role | Can it approve? |
|---|---|---|
| **Policy engine** (deterministic rules from the policy JSON) | Source of truth. Checks every written rule and does all the money maths | Yes, but only if every rule passes **and** the model clears the threshold |
| **ML model** (gradient boosting, trained on 12k historical applications) | Risk score *beyond* the rules. Its threshold (0.83) is written in the policy, clause NW-3.7 | It can only **decline** an application the rules passed. It can never approve one the rules rejected |
| **RAG / LLM** (retrieval plus optional Gemini) | Explains decisions and answers vehicle questions, grounded in retrieved text | Never. Its output is validated, and the system falls back to a template or "I don't know" |

### A3. Glossary (stakeholders will ask)

| Term | Meaning here |
|---|---|
| EMI | Equated Monthly Instalment: the fixed monthly repayment |
| DSR / debt-service limit | Total EMIs, including the new one, must be ≤ 50% of monthly income (NW-3.1) |
| LTV | Loan-to-value: the loan can't exceed 85% of the vehicle's on-road price (NW-3.5) |
| On-road price | Ex-showroom price plus registration, insurance and other mandatory charges |
| CIBIL / Experian | Indian credit bureaus. Score range 300–900 |
| Sanctioned amount | min(requested, what repayment capacity allows, product max of ₹50 lakh) |
| RAG | Retrieval-Augmented Generation: fetch the relevant document text first, then answer only from it |
| Tenant | A lender. There are two: **Northwind** (policy NW, model threshold 0.83) and **Southbay** (policy SB, threshold 0.88) |
| RLS | PostgreSQL row-level security: the database itself hides other tenants' rows |
| Replay | Re-run a stored decision against its frozen policy snapshot to prove it's reproducible |

### A4. Policy cheat sheet (Northwind NW-AUTO-STD 2026.1)

| Clause | Rule |
|---|---|
| NW-2.1 | Credit score ≥ 650 (CIBIL or Experian) |
| NW-2.2 | Monthly income ≥ ₹25,000 |
| NW-2.3 | Salaried ≥ 6 months, self-employed ≥ 24 months. Students and the unemployed aren't eligible |
| NW-2.4 | At most 3 active loans |
| NW-3.1 | Total EMIs ≤ 50% of income |
| NW-3.2 | Rate by score: 750–900 → 8.75%, 700–749 → 9.75%, 650–699 → 11.25% |
| NW-3.3 | Tenure 12–84 months |
| NW-3.4 | Loan ₹1,00,000 – ₹50,00,000 |
| NW-3.5 | LTV ≤ 85% of on-road price |
| NW-3.6 | 1% processing fee (min ₹2,500, max ₹15,000), paid upfront |
| NW-3.7 | Model probability must be ≥ 0.83 |
| NW-4.1 | Commercial vehicles excluded. Prices older than 120 days must be re-verified |
| NW-5.1 | Applicants declined on credit risk can request a manual review |

Source: [NW-AUTO-STD-2026.1.md](../data/documents/policy/NW-AUTO-STD-2026.1.md), plus the executable rules in the `.json` next to it.

### A5. Architecture in plain words

- **One backend** (FastAPI, Python), organised in layers:
  - `domain` holds the pure rules and money maths;
  - `application` holds the use cases and permissions;
  - `ml`, `rag` and `infrastructure` hold the database, Gemini, login and metrics;
  - `api` holds the routes.

  Diagram: [ARCHITECTURE.md](./ARCHITECTURE.md) §3.
- **Two frontends:**
  - **Streamlit** (port 8501): the applicant journey the brief asks for.
  - **Next.js dashboard** (port 3000): applications, policy admin, vehicles catalogue, audit log and stats, with role-based sign-in.
- **Data and AI assets:**
  - the trained model in `models/` (hash-checked before it's loaded);
  - the vector index in `vectorstore/`;
  - 26 vehicle brochures and 2 policies in `data/documents/`;
  - notebooks `01_eda` and `02_model_training`.
- **Production story** (documented and tested, but *not* part of the live demo): PostgreSQL with RLS, Redis/BullMQ workers, OIDC SSO, Docker Compose, Kubernetes and Terraform, and CI with image scanning. See the [ADRs](./adr), [RUNBOOK.md](./RUNBOOK.md) and [LOAD_TEST.md](./LOAD_TEST.md).

### A6. Demo identities

| User | Tenant | Role | What they can do |
|---|---|---|---|
| Alice, Arjun | Northwind | Applicant | Create applications and see only **their own** |
| Omar | Northwind | Loan officer | See **all** applications in the tenant and the audit log |
| Priya | Northwind | Policy admin | Upload, publish and ingest policies; see the audit log |
| Tara | Northwind | Tenant admin | Read everything in the tenant and the audit log |
| Ben | Southbay | Applicant | Different lender, so a different policy (threshold 0.88) |
| Lena | Southbay | Loan officer + policy admin | Southbay admin |

Streamlit only offers Alice, Arjun and Ben, via the **Demo identity** selector in the sidebar.

### A7. Numbers to memorise

| Topic | Number |
|---|---|
| Training data | 12,120 raw rows → 12,000 clean. Split 9,600 train / 2,400 test. Defects injected on purpose |
| Models compared | Gradient boosting (chosen), random forest, decision tree, logistic regression |
| Chosen model | CV ROC AUC 0.963. Test ROC AUC 0.960. False-approval rate 5.6% |
| Why threshold 0.83 | A false approval is assumed to cost 5× a false rejection, so the threshold is set to minimise expected cost |
| Rules vs model | On 364 historical cases, the model declined 55 of the 217 the rules approved, and approved **0** of the 147 the rules rejected |
| Load test | About 48 evaluations/s, p95 141 ms, on a single SQLite process. That's below the 150/s target; Postgres plus scaling is the documented path |
| Catalogue | 38 variants: 7 affordable for scenario 4.1, 2 unverified, 2 not eligible (commercial) |

### A8. Hands-on study path (do this once, alone)

1. Read [README.md](../README.md), from the top to "API endpoints".
2. Skim [EVALUATION.md](./EVALUATION.md) (model choice and brief scenarios) and [DATA.md](./DATA.md) (injected data defects).
3. Run the app (see B1) and click through **Part B** yourself, comparing what you see with the expected values.
4. Open `http://127.0.0.1:8000/docs`. Try `POST /predict` → `POST /loan-amount` → `POST /explain` using the `decision_id` returned by `/predict`. The brief endpoints default to Alice, so no headers are needed.
5. Optional for technical audiences: `cd backend; .venv\Scripts\python -m pytest tests/test_advisor.py -q`.

---

## Part B — The stakeholder demo (≈20 min + Q&A)

### B1. Setup (do it the day before, then again 15 min before)

```powershell
cd C:\Bright_Star_Projects\HCL_FDE\capstone-vehicle-intelligent-system
python run.py --reset-db          # first run: installs, npm build, can take 10–20 min
python run.py --reset-db --skip-install   # on the demo day: fast restart
```

- It needs Python 3.12+ and Node 20.9+, and ports 8000, 3000 and 8501 must be free. On this machine, `backend\.venv` is already installed (Python 3.14.7).
- Check http://127.0.0.1:8000/health. Expect: `{"status":"ok","model":"vla-eligibility@2026.11.09","knowledge":"local:hashing-tfidf-v1","llm":"disabled"}`.
  - `llm: disabled` means there's no `GEMINI_API_KEY` in `.env`. The explanations then come from the **template**, and the UI says so. That's fine; just know which mode you're in.
- Open three tabs: Streamlit (8501), the dashboard (3000) and API docs (8000/docs).
- Fallback if anything breaks: use the screenshots in [docs/screenshots/](./screenshots).

### B2. Opening (2 min)

> "Banks need lending decisions that are fast **and** defensible. This advisor tells an applicant whether they're eligible, how much they can borrow, which cars they can afford, and *why*. Every reason points to a clause in the lender's written policy. AI helps with risk scoring and plain-language explanations, but it never overrules the policy."

### B3. Streamlit: the applicant journey (8 min) — http://localhost:8501

| Step | Click | Expected on screen (verified) | Say |
|---|---|---|---|
| 1. Approved (brief 4.1) | **Eligibility** tab → keep the defaults (₹85,000 income, score 745, 72 months, EMIs ₹12,000, 1 loan, ₹8,00,000 over 60 months, ₹1,50,000 down) → **Check eligibility** | **Approved**. Approval probability ≈ **94.9%**, policy threshold 0.83. Main factors: credit score and existing EMI-to-income ratio | "All written rules passed first. Only then did the model's risk score count, and it cleared the lender's 0.83 bar." |
| 2. How much | **Loan amount** tab | Sanctioned **₹8,00,000** at **9.75%** for **60 months**. EMI **₹16,899**. Processing fee **₹8,000** upfront. A calculation table and the clauses applied | "This amount is *calculated*, not predicted, so it can never exceed what the policy allows. Each step is traceable to a clause." |
| 3. What can I buy | **Vehicles** tab → no filters → **Find vehicles** | **7 of 38 fit** (hatchbacks and one sedan: Aurora Nano, Breeze, Orion Metro, Vanta Spark EV, Lumen Glide). Lumen Pulse shows **Unverified** (incomplete or stale price). Orion Hauler and Ridgeback show **Not eligible** (commercial) | "Unverified prices are never treated as zero. Commercial vehicles are excluded by clause 4.1." |
| 4. Nothing fits | Same tab → Body type **suv** → sort **emi** → **Find vehicles** | 15 SUVs, **none affordable** (13 not affordable, 2 Lumen Pulse unverified). Guidance appears: increase the down payment by ₹X, or relax filters | "When nothing fits, the guidance is *computed* from the same maths, not generated, so the numbers are exact." |
| 5. Vehicle Q&A | Pick **Aurora Quest** from "Open vehicle details" (or choose it directly in **Vehicle details**) → ask *"What is the ground clearance?"* → then *"Does it have a sunroof?"* | First: "ground clearance mm: 200", source *Dimensions*. Second: **"I don't know… Please check with the dealer."** with no sources | "It answers only from this car's brochure. If the brochure doesn't say, it admits it, so there are no hallucinations." |
| 6. Rejected (brief 4.2) | **Eligibility** → income 22,000, score 580, months 12, EMIs 9,000, active loans 2 → **Check eligibility** | **Rejected** with 3 reasons: score 580 vs ≥ 650 (**NW-2.1**), income 22,000 vs ≥ 25,000 (**NW-2.2**), and no rate band for the score (**NW-3.2**). Model ≈ 0.4% (for transparency only) | "Every reason shows the applicant's value, the required value and the clause. That's what a customer or regulator needs." |
| 7. Explanation | **Explanation** tab → **Explain this decision** | A plain-language summary with clause citations. "Written by: template" (or Gemini if a key is set). Expand **Retrieved policy sources** to see NW-2.1, 2.2, 3.2 and others | "If AI writes the explanation, it's checked against the recorded decision. Any mismatch falls back to the safe template." |

Optional: switch the sidebar **Demo identity** to **Ben (Southbay)** and re-run step 1. It's a different lender, so a different policy and threshold (0.88). That shows multi-lender support in 30 seconds.

### B4. Next.js dashboard: the lender's view (7 min) — http://localhost:3000

Pick the rows that suit the audience. ★ = recommended for stakeholders.

| # | Sign in as | Do | Expected (verified) | Say |
|---|---|---|---|---|
| ★1 | Alice | **New application**: income 120000, CIBIL 780, salaried 36 mo, obligations 10000, 1 loan, ₹12,00,000 / 60 mo, cash 400000, Maharashtra → **Check eligibility** | **Approved ₹12,00,000** at 8.75%, EMI **₹24,764.68**. Full rule trace with clause texts | "The full audit trail for one decision on one screen." |
| ★2 | Alice | Same page → **Vehicles you can afford** → filter SUV, compare | 22 of 38 vehicles affordable overall, and 7 of 15 SUVs. Per vehicle: LTV, contribution, fees, shortfall. Unverified and stale prices flagged | |
| 3 | Alice | **Explain this decision** | Validated AI or template explanation | |
| 4 | Alice | New application with credit score 600 | Rejected, NW-2.1 (and NW-3.2) | |
| ★5 | Alice | Income 50000, obligations 5000, request 1500000 | Approved at only **₹9,46,000**, flagged **limited by repayment capacity** (EMI ₹19,983.53) | "It doesn't just say yes or no. It tells you the safe amount." |
| 6 | Alice | Same as row 1 but cash 0 | Approved ₹12,00,000, but **0 vehicles affordable** (the LTV cap means a down payment is needed) | |
| ★7 | Alice | Save a draft with only the credit score → evaluate | **INCOMPLETE**, with the missing fields listed | "Missing data never becomes a rejection." |
| ★8 | Ben | Paste Alice's application URL | **404** | "Lenders are fully isolated. Other lenders can't even tell the record exists." |
| 9 | Omar or Tara | **Applications** list, then the **Audit log** | Officers see every tenant application. Every action is audited | "Role-based access: applicants see their own, officers see all." |
| ★10 | Priya | **Policies** → upload a new policy version → publish → open an older decision → **Verify by replay** | Replay still reproducible | "Policy changes never rewrite history. Every past decision can be re-proven." |
| 11 | Priya | **Upload scanned policy** → extract draft rules | Needs a Gemini key. Without one, the document stays `TEXT_FAILED` (retryable). Clauses not quoted verbatim → `CLAUSES_NOT_GROUNDED` | Show this only if a key is configured |

Also worth a 20-second glance: the **Stats** home page (charts) and the **Vehicles** catalogue page.

### B5. How it was built and why you can trust it (3 min)

Show [EVALUATION.md](./EVALUATION.md) or `notebooks/02_model_training.ipynb`, and mention `01_eda.ipynb` for the data exploration. Make three points:

1. **The data was deliberately messy** (duplicates, typos, outliers, gaps, label noise). It was cleaned without leakage.
2. **Four models were compared on business cost**, not accuracy. The threshold is 0.83 because a bad approval is assumed to cost 5× a missed one.
3. **Safety nets:**
   - a tampered or missing model → **Needs review**, never auto-approval;
   - region and vehicle type are excluded as features, and age and gender are never collected;
   - about 107 automated tests, run in CI on SQLite and PostgreSQL.

### B6. Honest limitations and close (2 min)

- Synthetic data. Real data would need fresh EDA, bias testing and drift monitoring.
- The 5:1 cost ratio is an assumption, to be agreed with the lender's credit-risk team.
- Prices exist only for Maharashtra. Other regions show **Unverified**.
- The live demo runs on SQLite at about 48 evaluations/s. Production scale (Postgres plus horizontal pods) is designed but not yet load-tested. Gemini OCR and Cognito SSO aren't verified against live services yet.

> **Close:** "Deterministic rules make every decision reproducible and cited. The ML model can only make the policy stricter. AI explains and answers, grounded and willing to say 'I don't know'."

---

## Part C — Stakeholder Q&A crib

| Question | Short answer |
|---|---|
| Why not let AI decide? | AI can invent thresholds. Lending must be reproducible and auditable, so the rules decide and AI only explains, and that output is validated. |
| Isn't ML plus rules redundant? | No. On 364 cases the model caught 55 risky applications the rules passed, and it never approved one the rules rejected. |
| What if the model breaks? | Its hash is checked at load time. If it's missing or altered, applications go to **Needs review**, never auto-approval. |
| Fairness? | No age, gender or religion is collected. Region and vehicle type are excluded as proxies. Bias testing on real data is the next step. |
| Policy changed. What about old decisions? | Published policies are immutable. Each decision stores its policy snapshot and hash, and replay proves it. |
| Can one lender see another's data? | No. Access is checked by membership and ownership, and Postgres row-level security enforces it too. Cross-tenant access returns 404. |
| Does it scale? | It's measured at about 48 evaluations/s on one SQLite process. The documented path is Postgres with pooling and horizontal pods. |
| Gemini cost or outage? | Everything works without it, using template explanations and extractive answers. Gemini only improves the wording. |

For deeper technical questions, see §8 of [DEMO.md](./DEMO.md).

---

## Part D — Review of DEMO.md: gaps and corrections

**Verdict:** DEMO.md covers all five brief capabilities (5.1–5.5), the architecture, ML, security and limitations well. Its numbers mostly match the running system. Its weak points: it's written for a *technical evaluator*, it has a few factual slips, and it skips several features.

### Corrections (found by running the system)

| DEMO.md says | Actual | Fix |
|---|---|---|
| S3: "filter `suv` and sort by EMI" (implies affordable SUVs) | **No SUV is affordable** for scenario 4.1: 13 are `NOT_AFFORDABLE` and 2 are `UNVERIFIED`, and guidance appears | Run **unfiltered first** (7 affordable, plus the Unverified and Not eligible examples), then SUV or MPV for no-fit guidance |
| S3: "The MPV filter returns nothing" | It returns 2 MPVs, both not affordable, plus guidance (increase down payment, relax filters) | Reword to "nothing *fits*" |
| S3: the statuses `UNVERIFIED` and `NOT_ELIGIBLE` are listed under the SUV/MPV filters | They appear only with **no filter**, or with filter `suv` (Lumen Pulse, unverified) and `van` (commercial, not eligible) | Point at them on the unfiltered list |
| S5: model probability ≈ 0.003 | **0.0044** (≈ 0.4%) | Say "under 1%" |
| S5: two reasons | **Three**: NW-2.1, NW-2.2 **and NW-3.2** (no rate band for a score of 580) | Mention the third |
| S2: no EMI or fee figure | EMI **₹16,899.39**, fee **₹8,000**. Clauses cited: NW-3.1, 3.2, 3.3, 3.4, 3.6, 4.2, 3.7 | Add the figures |
| Pre-demo: "do this 15 minutes before" | The first `run.py` installs dependencies and builds Next.js, which takes 10–20 min or more | Do a full run the day before, then use `--skip-install` |
| "About 115 tests" | 107 collected locally (103 pass, 4 skip without Postgres/Redis). The README says 115 | Say "100+ tests" |

### Features DEMO.md doesn't cover

- **Next.js README rows 2–6:**
  - vehicle comparison with LTV and shortfall;
  - Explain in the dashboard;
  - a score-600 rejection;
  - an approval **limited by repayment capacity** (₹9,46,000);
  - cash 0 → 0 affordable vehicles.
- **Roles:** the loan officer (Omar), tenant admin (Tara) and Lena, and the **Audit log** page.
- The dashboard **Stats** page and the **Vehicles** catalogue page.
- The Streamlit **Demo identity** switch (Ben → Southbay policy, threshold 0.88).
- The Streamlit Vehicles tab's **"supplied terms" mode** (no approved decision: enter your own loan, rate and tenure).
- **`notebooks/01_eda.ipynb`** (EDA is a brief 5.1 requirement), plus [DATA.md](./DATA.md).
- **Ops artefacts:** the RUNBOOK's measured backup and restore drill, the ADRs, and the Kubernetes, Terraform and CI pipeline (mention only).
- **Audience fit:** stakeholders need plain-language framing and a glossary. Parts A and B above provide them.
