"""I2 (P5): allocation of a formation, through plan_lot and block by block."""

import hashlib
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from coalition_travel.application import savings_allocation, trip_planning
from coalition_travel.application.coalition_candidates import FormationLimits
from coalition_travel.application.coalition_formation import run_formation_stages
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.savings_allocation import (
    ALLOCATION_VERSION,
    THETA_CENTS,
    AllocationConsistencyError,
    AllocationPreconditionError,
    CoverCache,
    allocate_block,
    allocate_formation,
    canonical_allocation_content,
    split_unit_payment,
)
from coalition_travel.application.trip_planning import (
    DemandPoolSnapshot,
    PlanConsistencyError,
    PlanningInput,
    PlanningRequest,
    plan_lot,
)
from coalition_travel.domain.negotiation_request import negotiation_request_for
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile
from coalition_travel.infrastructure.demand.demand_pool import load_demand_pool
from coalition_travel.infrastructure.negotiation.market import open_simulated_market
from CoalitionStructureSearch import shapley_value
from p4_support import REFERENCE
from test_savings_allocation_math import game_of

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/catalog/catalog_v1.json"
POOL_PATH = ROOT / "data/demand/demand_pool_v1.jsonl"
PINNED = {
    "a": ("Tokyo", 1, "520"),
    "b": ("Tokyo", 1, "540"),
    "c": ("Tokyo", 2, "500"),
    "d": ("Tokyo", 1, "600"),
    "e": ("Rome", 2, "450"),
    "f": ("Rome", 1, "330"),
}


def request(request_id, destination="Tokyo", travellers=1, budget="520"):
    draft = TravelRequestDraft(
        destination=destination, travellers=travellers, budget_per_person=budget
    )
    return PlanningRequest(request_id, draft)


@pytest.fixture(scope="module")
def market():
    return open_simulated_market(CATALOG_PATH, REFERENCE)


@pytest.fixture(scope="module")
def tokyo_plan(market):
    pool = load_demand_pool(POOL_PATH)
    return plan_lot(PlanningInput((request("user", "Tokyo", 8, "500"),), pool, REFERENCE), market)


@pytest.fixture(scope="module")
def pinned_plan(market):
    pool = DemandPoolSnapshot(
        "test-pool", "0" * 64, "catalog-v1", tuple(request(k, *PINNED[k]) for k in "bcdf")
    )
    focus = (request("a", *PINNED["a"]), request("e", *PINNED["e"]))
    return plan_lot(PlanningInput(focus, pool, REFERENCE), market)


def unit(unit_id, *profiles):
    """profiles: (profile_id, seats, budget per seat in euros)."""
    built = tuple(
        TravelerProfile(profile_id, seats, "Tokyo", Decimal(budget))
        for profile_id, seats, budget in sorted(profiles)
    )
    return TravelUnit(unit_id, "tokyo", built, hashlib.sha256(unit_id.encode()).hexdigest())


# --- reference examples through the application -------------------------------------------


def test_e3_tokyo_block_is_reproduced_exactly(tokyo_plan):
    allocation = tokyo_plan.allocation
    block = allocation.block_for("user")
    assert block.unit_ids == ("pool-tyo-01", "pool-tyo-02", "pool-tyo-04", "user")
    assert dict(block.phi) == {
        "pool-tyo-01": 600,
        "pool-tyo-02": 1_500,
        "pool-tyo-04": 3_000,
        "user": 3_900,
    }
    assert not block.projection_active and block.lambda_star == 0
    assert dict(block.payments_cents) == {
        "pool-tyo-01": 48_000,
        "pool-tyo-02": 48_900,
        "pool-tyo-04": 51_000,
        "user": 380_100,
    }
    assert block.max_core_excess == 0  # {02, 04, user} is exactly at the core boundary
    shares = allocation.shares_for("user")
    assert [share.amount_cents for share in shares] == [47_513] * 4 + [47_512] * 4
    assert {share.unit_tau for share in shares} == {Fraction(95_025, 2)}  # 475,125 EUR
    singleton = allocation.block_for("pool-tyo-03")
    assert dict(singleton.payments_cents) == {"pool-tyo-03": 90_720} and singleton.phi[0][1] == 0


