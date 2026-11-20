"""Exact money conversions between Decimal inputs, integer cents and legacy agent floats.

Business contracts carry integer cents. ``Decimal`` is only used at input and display
boundaries, and ``float`` only at the boundary of the historical agents.

Every context-dependent ``Decimal`` operation in this module (``quantize``, ``scaleb``,
arithmetic) runs inside ``localcontext(MONEY_CONTEXT)``; constructors and comparisons are
exact in any context and are the only operations performed outside it. A caller that
lowers ``getcontext().prec`` therefore cannot change any result.
"""

from decimal import (
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from math import isfinite

Cents = int

MAX_CENTS: Cents = 100_000_000_000  # 10^9 EUR, the supported monetary domain
MAX_EUROS = Decimal("1000000000.00")  # exact literal, independent of any context
CENT = Decimal("0.01")
# 34 significant digits >> 12 digits of MAX_CENTS: quantize/scaleb results always fit.
MONEY_CONTEXT = Context(
    prec=34,
    rounding=ROUND_HALF_EVEN,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)
# Pre-filter for agent amounts; the exact bound is enforced on the rounded cents.
_MAX_AGENT_AMOUNT = MAX_CENTS / 100 + 0.01


class MoneyError(ValueError):
    """A monetary amount is outside the supported domain or cannot be represented."""


def require_cents(value: object, *, minimum: int = 0, name: str = "amount") -> Cents:
    """Return ``value`` if it is an int number of cents within [minimum, MAX_CENTS]."""
    if type(minimum) is not int or not 0 <= minimum <= MAX_CENTS:
        raise ValueError("minimum must be an int between 0 and MAX_CENTS")
    if type(value) is not int:
        raise TypeError(f"{name} must be an int number of cents, not {type(value).__name__}")
    if value < minimum or value > MAX_CENTS:
        raise MoneyError(f"{name} must be between {minimum} and {MAX_CENTS} cents, got {value}")
    return value


def cents_from_budget(amount: Decimal) -> Cents:
    """Convert a positive Decimal budget to cents, rounding down to the cent below.

    Rounding down keeps a budget a valid cap. The result must be at least one cent.
    """
    if not isinstance(amount, Decimal):
        raise TypeError(f"budget amount must be a Decimal, not {type(amount).__name__}")
    if not amount.is_finite():
        raise MoneyError("budget amount must be finite")
    if amount <= 0:
        raise MoneyError("budget amount must be positive")
    if amount > MAX_EUROS:
        raise MoneyError(f"budget amount must not exceed {MAX_EUROS} EUR")
    with localcontext(MONEY_CONTEXT):
        # quantize is exact on its operand: never multiply first and round afterwards.
        cents = int(amount.quantize(CENT, rounding=ROUND_FLOOR).scaleb(2))
    return require_cents(cents, minimum=1, name="budget")


def decimal_from_cents(value: Cents) -> Decimal:
    """Return the exact two-decimal EUR amount for a number of cents."""
    require_cents(value, name="value")
    with localcontext(MONEY_CONTEXT):
        return Decimal(value).scaleb(-2)


def to_agent_amount(value: Cents) -> float:
    """Convert cents to the float price used by the historical agents.

    ``int / int`` is correctly rounded, so the result is the double nearest to value/100.
    """
    require_cents(value, name="value")
    return value / 100


def from_agent_amount(amount: float) -> Cents:
    """Convert a historical agent price (a float, or an int) back to cents, half-even.

    The conversion uses the exact binary value of the float. A half cent (2k+1)/200 EUR
    is exactly representable only when 2k+1 is a multiple of 25, i.e. for odd multiples
    of 1/8 EUR (x.125, x.375, x.625, x.875); only those amounts are ties, and half-even
    resolves them deterministically (0.125 -> 12 cents, 0.375 -> 38 cents). Rounding to
    the nearest cent is monotonic, so an amount between two cent-exact bounds stays
    between them after conversion.
    """
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise TypeError(f"agent amount must be an int or a float, not {type(amount).__name__}")
    if isinstance(amount, float) and not isfinite(amount):
        raise MoneyError("agent amount must be finite")
    if amount < 0:
        raise MoneyError("agent amount must not be negative")
    if amount > _MAX_AGENT_AMOUNT:
        raise MoneyError(f"agent amount must not exceed {MAX_CENTS} cents")
    with localcontext(MONEY_CONTEXT):
        cents = int(Decimal(amount).quantize(CENT, rounding=ROUND_HALF_EVEN).scaleb(2))
    return require_cents(cents, name="agent amount")
