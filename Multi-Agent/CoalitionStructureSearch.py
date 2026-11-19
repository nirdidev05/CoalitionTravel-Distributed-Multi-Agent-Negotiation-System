"""Compatibility facade for the historical coalition search module."""

from itertools import combinations

import numpy as np
from coalition_travel.domain.cooperative_game import (
    allocate_shapley_payments as _allocate_shapley_payments,
)
from coalition_travel.domain.cooperative_game import (
    shapley_value,
)
from coalition_travel.domain.partition import validate_partition
from coalition_travel.domain.partition_optimization import (
    brute_force_search,
    dp_search,
    idp_search,
)
from coalition_travel.infrastructure.optimization.scipy_ip import ip_search
from scipy.optimize import Bounds, LinearConstraint, milp

__all__ = [
    "Bounds",
    "LinearConstraint",
    "brute_force_search",
    "combinations",
    "dp_search",
    "format_structure",
    "idp_search",
    "ip_search",
    "milp",
    "np",
    "print_result",
    "print_shapley_transfers",
    "shapley_value",
    "validate_partition",
]


def format_structure(struct):
    parts = [
        "{" + ", ".join(str(agent) for agent in sorted(coalition)) + "}" for coalition in struct
    ]
    return "{ " + "  |  ".join(parts) + " }"


def print_result(algo_name, val, struct, stat_label, stat_val, extra=None):
    print(f"\n  ┌─ {algo_name}")
    print(f"  │  SC*           = {format_structure(struct)}")
    print(f"  │  V(SC*)        = {val:.2f}")
    print(f"  │  {stat_label:<14} = {stat_val}")
    if extra:
        print(f"  │  {extra[0]:<14} = {extra[1]}")
    print(f"  └{'─' * 58}")


def print_shapley_transfers(coalition, v, total_price, budgets=None):
    allocation = _allocate_shapley_payments(coalition, v, total_price, budgets)
    if allocation.budget_adjusted:
        print("  Ajustement appliqué pour respecter les budgets individuels.")

    agents_in_c = allocation.agents
    shapley = allocation.shapley_values
    equal_share = allocation.equal_share
    avg_phi = allocation.average_contribution
    payments = allocation.payments

    print("\n  Valeur de Shapley & transferts de tokens (C3a, p.36-45) :")
    print(f"  {'Agent':<10} {'φᵢ(v)':>8}  {'Part payée':>10}  {'Part égale':>10}  Transfert token")
    print(f"  {'─' * 10} {'─' * 8}  {'─' * 10}  {'─' * 10}  {'─' * 22}")
    for agent in agents_in_c:
        phi = shapley[agent]
        token = phi - avg_phi
        payment = payments[agent]
        if abs(token) < 0.005:
            direction = "0.00€  (= moyenne)"
        elif token > 0:
            direction = f"reçoit  +{token:.2f}€  (atout)"
        else:
            direction = f"envoie  {token:.2f}€  (fardeau)"
        print(f"  {agent:<10} {phi:>8.2f}  {payment:>10.2f}€  {equal_share:>10.2f}€  {direction}")
    print(f"  {'─' * 10} {'─' * 8}  {'─' * 10}  {'─' * 10}  {'─' * 22}")
    print(
        f"  {'Σ':<10} {sum(shapley.values()):>8.2f}  {total_price:>10.2f}€  "
        f"(efficacité : Σφᵢ=v(c)={allocation.coalition_value:.2f}, Σtoken=0)"
    )
    return payments
