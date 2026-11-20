"""Exact mathematics of P5: Shapley on v*, projection, largest remainder, equal awards.

Pure functions on rationals (``fractions.Fraction``) and integer cents; no float is ever
produced. References: ``docs/PHASE_P4_SPECIFICATION.md`` §9.2 to §9.6,
``docs/PHASE_3H_P5_INTEGRATION_PLAN.md`` §6.1 (ID-5) and
``docs/PHASE_P5_ADDENDUM_ID6.md`` (theta = 0).

Objects and the properties that hold for each of them (scope review I2, §5.1):

- ``shapley_exact`` returns phi, the Shapley value of the cover game v*|C: efficiency,
  symmetry, null player, additivity, and phi >= 0 because v* is superadditive;
- ``project_onto_bounds`` returns y, the Euclidean projection of phi onto
  {sum y = V, l <= y <= h}: conserved sum, bounds, KKT form y = clip(phi - lambda*, l, h)
  and the lambda* convention. The Shapley axioms are *not* required of y: a null player
  can receive y > 0 when another unit is saturated;
- ``round_largest_remainder`` returns y' in cents: exact sum, y' in {floor y, floor y + 1},
  bounds kept, ties broken by key;
- ``constrained_equal_awards`` splits a unit payment X over its seats: q_s = min(b_s, tau)
  with sum q = X (equal awards under individual caps).
"""

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from math import factorial, floor


class AllocationMathError(ValueError):
    """An input is outside the domain of a P5 computation, or an exact check failed."""


def _require_int(value, name: str) -> int:
    if type(value) is not int:
        raise AllocationMathError(f"{name} must be an int, not {type(value).__name__}")
    return value


def _require_exact(value, name: str) -> Fraction:
    if type(value) is int:
        return Fraction(value)
    if type(value) is not Fraction:
        raise AllocationMathError(
            f"{name} must be an int or a Fraction, not {type(value).__name__}"
        )
    return value


def _clip(value: Fraction, low, high) -> Fraction:
    return min(max(value, Fraction(low)), Fraction(high))


# --- the cover game, indexed by bit masks -----------------------------------------------


def values_by_mask(members: Sequence[str], cover: Mapping[tuple[str, ...], int]) -> list[int]:
    """values[mask] = v*(S) where bit i of mask selects members[i]; values[0] = 0.

    ``cover`` must define every non-empty subset of ``members`` and nothing else.
    """
    members = tuple(members)
    if len(set(members)) != len(members) or not members:
        raise AllocationMathError("members must be unique and non-empty")
    index = {member: position for position, member in enumerate(members)}
    values: list[int | None] = [None] * (1 << len(members))
    values[0] = 0
    for coalition, value in cover.items():
        mask = 0
        for member in coalition:
            if member not in index:
                raise AllocationMathError(f"cover coalition {coalition} contains a non-member")
            mask |= 1 << index[member]
        if mask == 0 or values[mask] is not None:
            raise AllocationMathError(f"cover coalition {coalition} is empty or repeated")
        values[mask] = _require_int(value, f"v*{coalition}")
    if any(value is None for value in values):
        raise AllocationMathError("the cover must define v* on every non-empty subset")
    return values  # type: ignore[return-value]


# --- Shapley value ----------------------------------------------------------------------


@dataclass(frozen=True)
class ShapleyResult:
    phi: tuple[tuple[str, Fraction], ...]
    marginal_contributions: int


def shapley_exact(members: Sequence[str], values: Sequence[int]) -> ShapleyResult:
    """phi_u = N_u / n!, N_u = sum over S not containing u of |S|!(n-|S|-1)! (v(S+u) - v(S)).

    The numerator is an exact integer; one Fraction is built per member.
    """
    members = tuple(members)
    n = len(members)
    if len(values) != 1 << n or values[0] != 0:
        raise AllocationMathError("values must be indexed by every mask, with values[0] = 0")
    weights = [factorial(size) * factorial(n - size - 1) for size in range(n)]
    phi = []
    for position, member in enumerate(members):
        bit = 1 << position
        numerator = 0
        for mask in range(1 << n):
            if mask & bit:
                continue
            numerator += weights[mask.bit_count()] * (values[mask | bit] - values[mask])
        phi.append((member, Fraction(numerator, factorial(n))))
    return ShapleyResult(tuple(phi), n * (1 << (n - 1)))


