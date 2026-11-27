# Demo Script (Short) — ~15 minutes

## Before you start (15 min early)

```powershell
cd C:\Bright_Star_Projects\HCL_FDE\capstone-vehicle-intelligent-system
python run.py --skip-install
```

Open 3 tabs: `http://localhost:8501` (Streamlit) · `http://localhost:3000/login` (Dashboard) · `http://127.0.0.1:8000/health` (should say `"status":"ok"`).
Keep `docs/screenshots/` ready as backup. Never show the `.env` file.

---

## 1. Opening — slides (2 min)

> "Banks need loan decisions that are fast **and** explainable. Our advisor tells a customer: Am I eligible? How much can I borrow? Which cars can I afford? And **why**? Every reason points to a clause in the lender's written policy. AI helps with risk scoring and explanations, but it **never overrules the policy**."

Show slides: Problem → Solution → Architecture.

## 2. Approved customer — Streamlit (3 min)

Sidebar: **Alice (Northwind)**. Tab **Eligibility** — check defaults:
income `85000`, score `745`, salaried `72` months, EMIs `12000`, active loans `1`, request `800000`, `60` months, down payment `150000`, region `IN-MH`.

Click **Check eligibility** → **Approved**, probability ~95%, threshold 0.83.

> "Customer passes all policy rules, and the ML score also clears the lender's threshold."

Tab **Loan amount** → ₹8,00,000, EMI ₹16,899, 9.75%, fee ₹8,000.

> "50% of ₹85,000 is ₹42,500. Minus existing ₹12,000 leaves ₹30,500 for a new EMI. The amount is **calculated**, not guessed by AI."

## 3. Cars — Streamlit (2 min)

Tab **Vehicles** → all filters Any / 0, sort `best_fit` → **Find vehicles** (~7 of 38 fit).

> "We check both the monthly EMI and the cash needed today. Stale prices show as *Unverified*; commercial vans are *Not eligible*."

Change Body type = `suv` → Find → none fit, guidance appears.

> "Instead of a dead end, it suggests what would help — more down payment or other options."

## 4. Car Q&A — Streamlit (2 min)

Select **Aurora Quest** → tab **Vehicle details**. Ask:
- `What is the ground clearance?` → **200 mm** with source.
- `Does it have a sunroof?` → **"I don't know… check with the dealer."**

> "Answers come only from this car's brochure. If it's not there, the system says *I don't know* instead of making it up."

## 5. Rejected customer + explanation — Streamlit (2 min)

Tab **Eligibility**: income `22000`, score `580`, months `12`, EMIs `9000`, active loans `2`, request `300000`, down payment `50000` → **Rejected**.

> "We show the customer's value beside the rule: score 580 vs required 650, clause NW-2.1. Even a high AI score cannot rescue a failed rule."

Tab **Explanation** → **Explain this decision** → expand **Retrieved policy sources**.

> "This is RAG: we fetch the actual policy text and explain using it. The explanation cannot change the decision."

## 6. Lender view — Dashboard (3 min)

Login **Alice Applicant** → **New Application**: income `120000`, score `780`, salaried `36`, debts `10000`, loans `1`, request `1200000`, `60` months, cash `400000`, Maharashtra → **Check eligibility** → Approved ₹12,00,000.

- Scroll to **Rule trace** → "Every rule, value, requirement, and clause."
- Click **Verify by replay** → "Reproduced exactly." → "We can prove any old decision later — important for audits."
- Sign out → login **Omar Officer** → **Audit Log** → "Who did what, when."
- (Optional) Login **Priya** → **Policies** → "Rules are versioned; a draft does nothing until published."

## 7. Close — slides (1 min)

> "To summarise: the policy engine decides and records evidence, the ML model adds a stricter risk check, and RAG gives grounded explanations. All data is synthetic; next steps are real data, bias testing and production load testing. Thank you — happy to take questions."

---

**If something breaks:** stay calm, say "Let me show the recorded result", and open `docs/screenshots/`.
