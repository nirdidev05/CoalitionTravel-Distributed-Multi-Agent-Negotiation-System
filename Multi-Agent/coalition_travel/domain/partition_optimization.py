"""Exact coalition partition algorithms that do not require a solver backend."""

from itertools import combinations

import numpy as np

from coalition_travel.domain.partition import _validate_agents, validate_partition


def _v_idx(agents, v_named, S_indices):
    value = v_named(frozenset(agents[i] for i in S_indices))
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, float, np.number))
        or not np.isfinite(value)
    ):
        raise ValueError("coalition values must be finite numbers")
    return float(value)


def _all_subsets(n):
    for size in range(1, n + 1):
        for combo in combinations(range(n), size):
            yield frozenset(combo)


def dp_search(agents, v):
    _validate_agents(agents)
    n = len(agents)
    if n == 0:
        return 0.0, [], 0
    f = {}
    count = 0

    for size in range(1, n + 1):
        for combo in combinations(range(n), size):
            C = frozenset(combo)
            count += 1
            opt_val = _v_idx(agents, v, C)
            opt_struct = [C]

            if size >= 2:
                pivot = min(C)
                others = sorted(C - {pivot})

                for k1 in range(1, size):
                    for sub in combinations(others, k1 - 1):
                        C1 = frozenset([pivot] + list(sub))
                        C2 = C - C1
                        v1, s1 = f[C1]
                        v2, s2 = f[C2]
                        if v1 + v2 > opt_val:
                            opt_val = v1 + v2
                            opt_struct = s1 + s2

            f[C] = (opt_val, opt_struct)

    S_all = frozenset(range(n))
    val, struct = f[S_all]
    named = [frozenset(agents[i] for i in coalition) for coalition in struct]
    validate_partition(agents, named)
    return val, named, count


def idp_search(agents, v):
    _validate_agents(agents)
    n = len(agents)
    if n == 0:
        return 0.0, [], 0, 0
    f = {}
    UB = {}
    count = 0
    pruned_pairs = 0

    for size in range(1, n + 1):
        UB[size] = 0.0

        for combo in combinations(range(n), size):
            C = frozenset(combo)
            count += 1
            opt_val = _v_idx(agents, v, C)
            opt_struct = [C]

            if size >= 2:
                pivot = min(C)
                others = sorted(C - {pivot})

                for k1 in range(1, size):
                    k2 = size - k1
                    ub_k1 = UB.get(k1, 0.0)
                    ub_k2 = UB.get(k2, 0.0)
                    if ub_k1 + ub_k2 <= opt_val:
                        pruned_pairs += 1
                        continue

                    for sub in combinations(others, k1 - 1):
                        C1 = frozenset([pivot] + list(sub))
                        C2 = C - C1
                        v1, s1 = f[C1]
                        v2, s2 = f[C2]
                        if v1 + v2 > opt_val:
                            opt_val = v1 + v2
                            opt_struct = s1 + s2

            f[C] = (opt_val, opt_struct)
            if opt_val > UB[size]:  # noqa: PLR1730 - preserve the historical update step
                UB[size] = opt_val

    S_all = frozenset(range(n))
    val, struct = f[S_all]
    named = [frozenset(agents[i] for i in coalition) for coalition in struct]
    validate_partition(agents, named)
    return val, named, count, pruned_pairs


def brute_force_search(agents, v, max_agents=10):
    """Reference oracle for small instances; enumerates set partitions exactly."""
    _validate_agents(agents)
    n = len(agents)
    if n > max_agents:
        raise ValueError(f"brute-force oracle is limited to {max_agents} agents")
    if n == 0:
        return 0.0, [], 1

    best_value = -float("inf")
    best_structure = None
    partitions_seen = 0

    def visit(index, blocks):
        nonlocal best_value, best_structure, partitions_seen
        if index == n:
            partitions_seen += 1
            value = sum(_v_idx(agents, v, frozenset(block)) for block in blocks)
            if value > best_value:
                best_value = value
                best_structure = [frozenset(block) for block in blocks]
            return
        for block in blocks:
            block.add(index)
            visit(index + 1, blocks)
            block.remove(index)
        blocks.append({index})
        visit(index + 1, blocks)
        blocks.pop()

    visit(0, [])
    named = [frozenset(agents[i] for i in block) for block in best_structure]
    validate_partition(agents, named)
    return best_value, named, partitions_seen
