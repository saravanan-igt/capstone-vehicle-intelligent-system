from decimal import Decimal

import pytest

from app.domain.money import emi, floor_to, monthly_rate_from_nominal_annual, principal_for_emi, round_half_up


def test_emi_standard_reference_value() -> None:
    # 1,00,000 at 12% nominal for 12 months -> textbook EMI 8884.88
    assert round_half_up(emi(Decimal("100000"), Decimal("0.01"), 12)) == Decimal("8884.88")


def test_zero_interest_emi_is_principal_over_n() -> None:
    assert emi(Decimal("120000"), Decimal("0"), 12) == Decimal("10000")
    assert round_half_up(emi(Decimal("100000"), Decimal("0"), 7)) == Decimal("14285.71")


def test_principal_for_emi_inverts_emi() -> None:
    r = monthly_rate_from_nominal_annual(Decimal("0.0875"))
    p = principal_for_emi(Decimal("50000"), r, 60)
    assert abs(emi(p, r, 60) - Decimal("50000")) < Decimal("0.000001")
    assert principal_for_emi(Decimal("500"), Decimal("0"), 24) == Decimal("12000")


def test_non_positive_inputs() -> None:
    assert emi(Decimal("0"), Decimal("0.01"), 12) == 0
    assert principal_for_emi(Decimal("0"), Decimal("0.01"), 12) == 0
    with pytest.raises(ValueError):
        emi(Decimal("1000"), Decimal("0.01"), 0)
    with pytest.raises(ValueError):
        emi(Decimal("1000"), Decimal("-0.01"), 12)


def test_rounding_rules() -> None:
    assert floor_to(Decimal("1234567.89"), Decimal("1000")) == Decimal("1234000.00")
    assert round_half_up(Decimal("10.005")) == Decimal("10.01")
    assert round_half_up(Decimal("10.004999")) == Decimal("10.00")
