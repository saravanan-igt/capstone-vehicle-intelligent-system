from datetime import date
from decimal import Decimal

from app.domain.affordability import PriceQuote, assess_vehicle
from tests.conftest import nw_policy

AS_OF = date(2026, 11, 7)


def quote(**kw: object) -> PriceQuote:
    base: dict[str, object] = dict(vehicle_id="v1", category="private", region="IN-MH", currency="INR",
                                   ex_showroom=Decimal("1680000"), registration=Decimal("168000"),
                                   insurance=Decimal("67200"), other_charges=Decimal("15000"),
                                   price_date=date(2026, 10, 1))
    base.update(kw)
    return PriceQuote(**base)  # type: ignore[arg-type]


def assess(q: PriceQuote, capacity: str = "2422000", down: str = "400000"):  # type: ignore[no-untyped-def]
    return assess_vehicle(q, policy=nw_policy(), borrowing_capacity=Decimal(capacity), down_payment=Decimal(down),
                          annual_rate=Decimal("0.0875"), tenure_months=60, as_of=AS_OF)


def test_affordable_vehicle_ltv_and_contribution() -> None:
    a = assess(quote())
    assert a.status == "AFFORDABLE"
    v = a.values
    assert v["on_road_price"] == "1930200.00"
    assert v["ltv_loan_limit"] == "1640000.00"  # floor(1,930,200 x 0.85, 1000)
    assert v["loan_principal"] == "1640000.00"
    assert v["required_contribution"] == "290200.00"
    assert v["processing_fee"] == "15000.00"  # 1% capped at 15,000
    assert v["upfront_cash_required"] == "305200.00"


def test_down_payment_shortfall_is_not_affordable() -> None:
    a = assess(quote(), down="200000")
    assert a.status == "NOT_AFFORDABLE" and a.reasons == ["DOWN_PAYMENT_SHORTFALL"]
    assert a.values["shortfall"] == "105200.00"


def test_capacity_constrains_before_ltv() -> None:
    a = assess(quote(), capacity="1000000", down="1000000")
    assert a.values["loan_principal"] == "1000000.00"
    assert a.values["required_contribution"] == "930200.00"


def test_missing_on_road_cost_is_unverified_not_zero() -> None:
    a = assess(quote(insurance=None))
    assert a.status == "UNVERIFIED" and a.reasons == ["ON_ROAD_COST_INCOMPLETE"]
    assert "on_road_price" not in a.values


def test_stale_price_is_unverified() -> None:
    a = assess(quote(price_date=date(2025, 1, 15)))
    assert a.status == "UNVERIFIED" and a.reasons == ["STALE_PRICE"] and a.citations == ["NW-4.1"]


def test_excluded_category() -> None:
    assert assess(quote(category="commercial")).status == "NOT_ELIGIBLE"