# --- projection onto the bounds (specification §9.5) --------------------------------------


@dataclass(frozen=True)
class ProjectionResult:
    y: tuple[tuple[str, Fraction], ...]
    lambda_star: Fraction
    saturated_high: tuple[str, ...]
    saturated_low: tuple[str, ...]
    active: bool


def project_onto_bounds(
    phi: Mapping[str, Fraction],
    total,
    lower: Mapping[str, int],
    upper: Mapping[str, int],
) -> ProjectionResult:
    """Projection of phi onto {sum y = total, lower <= y <= upper}, computed exactly.

    y_u = clip(phi_u - lambda*, lower_u, upper_u), where lambda* is the point of the root
    interval of g(lambda) = sum clip(phi_u - lambda, l_u, h_u) - total that is closest to 0
    (convention lambda* = min(max(0, lambda_lo), lambda_hi)).
    """
    keys = sorted(phi)
    if set(keys) != set(lower) or set(keys) != set(upper) or not keys:
        raise AllocationMathError("phi, lower and upper must describe the same units")
    target = _require_exact(total, "total")
    values = {key: _require_exact(phi[key], f"phi[{key}]") for key in keys}
    for key in keys:
        if _require_int(lower[key], "lower") > _require_int(upper[key], "upper"):
            raise AllocationMathError(f"bounds of {key} are inverted")
    if not sum(lower[key] for key in keys) <= target <= sum(upper[key] for key in keys):
        raise AllocationMathError("the projection is infeasible: total outside the bounds")

    def g(lam: Fraction) -> Fraction:
        return sum(_clip(values[k] - lam, lower[k], upper[k]) for k in keys) - target

    breakpoints = sorted(
        {values[k] - upper[k] for k in keys} | {values[k] - lower[k] for k in keys}
    )
    zero = Fraction(0)
    g_zero = g(zero)
    lam: Fraction | None = None
    if g_zero == 0:
        lam = zero
    elif g_zero < 0:  # roots lie left of 0: take the largest one
        right, g_right = zero, g_zero
        for left in reversed([point for point in breakpoints if point < 0]):
            g_left = g(left)
            if g_left >= 0:
                lam = left + (right - left) * g_left / (g_left - g_right)
                break
            right, g_right = left, g_left
    else:  # roots lie right of 0: take the smallest one
        left, g_left = zero, g_zero
        for right in [point for point in breakpoints if point > 0]:
            g_right = g(right)
            if g_right <= 0:
                lam = left + (right - left) * g_left / (g_left - g_right)
                break
            left, g_left = right, g_right
    if lam is None or g(lam) != 0:
        raise AllocationMathError("no exact root found for a feasible projection")
    y = {k: _clip(values[k] - lam, lower[k], upper[k]) for k in keys}
    if sum(y.values()) != target:
        raise AllocationMathError("the projected allocation does not sum to the total")
    return ProjectionResult(
        y=tuple((k, y[k]) for k in keys),
        lambda_star=lam,
        saturated_high=tuple(k for k in keys if values[k] - lam > upper[k]),
        saturated_low=tuple(k for k in keys if values[k] - lam < lower[k]),
        active=any(y[k] != values[k] for k in keys),
    )


# --- largest remainder (specification §9.6) -----------------------------------------------


