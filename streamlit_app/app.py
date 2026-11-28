"""Capstone - Intelligent Vehicle Loan Advisor (Streamlit frontend).

Talks only to the FastAPI service. It runs server-side and acts as a trusted backend-for-frontend in dev auth
mode: the shared secret never reaches the browser. All decisions, amounts and answers come from the API."""

import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
DEMO_USERS = {"Alice (applicant, Northwind)": "u-alice", "Arjun (applicant, Northwind)": "u-arjun",
              "Ben (applicant, Southbay)": "u-ben"}
CUSTOMER_PROFILES = {
    "u-alice": {
        "income": 85000, "score": 745, "provider": "CIBIL", "category": "salaried",
        "months": 72, "active": 1, "emi": 12000, "amount": 800000, "tenure": 60,
        "down": 150000,
    },
    "u-arjun": {
        "income": 75000, "score": 720, "provider": "EXPERIAN", "category": "self_employed",
        "months": 48, "active": 1, "emi": 6000, "amount": 650000, "tenure": 48,
        "down": 120000,
    },
    "u-ben": {
        "income": 22000, "score": 580, "provider": "CIBIL", "category": "unemployed",
        "months": 0, "active": 2, "emi": 9000, "amount": 500000, "tenure": 60,
        "down": 50000,
    },
}
PROFILE_WIDGET_KEYS = (
    "income", "score", "provider", "category", "months", "active",
    "emi", "amount", "tenure", "down", "region",
)
BODY_TYPES = ["", "hatchback", "sedan", "suv", "mpv", "coupe"]
FUEL_TYPES = ["", "petrol", "diesel", "cng", "electric", "hybrid"]


def _shared_secret() -> str:
    secret = os.getenv("DEV_BFF_SHARED_SECRET")
    if secret:
        return secret
    env_file = Path(__file__).resolve().parents[1] / ".env"  # local runs: reuse the repository .env
    if env_file.exists():
        for line in env_file.read_text("utf-8").splitlines():
            if line.startswith("DEV_BFF_SHARED_SECRET="):
                return line.split("=", 1)[1].strip()
    return "local-dev-only"


