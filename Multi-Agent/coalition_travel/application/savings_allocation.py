"""P5: allocation of the savings of every formed block (plan 3H/P5, step I2).

Inputs are the P4 ``FormationResult`` (blocks and component games) and the lot's
``TravelUnit`` budgets. No oracle is ever called: every value comes from the games P4
already built (specification §9.2), checked by the preconditions below.

Per non-singleton block C (scope review I2, §3.3):

1. v*|C from ``CoverCache`` (restriction of a cached component cover when available);
2. phi = exact Shapley value of v*|C, with phi >= 0 and sum phi = v(C) checked;
3. y = projection of phi onto [0, ref_u] (theta = 0, addendum ID-6), with lambda*;
4. y' = largest remainder in cents (ties by unit_id), x'_u = ref_u - y'_u;
5. traveller shares: equal awards under per-seat budgets, then largest remainder per
   seat (ties by profile_id, then seat rank);
6. diagnostics: projection activity, distances, rounding gap, maximum core excess.

A singleton pays its reference (phi = 0). Units without a block (unserved or unresolved)
are listed in ``unallocated`` with their reason and never receive a fictitious amount.
The invariants of §3.5 are checked on every run. The official computation never uses the
historical float Shapley value (``CoalitionStructureSearch.shapley_value``); that function
is a test-only differential oracle.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from time import perf_counter

from coalition_travel.application.coalition_formation import FormationResult, FormedBlock
from coalition_travel.domain.coalition_game import Coalition, CoalitionGame, canonical_coalition
from coalition_travel.domain.savings_allocation import (
    constrained_equal_awards,
    max_core_excess,
    max_distance,
    project_onto_bounds,
    round_largest_remainder,
    shapley_exact,
    squared_distance,
    values_by_mask,
)
from coalition_travel.domain.travel_unit import TravelUnit

ALLOCATION_VERSION = "p5-allocation-v1"
THETA_CENTS = 0  # ID-6, docs/PHASE_P5_ADDENDUM_ID6.md
SUBSTEPS = ("cover", "shapley", "projection", "rounding", "core_excess", "traveler_split")


class AllocationPreconditionError(RuntimeError):
    """The formation does not provide what P5 needs (scope review I2, §3.2)."""


class AllocationConsistencyError(RuntimeError):
    """An allocation invariant (scope review I2, §3.5) does not hold."""


# --- cover cache --------------------------------------------------------------------------


class CoverCache:
    """v* tables for one allocation run, keyed by (component_id, subset).

    Restriction lemma: for S ⊆ block ⊆ component, v* computed on the component and v*
    computed on the block agree on S, because v*(S) depends on F ∩ 2^S only. A block
    cover is therefore read from a cached component cover when one exists.
    """

    def __init__(self):
        self._covers: dict[tuple[str, Coalition], dict[Coalition, int]] = {}
        self._games: dict[str, tuple] = {}
        self.computed = 0
        self.reused = 0
        self.masks_visited = 0

    def _check_game(self, game: CoalitionGame) -> None:
        known = self._games.setdefault(game.component_id, game.values)
        if known != game.values:
            raise AllocationConsistencyError("a CoverCache must not be reused across games")

    def _compute(self, game: CoalitionGame, subset: Coalition) -> dict[Coalition, int]:
        cover = game.cover_values(subset)
        self.computed += 1
        self.masks_visited += (1 << len(subset)) - 1
        self._covers[(game.component_id, subset)] = cover
        return cover

    def component_cover(self, game: CoalitionGame) -> dict[Coalition, int]:
        self._check_game(game)
        key = (game.component_id, game.players)
        if key in self._covers:
            self.reused += 1
            return self._covers[key]
        return self._compute(game, game.players)

    def block_cover(self, game: CoalitionGame, block: Iterable[str]) -> dict[Coalition, int]:
        self._check_game(game)
        members = canonical_coalition(block)
        key = (game.component_id, members)
        if key in self._covers:
            self.reused += 1
            return self._covers[key]
        full = self._covers.get((game.component_id, game.players))
        if full is not None:
            allowed = set(members)
            restricted = {S: value for S, value in full.items() if set(S) <= allowed}
            self._covers[key] = restricted
            self.reused += 1
            return restricted
        return self._compute(game, members)


# --- results ------------------------------------------------------------------------------


@dataclass(frozen=True)
class BlockAllocation:
    unit_ids: tuple[str, ...]
    offer_id: str
    cost_cents: int
    value_cents: int
    references_cents: tuple[tuple[str, int], ...]
    phi: tuple[tuple[str, Fraction], ...]
    y: tuple[tuple[str, Fraction], ...]
    y_rounded: tuple[tuple[str, int], ...]
    payments_cents: tuple[tuple[str, int], ...]
    projection_active: bool
    saturated_unit_ids: tuple[str, ...]
    lambda_star: Fraction
    distance_squared: Fraction
    distance_max: Fraction
    rounding_gap: Fraction
    max_core_excess: Fraction | None

    def payment(self, unit_id: str) -> int:
        return dict(self.payments_cents)[unit_id]


@dataclass(frozen=True)
class TravelerShare:
    unit_id: str
    profile_id: str
    seat_rank: int
    budget_cents: int
    amount_cents: int
    profile_saturated: bool
    unit_tau: Fraction


@dataclass(frozen=True)
class UnallocatedUnit:
    unit_id: str
    reason: str


@dataclass(frozen=True)
class AllocationCounters:
    blocks: int
    covers_computed: int
    covers_reused: int
    cover_masks_visited: int
    marginal_contributions: int


@dataclass(frozen=True)
class AllocationResult:
    allocation_version: str
    theta_cents: int
    formation_run_id: str
    blocks: tuple[BlockAllocation, ...]
    shares: tuple[TravelerShare, ...]
    unallocated: tuple[UnallocatedUnit, ...]
    counters: AllocationCounters
    durations_seconds: tuple[tuple[str, float], ...]  # volatile, outside the digest
    allocation_sha256: str

    def block_for(self, unit_id: str) -> BlockAllocation:
        for block in self.blocks:
            if unit_id in block.unit_ids:
                return block
        raise KeyError(unit_id)

    def payment(self, unit_id: str) -> int:
        return self.block_for(unit_id).payment(unit_id)

    def shares_for(self, unit_id: str) -> tuple[TravelerShare, ...]:
        return tuple(share for share in self.shares if share.unit_id == unit_id)


# --- computation --------------------------------------------------------------------------


class SubstepClock:
    def __init__(self):
        self.totals = dict.fromkeys(SUBSTEPS, 0.0)

    def add(self, name: str, started: float) -> None:
        self.totals[name] += perf_counter() - started


def allocate_block(
    game: CoalitionGame,
    unit_ids: Iterable[str],
    offer_id: str,
    cost_cents: int,
    cover_cache: CoverCache,
    clock: SubstepClock | None = None,
) -> tuple[BlockAllocation, int]:
    """Steps 1 to 4 and 6 for one block of a component game; returns the marginal count.

    The caller checks the preconditions on the formation (``allocate_formation``).
    """
    clock = clock or SubstepClock()
    block = canonical_coalition(unit_ids)
    references = {unit: game.reference(unit) for unit in block}
    value = sum(references.values()) - cost_cents
    if len(block) == 1:
        unit = block[0]
        if value != 0:
            raise AllocationConsistencyError(f"singleton {unit} must have value 0")
        zero = Fraction(0)
        return (
            BlockAllocation(
                unit_ids=block,
                offer_id=offer_id,
                cost_cents=cost_cents,
                value_cents=0,
                references_cents=((unit, references[unit]),),
                phi=((unit, zero),),
                y=((unit, zero),),
                y_rounded=((unit, 0),),
                payments_cents=((unit, references[unit]),),
                projection_active=False,
                saturated_unit_ids=(),
                lambda_star=zero,
                distance_squared=zero,
                distance_max=zero,
                rounding_gap=zero,
                max_core_excess=None,
            ),
            0,
        )
    if not game.is_feasible(block) or game.value(block) != value:
        raise AllocationConsistencyError(f"block {block} disagrees with its component game")
    if value < 0:
        raise AllocationConsistencyError(f"block {block} has a negative value")

    started = perf_counter()
    cover = cover_cache.block_cover(game, block)
    masks = values_by_mask(block, cover)
    clock.add("cover", started)
    if masks[-1] != value:
        raise AllocationConsistencyError("v*(C) must equal v(C) for a formed block")

    started = perf_counter()
    shapley = shapley_exact(block, masks)
    clock.add("shapley", started)
    phi = dict(shapley.phi)
    if any(amount < 0 for amount in phi.values()):
        raise AllocationConsistencyError(f"negative Shapley value in block {block}")
    if sum(phi.values()) != value:
        raise AllocationConsistencyError(f"Shapley values of {block} do not sum to v(C)")

    started = perf_counter()
    lower = dict.fromkeys(block, 0)
    upper = {unit: references[unit] - THETA_CENTS for unit in block}
    projection = project_onto_bounds(phi, value, lower, upper)
    clock.add("projection", started)
    y = dict(projection.y)

    started = perf_counter()
    rounded = round_largest_remainder(y, value, upper)
    clock.add("rounding", started)
    payments = {unit: references[unit] - rounded[unit] for unit in block}

    started = perf_counter()
    excess = max_core_excess(block, masks, y)
    clock.add("core_excess", started)
    allocation = BlockAllocation(
        unit_ids=block,
        offer_id=offer_id,
        cost_cents=cost_cents,
        value_cents=value,
        references_cents=tuple((unit, references[unit]) for unit in block),
        phi=shapley.phi,
        y=projection.y,
        y_rounded=tuple((unit, rounded[unit]) for unit in block),
        payments_cents=tuple((unit, payments[unit]) for unit in block),
        projection_active=projection.active,
        saturated_unit_ids=projection.saturated_high,
        lambda_star=projection.lambda_star,
        distance_squared=squared_distance(y, phi),
        distance_max=max_distance(y, phi),
        rounding_gap=max(abs(rounded[unit] - y[unit]) for unit in block),
        max_core_excess=excess,
    )
    return allocation, shapley.marginal_contributions


def split_unit_payment(
    unit: TravelUnit, amount_cents: int, clock: SubstepClock | None = None
) -> tuple[TravelerShare, ...]:
    """Equal awards under per-seat budgets, then largest remainder per seat (plan §6.1)."""
    clock = clock or SubstepClock()
    started = perf_counter()
    caps = {}
    for profile in unit.profiles:
        budget = unit.budget_per_seat_cents(profile.profile_id)
        for rank in range(1, profile.traveller_count + 1):
            caps[(profile.profile_id, rank)] = budget
    awards = constrained_equal_awards(amount_cents, caps)
    rounded = round_largest_remainder(dict(awards.amounts), amount_cents, caps)
    saturated = set(awards.saturated)
    shares = tuple(
        TravelerShare(
            unit_id=unit.unit_id,
            profile_id=profile_id,
            seat_rank=rank,
            budget_cents=caps[(profile_id, rank)],
            amount_cents=rounded[(profile_id, rank)],
            profile_saturated=(profile_id, rank) in saturated,
            unit_tau=awards.tau,
        )
        for profile_id, rank in sorted(caps)
    )
    clock.add("traveler_split", started)
    return shares


def _component_of(formation: FormationResult, block: FormedBlock):
    members = set(block.unit_ids)
    for component in formation.components:
        if members <= set(component.unit_ids):
            return component
    raise AllocationPreconditionError(f"block {block.unit_ids} belongs to no component")


def _check_preconditions(formation: FormationResult, block: FormedBlock, evaluated: set) -> None:
    """Scope review I2, §3.2: the game exists, C is in F, every subset of C was evaluated."""
    component = _component_of(formation, block)
    game = component.game
    if game is None:
        raise AllocationPreconditionError(f"no game for the component of {block.unit_ids}")
    if not game.is_feasible(block.unit_ids):
        raise AllocationPreconditionError(f"block {block.unit_ids} is not a feasible coalition")
    for size in range(1, len(block.unit_ids) + 1):
        for subset in combinations(block.unit_ids, size):
            if subset not in evaluated:
                raise AllocationPreconditionError(
                    f"sub-coalition {subset} of {block.unit_ids} was not evaluated by P4"
                )
    references = sum(game.reference(unit) for unit in block.unit_ids)
    if references != block.reference_total_cents or block.cost_cents <= 0:
        raise AllocationPreconditionError(f"amounts of block {block.unit_ids} are inconsistent")


def _fraction(value: Fraction | None) -> str | None:
    return None if value is None else f"{value.numerator}/{value.denominator}"


def _digest(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def canonical_allocation_content(
    formation_run_id: str,
    blocks: Iterable[BlockAllocation],
    shares: Iterable[TravelerShare],
    unallocated: Iterable[UnallocatedUnit],
) -> dict:
    """Everything that determines the allocation, with theta and the version (ID-6)."""
    return {
        "allocation_version": ALLOCATION_VERSION,
        "theta_cents": THETA_CENTS,
        "formation_run_id": formation_run_id,
        "blocks": [
            {
                "unit_ids": list(block.unit_ids),
                "offer_id": block.offer_id,
                "cost_cents": block.cost_cents,
                "value_cents": block.value_cents,
                "phi": [[unit, _fraction(value)] for unit, value in block.phi],
                "y": [[unit, _fraction(value)] for unit, value in block.y],
                "payments_cents": [list(item) for item in block.payments_cents],
                "lambda_star": _fraction(block.lambda_star),
                "saturated": list(block.saturated_unit_ids),
                "max_core_excess": _fraction(block.max_core_excess),
            }
            for block in blocks
        ],
        "shares": [
            [share.unit_id, share.profile_id, share.seat_rank, share.amount_cents]
            for share in shares
        ],
        "unallocated": [[item.unit_id, item.reason] for item in unallocated],
    }


def _check_block_invariants(block: BlockAllocation, units: dict[str, TravelUnit]) -> None:
    """Scope review I2, §3.5, block level: checked before any traveller split."""
    payments = dict(block.payments_cents)
    references = dict(block.references_cents)
    if sum(payments.values()) != block.cost_cents:
        raise AllocationConsistencyError(f"block {block.unit_ids}: sum x' != c(C)")
    for unit_id, payment in payments.items():
        if not 0 <= payment <= references[unit_id] <= units[unit_id].budget_total_cents:
            raise AllocationConsistencyError(f"{unit_id}: 0 <= x' <= ref <= B violated")


def _check_share_invariants(
    blocks: tuple[BlockAllocation, ...], shares: tuple[TravelerShare, ...]
) -> None:
    """Scope review I2, §3.5, traveller level."""
    paid = {unit: amount for block in blocks for unit, amount in block.payments_cents}
    by_unit: dict[str, int] = {}
    for share in shares:
        if not 0 <= share.amount_cents <= share.budget_cents:
            raise AllocationConsistencyError(
                f"{share.unit_id}/{share.profile_id}#{share.seat_rank}: 0 <= q' <= b violated"
            )
        by_unit[share.unit_id] = by_unit.get(share.unit_id, 0) + share.amount_cents
    if by_unit != paid:
        raise AllocationConsistencyError("traveller shares do not sum to their unit payment")


def allocate_formation(
    formation: FormationResult,
    units: Iterable[TravelUnit],
    *,
    cover_cache: CoverCache | None = None,
) -> AllocationResult:
    """P5 for every block of a formation; never calls an oracle."""
    if not isinstance(formation, FormationResult):
        raise TypeError("formation must be a FormationResult")
    unit_map = {unit.unit_id: unit for unit in units}
    cache = cover_cache if cover_cache is not None else CoverCache()
    clock = SubstepClock()
    evaluated = {cost.unit_ids for cost in formation.evaluations}
    blocks: list[BlockAllocation] = []
    shares: list[TravelerShare] = []
    marginal = 0
    for block in formation.blocks:
        missing = [unit for unit in block.unit_ids if unit not in unit_map]
        if missing:
            raise AllocationPreconditionError(f"units {missing} are not in the lot")
        if len(block.unit_ids) > 1:
            _check_preconditions(formation, block, evaluated)
        game = _component_of(formation, block).game
        if game is None:
            raise AllocationPreconditionError(f"no game for the component of {block.unit_ids}")
        allocation, contributions = allocate_block(
            game, block.unit_ids, block.offer_id, block.cost_cents, cache, clock
        )
        marginal += contributions
        _check_block_invariants(allocation, unit_map)
        blocks.append(allocation)
        for unit_id, payment in allocation.payments_cents:
            shares.extend(split_unit_payment(unit_map[unit_id], payment, clock))
    unresolved_reason = (
        "capacity_model_violated"
        if formation.status == "capacity_model_violated"
        else "component_too_large"
    )
    unallocated = sorted(
        [UnallocatedUnit(item.unit_id, item.reason) for item in formation.unserved]
        + [
            UnallocatedUnit(unit_id, unresolved_reason) for unit_id in formation.unresolved_unit_ids
        ],
        key=lambda item: item.unit_id,
    )
    block_tuple, share_tuple = tuple(blocks), tuple(shares)
    _check_share_invariants(block_tuple, share_tuple)
    content = canonical_allocation_content(
        formation.formation_run_id, block_tuple, share_tuple, unallocated
    )
    return AllocationResult(
        allocation_version=ALLOCATION_VERSION,
        theta_cents=THETA_CENTS,
        formation_run_id=formation.formation_run_id,
        blocks=block_tuple,
        shares=share_tuple,
        unallocated=tuple(unallocated),
        counters=AllocationCounters(
            blocks=len(block_tuple),
            covers_computed=cache.computed,
            covers_reused=cache.reused,
            cover_masks_visited=cache.masks_visited,
            marginal_contributions=marginal,
        ),
        durations_seconds=tuple(clock.totals.items()),
        allocation_sha256=_digest(content),
    )
