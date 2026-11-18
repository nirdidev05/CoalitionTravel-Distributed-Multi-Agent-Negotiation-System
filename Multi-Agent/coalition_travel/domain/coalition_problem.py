"""Validated coalition game inputs and a pure characteristic function."""

from collections.abc import Mapping
from math import isfinite


class CoalitionProblem:
    """A small, immutable-by-convention coalition game definition.

    Keeping budgets and discount rules explicit removes the hidden global state
    previously captured by ``Entry.coalition_value`` and makes separate requests
    safe to evaluate independently.
    """

    def __init__(self, budgets: Mapping[str, float], discounts: Mapping[int, float]):
        if not budgets:
            raise ValueError("budgets must contain at least one agent")
        if any(not isinstance(name, str) or not name.strip() for name in budgets):
            raise ValueError("agent names must be non-empty strings")
        for name, amount in budgets.items():
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                raise TypeError(f"budget for {name!r} must be numeric")
            if not isfinite(amount) or amount <= 0:
                raise ValueError(f"budget for {name!r} must be finite and positive")

        for size, rate in discounts.items():
            if isinstance(size, bool) or not isinstance(size, int) or size < 1:
                raise ValueError("discount keys must be positive coalition sizes")
            if isinstance(rate, bool) or not isinstance(rate, (int, float)):
                raise TypeError("discount values must be numeric")
            if not isfinite(rate) or not 0 <= rate < 1:
                raise ValueError("discount values must be finite and in [0, 1)")

        self._budgets = dict(budgets)
        self._discounts = dict(discounts)
        self.agents = tuple(budgets)

    @property
    def budgets(self) -> dict[str, float]:
        """Return a defensive copy of the agent budget mapping."""
        return self._budgets.copy()

    @property
    def discounts(self) -> dict[int, float]:
        """Return a defensive copy of the coalition discount mapping."""
        return self._discounts.copy()

    def value(self, coalition) -> float:
        """Return simulated savings; the empty coalition has value zero."""
        members = frozenset(coalition)
        if not members:
            return 0.0
        unknown = members.difference(self._budgets)
        if unknown:
            raise ValueError(f"unknown coalition members: {sorted(unknown)}")
        total_budget = sum(self._budgets[name] for name in members)
        return total_budget * self._discounts.get(len(members), 0.0)