def api(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    headers = {"X-Dev-User": st.session_state.user, "X-Dev-Secret": _shared_secret()}
    try:
        res = httpx.request(method, f"{API_URL}{path}", headers=headers, timeout=60, **kwargs)
    except httpx.HTTPError as exc:
        st.error(f"Cannot reach the API at {API_URL}: {type(exc).__name__}")
        st.stop()
    if res.status_code >= 400:
        error = res.json().get("error", {}) if res.headers.get("content-type", "").startswith("application/json") else {}
        st.error(f"{error.get('code', res.status_code)}: {error.get('message', res.text[:300])}")
        if error.get("details"):
            st.json(error["details"], expanded=False)
        st.stop()
    return res.json()


def inr(value: Any) -> str:
    if value in (None, ""):
        return "-"
    amount = Decimal(str(value)).quantize(Decimal("1"))
    digits = str(abs(amount))
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    text = ",".join(([head] if head else []) + groups + [tail]) if head or groups else tail
    return f"INR {'-' if amount < 0 else ''}{text}"


def header() -> None:
    st.set_page_config(page_title="Capstone - Vehicle Loan Advisor", page_icon="🚗", layout="wide")
    st.markdown(
        """<style>
        .brand {font-family: 'Montserrat', sans-serif; font-weight: 800; font-size: 2rem; color: #2b3ab0;}
        .brand span {color: #f7b924;}
        .pill {display:inline-block;padding:2px 10px;border-radius:12px;font-size:0.8rem;color:white;}
        .ok {background:#36c98b;} .bad {background:#e5484d;} .warn {background:#ff9a3c;}
        </style>""", unsafe_allow_html=True)
    if "user" not in st.session_state:
        st.session_state.user = "u-alice"
    with st.sidebar:
        st.markdown('<div class="brand">Cap<span>stone</span></div>', unsafe_allow_html=True)
        st.caption("Intelligent Vehicle Loan Advisor - synthetic data, indicative results only")
        label = st.selectbox("Demo identity", list(DEMO_USERS), key="user_label")
        if DEMO_USERS[label] != st.session_state.user:
            st.session_state.user = DEMO_USERS[label]
            st.session_state.tabs_epoch = st.session_state.get("tabs_epoch", 0) + 1
            for key in ("decision", "loan", "shortlist", "explanation", "vehicle_id", "answers"):
                st.session_state.pop(key, None)
            for widget_key in PROFILE_WIDGET_KEYS:
                st.session_state.pop(f"{widget_key}_{st.session_state.user}", None)
        try:
            health = httpx.get(f"{API_URL}/health", timeout=5).json()
            st.success(f"API online - model {health.get('model') or 'unavailable'}")
            st.caption(f"Knowledge index: {health.get('knowledge') or 'unavailable'} | LLM: {health.get('llm')}")
        except httpx.HTTPError:
            st.error(f"API offline ({API_URL})")
        decision = st.session_state.get("decision")
        if decision:
            st.divider()
            st.write("**Current decision**")
            st.write(f"{decision['prediction']} - `{decision['decision_id'][:10]}`")


def eligibility_tab() -> None:
    st.subheader("Check your eligibility")
    profile = CUSTOMER_PROFILES[st.session_state.user]
    profile_key = st.session_state.user
    st.caption(
        f"Profile loaded: income INR {profile['income']:,.0f}, score {profile['score']}, "
        f"{profile['category']}, {profile['months']} months, {profile['active']} active loans"
    )
    with st.form("applicant"):
        c1, c2, c3 = st.columns(3)
        income = c1.number_input("Monthly income (INR)", min_value=0, value=profile["income"], step=1000,
                                 key=f"income_{profile_key}")
        score = c2.number_input("Credit score", min_value=300, max_value=900, value=profile["score"],
                                key=f"score_{profile_key}")
        provider = c3.selectbox("Credit bureau", ["CIBIL", "EXPERIAN"],
                                index=["CIBIL", "EXPERIAN"].index(profile["provider"]),
                                key=f"provider_{profile_key}")
        c1, c2, c3 = st.columns(3)
        category = c1.selectbox("Employment", ["salaried", "self_employed", "student", "unemployed"],
                                index=["salaried", "self_employed", "student", "unemployed"].index(profile["category"]),
                                key=f"category_{profile_key}")
        months = c2.number_input("Employment experience (months)", min_value=0, max_value=600, value=profile["months"],
                                 key=f"months_{profile_key}")
        active = c3.number_input("Active loans", min_value=0, max_value=50, value=profile["active"],
                                 key=f"active_{profile_key}")
        c1, c2, c3 = st.columns(3)
        emi = c1.number_input("Existing EMIs per month (INR)", min_value=0, value=profile["emi"], step=500,
                              key=f"emi_{profile_key}")
        amount = c2.number_input("Loan amount requested (INR)", min_value=0, value=profile["amount"], step=10000,
                                 key=f"amount_{profile_key}")
        tenure = c3.selectbox("Tenure (months)", [12, 24, 36, 48, 60, 72, 84],
                              index=[12, 24, 36, 48, 60, 72, 84].index(profile["tenure"]),
                              key=f"tenure_{profile_key}")
        c1, c2 = st.columns(2)
        down = c1.number_input("Down payment available (INR)", min_value=0, value=profile["down"], step=5000,
                               key=f"down_{profile_key}")
        region = c2.selectbox("Region (catalogue prices are for Maharashtra)", ["IN-MH"],
                              key=f"region_{profile_key}")
        submitted = st.form_submit_button("Check eligibility", type="primary")
    if submitted:
        payload = {"income_amount": str(income), "income_frequency": "monthly", "credit_score": int(score),
                   "score_provider": provider, "employment_category": category, "employment_months": int(months),
                   "existing_monthly_obligations": str(emi), "active_loans": int(active),
                   "requested_principal": str(amount), "requested_tenure_months": int(tenure),
                   "down_payment_available": str(down), "currency": "INR", "jurisdiction": "IN", "region": region}
        st.session_state.decision = api("POST", "/predict", json=payload)
        for key in ("loan", "shortlist", "explanation"):
            st.session_state.pop(key, None)
    decision = st.session_state.get("decision")
    if not decision:
        return
    css = {"Approved": "ok", "Rejected": "bad"}.get(decision["prediction"], "warn")
    st.markdown(f'### Decision: <span class="pill {css}">{decision["prediction"]}</span>', unsafe_allow_html=True)
    policy = decision.get("policy") or {}
    if policy.get("policy_code"):
        st.caption(f"Policy {policy['policy_code']} v{policy['version']} - {policy['lender_name']}")
    model = decision.get("model")
    if model:
        c1, c2, c3 = st.columns(3)
        c1.metric("Model prediction", model["prediction"])
        c2.metric("Approval probability", f"{model['approval_probability']:.1%}")
        c3.metric("Confidence", f"{model['confidence']:.1%}")
        st.caption(f"{model['name']} v{model['version']} ({model['algorithm']}). Policy threshold "
                   f"{model.get('policy_threshold') or '-'}; the model can decline but never overrides policy rules.")
        if model["top_factors"]:
            st.write("Main factors: " + "; ".join(f"{f['label']} {f['direction']} the score"
                                                  for f in model["top_factors"]))
    if decision["reasons"] and decision["prediction"] != "Approved":
        st.write("**Reasons**")
        for r in decision["reasons"]:
            line = f"- {r['text']}"
            if r.get("observed"):
                line += f" Your value: **{r['observed']}**; required: **{r['required']}**."
            line += f" _(clause {r['clause_id']})_" if r.get("clause_id") else " _(not covered by a policy clause)_"
            st.markdown(line)
    if decision["missing_fields"]:
        st.warning("Missing information: " + ", ".join(decision["missing_fields"]))


def loan_tab() -> None:
    decision = st.session_state.get("decision")
    if not decision:
        st.info("Check eligibility first.")
        return
    if "loan" not in st.session_state:
        st.session_state.loan = api("POST", "/loan-amount", json={"decision_id": decision["decision_id"]})
    loan = st.session_state.loan
    if not loan["eligible"]:
        st.error("No loan can be sanctioned for this application.")
        for reason in loan["reasons"]:
            st.write(f"- {reason}")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sanctioned amount", inr(loan["eligible_principal"]))
    c2.metric("EMI", inr(loan["emi"]))
    c3.metric("Rate (nominal p.a.)", f"{Decimal(loan['annual_rate']) * 100:.2f}%")
    c4.metric("Tenure", f"{loan['tenure_months']} months")
    st.caption(f"Processing fee {inr(loan['processing_fee'])} payable upfront. Total repayment "
               f"{inr(loan['total_repayment'])}. Indicative, not a binding sanction.")
    if loan["flags"]:
        st.info("Note: " + ", ".join(f.replace("_", " ").lower() for f in loan["flags"]))
    st.write("**How the amount was calculated**")
    st.table(pd.DataFrame(loan["calculation"]))
    with st.expander("Policy clauses applied"):
        for c in loan["citations"]:
            st.markdown(f"**{c['id']} {c.get('title') or ''}** (page {c['page']}): {c['text']}")


def vehicles_tab() -> None:
    decision = st.session_state.get("decision")
    use_decision = bool(decision and decision["prediction"] == "Approved")
    st.subheader("Vehicles within budget")
    with st.form("filters"):
        body: dict[str, Any] = {}
        if use_decision:
            st.caption("Using your sanctioned amount, down payment, rate and tenure from the decision.")
            body["decision_id"] = decision["decision_id"]
        else:
            st.caption("No approved decision: enter your own terms (this is not a credit decision).")
            c1, c2, c3, c4 = st.columns(4)
            body["sanctioned_amount"] = str(c1.number_input("Loan amount", min_value=0, value=700000, step=10000))
            body["down_payment"] = str(c2.number_input("Down payment", min_value=0, value=150000, step=5000))
            body["tenure_months"] = int(c3.selectbox("Tenure", [12, 24, 36, 48, 60, 72, 84], index=4))
            body["annual_rate"] = str(c4.number_input("Rate p.a. (%)", min_value=1.0, max_value=30.0,
                                                      value=9.75, step=0.25) / 100)
        c1, c2, c3, c4, c5 = st.columns(5)
        body_type = c1.selectbox("Body type", BODY_TYPES, format_func=lambda x: x or "Any")
        fuel = c2.selectbox("Fuel", FUEL_TYPES, format_func=lambda x: x or "Any")
        max_price = c3.number_input("Max on-road price (0 = any)", min_value=0, value=0, step=50000)
        max_emi = c4.number_input("Max EMI (0 = any)", min_value=0, value=0, step=1000)
        sort = c5.selectbox("Sort by", ["best_fit", "price", "emi"])
        submitted = st.form_submit_button("Find vehicles", type="primary")
    if submitted:
        body.update({"sort": sort, "body_type": body_type or None, "fuel_type": fuel or None,
                     "max_price": str(max_price) if max_price else None, "max_emi": str(max_emi) if max_emi else None})
        st.session_state.shortlist = api("POST", "/vehicles", json={k: v for k, v in body.items() if v is not None})
    shortlist = st.session_state.get("shortlist")
    if not shortlist:
        return
    rows = []
    for item in shortlist["items"]:
        v, a = item["vehicle"], item["assessment"]
        values = a["values"]
        rows.append({"id": v["id"], "Vehicle": f"{v['make']} {v['model']} {v['variant']}",
                     "Status": a["status"].replace("_", " ").title(),
                     "On-road price": inr(values.get("on_road_price") or values.get("ex_showroom")),
                     "EMI": inr(values.get("emi")), "Upfront cash": inr(values.get("upfront_cash_required")),
                     "Loan": inr(values.get("loan_principal")), "Body": v["body_type"], "Fuel": v["fuel_type"],
                     "Seats": v["seating"], "Note": ", ".join(r.replace("_", " ").lower() for r in a["reasons"])})
    affordable = sum(1 for r in rows if r["Status"] == "Affordable")
    st.write(f"**{affordable}** of {shortlist['total']} vehicles fit. Sorted by {shortlist['sort'].replace('_', ' ')}.")
    for g in shortlist.get("guidance", []):
        st.info(g["text"] + (f"  _(clauses: {', '.join(g['citations'])})_" if g["citations"] else ""))
    if rows:
        frame = pd.DataFrame(rows).set_index("id")
        st.dataframe(frame, width="stretch", hide_index=True)
        choice = st.selectbox("Open vehicle details", [""] + list(frame.index),
                              format_func=lambda x: frame.loc[x, "Vehicle"] if x else "Select a vehicle")
        if choice:
            st.session_state.vehicle_id = choice
            st.success("Open the 'Vehicle details' tab.")


def vehicle_tab() -> None:
    vehicle_id = st.session_state.get("vehicle_id")
    if not vehicle_id:
        catalogue = api("GET", "/v1/vehicles", params={"limit": 100})["items"]
        options = {f"{v['make']} {v['model']} {v['variant']}": v["id"] for v in catalogue}
        label = st.selectbox("Choose a vehicle", [""] + sorted(options))
        if not label:
            return
        vehicle_id = options[label]
    v = api("GET", f"/vehicles/{vehicle_id}")
    st.subheader(f"{v['make']} {v['model']} {v['variant']}")
    specs = v["specs"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Body / seats", f"{v['body_type']} / {v['seating']}")
    c2.metric("Fuel / gearbox", f"{v['fuel_type']} / {v['transmission']}")
    c3.metric("Efficiency", specs.get("claimed_efficiency") or "-")
    c4.metric("Power", f"{specs.get('power_kw', '-')} kW")
    st.caption(f"Warranty {specs.get('warranty', '-')}; service {specs.get('service_interval', '-')}; colours: "
               f"{', '.join(specs.get('colours', [])) or '-'}")
    if v["prices"]:
        st.write("**Price breakdown**")
        st.table(pd.DataFrame([{"Region": p["region"], "Ex-showroom": inr(p["ex_showroom"]),
                                "Registration": inr(p["registration"]), "Insurance": inr(p["insurance"]),
                                "Other": inr(p["other_charges"]), "On-road": inr(p["on_road"]),
                                "Price date": p["price_date"]} for p in v["prices"]]))
    if specs.get("features"):
        st.write("**Features:** " + ", ".join(specs["features"]))
    if v.get("other_variants"):
        st.write("**Other variants:** " + ", ".join(f"{o['variant']} ({o['fuel_type']}, {o['transmission']})"
                                                  for o in v["other_variants"]))
    with st.expander("Brochure"):
        st.markdown(v.get("brochure") or "_No brochure available._")
    st.write("**Ask about this vehicle**")
    answers = st.session_state.setdefault("answers", {}).setdefault(vehicle_id, [])
    question = st.chat_input("e.g. What is the warranty? What colours are available?")
    if question:
        answers.append(api("POST", f"/vehicles/{vehicle_id}/ask", json={"question": question}))
    for a in answers:
        with st.chat_message("user"):
            st.write(a["question"])
        with st.chat_message("assistant"):
            st.write(a["answer"])
            if a["sources"]:
                st.caption("Sources: " + "; ".join(f"{s['source']} - {s['section']} (score {s['score']})"
                                                  for s in a["sources"]))


def explanation_tab() -> None:
    decision = st.session_state.get("decision")
    if not decision:
        st.info("Check eligibility first.")
        return
    if st.button("Explain this decision", type="primary") or "explanation" in st.session_state:
        if "explanation" not in st.session_state:
            st.session_state.explanation = api("POST", "/explain", json={"decision_id": decision["decision_id"]})
        e = st.session_state.explanation
        content = e["content"]
        st.write(f"**{content['summary']}**")
        for p in content["points"]:
            cites = f" _({', '.join(p['citations'])})_" if p["citations"] else ""
            st.markdown(f"- {p['text']}{cites}")
        st.caption(f"Written by: {'Gemini (validated against the decision)' if e['source'] == 'ai' else 'template'}"
                   + (f" - fallback reason: {e['fallback_reason']}" if e.get("fallback_reason") else ""))
        with st.expander(f"Retrieved policy sources ({e.get('retrieval_index') or 'no index'})"):
            for s in e.get("retrieved_sources", []):
                st.markdown(f"**{s['id']} {s.get('title') or ''}** (page {s['page']}, similarity {s['score']}): "
                            f"{s['text']}")


def main() -> None:
    header()
    tabs = st.tabs(
        ["Eligibility", "Loan amount", "Vehicles", "Vehicle details", "Explanation"],
        key=f"main_tabs_{st.session_state.get('tabs_epoch', 0)}",
    )
    with tabs[0]:
        eligibility_tab()
    decision = st.session_state.get("decision")
    has_decision = decision is not None
    is_approved = bool(decision and decision.get("prediction") == "Approved")
    disabled_tabs = ([] if is_approved else [2, 3, 4]) + ([] if has_decision else [5])
    if disabled_tabs:
        selectors = ", ".join(
            f'[data-testid="stTabs"] [data-testid="stTab"]:nth-child({idx})'
            for idx in disabled_tabs
        )
        st.markdown(
            f"<style>{selectors} {{ pointer-events: none; opacity: 0.4; cursor: not-allowed; }}</style>",
            unsafe_allow_html=True,
        )
    with tabs[1]:
        if is_approved:
            loan_tab()
        else:
            st.info("Loan amount is unlocked once your application is Approved.")
    with tabs[2]:
        if is_approved:
            vehicles_tab()
        else:
            st.info("Vehicles within budget are unlocked once your application is Approved.")
    with tabs[3]:
        if is_approved:
            vehicle_tab()
        else:
            st.info("Vehicle details are unlocked once your application is Approved.")
    with tabs[4]:
        if has_decision:
            explanation_tab()
        else:
            st.info("Check eligibility first to unlock the decision explanation.")


main()