def round_largest_remainder(
    values: Mapping[Hashable, Fraction], total: int, upper: Mapping[Hashable, int]
) -> dict:
    """Integer allocation summing to ``total``: floors, then +1 to the largest fractions.

    Ties between equal fractional parts are broken by ascending key. A key whose value is
    an integer never receives a unit; every result stays within [floor, upper].
    """
    _require_int(total, "total")
    keys = sorted(values)
    exact = {key: _require_exact(values[key], f"value[{key}]") for key in keys}
    if sum(exact.values()) != total:
        raise AllocationMathError("values must sum exactly to the total before rounding")
    floors = {key: floor(exact[key]) for key in keys}
    remainder = total - sum(floors.values())
    fractional = [key for key in keys if exact[key] != floors[key]]
    # The fractional parts are < 1 and sum to the remainder r, so r > 0 implies that
    # strictly more than r values are fractional (specification §9.6).
    if remainder < 0 or (remainder > 0 and remainder >= len(fractional)):
        raise AllocationMathError("the remainder is outside [0, number of fractional values)")
    ranked = sorted(fractional, key=lambda key: (-(exact[key] - floors[key]), key))
    result = dict(floors)
    for key in ranked[:remainder]:
        result[key] += 1
    for key in keys:
        if result[key] > _require_int(upper[key], f"upper[{key}]"):
            raise AllocationMathError(f"rounding pushed {key} above its upper bound")
    return result


# --- equal awards under individual caps (plan §6.1, ID-5) --------------------------------


@dataclass(frozen=True)
class EqualAwardsResult:
    tau: Fraction
    amounts: tuple[tuple[Hashable, Fraction], ...]
    saturated: tuple[Hashable, ...]


def constrained_equal_awards(total: int, caps: Mapping[Hashable, int]) -> EqualAwardsResult:
    """q_s = min(b_s, tau) with sum q = total: the most equal split under the caps b_s.

    tau is unique when total < sum caps; when total = sum caps the convention is
    tau = max caps (the vector q = caps is the same for every admissible tau).
    """
    _require_int(total, "total")
    keys = sorted(caps)
    if not keys:
        raise AllocationMathError("at least one seat is required")
    for key in keys:
        if _require_int(caps[key], f"cap[{key}]") < 0:
            raise AllocationMathError("caps must be non-negative")
    capacity = sum(caps[key] for key in keys)
    if not 0 <= total <= capacity:
        raise AllocationMathError("the amount must lie between 0 and the sum of the caps")
    if total == capacity:
        tau = Fraction(max(caps[key] for key in keys))
    else:
        remaining, count = total, len(keys)
        tau = None
        for key in sorted(keys, key=lambda item: (caps[item], item)):
            candidate = Fraction(remaining, count)
            if candidate <= caps[key]:
                tau = candidate
                break
            remaining -= caps[key]
            count -= 1
        if tau is None:
            raise AllocationMathError("no level tau found although total < sum of caps")
    amounts = {key: min(Fraction(caps[key]), tau) for key in keys}
    if sum(amounts.values()) != total:
        raise AllocationMathError("equal awards do not sum to the total")
    return EqualAwardsResult(
        tau=tau,
        amounts=tuple((key, amounts[key]) for key in keys),
        saturated=tuple(key for key in keys if caps[key] < tau),
    )


# --- diagnostics ------------------------------------------------------------------------


def max_core_excess(
    members: Sequence[str], values: Sequence[int], y: Mapping[str, Fraction]
) -> Fraction | None:
    """max over proper non-empty S of v*(S) - sum_{u in S} y_u; None for a singleton.

    Measured only: a positive value means some sub-group would gain by seceding.
    """
    members = tuple(members)
    n = len(members)
    if n < 2:
        return None
    sums = [Fraction(0)] * (1 << n)
    best: Fraction | None = None
    full = (1 << n) - 1
    for mask in range(1, full + 1):
        lowest = (mask & -mask).bit_length() - 1
        sums[mask] = sums[mask & (mask - 1)] + y[members[lowest]]
        if mask != full:
            excess = values[mask] - sums[mask]
            best = excess if best is None or excess > best else best
    return best


def squared_distance(a: Mapping[str, Fraction], b: Mapping[str, Fraction]) -> Fraction:
    return sum(((a[key] - b[key]) ** 2 for key in a), Fraction(0))


def max_distance(a: Mapping[str, Fraction], b: Mapping[str, Fraction]) -> Fraction:
    return max((abs(a[key] - b[key]) for key in a), default=Fraction(0))
