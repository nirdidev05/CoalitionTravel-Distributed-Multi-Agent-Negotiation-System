"""P1.1 — exact conversions between Decimal budgets, integer cents and agent floats."""

import math
import random
from decimal import ROUND_FLOOR, Decimal, localcontext

import pytest
from coalition_travel.domain.money import (
    CENT,
    MAX_CENTS,
    MAX_EUROS,
    MoneyError,
    cents_from_budget,
    decimal_from_cents,
    from_agent_amount,
    require_cents,
    to_agent_amount,
)

SEED = 20261119


# --- require_cents -------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1, 12_345, MAX_CENTS])
def test_require_cents_accepts_ints_inside_the_domain(value):
    assert require_cents(value) == value


@pytest.mark.parametrize("value", [True, False, 1.0, Decimal(1), "1", None])
def test_require_cents_rejects_non_int_types(value):
    with pytest.raises(TypeError):
        require_cents(value)


@pytest.mark.parametrize("value,minimum", [(-1, 0), (0, 1), (MAX_CENTS + 1, 0)])
def test_require_cents_rejects_values_outside_bounds(value, minimum):
    with pytest.raises(MoneyError):
        require_cents(value, minimum=minimum)


@pytest.mark.parametrize("minimum", [-1, MAX_CENTS + 1, 1.0, True])
def test_require_cents_rejects_invalid_minimum(minimum):
    with pytest.raises(ValueError):
        require_cents(10, minimum=minimum)


# --- cents_from_budget ---------------------------------------------------------------


@pytest.mark.parametrize(
    "amount,expected",
    [
        (Decimal("0.01"), 1),
        (Decimal(500), 50_000),
        (Decimal("500.00"), 50_000),
        (Decimal("333.335"), 33_333),  # sub-cent budgets round down to the cent below
        (Decimal("333.339999"), 33_333),
        (Decimal("1E+5"), 10_000_000),
        (Decimal("999999999.99"), MAX_CENTS - 1),
        (MAX_EUROS, MAX_CENTS),
        (Decimal("1234567.0199999999999999999999999999999"), 123_456_701),
    ],
)
def test_cents_from_budget_rounds_down_exactly(amount, expected):
    assert cents_from_budget(amount) == expected