def test_e3_differential_oracle_on_the_cover_game(tokyo_plan):
    """A4 on E3: the historical float shapley_value on v*|C agrees with the exact phi."""
    block = tokyo_plan.allocation.block_for("user")
    (game,) = (
        component.game
        for component in tokyo_plan.formation.components
        if set(block.unit_ids) <= set(component.game.players)
    )
    cover = game.cover_values(block.unit_ids)

    def v_star(coalition):
        return cover[tuple(sorted(coalition))] if coalition else 0

    tolerance = 1e-6 * max(1, abs(cover[block.unit_ids]))
    for unit, phi in block.phi:
        assert abs(shapley_value(unit, block.unit_ids, v_star) - phi) <= tolerance


def test_pinned_lot_allocation_is_pinned(pinned_plan):
    """Computed once at the start of I2, explained in the I2 report, then pinned."""
    allocation = pinned_plan.allocation
    assert [(b.unit_ids, dict(b.phi), b.payments_cents) for b in allocation.blocks] == [
        (
            ("a", "b", "c"),
            {"a": 900, "b": 1_260, "c": 360},
            (("a", 47_700), ("b", 49_140), ("c", 90_360)),
        ),
        (("d",), {"d": 0}, (("d", 54_000),)),
        (("e", "f"), {"e": 4_500, "f": 4_500}, (("e", 55_500), ("f", 25_500))),
    ]
    assert [(s.unit_id, s.seat_rank, s.amount_cents) for s in allocation.shares] == [
        ("a", 1, 47_700),
        ("b", 1, 49_140),
        ("c", 1, 45_180),
        ("c", 2, 45_180),
        ("d", 1, 54_000),
        ("e", 1, 27_750),
        ("e", 2, 27_750),
        ("f", 1, 25_500),
    ]
    assert allocation.unallocated == ()
    for block in allocation.blocks:
        assert sum(dict(block.payments_cents).values()) == block.cost_cents


def test_e2_and_e6_through_allocate_block():
    references = {"a": 100, "b": 1_000, "c": 1_000}
    e2 = game_of(references, {("a", "b", "c"): 900})
    block, _ = allocate_block(e2, ("a", "b", "c"), "offer", 1_200, CoverCache())
    assert dict(block.payments_cents) == {"a": 0, "b": 600, "c": 600}
    assert block.saturated_unit_ids == ("a",) and block.lambda_star == -100
    assert block.projection_active and block.distance_max == 200
    e6 = game_of(references, {("a", "b"): 900, ("a", "b", "c"): 900})
    block, _ = allocate_block(e6, ("a", "b", "c"), "offer", 1_200, CoverCache())
    assert dict(block.y) == {"a": 100, "b": 625, "c": 175}
    assert dict(block.payments_cents) == {"a": 0, "b": 375, "c": 825}


def test_e4_and_e5_through_split_unit_payment():
    shares = split_unit_payment(unit("u", ("a", 1, "10.00"), ("b", 1, "100.00")), 5_000)
    assert [(s.profile_id, s.amount_cents, s.profile_saturated) for s in shares] == [
        ("a", 1_000, True),
        ("b", 4_000, False),
    ]
    before = split_unit_payment(unit("u", ("a", 1, "100.00"), ("b", 1, "200.00")), 3_001)
    after = split_unit_payment(unit("u", ("a", 1, "200.00"), ("b", 1, "100.00")), 3_001)
    assert [(s.profile_id, s.budget_cents, s.amount_cents) for s in before] == [
        ("a", 10_000, 1_501),
        ("b", 20_000, 1_500),
    ]
    assert [(s.profile_id, s.budget_cents, s.amount_cents) for s in after] == [
        ("a", 20_000, 1_501),
        ("b", 10_000, 1_500),
    ]


# --- unallocated units, preconditions, invariants ------------------------------------------


