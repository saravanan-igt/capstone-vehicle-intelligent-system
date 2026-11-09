# Evaluation report

This report covers the eligibility model, the sanctioned-amount logic, vehicle recommendation, retrieval-augmented answers and explanations, and the brief's sample scenarios. The full analysis, with plots, is in [notebooks/01_eda.ipynb](../notebooks/01_eda.ipynb) and [notebooks/02_model_training.ipynb](../notebooks/02_model_training.ipynb). Both notebooks are committed with their outputs.

## 1. Which mistakes are costly

| Mistake                                           | Who pays                          | Consequence                                                                                                  |
| ------------------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **False approval**: a risky applicant is approved | Lender                            | Credit loss, collections cost, regulatory exposure                                                           |
| **False rejection**: a good applicant is declined | Customer, and the lender's margin | Lost business; the customer is frustrated but gets a cited reason and can ask for manual review (clause 5.1) |

We assume a false approval costs **5 times** as much as a false rejection (`COST_FALSE_APPROVAL = 5`, `COST_FALSE_REJECTION = 1` in `app/ml/pipeline.py`).

- **Primary metric:** expected cost per application, which is used to choose both the model and its threshold.
- **Also reported:** ROC AUC (ranking), PR AUC, Brier score (calibration), and the false-approval and false-rejection rates.

Accuracy alone is not used, because it treats both errors as equally bad.

## 2. Model comparison (5-fold stratified CV on the 9,600-row training split)

| Model                          | Best params     | CV ROC AUC | CV PR AUC  | CV Brier   | False-approval rate | False-rejection rate | Expected cost | Threshold |
| ------------------------------ | --------------- | ---------- | ---------- | ---------- | ------------------- | -------------------- | ------------- | --------- |
| **Gradient boosting** (HistGB) | lr 0.1, depth 3 | **0.9626** | **0.9600** | **0.0607** | 0.0560              | 0.2016               | **0.2382**    | 0.83      |
| Random forest                  | depth 14        | 0.9615     | 0.9578     | 0.0617     | 0.0600              | 0.1916               | 0.2423        | 0.80      |
| Decision tree                  | depth 8         | 0.9458     | 0.9292     | 0.0662     | 0.0973              | 0.1287               | 0.2957        | 0.80      |
| Logistic regression            | C 10            | 0.8614     | 0.8421     | 0.1478     | 0.0652              | 0.5996               | 0.4719        | 0.82      |

**Choice: gradient boosting.**

- It has the lowest expected cost and the best ranking and calibration.
- It handles missing values natively.
- It is small and fast to score.

The tree ensembles beat logistic regression by a wide margin because eligibility depends on thresholds and interactions; for example, income only matters once the credit score clears a bar. The random forest is a close second. The single tree is easier to read but makes about 70% more false approvals.

