"""Integer-programming partition search implemented with SciPy and HiGHS."""

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from coalition_travel.domain.partition import _validate_agents, validate_partition
from coalition_travel.domain.partition_optimization import _all_subsets, _v_idx


def ip_search(agents, v):
    _validate_agents(agents)
    n = len(agents)
    if n == 0:
        return 0.0, [], 0

    all_coalitions = list(_all_subsets(n))
    m = len(all_coalitions)
    values = np.array([_v_idx(agents, v, coalition) for coalition in all_coalitions], dtype=float)

    A = np.zeros((n, m), dtype=float)
    for j, coalition in enumerate(all_coalitions):
        for i in coalition:
            A[i, j] = 1.0

    result = milp(
        c=-values,
        constraints=LinearConstraint(A, lb=np.ones(n), ub=np.ones(n)),
        integrality=np.ones(m),
        bounds=Bounds(lb=0.0, ub=1.0),
    )

    if result.status != 0:
        raise RuntimeError(f"ILP solver failed: {result.message}")

    selected = [j for j in range(m) if result.x[j] > 0.5]
    opt_val = -result.fun
    opt_struct = [frozenset(agents[i] for i in all_coalitions[j]) for j in selected]
    validate_partition(agents, opt_struct)

    return opt_val, opt_struct, m