def test_units_without_a_block_are_unallocated_with_their_reason(market):
    pool = load_demand_pool(POOL_PATH)
    poor = plan_lot(PlanningInput((request("user", "Tokyo", 1, "100"),), pool, REFERENCE), market)
    assert ("user", "no_solo_reference") in [
        (item.unit_id, item.reason) for item in poor.allocation.unallocated
    ]
    with pytest.raises(KeyError):
        poor.allocation.block_for("user")
    focus = (request("user", "Rome", 20, "400"), request("user-2", "Rome", 20, "400"))
    violated = plan_lot(PlanningInput(focus, pool, REFERENCE), market)
    assert violated.allocation.blocks == ()
    assert {item.reason for item in violated.allocation.unallocated} == {"capacity_model_violated"}
    small = PlanningInput(
        (request("user", "Tokyo", 1, "520"),),
        pool,
        REFERENCE,
        FormationLimits(max_component_units=4),
    )
    too_large = plan_lot(small, market)
    assert {item.reason for item in too_large.allocation.unallocated} == {"component_too_large"}


def test_a_missing_sub_coalition_is_a_precondition_error(tokyo_plan):
    formation = tokyo_plan.formation
    removed = ("pool-tyo-01", "pool-tyo-04")
    partial = replace(
        formation, evaluations=tuple(c for c in formation.evaluations if c.unit_ids != removed)
    )
    with pytest.raises(AllocationPreconditionError, match="was not evaluated"):
        allocate_formation(partial, tokyo_plan.units)
    with pytest.raises(AllocationPreconditionError, match="not in the lot"):
        allocate_formation(formation, tokyo_plan.units[1:])


@pytest.mark.parametrize(
    ("target", "fake", "message"),
    [
        (
            "round_largest_remainder",
            lambda real: (
                lambda values, total, upper: {
                    k: v + (1 if i == 0 else 0)
                    for i, (k, v) in enumerate(real(values, total, upper).items())
                }
            ),
            "sum x' != c",
        ),
        (
            "split_unit_payment",
            lambda real: (
                lambda unit, amount, clock=None: tuple(
                    replace(s, amount_cents=s.amount_cents + 1) for s in real(unit, amount, clock)
                )
            ),
            "do not sum",
        ),
        (
            "split_unit_payment",
            lambda real: (
                lambda unit, amount, clock=None: tuple(
                    replace(s, budget_cents=s.amount_cents - 1) for s in real(unit, amount, clock)
                )
            ),
            "q' <= b",
        ),
        (
            "shapley_exact",
            lambda real: (
                lambda members, values: replace(
                    real(members, values),
                    phi=tuple((u, v + 1) for u, v in real(members, values).phi),
                )
            ),
            "do not sum to v",
        ),
    ],
)
def test_each_runtime_invariant_detects_its_violation(
    monkeypatch, tokyo_plan, target, fake, message
):
    real = getattr(savings_allocation, target)
    monkeypatch.setattr(savings_allocation, target, fake(real))
    with pytest.raises(AllocationConsistencyError, match=message):
        allocate_formation(tokyo_plan.formation, tokyo_plan.units)


def test_payment_above_the_reference_is_refused(monkeypatch, tokyo_plan):
    """Sum preserved, but 10 000 cents of savings moved from one unit to another."""
    real = savings_allocation.round_largest_remainder

    def shifted(values, total, upper):
        result = real(values, total, upper)
        keys = sorted(result)
        if keys and isinstance(keys[0], str) and len(keys) > 1:  # unit level only
            result[keys[0]] -= 10_000
            result[keys[-1]] += 10_000
        return result

    monkeypatch.setattr(savings_allocation, "round_largest_remainder", shifted)
    with pytest.raises(AllocationConsistencyError, match="0 <= x' <= ref <= B"):
        allocate_formation(tokyo_plan.formation, tokyo_plan.units)


# --- cover cache, zero oracle call, digest --------------------------------------------------


