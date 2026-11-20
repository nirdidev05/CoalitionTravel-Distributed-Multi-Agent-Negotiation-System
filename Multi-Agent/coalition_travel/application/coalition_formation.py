"""Coalition formation for a lot: orchestration of M1 to M5, one component at a time (M9).

Pipeline (specification section 2):

    lot_admissibility ─► H2 ─► compute_reference_costs (cached oracle)
        └─► for each effective component K, in component_id order:
              enumerate_candidates ─► check_structural_feasibility ─► negotiate_candidate
              ─► build_game (exclusion, v({u}) = 0 checked) ─► solve_component

Independence of components (section 5): under H2 and the independence of seller mandates
(I1), with one oracle configuration (I2), the optimal structure of the lot is the union of
the optimal structures of its components. A component above the operational limits is
reported as ``component_too_large`` and its units as unresolved: they are never presented
as optimally served.

Identifiers (section 10): ``formation_run_id`` hashes every input that determines the
result; ``result_sha256`` hashes the canonical result. No duration, timestamp or cache
statistic enters either digest.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from coalition_travel.application.coalition_candidates import (
    DEFAULT_LIMITS,
    ComponentTooLarge,
    FormationLimits,
    enumerate_candidates,
)
from coalition_travel.application.coalition_costs import (
    CoalitionCost,
    OracleConfigurationMismatch,
    negotiate_candidate,
)
from coalition_travel.application.coalition_feasibility import check_structural_feasibility
from coalition_travel.application.lot_admissibility import (
    LotAdmissibilityResult,
    UnitExclusion,
    lot_admissibility,
)
from coalition_travel.application.negotiation_cache import (
    CacheStatistics,
    CachingNegotiationOracle,
    ConfiguredNegotiationOracle,
)
from coalition_travel.application.partition_solver import (
    ComponentSolution,
    SolverMethod,
    solve_component,
)
from coalition_travel.application.reference_costs import (
    ReferenceCostsResult,
    compute_reference_costs,
)
from coalition_travel.domain.coalition_game import (
    INFEASIBLE_PENALTY,
    Coalition,
    CoalitionGame,
    build_game,
)
from coalition_travel.domain.offer import OfferCatalog
from coalition_travel.domain.travel_unit import TravelUnit

FORMATION_ADAPTER_VERSION = "p4-formation-v1"
FormationStatus = Literal["optimized", "incomplete", "capacity_model_violated", "no_eligible_units"]
ComponentFormationStatus = Literal[
    "optimized", "singleton_component", "no_beneficial_coalition", "component_too_large"
]


class FormationConsistencyError(RuntimeError):
    """An internal identity of the formation result does not hold."""


@dataclass(frozen=True)
class FormedBlock:
    """One block of the final structure and the agreement that realizes it."""

    unit_ids: tuple[str, ...]
    offer_id: str
    seats: int
    reference_total_cents: int
    cost_cents: int
    value_cents: int

    def __post_init__(self):
        if self.reference_total_cents - self.cost_cents != self.value_cents:
            raise ValueError("value must equal the references minus the collective cost")


@dataclass(frozen=True)
class ComponentFormation:
    component_id: str
    unit_ids: tuple[str, ...]
    status: ComponentFormationStatus
    candidate_count: int
    feasible_count: int
    negotiation_count: int
    game: CoalitionGame | None
    solution: ComponentSolution | None


@dataclass(frozen=True)
class FormationResult:
    formation_run_id: str
    admissibility_id: str
    oracle_configuration_id: str | None
    limits: FormationLimits
    method: str
    cross_checks: tuple[str, ...]
    components: tuple[ComponentFormation, ...]
    blocks: tuple[FormedBlock, ...]
    evaluations: tuple[CoalitionCost, ...]
    total_reference_cents: int
    total_cost_cents: int
    total_value_cents: int
    unserved: tuple[UnitExclusion, ...]
    unresolved_unit_ids: tuple[str, ...]
    status: FormationStatus
    result_sha256: str
    cache_statistics: CacheStatistics | None = None  # informative, outside every digest

    @property
    def structure(self) -> tuple[Coalition, ...]:
        return tuple(block.unit_ids for block in self.blocks)

    def component(self, component_id: str) -> ComponentFormation:
        for item in self.components:
            if item.component_id == component_id:
                return item
        raise KeyError(component_id)


def _digest(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _unserved(lot: LotAdmissibilityResult, references: ReferenceCostsResult | None):
    items = list(lot.exclusions)
    if references is not None:
        items.extend(references.exclusions)
    return tuple(sorted(items, key=lambda item: item.unit_id))


def _run_id(
    lot: LotAdmissibilityResult,
    references: ReferenceCostsResult | None,
    configuration: str | None,
    limits: FormationLimits,
    method: str,
    cross_checks: tuple[str, ...],
) -> str:
    referenced = (
        []
        if references is None
        else [
            [item.unit_id, item.agreed_total_cents, item.offer_id]
            for item in references.unit_references
            if item.status == "referenced"
        ]
    )
    components = (
        [] if references is None else [c.component_id for c in references.effective_components]
    )
    return _digest(
        {
            "adapter": FORMATION_ADAPTER_VERSION,
            "admissibility_id": lot.admissibility_id,
            "oracle_configuration_id": configuration,
            "references": referenced,
            "method": method,
            "cross_checks": list(cross_checks),
            "tie_break": {"K": "number_of_component_players", "P": INFEASIBLE_PENALTY},
            "limits": {
                "max_component_units": limits.max_component_units,
                "max_offer_neighbourhood": limits.max_offer_neighbourhood,
                "brute_force_max_units": limits.brute_force_max_units,
            },
            "components": components,
        }
    )


def _result_digest(
    run_id: str,
    status: str,
    components: Iterable[ComponentFormation],
    blocks: Iterable[FormedBlock],
    evaluations: Iterable[CoalitionCost],
    unserved: Iterable[UnitExclusion],
    unresolved: Iterable[str],
) -> str:
    return _digest(
        {
            "formation_run_id": run_id,
            "status": status,
            "components": [
                {
                    "component_id": item.component_id,
                    "unit_ids": list(item.unit_ids),
                    "status": item.status,
                    "candidates": item.candidate_count,
                    "feasible": item.feasible_count,
                    "negotiations": item.negotiation_count,
                    "structure": None
                    if item.solution is None
                    else [list(block) for block in item.solution.structure],
                    "value_cents": None if item.solution is None else item.solution.value_cents,
                    "score": None if item.solution is None else item.solution.tie_break_score,
                    "method": None if item.solution is None else item.solution.method,
                    "checks": None if item.solution is None else list(item.solution.checks),
                }
                for item in components
            ],
            "blocks": [
                [list(b.unit_ids), b.offer_id, b.seats, b.reference_total_cents, b.cost_cents]
                for b in blocks
            ],
            "evaluations": [
                {
                    "unit_ids": list(cost.unit_ids),
                    "offer_id": cost.offer_id,
                    "cost_cents": cost.cost_cents,
                    "attempts": [
                        [a.offer_id, a.request_key, a.status, a.agreed_total_cents, a.turns]
                        for a in cost.attempts
                    ],
                }
                for cost in evaluations
            ],
            "unserved": [[item.unit_id, item.reason, list(item.details)] for item in unserved],
            "unresolved": list(unresolved),
        }
    )


def form_coalitions(
    lot: LotAdmissibilityResult,
    references: ReferenceCostsResult,
    oracle: CachingNegotiationOracle,
    *,
    limits: FormationLimits = DEFAULT_LIMITS,
    method: SolverMethod = "idp",
    cross_checks: tuple[SolverMethod, ...] = ("dp", "brute_force"),
) -> FormationResult:
    """Optimal coalition structure of a lot whose references are already computed."""
    if not isinstance(lot, LotAdmissibilityResult):
        raise TypeError("lot must be a LotAdmissibilityResult")
    if not isinstance(references, ReferenceCostsResult):
        raise TypeError("references must be a ReferenceCostsResult")
    if not isinstance(oracle, CachingNegotiationOracle):
        raise TypeError("the oracle must be the CachingNegotiationOracle shared with P2")
    if not isinstance(limits, FormationLimits):
        raise TypeError("limits must be FormationLimits")
    lot.require_optimizable()
    if references.admissibility_id != lot.admissibility_id:
        raise ValueError("references were computed for another lot")
    configuration = oracle.oracle_configuration_id
    if (
        references.oracle_configuration_id is not None
        and references.oracle_configuration_id != configuration
    ):
        raise OracleConfigurationMismatch(
            "references and coalitions must use the same oracle configuration (I2)"
        )
    cross_checks = tuple(cross_checks)
    run_id = _run_id(lot, references, configuration, limits, method, cross_checks)
    relation = references.effective_relation
    reference_offers = {
        item.unit_id: item.offer_id
        for item in references.unit_references
        if item.status == "referenced"
    }
    components: list[ComponentFormation] = []
    blocks: list[FormedBlock] = []
    evaluations: list[CoalitionCost] = []
    unresolved: list[str] = []
    seats_of = {unit.unit_id: unit.seats for unit in relation.units}
    for component in references.effective_components:
        unit_ids = tuple(unit.unit_id for unit in component.units)
        try:
            candidates = enumerate_candidates(relation, component, limits)
        except ComponentTooLarge:
            components.append(
                ComponentFormation(
                    component.component_id, unit_ids, "component_too_large", 0, 0, 0, None, None
                )
            )
            unresolved.extend(unit_ids)
            continue
        costs: dict[Coalition, CoalitionCost] = {}
        for candidate in candidates:
            check_structural_feasibility(candidate, lot, references)
            costs[candidate.unit_ids] = negotiate_candidate(candidate, relation, oracle)
        game = build_game(
            component.component_id,
            {unit_id: references.reference(unit_id) for unit_id in unit_ids},
            {coalition: cost.cost_cents for coalition, cost in costs.items()},
            configuration,
        )
        solution = solve_component(game, method=method, cross_checks=cross_checks, limits=limits)
        for block in solution.structure:
            cost = costs[block]
            if len(block) == 1 and cost.offer_id != reference_offers[block[0]]:
                raise FormationConsistencyError(
                    f"singleton {block[0]} uses {cost.offer_id}, not its reference offer"
                )
            blocks.append(
                FormedBlock(
                    unit_ids=block,
                    offer_id=cost.offer_id,
                    seats=sum(seats_of[unit_id] for unit_id in block),
                    reference_total_cents=sum(references.reference(u) for u in block),
                    cost_cents=cost.cost_cents,
                    value_cents=game.value(block),
                )
            )
        evaluations.extend(costs[key] for key in sorted(costs, key=lambda c: (len(c), c)))
        components.append(
            ComponentFormation(
                component_id=component.component_id,
                unit_ids=unit_ids,
                status=solution.status,
                candidate_count=len(candidates),
                feasible_count=sum(1 for cost in costs.values() if cost.feasible),
                negotiation_count=sum(len(cost.attempts) for cost in costs.values()),
                game=game,
                solution=solution,
            )
        )
    blocks.sort(key=lambda block: block.unit_ids)
    total_reference = sum(block.reference_total_cents for block in blocks)
    total_cost = sum(block.cost_cents for block in blocks)
    total_value = sum(block.value_cents for block in blocks)
    if total_reference - total_cost != total_value:
        raise FormationConsistencyError("sum of values differs from references minus costs")
    if sum(item.solution.value_cents for item in components if item.solution) != total_value:
        raise FormationConsistencyError("block values differ from the component optima")
    if not components:
        status: FormationStatus = "no_eligible_units"
    elif unresolved:
        status = "incomplete"
    else:
        status = "optimized"
    unserved = _unserved(lot, references)
    evaluations_tuple = tuple(evaluations)
    return FormationResult(
        formation_run_id=run_id,
        admissibility_id=lot.admissibility_id,
        oracle_configuration_id=configuration,
        limits=limits,
        method=method,
        cross_checks=cross_checks,
        components=tuple(components),
        blocks=tuple(blocks),
        evaluations=evaluations_tuple,
        total_reference_cents=total_reference,
        total_cost_cents=total_cost,
        total_value_cents=total_value,
        unserved=unserved,
        unresolved_unit_ids=tuple(sorted(unresolved)),
        status=status,
        result_sha256=_result_digest(
            run_id, status, components, blocks, evaluations_tuple, unserved, sorted(unresolved)
        ),
        cache_statistics=oracle.statistics,
    )


@dataclass(frozen=True)
class FormationStages:
    """The three results of the pipeline, kept for callers that must explain them (3H).

    ``references`` is None exactly when H2 fails: the oracle is then never called.
    """

    lot: LotAdmissibilityResult
    references: ReferenceCostsResult | None
    formation: FormationResult

    def __post_init__(self):
        if (self.references is None) != (self.formation.status == "capacity_model_violated"):
            raise FormationConsistencyError(
                "references are absent exactly when the capacity model is violated"
            )


def run_formation_pipeline(
    units: Iterable[TravelUnit],
    catalog: OfferCatalog,
    reference_date: date,
    oracle: ConfiguredNegotiationOracle,
    *,
    limits: FormationLimits = DEFAULT_LIMITS,
    method: SolverMethod = "idp",
    cross_checks: tuple[SolverMethod, ...] = ("dp", "brute_force"),
) -> FormationResult:
    """P2 admissibility, H2, cached references and formation, in one deterministic call.

    When H2 fails, the result has status ``capacity_model_violated`` and the oracle is
    never called (section 5). Thin wrapper of ``run_formation_stages`` (3H, I1).
    """
    return run_formation_stages(
        units,
        catalog,
        reference_date,
        oracle,
        limits=limits,
        method=method,
        cross_checks=cross_checks,
    ).formation


def run_formation_stages(
    units: Iterable[TravelUnit],
    catalog: OfferCatalog,
    reference_date: date,
    oracle: ConfiguredNegotiationOracle,
    *,
    limits: FormationLimits = DEFAULT_LIMITS,
    method: SolverMethod = "idp",
    cross_checks: tuple[SolverMethod, ...] = ("dp", "brute_force"),
) -> FormationStages:
    """Same computation as ``run_formation_pipeline``, returning the lot and references too.

    The body is the former pipeline, unchanged: only the return value differs.
    """
    lot = lot_admissibility(units, catalog, reference_date)
    caching = (
        oracle if isinstance(oracle, CachingNegotiationOracle) else CachingNegotiationOracle(oracle)
    )
    if lot.status == "capacity_model_violated":
        cross_checks = tuple(cross_checks)
        run_id = _run_id(lot, None, caching.oracle_configuration_id, limits, method, cross_checks)
        unserved = _unserved(lot, None)
        excluded = {item.unit_id for item in unserved}
        unresolved = tuple(
            sorted(unit.unit_id for unit in lot.relation.units if unit.unit_id not in excluded)
        )
        violated = FormationResult(
            formation_run_id=run_id,
            admissibility_id=lot.admissibility_id,
            oracle_configuration_id=caching.oracle_configuration_id,
            limits=limits,
            method=method,
            cross_checks=cross_checks,
            components=(),
            blocks=(),
            evaluations=(),
            total_reference_cents=0,
            total_cost_cents=0,
            total_value_cents=0,
            unserved=unserved,
            unresolved_unit_ids=unresolved,
            status="capacity_model_violated",
            result_sha256=_result_digest(
                run_id, "capacity_model_violated", (), (), (), unserved, unresolved
            ),
            cache_statistics=caching.statistics,
        )
        return FormationStages(lot, None, violated)
    references = compute_reference_costs(lot, caching)
    formation = form_coalitions(
        lot, references, caching, limits=limits, method=method, cross_checks=cross_checks
    )
    return FormationStages(lot, references, formation)
