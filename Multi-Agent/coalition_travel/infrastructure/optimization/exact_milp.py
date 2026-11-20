"""Optional mixed-integer linear programme (MILP) for one component (P4.4-bis).

Set partitioning: one binary column per feasible coalition (singletons included), one
equality row per player, objective max sum of w(C) (solved as min of -w). This is an
integer *linear* programme solved by HiGHS through SciPy. It is not the anytime "IP"
algorithm of Rahwan et al. (2009) taught in the course (specification section 6.3).

Two confidence levels are never confused:

- ``milp_solver_optimal``: HiGHS status 0 and steps 1 to 5 succeed; optimal only up to
  the solver tolerances (mip_abs_gap 1e-6, feasibility tolerances), floating point;
- ``milp_certified_exact``: steps 1 to 6 succeed, step 6 being the exact integer
  equality of W with ``idp_search`` on the same table.

Anything weaker is ``milp_feasible_unverified``. The official P4 structure always comes
from ``idp_search``; the MILP is a control and a research object only.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from coalition_travel.application.partition_solver import ComponentSolution, PartitionInvalid
from coalition_travel.domain.coalition_game import Coalition, CoalitionGame

MilpLabel = Literal["milp_certified_exact", "milp_solver_optimal", "milp_feasible_unverified"]
INTEGRALITY_TOLERANCE = 1e-6
DUAL_BOUND_MARGIN = 0.5


class SolverNotOptimal(RuntimeError):
    """HiGHS stopped without a usable solution (status 4, or status 1 without x)."""


class SolverAnomaly(RuntimeError):
    """Status 2 (infeasible) or 3 (unbounded): impossible for this model."""


class IntegralityViolation(RuntimeError):
    """A selected variable is not within 1e-6 of 0 or 1."""


class CertificateFailure(RuntimeError):
    """The exact score differs from idp_search: the MILP solution is discarded."""


@dataclass(frozen=True)
class MilpSolution:
    component_id: str
    label: MilpLabel
    structure: tuple[Coalition, ...]
    value_cents: int
    tie_break_score: int
    solver_status: int
    solver_message: str
    dual_bound: float | None


def solve_component_milp(
    game: CoalitionGame, *, certify_with: ComponentSolution | None = None
) -> MilpSolution:
    """Solve with HiGHS (mip_rel_gap = 0) and apply the acceptance procedure."""
    if not isinstance(game, CoalitionGame):
        raise TypeError("game must be a CoalitionGame")
    if certify_with is not None and certify_with.component_id != game.component_id:
        raise ValueError("the certificate must come from the same component")
    game.require_numeric_domain()
    columns = game.feasible_coalitions()
    index = {unit: row for row, unit in enumerate(game.players)}
    matrix = np.zeros((game.n, len(columns)))
    for column, coalition in enumerate(columns):
        for unit in coalition:
            matrix[index[unit], column] = 1.0
    weights = np.array([game.weight(coalition) for coalition in columns], dtype=float)
    result = milp(
        c=-weights,
        constraints=LinearConstraint(matrix, lb=np.ones(game.n), ub=np.ones(game.n)),
        integrality=np.ones(len(columns)),
        bounds=Bounds(lb=0.0, ub=1.0),
        options={"mip_rel_gap": 0.0},
    )
    status = int(result.status)
    message = str(result.message)
    if status in (2, 3):
        raise SolverAnomaly(f"HiGHS status {status} ({message}) is impossible for this model")
    if status not in (0, 1) or result.x is None:
        raise SolverNotOptimal(f"HiGHS status {status}: {message}")
    # Step 2: integrality of every variable.
    values = np.asarray(result.x, dtype=float)
    if np.any(np.minimum(np.abs(values), np.abs(values - 1.0)) > INTEGRALITY_TOLERANCE):
        raise IntegralityViolation("a variable is not within 1e-6 of 0 or 1")
    # Steps 3 and 4: exact partition and exact integer score.
    selected = [columns[column] for column in range(len(columns)) if values[column] > 0.5]
    try:
        structure = game.check_structure(selected)
    except (TypeError, ValueError) as exc:
        raise PartitionInvalid(f"MILP selection is not an exact partition: {exc}") from exc
    score = game.structure_score(structure)
    value = game.structure_value(structure)
    dual = result.mip_dual_bound
    dual_bound = None if dual is None else float(dual)
    label: MilpLabel = "milp_feasible_unverified"
    # Step 5: status 0 and a finite, consistent dual bound (minimizing -W, integer objective).
    if (
        status == 0
        and dual_bound is not None
        and isfinite(dual_bound)
        and (-score) - dual_bound <= DUAL_BOUND_MARGIN
    ):
        label = "milp_solver_optimal"
    # Step 6: exact certificate against idp_search.
    if certify_with is not None:
        if score != certify_with.tie_break_score:
            raise CertificateFailure(
                f"MILP score {score} differs from idp_search {certify_with.tie_break_score}"
            )
        if label == "milp_solver_optimal":
            label = "milp_certified_exact"
    return MilpSolution(
        component_id=game.component_id,
        label=label,
        structure=structure,
        value_cents=value,
        tie_break_score=score,
        solver_status=status,
        solver_message=message,
        dual_bound=dual_bound,
    )