**Threshold.** Expected cost is minimised at **0.83**, not at the default 0.5. With a 5:1 cost ratio, the model should approve only when it is quite sure. The threshold is written into the policy (clause NW-3.7 at 0.83; Southbay's stricter prime product uses 0.88), so changing it is a governed policy change, not a code change.

## 3. Held-out test results (2,400 rows, never used for tuning)

| ROC AUC | PR AUC | Precision (Approved) | Recall (Approved) | F1     | Brier  | False-approval rate | False-rejection rate | Expected cost |
| ------- | ------ | -------------------- | ----------------- | ------ | ------ | ------------------- | -------------------- | ------------- |
| 0.9603  | 0.9578 | 0.9413               | 0.7891            | 0.8585 | 0.0635 | **0.0562**          | 0.2109               | 0.2437        |

Confusion matrix at 0.83: TP 1,010 · FP 63 · TN 1,057 · FN 270. The test results match the CV estimates, so there is no sign of overfitting.

**Error analysis.**

- **False approvals** cluster at borderline credit scores (median 694) with larger requested amounts, plus the label noise from manual exceptions.
- **False rejections** have higher existing EMIs (median INR 11,600 against 4,200 overall) and more active loans. These are the customers the lender may lose. They receive the specific reason and the manual-review route.

## 4. How the model and the written policy work together

The deterministic engine applies the policy's rules first, and every failure is cited. The model's approval probability is then compared with the policy's threshold, **only** for applications that pass every rule.

- The model can decline (`CREDIT_RISK_BELOW_THRESHOLD`, citing NW-3.7).
- The model can never approve an application the rules reject. This is enforced in the engine and covered by tests.
- If the model is unavailable or fails its integrity check, the application goes to **manual review**. It is never silently approved.

On 364 complete historical applications (notebook section 6):

| Rules alone → final     | Approved | Rejected                   |
| ----------------------- | -------- | -------------------------- |
| Approved by rules (217) | 162      | 55 (declined by the model) |
| Rejected by rules (147) | 0        | 147                        |

The model's integrity is protected in three ways:

- The model file's SHA-256 must match `model_card.json`, or the API refuses to load it.
- Every decision snapshot records the model version, algorithm, artifact hash, probability and top factors.
- Replay re-runs the engine with the recorded probability and reports `model_unchanged`.

## 5. Sanctioned amount: rules, not a model

The amount is **calculated** by the deterministic engine, not predicted. A regression model could approximate it, but it could not _guarantee_ the brief's hard requirement that the amount never exceeds what the policy allows, and its output could not be traced to clauses.

The calculation:

```
available EMI      = qualifying income x max debt-service ratio (NW-3.1) - existing EMIs
capacity principal = PV(available EMI, policy rate for the score band (NW-3.2), tenure (NW-3.3)), floored to INR 1,000 (NW-4.2)
borrowing capacity = min(capacity principal, product maximum (NW-3.4))
sanctioned amount  = min(requested amount, borrowing capacity)
per vehicle        = min(sanctioned amount, 85% of on-road price (NW-3.5)); fee (NW-3.6) is paid upfront
```

All arithmetic uses `Decimal`. `POST /loan-amount` returns every step, with the clause texts.

## 6. Vehicle recommendation

`POST /vehicles` assesses every catalogue vehicle against the sanctioned amount, the down payment, the policy rate and the tenure. For each vehicle it returns:

- the on-road price, the loan principal after the LTV cap, the EMI and the upfront cash needed;
- a status: `AFFORDABLE`, `NOT_AFFORDABLE` (with the shortfall), `UNVERIFIED` (stale or incomplete price, never treated as zero) or `NOT_ELIGIBLE` (commercial vehicles, citing NW-4.1).

Filters cover body type, fuel, make, minimum seating, price range and maximum EMI. Sorting can be by best fit (the most vehicle the budget covers, then the nearest misses), by price or by EMI.

**No-fit guidance** is computed, not generated:

- the smallest down-payment increase that makes a vehicle affordable;
- what the policy's maximum tenure would allow (re-running the capacity calculation);
- unused repayment capacity, if the applicant asked for less than they could borrow;
- vehicles that fit if the filters are dropped;
- the lowest-priced variant.

These scenarios are covered by `tests/test_advisor.py`.

## 7. Retrieval: explanations and vehicle Q&A

**Index.** There are 218 chunks: 36 policy clauses and 182 brochure sections. Each chunk carries filterable metadata: `doc_type`, `policy_code`, `version`, `clause_id`, `model_key` and `section`.

- With a key, the index uses Gemini `gemini-embedding-001` (768 dimensions, `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY` task types, re-normalised).
- Offline, it uses a deterministic hashed TF-IDF (unigrams and bigrams).

**Retrieval is always scoped.**

- An explanation only searches the exact policy version that made the decision.
- A vehicle question only searches that model's brochure.

**"I don't know" behaviour.** A question is answered only if both of these hold:

- the best chunk's similarity is at or above the index's threshold (local index 0.05, Gemini 0.55);
- the chunk contains at least one of the question's key terms.

Otherwise the reply is "I don't know … please check with the dealer", with no sources.

The thresholds were calibrated on probe questions:

| Question (Aurora Quest)                 | Top similarity (local)       | Result           |
| --------------------------------------- | ---------------------------- | ---------------- |
| What is the ground clearance?           | 0.293 (Dimensions)           | Answered: 200 mm |
| What is the warranty?                   | 0.276 (Warranty and service) | Answered         |
| What is the mileage of the CNG variant? | 0.145 (Variants and prices)  | Answered         |
| Does it have a sunroof? / Android Auto? | 0.000                        | I don't know     |
| Who won the cricket world cup?          | 0.000                        | I don't know     |

**Generated answers are verified.**

- Gemini drafts an answer from the retrieved chunks only, at temperature 0, with a JSON schema.
- Every number in the answer must appear in a cited source, or the draft is discarded and the extractive answer is used.
- If Gemini says the sources do not answer the question, the reply is "I don't know".

**Explanations** give the LLM the decision facts plus the clauses retrieved from that policy version. The draft is rejected if any of these holds:

- its outcome differs from the recorded decision;
- it cites a clause that was neither used nor retrieved;
- it states a number that does not appear in the decision or the clause texts.

When that happens, the deterministic template is used instead. Any reason without a supporting clause (for example, missing data) is labelled as "not contained in the policy" rather than being given a made-up justification. The retrieved sources are stored with each explanation and shown in both UIs.

## 8. Sample scenarios from the brief (automated in `tests/test_advisor.py`)

| Scenario     | Input                                                                                            | Result                                                                                                                                                                                                                                                                                                                |
| ------------ | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 4.1 Approved | Income 85,000; score 745; 6 years; EMIs 12,000; 5 years; down payment 1,50,000; request 8,00,000 | **Approved**. Model probability 0.949 against the 0.83 policy threshold. Sanctioned INR 8,00,000 at 9.75% for 60 months, citing NW-3.1, 3.2, 3.3 and 3.7. The shortlist lists several affordable vehicles, each with EMI and upfront cash. Vehicle details include the brochure, specs, variants and price breakdown. |
| 4.2 Rejected | Income 22,000; score 580; 1 year; EMIs 9,000; 2 active loans                                     | **Rejected**: "credit score is below the policy minimum. Your value 580; required ≥ 650 (NW-2.1)" and "income 22,000 below 25,000 (NW-2.2)". Model probability 0.003. No sanctioned amount; vehicle guidance says the applicant is not eligible.                                                                      |

## 9. Limitations

- The data is synthetic. The model learns the generator, not real credit behaviour. Real data would need fresh EDA, bias testing across protected groups and monitoring for drift.
- The 5:1 cost ratio is an assumption and should be set with the lender's credit-risk team.
- The local retrieval index is lexical. Paraphrased questions (for example "fuel economy" when the brochure says "efficiency") rely on a small synonym list unless the Gemini index is built.
- Prices exist for one region (Maharashtra). Other regions show as `UNVERIFIED` rather than being guessed.
