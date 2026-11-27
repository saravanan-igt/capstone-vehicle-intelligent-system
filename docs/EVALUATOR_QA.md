# Evaluator Questions & Answers

Short, honest answers. If you don't know something, say: *"Good question — I'd verify that in the code/docs rather than guess."*

## A. Project & business

**Q1. What problem does this solve?**
Loan officers must check rules, calculate EMIs, match cars and explain decisions manually. This app does all of it consistently in seconds and shows evidence for every decision.

**Q2. Is this real customer/bank data?**
No. All lenders, applicants, loan history and cars are synthetic. Results are indicative, not a binding loan sanction.

**Q3. Who are the users?**
Applicants (check eligibility, find cars), loan officers (review cases, audit), and policy admins (manage lending rules).

**Q4. Why two frontends?**
Streamlit gives a quick customer journey (required by the brief). Next.js is a professional lender dashboard with saved cases, roles, audit and policy management.

## B. Decision logic

**Q5. Who actually decides — AI or rules?**
The deterministic **policy engine** decides. The ML score is one extra gate (must be ≥ 0.83). Gemini only writes explanation text. "AI informs, policy controls."

**Q6. Can a high ML score approve someone who fails a rule?**
No. If any rule fails (e.g. credit score 580 < 650), the result is Rejected regardless of the ML score.

**Q7. Isn't ML + rules redundant?**
No. Rules check hard limits; ML catches risky combinations the rules miss. In 364 test cases the model declined 55 of 217 rules-passing cases and approved none of the 147 rule failures.

**Q8. How is the loan amount calculated?**
Total EMIs must be ≤ 50% of income (DSR). The leftover EMI room is converted into a maximum loan using the standard EMI formula. We give the lower of what was requested and that capacity, within ₹1 lakh–₹50 lakh.

**Q9. Why can an approved customer see zero affordable cars?**
The bank lends at most 85% of the car price (LTV). The customer must pay the remaining 15% + processing fee from own cash. With little cash, no car fits.

**Q10. What does "Needs review" / "Incomplete" mean?**
Incomplete = required info missing. Needs review = system can't safely decide (e.g. ML model missing). Neither is a rejection.

## C. Machine learning

**Q11. What data was the model trained on?**
12,120 synthetic historical loans, cleaned to 12,000 (duplicates, typos, outliers removed). Split 80/20: 9,600 train, 2,400 test.

**Q12. Which models did you compare and why Gradient Boosting?**
Logistic Regression, Decision Tree, Random Forest, Gradient Boosting — with 5-fold cross-validation. Gradient Boosting had the best ROC AUC (0.96) and the **lowest business cost**.

**Q13. Why threshold 0.83 instead of 0.5?**
We assumed a wrong approval (possible default) costs **5×** a wrong rejection. 0.83 minimises total expected cost. Southbay is stricter at 0.88.

**Q14. What are the model's results?**
Test ROC AUC 0.96, precision 94%, recall 79%, false-approval rate 5.6%.

**Q15. Why not just accuracy?**
Accuracy hides which mistakes happen. In lending a bad approval is far costlier than a missed one, so we optimise business cost.

**Q16. What features does the model use?**
12: income, credit score, employment months, existing EMI, active loans, requested amount, tenure, down payment, employment type, and 3 ratios (EMI-to-income, loan-to-income, down-payment ratio).

**Q17. What about fairness/bias?**
Gender, age, religion, region and vehicle type are **not** used as features. That alone doesn't prove fairness — real data would need a proper bias audit.

**Q18. How do you avoid data leakage?**
Missing values are filled using training-fold statistics only, and the test set is held out until the final evaluation.

## D. RAG & GenAI

**Q19. What is RAG and where is it used?**
Retrieval-Augmented Generation: first search the right documents, then answer using only them. Used for (1) decision explanations from policy text and (2) car Q&A from brochures.

**Q20. How do you prevent hallucinations?**
Search is limited to the relevant policy version or car brochure; answers must cite retrieved sources; numbers must appear in the evidence; otherwise it says **"I don't know"**. These reduce risk — we don't claim zero hallucinations.

**Q21. What if Gemini is down or has no key?**
Everything core still works: decisions, amounts, car matching, replay. Explanations use a template, and Q&A quotes brochure lines using the local TF-IDF index.

**Q22. What is a vector index/embedding?**
Text converted to numbers so similar meaning can be searched quickly. Stored in `vectorstore/`.

## E. Architecture & security

**Q23. What is the tech stack?**
Python FastAPI backend, scikit-learn ML, Streamlit + Next.js frontends, SQLite (local) / PostgreSQL (production), optional Gemini, Docker, Kubernetes, Terraform, GitHub Actions CI.

**Q24. Why a modular monolith, not microservices?**
Simpler to build, test and deploy for this scale; layers (api / application / domain / infrastructure) keep it clean and splittable later.

**Q25. How do you stop one lender seeing another's data?**
Tenant membership + ownership checks in code, plus PostgreSQL Row-Level Security in production. Cross-tenant access returns 404.

**Q26. How is authentication done?**
Demo login locally; OIDC single sign-on (e.g. Amazon Cognito with MFA) in production. Permissions come from roles stored in our database, not from the token.

**Q27. If the policy changes, what happens to old decisions?**
Published policies are versioned and immutable. Each decision stores its inputs, policy version, model score and hashes. **Replay** re-runs it and proves the same result.

**Q28. How do you audit?**
Every important action (create, evaluate, explain, publish) is logged with who, what and when in the Audit Log.

**Q29. Why Decimal for money?**
Normal floating-point numbers cause tiny rounding errors; Decimal gives exact currency maths.

## F. Quality & scale

**Q30. How did you test it?**
100+ automated tests (pytest) covering rules, money maths, permissions, ML, RAG and documents. The brief's sample scenarios 4.1 and 4.2 are automated. CI runs tests and scans Docker images.

**Q31. Does it scale?**
Measured ~48 decisions/second on one SQLite process (p95 141 ms). Production design is PostgreSQL + multiple Kubernetes pods — designed but not load-tested at scale yet.

**Q32. What are the limitations?**
Synthetic data; 5:1 cost ratio is an assumption; prices only for Maharashtra; income is self-declared, not verified; production scale not yet proven.

**Q33. What would you do next?**
Train on real data with bias testing and drift monitoring, connect to credit bureau APIs, verify documents, and load-test the production stack.

**Q34. How did you use AI to build it?**
I used GitHub Copilot as a coding assistant. I designed the requirements, reviewed the outputs, ran the tests and verified the demo scenarios.
