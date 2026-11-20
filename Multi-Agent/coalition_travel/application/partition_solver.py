"""Solver adapter around the unmodified historical partition algorithms (M5).

The historical solvers (``dp_search``, ``idp_search``, ``brute_force_search``) need a
finite value for every non-empty subset. The adapter hands them the pure weight function
of the game: w(C) = K*v(C) - (|C|-1) on F, -1 outside F (sections 3.4 and 4 of the
specification). Proposition 4 guarantees that no optimal partition contains a penalized
block; proposition 1 that the optimum maximizes the savings first, then the number of
blocks; proposition 3 that V = ceil(W / K).

Naming: ``idp_search`` is the historical name of a dynamic programme with pruning by size
bounds. It is exact, it follows the same trajectory as ``dp_search``, and it is not the
IDP of Rahwan and Jennings (2008) taught in the course (specification section 6.3).

Every solver result is re-checked exactly in integers: partition, feasibility of each
block, recomputed score equal to the solver's float, and decoded savings. Cross-checks
compare the exact score (and, for ``dp_search``, the structure itself).
"""

from dataclasses import dataclass
from typing import Literal

from coalition_travel.application.coalition_candidates import DEFAULT_LIMITS, FormationLimits
from coalition_travel.domain.coalition_game import Coalition, CoalitionGame, canonical_structure
from coalition_travel.domain.partition_optimization import (
    brute_force_search,
    dp_search,
    idp_search,
)

SolverMethod = Literal["idp", "dp", "brute_force"]
SOLVER_METHODS = ("idp", "dp", "brute_force")
ComponentStatus = Literal["optimized", "singleton_component", "no_beneficial_coalition"]


class SolverDisagreement(RuntimeError):
    """Two exact solvers, or a solver and its exact recomputation, disagree."""


class PartitionInvalid(RuntimeError):
    """A solver returned a structure that is not a partition into feasible blocks."""


@dataclass(frozen=True)
class ComponentSolution:
    component_id: str
    players: tuple[str, ...]
    structure: tuple[Coalition, ...]
    value_cents: int
    block_count: int
    tie_break_score: int
    method: str
    checks: tuple[str, ...]
    evaluated_coalitions: int
    pruned_pairs: int | None
    status: ComponentStatus

    @property
    def coalitions(self) -> tuple[Coalition, ...]:
        """Blocks with at least two units."""
        return tuple(block for block in self.structure if len(block) > 1)


def _run(method: str, game: CoalitionGame, limits: FormationLimits):
    """Call one historical solver; return (float score, structure, counters)."""
    agents = list(game.players)
    weight = game.weight
    if method == "idp":
        score, structure, evaluated, pruned = idp_search(agents, weight)
        return score, structure, evaluated, pruned
    if method == "dp":
        score, structure, evaluated = dp_search(agents, weight)
        return score, structure, evaluated, None
    if method == "brute_force":
        score, structure, partitions = brute_force_search(
            agents, weight, max_agents=limits.brute_force_max_units
        )
        return score, structure, partitions, None
    raise ValueError(f"unknown solver method {method!r}")


def _exact(game: CoalitionGame, method: str, raw_score, raw_structure) -> tuple:
    """Validate a solver output exactly; return (structure, score, value)."""
    try:
        structure = game.check_structure(raw_structure)
    except (TypeError, ValueError) as exc:
        raise PartitionInvalid(f"{method} returned an invalid structure: {exc}") from exc
    score = game.structure_score(structure)
    if float(score) != raw_score:
        raise SolverDisagreement(
            f"{method} reported {raw_score}, the exact recomputation gives {score}"
        )
    value = game.structure_value(structure)
    if game.decode(score) != value:
        raise SolverDisagreement("decoded savings differ from the sum of block values")
    return structure, score, value


def solve_component(
    game: CoalitionGame,
    *,
    method: SolverMethod = "idp",
    cross_checks: tuple[SolverMethod, ...] = ("dp", "brute_force"),
    limits: FormationLimits = DEFAULT_LIMITS,
) -> ComponentSolution:
    """Optimal partition of one component, with exact cross-checks.

    A component of one unit is its own singleton, without solver call. ``brute_force`` is
    run only when the component has at most ``limits.brute_force_max_units`` units.
    """
    if not isinstance(game, CoalitionGame):
        raise TypeError("game must be a CoalitionGame")
    if method not in SOLVER_METHODS:
        raise ValueError(f"unknown solver method {method!r}")
    if any(check not in SOLVER_METHODS or check == method for check in cross_checks):
        raise ValueError("cross_checks must be other solver methods")
    if game.n == 1:
        structure = canonical_structure([game.players])
        return ComponentSolution(
            component_id=game.component_id,
            players=game.players,
            structure=structure,
            value_cents=0,
            block_count=1,
            tie_break_score=0,
            method="singleton",
            checks=(),
            evaluated_coalitions=0,
            pruned_pairs=None,
            status="singleton_component",
        )
    game.require_numeric_domain()
    if method == "brute_force" and game.n > limits.brute_force_max_units:
        raise ValueError("brute_force is limited to brute_force_max_units units")
    raw_score, raw_structure, evaluated, pruned = _run(method, game, limits)
    structure, score, value = _exact(game, method, raw_score, raw_structure)
    performed = []
    for check in cross_checks:
        if check == "brute_force" and game.n > limits.brute_force_max_units:
            continue
        check_score, check_structure, _, _ = _run(check, game, limits)
        check_structure, exact_score, _ = _exact(game, check, check_score, check_structure)
        if exact_score != score:
            raise SolverDisagreement(f"{check} score {exact_score} differs from {method} {score}")
        if {method, check} == {"idp", "dp"} and check_structure != structure:
            raise SolverDisagreement("idp_search and dp_search must return the same structure")
        performed.append(check)
    status: ComponentStatus = (
        "optimized" if any(len(block) > 1 for block in structure) else "no_beneficial_coalition"
    )
    return ComponentSolution(
        component_id=game.component_id,
        players=game.players,
        structure=structure,
        value_cents=value,
        block_count=len(structure),
        tie_break_score=score,
        method=method,
        checks=tuple(performed),
        evaluated_coalitions=evaluated,
        pruned_pairs=pruned,
        status=status,
    )