@pytest.mark.parametrize(
    "amount",
    [
        Decimal(0),
        Decimal(-1),
        Decimal("0.004"),
        Decimal("0.0099999999999999999999999999999"),  # 31 digits: true floor is 0 cents
        Decimal("1E-50"),
        MAX_EUROS + CENT,
        Decimal("1E+40"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_cents_from_budget_rejects_amounts_outside_the_domain(amount):
    with pytest.raises(MoneyError):
        cents_from_budget(amount)


@pytest.mark.parametrize("amount", [500, 500.0, True, "500", None])
def test_cents_from_budget_requires_a_decimal(amount):
    with pytest.raises(TypeError):
        cents_from_budget(amount)


def test_multiply_then_round_would_be_wrong_which_is_why_quantize_is_used():
    """Characterizes the Decimal pitfall the module avoids (default 28-digit context)."""
    amount = Decimal("0.0099999999999999999999999999999")
    with localcontext() as context:
        context.prec = 28
        naive = (amount * 100).to_integral_value(rounding=ROUND_FLOOR)
    assert naive == 1  # wrong: the true floor is 0 cents
    with pytest.raises(MoneyError):
        cents_from_budget(amount)


# --- decimal_from_cents --------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "0.00"),
        (1, "0.01"),
        (50_000, "500.00"),
        (MAX_CENTS - 1, "999999999.99"),
        (MAX_CENTS, "1000000000.00"),
    ],
)
def test_decimal_from_cents_is_exact_with_two_decimals(value, expected):
    result = decimal_from_cents(value)
    assert str(result) == expected
    assert result == Decimal(expected)


@pytest.mark.parametrize("value", [-1, MAX_CENTS + 1])
def test_decimal_from_cents_rejects_out_of_domain_values(value):
    with pytest.raises(MoneyError):
        decimal_from_cents(value)


@pytest.mark.parametrize("value", [1.0, True, Decimal(1)])
def test_decimal_from_cents_rejects_non_int(value):
    with pytest.raises(TypeError):
        decimal_from_cents(value)


# --- to_agent_amount / from_agent_amount ---------------------------------------------


def test_to_agent_amount_bounds():
    assert to_agent_amount(0) == 0.0
    assert to_agent_amount(181_440) == 1814.4
    assert to_agent_amount(MAX_CENTS) == 1e9
    with pytest.raises(MoneyError):
        to_agent_amount(MAX_CENTS + 1)
    with pytest.raises(MoneyError):
        to_agent_amount(-1)
    with pytest.raises(TypeError):
        to_agent_amount(1.0)
    with pytest.raises(TypeError):
        to_agent_amount(True)


@pytest.mark.parametrize(
    "amount,expected",
    [
        (0.0, 0),
        (-0.0, 0),
        (0, 0),
        (560, 56_000),
        (1814.4, 181_440),
        (1452.0000000000002, 145_200),  # float artefact seen in the legacy negotiation
        (999999999.99, MAX_CENTS - 1),
        (999999999.995, MAX_CENTS),
        (1e9, MAX_CENTS),
        (math.nextafter(1e9, math.inf), MAX_CENTS),
        (math.nextafter(1e9, 0.0), MAX_CENTS),
    ],
)
def test_from_agent_amount_converts_to_nearest_cent(amount, expected):
    assert from_agent_amount(amount) == expected


@pytest.mark.parametrize(
    "amount",
    [
        1000000000.01,
        1e10,
        MAX_CENTS,  # an int of euros far above the domain
        math.nextafter(0.0, -1.0),
        -0.01,
        -1,
        math.nan,
        math.inf,
        -math.inf,
    ],
)
def test_from_agent_amount_rejects_amounts_outside_the_domain(amount):
    with pytest.raises(MoneyError):
        from_agent_amount(amount)


@pytest.mark.parametrize("amount", [True, False, Decimal("1.00"), "1.00", None])
def test_from_agent_amount_rejects_invalid_types(amount):
    with pytest.raises(TypeError):
        from_agent_amount(amount)


def test_round_trip_cents_agent_cents_is_exact_on_bounds_and_random_samples():
    generator = random.Random(SEED)
    samples = {0, 1, 99, 100, 101, MAX_CENTS - 1, MAX_CENTS}
    samples.update(range(MAX_CENTS - 1000, MAX_CENTS + 1))
    samples.update(generator.randrange(0, MAX_CENTS + 1) for _ in range(10_000))
    for value in samples:
        assert from_agent_amount(to_agent_amount(value)) == value


def test_from_agent_amount_is_monotonic():
    generator = random.Random(SEED)
    for _ in range(5_000):
        low = generator.uniform(0.0, 1e9)
        high = math.nextafter(low, math.inf)
        assert from_agent_amount(low) <= from_agent_amount(high)
        other = generator.uniform(0.0, 1e9)
        first, second = sorted((low, other))
        assert from_agent_amount(first) <= from_agent_amount(second)


def test_half_cent_ties_exist_only_for_odd_eighths_of_a_euro():
    """(2k+1)/200 EUR is exactly representable iff 2k+1 is a multiple of 25 (= m/8 EUR)."""
    generator = random.Random(SEED)
    ties = 0
    with localcontext() as context:
        context.prec = 100  # exact products of up to ~55-digit binary expansions
        for _ in range(5_000):
            # 25 * odd / 200 must stay within the 10^9 EUR domain: odd < 8 * 10^9.
            odd = 2 * generator.randrange(0, 4_000_000_000) + 1
            for candidate in (odd, 25 * odd):
                amount = candidate / 200
                is_tie = Decimal(amount) * 200 == Decimal(candidate)
                assert is_tie == (candidate % 25 == 0)
                if is_tie:
                    ties += 1
                    lower = (candidate - 1) // 2
                    expected = lower if lower % 2 == 0 else lower + 1  # half-even
                    assert from_agent_amount(amount) == expected
    assert ties > 0


@pytest.mark.parametrize(
    "amount,expected",
    [(0.125, 12), (0.375, 38), (0.625, 62), (0.875, 88), (1814.125, 181_412)],
)
def test_exact_half_cent_ties_round_half_even(amount, expected):
    assert from_agent_amount(amount) == expected


# --- independence from the global Decimal context ------------------------------------


def test_results_do_not_depend_on_a_reduced_global_decimal_context():
    """Another module lowering getcontext().prec must not change any conversion."""
    budgets = [Decimal("999999999.99"), MAX_EUROS, Decimal("333.335"), Decimal("123456.78")]
    cents_values = [MAX_CENTS, MAX_CENTS - 1, MAX_CENTS - 99, 1, 12_345_678]
    agent_amounts = [999999999.99, 1e9, 1814.4, 0.01]
    expected = (
        [cents_from_budget(amount) for amount in budgets],
        [decimal_from_cents(value) for value in cents_values],
        [str(decimal_from_cents(value)) for value in cents_values],
        [from_agent_amount(amount) for amount in agent_amounts],
    )
    with localcontext() as context:
        context.prec = 5
        reduced = (
            [cents_from_budget(amount) for amount in budgets],
            [decimal_from_cents(value) for value in cents_values],
            [str(decimal_from_cents(value)) for value in cents_values],
            [from_agent_amount(amount) for amount in agent_amounts],
        )
        for value in range(MAX_CENTS - 1000, MAX_CENTS + 1):
            assert from_agent_amount(to_agent_amount(value)) == value
    assert reduced == expected
    assert expected[0] == [MAX_CENTS - 1, MAX_CENTS, 33_333, 12_345_678]
    assert expected[2][:2] == ["1000000000.00", "999999999.99"]
