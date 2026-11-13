diff --git a/root/.copilot/session-state/8ede4a3ce0f04b7aac16e5c5afd15e4d/files/DEMO_SCRIPT.md b/root/.copilot/session-state/8ede4a3ce0f04b7aac16e5c5afd15e4d/files/DEMO_SCRIPT.md
create file mode 100644
index 0000000..0000000
--- a/dev/null
+++ b/root/.copilot/session-state/8ede4a3ce0f04b7aac16e5c5afd15e4d/files/DEMO_SCRIPT.md
@@ -1,0 +1,224 @@
+# Demo Script — Intelligent Vehicle Loan Advisor (Capstone)
+
+**Audience:** technical evaluator · **Length:** ~25 min talk and demo, plus Q&A · **Repo:** `saravanan-igt/capstone-vehicle-intelligent-system`
+
+> Lines in quotes are suggested talk track. **[DO]** marks an action on screen. ⏱ gives the running time.
+
+---
+
+## 0. Pre-demo checklist (do this 15 minutes before)
+
+- [ ] `python run.py --reset-db` (fresh seed data). Wait until the browser opens.
+  - Streamlit: http://localhost:8501
+  - Next.js dashboard: http://localhost:3000
+  - API docs: http://127.0.0.1:8000/docs
+- [ ] Open http://127.0.0.1:8000/health and confirm that the model version and the active vector index are loaded.
+- [ ] Decide whether you're demoing **with** `GEMINI_API_KEY` (AI-drafted explanations) or **without** it (deterministic template fallback). Both work. Know which one you have.
+- [ ] Open these tabs in your IDE: `backend/app/domain/eligibility.py`, `backend/app/domain/explanation.py`, `backend/app/rag/qa.py`, `backend/app/ml/model.py`, `docs/EVALUATION.md`, `notebooks/02_model_training.ipynb`.
+- [ ] Back-up plan: if the live stack fails, use the screenshots in `docs/screenshots/` and the automated scenarios in `backend/tests/test_advisor.py` (`python -m pytest backend/tests/test_advisor.py -q`).
+- [ ] Reminder to self: **all data is synthetic**, and an approval is *indicative*, not a binding sanction.
+
+---
+
+## 1. Opening — the problem (⏱ 0:00–2:00)
+
+> "This is an Intelligent Vehicle Loan Advisor. An applicant enters their financial details. The system tells them whether they're eligible under a lender's **published lending policy**, how much they can borrow and how that amount was worked out, which vehicles in the catalogue they can actually afford, and *why*, with citations to the exact policy clauses."
+
+> "My key design principle is that **AI informs, rules decide**. Lending decisions have to be reproducible, auditable and explainable at clause level. An LLM on its own can invent thresholds. So I built a deterministic policy engine as the source of truth. On top of it there's an ML model trained on historical loan data, and retrieval-augmented generation that explains decisions and answers vehicle questions, always grounded and always validated."
+
+The four brief capabilities to name:
+1. Eligibility prediction (ML model plus policy rules) — brief 5.1
+2. Sanctioned amount, with the calculation shown — 5.2
+3. Vehicles within budget, with EMI, filters and no-fit guidance — 5.3
+4. Grounded vehicle Q&A ("I don't know") and policy-grounded explanations — 5.4, 5.5
+
+---
+
+## 2. Architecture in 3 minutes (⏱ 2:00–5:00)
+
+**[DO]** Show the Mermaid diagram in `docs/ARCHITECTURE.md` §3.
+
+> "It's a **modular monolith** in FastAPI with hexagonal boundaries. The `domain/` package imports no FastAPI, no ORM, no Redis and no Gemini, so it's pure and easy to test."
+
+Walk the layers:
+| Layer | What to say |
+|---|---|
+| `domain/` | Policy schema, eligibility engine, money maths (Decimal, 34-digit precision), affordability, explanation validation |
+| `application/` | Use cases and authorisation (role, tenant membership and object ownership) |
+| `ml/` | Feature engineering, training pipeline, a hash-checked model loader |
+| `rag/` | Chunking, embeddings (Gemini, or local TF-IDF offline), scoped vector store, Q&A |
+| `infrastructure/` | DB (SQLite locally, PostgreSQL with RLS in prod), Gemini adapters, OIDC, quotas, metrics |
+| `api/` | Brief endpoints (`/predict`, `/loan-amount`, `/vehicles`, `/vehicles/{id}`, `/vehicles/{id}/ask`, `/explain`, `/health`) plus the tenant-aware `/v1` |
+
+> "There are two frontends: **Streamlit** for the applicant journey from the brief, and a **Next.js** dashboard for applications, policy administration and audit. Both are server-side BFFs, so the browser never holds API credentials."
+
+> "Why a monolith? I have one team and one transactional boundary, where the decision, its snapshot and the audit event commit together. I'd split out a service only when a module needs to scale independently, like ingestion workers, which are already a separate process."
+
+---
+
+## 3. Live demo — Streamlit applicant journey (⏱ 5:00–13:00)
+
+Open http://localhost:8501.
+
+### S1 — Approved applicant (brief scenario 4.1)
+**[DO]** Open the **Eligibility** tab and keep the defaults: income 85,000 · score 745 · 72 months employed · EMIs 12,000 · 1 active loan · request ₹8,00,000 over 60 months · down payment ₹1,50,000. Submit.
+
+Point at:
+- **Approved**, with the model probability **≈0.949** against the policy threshold **0.83** (clause NW-3.7)
+- the top factors that drove the model score
+
+> "Notice the order. The engine evaluates **every written rule first**. Only if all of them pass does it compare the model's probability with the threshold, and that threshold lives **in the policy**, not in code. So the model can **decline** an application that passes the rules, but it can **never approve** one the rules reject."
+
+### S2 — Sanctioned amount
+**[DO]** Open the **Loan amount** tab.
+
+Point at: sanctioned **₹8,00,000 at 9.75% for 60 months**, the EMI, the step-by-step calculation and the clauses (NW-3.1, 3.2, 3.3).
+
+> "The amount is **calculated, not predicted**. A regression model can't *guarantee* that the amount never exceeds what the policy allows, and its output can't be traced to clauses."
+
+Say the formula out loud:
+```
+available EMI      = income × max DSR (NW-3.1) − existing EMIs
+capacity principal = PV(available EMI, rate for score band (NW-3.2), tenure (NW-3.3)), floored to ₹1,000
+borrowing capacity = min(capacity, product max (NW-3.4))
+sanctioned         = min(requested, borrowing capacity)
+per vehicle loan   = min(sanctioned, 85% of on-road (NW-3.5)); fee paid upfront (NW-3.6)
+```
+
+### S3 — Vehicles within budget
+**[DO]** Open the **Vehicles** tab, filter `suv` and sort by EMI. Then filter `mpv`.
+
+Point at:
+- each vehicle's on-road price, the loan after the LTV cap, the EMI and the upfront cash needed
+- statuses: `AFFORDABLE`, `NOT_AFFORDABLE` (with the shortfall), `UNVERIFIED` (a stale or incomplete price, **never treated as zero**), `NOT_ELIGIBLE` (commercial vehicles, NW-4.1)
+- the MPV filter returns nothing, so **no-fit guidance** appears: the smallest down-payment increase, what the maximum tenure would allow, unused capacity, and vehicles that fit if the filters are dropped
+
+> "The guidance is **computed, not generated**. It re-runs the capacity maths, so every number is accurate."
+
+### S4 — Vehicle details and grounded Q&A
+**[DO]** Pick a vehicle (for example Aurora Quest) and open **Vehicle details**. Show the specs, variants and price breakdown.
+**[DO]** Ask: *"What is the ground clearance?"* The answer is **200 mm**, with its brochure source.
+**[DO]** Ask: *"Does it have a sunroof?"* The answer is **"I don't know… please check with the dealer"**, with no sources.
+
+> "Retrieval is **scoped to this model's brochure only**. To answer, the system needs two things: a similarity at or above a calibrated threshold (0.05 local, 0.55 Gemini), **and** at least one of the question's key terms in the chunk. If Gemini drafts the answer, every number in it must appear in a cited source, or I fall back to an extractive answer. That's how it says 'I don't know' instead of guessing."
+
+### S5 — Rejected applicant (brief scenario 4.2), then the explanation
+**[DO]** In **Eligibility**, enter income 22,000 · score 580 · 12 months · EMIs 9,000 · 2 active loans. Submit, then open **Explanation**.
+
+Point at:
+- **Rejected**: "Your value 580; required ≥ 650 (NW-2.1)" and "income 22,000 below 25,000 (NW-2.2)"
+- the model probability (≈0.003), shown for transparency only, because the rules already rejected the application
+- the explanation, with **retrieved policy sources** listed
+
+> "Every reason names the **threshold, the applicant's value and the clause**. The explanation retrieves only from the **exact policy version** that made this decision. If an LLM draft is used, I validate three things before showing it: the outcome matches the recorded decision, every citation is a clause that was actually evaluated or retrieved, and every number appears in the decision or the clause text. If any check fails, the deterministic template is used and the fallback reason is stored."
+
+---
+
+## 4. Live demo — Next.js dashboard highlights (⏱ 13:00–17:00)
+
+Open http://localhost:3000. Pick only 3 or 4 of these, depending on time.
+
+| # | Sign in as | Action | Talking point |
+|---|---|---|---|
+| 1 | Alice (Northwind applicant) | New application: income 120000, CIBIL 780, salaried 36 mo, obligations 10000, 1 loan, request 1200000 / 60 mo, cash 400000, Maharashtra → **Check eligibility** | Approved ₹12,00,000, EMI ₹24,764.68, a full rule trace and the clause texts |
+| 7 | Alice | Save a draft with only the credit score, then evaluate | **INCOMPLETE**, with the missing fields listed. "Missing data never produces a rejection or a made-up decision." |
+| 8 | Ben (Southbay) | Paste Alice's application URL | **404**. "Tenant isolation. It's a 404 rather than a 403, so other tenants can't discover the record exists. In Postgres, row-level security enforces this even if application code has a bug." |
+| 9 | Priya (policy admin) | Upload a new policy version → publish → open an older decision → **Verify by replay** | "Published policies are immutable. Each decision stores an immutable snapshot: inputs, the policy version and its SHA-256, each rule result and the model probability. Replay re-runs it and compares hashes." |
+| 10 | Priya | Upload a scanned policy → extract draft rules | "Gemini OCR and extraction produce **untrusted drafts**. A clause that isn't quoted verbatim from its page is rejected with `CLAUSES_NOT_GROUNDED`. Nothing affects decisions until a human confirms it and it's published." |
+
+**[DO]** Optionally show http://127.0.0.1:8000/docs and run `POST /predict` live, to show the API contract and the consistent error envelope `{error:{code,message,correlation_id,details}}`.
+
+---
+
+## 5. ML deep dive (⏱ 17:00–20:00)
+
+**[DO]** Open `notebooks/02_model_training.ipynb` or `docs/EVALUATION.md`.
+
+**Data:** 12,120 synthetic historical applications (53.4% approved), with **deliberately injected defects** to show data preparation:
+- 1% duplicates (dropped)
+- about 4% inconsistent category spellings (normalised)
+- 41 income outliers at ×25 (set to missing)
+- 1.7–3.2% missing values (imputed *inside* the pipeline, fitted on training folds only, so nothing leaks)
+- about 2% label noise (kept, and it shows up as irreducible error)
+
+Derived features: `emi_to_income`, `loan_to_annual_income`, `down_payment_ratio`. `vehicle_type` and `region` are **excluded** because they carry no signal and could proxy for protected characteristics.
+
+**Business-fit metric:**
+> "Accuracy is the wrong metric, because the two errors don't cost the same. A false approval means credit loss for the lender, so I assumed it costs **5×** a false rejection. Both the model and the threshold were chosen by **expected cost**."
+
+| Model | CV ROC AUC | Brier | Expected cost |
+|---|---|---|---|
+| **Gradient boosting (chosen)** | **0.9626** | **0.0607** | **0.2382** |
+| Random forest | 0.9615 | 0.0617 | 0.2423 |
+| Decision tree | 0.9458 | 0.0662 | 0.2957 |
+| Logistic regression | 0.8614 | 0.1478 | 0.4719 |
+
+- The threshold is **0.83**, not 0.5. "With a 5:1 cost ratio, the model should approve only when it's quite sure."
+- On the held-out test set (2,400 rows): ROC AUC 0.9603, **false-approval rate 5.6%**, which matches CV, so there's no sign of overfitting.
+- "Trees beat logistic regression because eligibility depends on thresholds and interactions. For example, income only matters once the credit score clears a bar."
+- Integrity: the API **refuses to load** the model if its SHA-256 doesn't match `model_card.json`. Each decision records the model version, hash, probability and top factors. If the model is missing, the application goes to `NEEDS_REVIEW` and is never silently approved.
+
+**[DO]** Show `backend/app/domain/eligibility.py` near line 180: `CREDIT_RISK_MODEL_UNAVAILABLE` → NEEDS_REVIEW, and `CREDIT_RISK_BELOW_THRESHOLD`.
+
+---
+
+## 6. Engineering quality, security and operations (⏱ 20:00–23:00)
+
+Pick 4 or 5 of these:
+- **Tests:** about 115 tests: unit, end to end, the brief scenarios (`test_advisor.py`), ML and RAG integrity. They run on **both SQLite and PostgreSQL 18** (with RLS, as the non-owner `vla_app` role). One test fails if the documents change without the vector index being rebuilt, and another fails if the migrations drift from the models.
+- **Prompt-injection resistance:** the engine never reads prose, so injected text in a policy can't change a decision (`test_6b_ai_claims_are_validated`).
+- **Security:** an OIDC BFF (Auth Code + PKCE, Cognito-ready), HttpOnly SameSite=Strict cookies, CSRF checks, a tenant derived from membership (never from token claims), a full audit trail, and `extra=forbid` so no sensitive attributes such as age or gender are collected.
+- **Postgres:** row-level security on every tenant table and **append-only grants**, so the app role can't update or delete decisions or audit events.
+- **Reliability:** a transactional outbox to BullMQ workers, idempotent handlers, retries with jitter, DLQ replay, and Prometheus metrics.
+- **Delivery:** Docker Compose (a SQLite demo stack and a full Postgres/Redis stack), CI with image scanning and smoke tests, and reference Terraform/K8s artefacts.
+- **Load test (honest numbers):** about 180 req/s and **48 evaluations/s with p95 141 ms** on a single process with SQLite. It saturates at 16 clients because SQLite allows one writer. "That doesn't meet my assumed peak of 150 evaluations/s. The remedy is Postgres with pooling and horizontal pods, which I documented but haven't measured yet."
+
+---
+
+## 7. Limitations and next steps (⏱ 23:00–25:00)
+
+> "Being upfront about the limits:"
+- The data is **synthetic**, so the model learns the generator, not real credit behaviour. Real data would need fresh EDA, **bias testing** across protected groups and drift monitoring.
+- The **5:1 cost ratio** is an assumption. I'd set it with the lender's credit-risk team.
+- The local retrieval index is lexical. Paraphrased questions depend on a small synonym list unless the Gemini embedding index is built.
+- Prices exist for one region (Maharashtra). Other regions show as `UNVERIFIED` rather than guessed.
+- Not yet verified against live Gemini OCR or a real Cognito pool. The load test hasn't been repeated on PostgreSQL. OpenTelemetry tracing isn't done yet.
+
+**Closing line:**
+> "To summarise: a deterministic engine makes every decision reproducible and cited. The ML model, trained and chosen on business cost, can only make the policy stricter. RAG explains decisions and answers questions, but it's grounded, validated and willing to say 'I don't know'. Thank you. Happy to take questions."
+
+---
+
+## 8. Likely evaluator questions — prepared answers
+
+| Question | Answer |
+|---|---|
+| Why not just let the LLM decide? | Decisions must be reproducible, auditable and cited. LLM output is probabilistic and can invent thresholds. Here the LLM only explains, and its output is validated against the recorded decision. |
+| Why combine ML with rules? Isn't that redundant? | The rules encode the written policy (hard knockouts). The model captures risk *beyond* the rules (interactions, borderline cases). On 364 complete historical applications, 55 of the 217 that the rules approved were declined by the model, and the model approved 0 of the 147 the rules rejected. |
+| Why threshold 0.83? | It minimises expected cost under a 5:1 false-approval to false-rejection cost ratio. It's stored in the policy (NW-3.7; Southbay uses 0.88), so changing it is a governed policy change. |
+| Why gradient boosting over random forest? | Lowest expected cost, best AUC and calibration, native handling of missing values, and fast scoring. The random forest is a close second. |
+| What if the model file is tampered with or missing? | The SHA-256 check against the model card fails, so the API won't load it. Applications go to `NEEDS_REVIEW` and are never auto-approved. |
+| How do you stop hallucinations? | Scoped retrieval, a similarity threshold plus a key-term check, temperature 0 with a JSON schema, and validation of numbers and citations. Any failure falls back to the extractive answer or the template, or to "I don't know". |
+| Why is the sanctioned amount not a model? | A model can't guarantee the amount stays within policy limits, and its output can't be traced to clauses. Decimal maths can. |
+| How does a policy change affect past decisions? | It doesn't. Published versions are immutable, and each decision snapshots its policy version and hash. Replay re-verifies it. |
+| Fairness? | No age, gender or religion is collected (`extra=forbid`). Region and vehicle type are excluded as possible proxies. Bias testing on real data is a stated next step. |
+| How does it scale? | Today it runs as a single process on SQLite, measured at about 48 evaluations/s. The path forward is PostgreSQL with pooling, horizontal pods, partitioned decision and audit tables, and caching vehicle assessments. |
+| Multi-tenancy guarantees? | Composite tenant-aware foreign keys, plus authorisation by membership and ownership, plus Postgres RLS set per transaction. Cross-tenant access returns 404. |
+| What happens with missing data? | The application becomes `INCOMPLETE` or `NEEDS_REVIEW` and is never rejected. The missing fields are listed. |
+
+---
+
+## Appendix — key file pointers
+
+| Topic | File |
+|---|---|
+| Eligibility engine | `backend/app/domain/eligibility.py` |
+| EMI and money maths | `backend/app/domain/money.py` |
+| Vehicle affordability | `backend/app/domain/affordability.py`, `backend/app/application/advisor.py` |
+| Explanation validation | `backend/app/domain/explanation.py` (`validate_explanation`) |
+| Vehicle Q&A ("I don't know") | `backend/app/rag/qa.py` (`answer_question`, `grounded`) |
+| Model loading and scoring | `backend/app/ml/model.py`, `models/model_card.json` |
+| Training | `backend/app/ml/train.py`, `notebooks/02_model_training.ipynb` |
+| Brief endpoints | `backend/app/api/brief.py` |
+| Brief scenario tests | `backend/tests/test_advisor.py` |
+| Policies | `data/documents/policy/NW-AUTO-STD-2026.1.{md,json}` |