def test_cover_cache_restricts_a_cached_component_cover(tokyo_plan):
    game = tokyo_plan.formation.components[0].game
    cache = CoverCache()
    cache.component_cover(game)
    reused = allocate_formation(tokyo_plan.formation, tokyo_plan.units, cover_cache=cache)
    fresh = allocate_formation(tokyo_plan.formation, tokyo_plan.units)
    assert reused.allocation_sha256 == fresh.allocation_sha256
    assert (reused.counters.covers_computed, reused.counters.covers_reused) == (1, 1)
    assert (fresh.counters.covers_computed, fresh.counters.covers_reused) == (1, 0)
    other = game_of({"a": 10_000, "b": 10_000}, {("a", "b"): 5})
    impostor = replace(other, component_id=game.component_id)  # same id, other game
    with pytest.raises(AllocationConsistencyError, match="reused across games"):
        cache.block_cover(impostor, ("a", "b"))


def test_allocation_makes_no_oracle_call(market):
    """A5: the oracle is armed to fail once the formation is done."""
    pool = load_demand_pool(POOL_PATH)
    units = tuple(
        trip_planning.build_travel_unit(item.request_id, item.draft, REFERENCE)
        for item in pool.requests
        if item.draft.destination == "Tokyo"
    )
    session = market.open_session()

    class Armed:
        oracle_configuration_id = session.oracle_configuration_id
        armed = False

        def negotiate(self, negotiation_request):
            if Armed.armed:
                raise AssertionError("P5 called the oracle")
            return session.negotiate(negotiation_request)

    stages = run_formation_stages(units, market.catalog, REFERENCE, Armed())
    Armed.armed = True
    calls = session.oracle_calls
    allocation = allocate_formation(stages.formation, units)
    assert allocation.blocks and session.oracle_calls == calls


def test_plan_lot_refuses_an_allocation_that_negotiates(monkeypatch, market):
    sessions = []
    real_open = market.open_session

    class Recording:
        catalog = market.catalog
        reference_date = market.reference_date
        oracle_configuration_id = market.oracle_configuration_id

        def open_session(self):
            sessions.append(real_open())
            return sessions[-1]

    def negotiating(formation, units):
        offer = market.catalog.get("tyo-northstar-20270310")
        sessions[-1].negotiate(negotiation_request_for((units[0],), offer))
        return allocate_formation(formation, units)

    monkeypatch.setattr(trip_planning, "allocate_formation", negotiating)
    with pytest.raises(PlanConsistencyError, match="must not call"):
        plan_lot(PlanningInput((request("user"),), None, REFERENCE), Recording())


def test_digest_is_deterministic_and_carries_theta(tokyo_plan, market):
    again = allocate_formation(tokyo_plan.formation, tokyo_plan.units)
    assert again.allocation_sha256 == tokyo_plan.allocation.allocation_sha256
    assert (
        (again.allocation_version, again.theta_cents)
        == (ALLOCATION_VERSION, THETA_CENTS)
        == (
            "p5-allocation-v1",
            0,
        )
    )
    content = canonical_allocation_content(
        again.formation_run_id, again.blocks, again.shares, again.unallocated
    )
    assert content["theta_cents"] == 0 and content["allocation_version"] == ALLOCATION_VERSION
    changed = canonical_allocation_content(
        again.formation_run_id,
        again.blocks,
        tuple(replace(s, amount_cents=s.amount_cents + 1) for s in again.shares),
        again.unallocated,
    )
    assert changed != content
    assert {name for name, _ in again.durations_seconds} == set(savings_allocation.SUBSTEPS)


def test_trip_plan_allocation_must_belong_to_its_formation(tokyo_plan, pinned_plan):
    assert tokyo_plan.allocation.formation_run_id == tokyo_plan.formation.formation_run_id
    with pytest.raises(PlanConsistencyError, match="belongs to the formation"):
        replace(tokyo_plan, allocation=pinned_plan.allocation)
    rejected = plan_lot(
        PlanningInput(
            (PlanningRequest("user", TravelRequestDraft(destination="Tokyo", travellers=2)),),
            None,
            REFERENCE,
        ),
        open_simulated_market(CATALOG_PATH, REFERENCE),
    )
    assert rejected.allocation is None
