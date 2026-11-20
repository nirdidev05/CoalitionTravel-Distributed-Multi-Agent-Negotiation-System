"""Cooperative game value calculations and Shapley based payment allocation."""

from dataclasses import dataclass
from itertools import combinations
from math import factorial

import numpy as np


def shapley_value(agent, coalition, v):
    agents_in_c = sorted(coalition)
    n = len(agents_in_c)
    others = [a for a in agents_in_c if a != agent]
    phi = 0.0
    for size in range(len(others) + 1):
        for subset in combinations(others, size):
            S_set = frozenset(subset)
            weight = factorial(size) * factorial(n - size - 1) / factorial(n)
            phi += weight * (v(S_set | {agent}) - v(S_set))
    return phi


@dataclass(frozen=True)
class ShapleyAllocation:
    """Calculated allocation data consumed by the legacy presentation wrapper."""

    agents: tuple
    coalition_value: float
    equal_share: float
    average_contribution: float
    shapley_values: dict
    payments: dict
    budget_adjusted: bool


def allocate_shapley_payments(coalition, v, total_price, budgets=None):
    agents_in_c = sorted(coalition)
    n = len(agents_in_c)
    if n == 0:
        raise ValueError("coalition must not be empty")
    if (
        isinstance(total_price, bool)
        or not isinstance(total_price, (int, float, np.number))
        or total_price < 0
        or not np.isfinite(total_price)
    ):
        raise ValueError("total_price must be a finite non-negative number")
    coalition_value = v(frozenset(agents_in_c))
    equal_share = total_price / n
    average_contribution = coalition_value / n
    shapley_values = {
        agent: shapley_value(agent, frozenset(agents_in_c), v) for agent in agents_in_c
    }
    raw_payments = {
        agent: equal_share - (shapley_values[agent] - average_contribution) for agent in agents_in_c
    }
    if budgets is None:
        payments = raw_payments
    else:
        if set(budgets) != set(agents_in_c):
            raise ValueError("budgets must contain exactly the coalition members")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float, np.number))
            or not np.isfinite(value)
            or value < 0
            for value in budgets.values()
        ):
            raise ValueError("member budgets must be finite non-negative numbers")
        if total_price > sum(budgets.values()) + 1e-8:
            raise ValueError("agreement exceeds the coalition's combined budget")
        payments = {
            agent: min(max(raw_payments[agent], 0.0), budgets[agent]) for agent in agents_in_c
        }
        remainder = total_price - sum(payments.values())
        while remainder > 1e-8:
            eligible = [agent for agent in agents_in_c if budgets[agent] - payments[agent] > 1e-8]
            if not eligible:
                raise ValueError("cannot allocate agreement within member budgets")
            increment = remainder / len(eligible)
            used = 0.0
            for agent in eligible:
                addition = min(increment, budgets[agent] - payments[agent])
                payments[agent] += addition
                used += addition
            remainder -= used

    budget_adjusted = any(
        abs(payments[agent] - raw_payments[agent]) > 1e-8 for agent in agents_in_c
    )
    return ShapleyAllocation(
        agents=tuple(agents_in_c),
        coalition_value=coalition_value,
        equal_share=equal_share,
        average_contribution=average_contribution,
        shapley_values=shapley_values,
        payments=payments,
        budget_adjusted=budget_adjusted,
    )
