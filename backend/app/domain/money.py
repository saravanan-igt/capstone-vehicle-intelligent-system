"""Decimal money arithmetic. No floats are used anywhere in lending calculations."""

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
_PRECISION = 34


def round_half_up(amount: Decimal, step: Decimal = CENT) -> Decimal:
    return amount.quantize(step, rounding=ROUND_HALF_UP)


def floor_to(amount: Decimal, step: Decimal) -> Decimal:
    """Floor to a multiple of `step` (e.g. 1000). Conservative for principal limits."""
    if step <= 0:
        raise ValueError("step must be positive")
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        units = (amount / step).to_integral_value(rounding=ROUND_FLOOR)
        return (units * step).quantize(CENT)


def monthly_rate_from_nominal_annual(annual_rate: Decimal) -> Decimal:
    """Nominal annual rate compounded monthly -> periodic monthly rate (annual / 12)."""
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        return annual_rate / Decimal(12)


def emi(principal: Decimal, monthly_rate: Decimal, months: int) -> Decimal:
    """EMI = P*r*(1+r)^n / ((1+r)^n - 1); zero-rate case EMI = P/n. Unrounded."""
    if months <= 0:
        raise ValueError("months must be positive")
    if monthly_rate < 0:
        raise ValueError("rate must be non-negative")
    if principal <= 0:
        return ZERO
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        if monthly_rate == 0:
            return principal / Decimal(months)
        factor = (ONE + monthly_rate) ** months
        return principal * monthly_rate * factor / (factor - ONE)


def principal_for_emi(installment: Decimal, monthly_rate: Decimal, months: int) -> Decimal:
    """Inverse of `emi`: the principal fully amortised by `installment` over `months`. Unrounded."""
    if months <= 0:
        raise ValueError("months must be positive")
    if monthly_rate < 0:
        raise ValueError("rate must be non-negative")
    if installment <= 0:
        return ZERO
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        if monthly_rate == 0:
            return installment * Decimal(months)
        factor = (ONE + monthly_rate) ** months
        return installment * (factor - ONE) / (monthly_rate * factor)


def fmt(amount: Decimal | None) -> str | None:
    return None if amount is None else str(round_half_up(amount))
