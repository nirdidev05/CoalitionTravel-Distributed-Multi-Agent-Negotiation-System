"""3H, I1: plan_lot over P2, P3 and P4 with one cache and one journaling session."""

from dataclasses import fields, replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest
from coalition_travel.application.coalition_formation import (
    FormationConsistencyError,
    FormationStages,
    run_formation_pipeline,
    run_formation_stages,
)
from coalition_travel.application.lot_admissibility import lot_admissibility
from coalition_travel.application.negotiation_cache import (
    CacheStatistics,
    CachingNegotiationOracle,
)
from coalition_travel.application.reference_costs import compute_reference_costs
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.travel_units import build_travel_unit
from coalition_travel.application.trip_planning import (
    DemandPoolSnapshot,
    PlanConsistencyError,
    PlanningInput,
    PlanningInputError,
    PlanningRequest,
    PoolRequestError,
    TripPlan,
    plan_lot,
    verify_journal_invariants,
)
from coalition_travel.domain.negotiation_request import negotiation_request_for
from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog
from coalition_travel.infrastructure.demand.demand_pool import load_demand_pool
from coalition_travel.infrastructure.evaluation.formation_scenarios import (
    ScenarioParameters,
    build_scenario,
)
from coalition_travel.infrastructure.negotiation.journaling_oracle import (
    JournalingNegotiationOracle,
)
from coalition_travel.infrastructure.negotiation.market import open_simulated_market
from coalition_travel.infrastructure.negotiation.simulated_oracle import (
    SimulatedNegotiationOracle,
    SimulatedOracleConfig,
)
from p4_support import REFERENCE

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/catalog/catalog_v1.json"
POOL_PATH = ROOT / "data/demand/demand_pool_v1.jsonl"

# Drafts economically identical to the pinned lot of tests/test_coalition_formation.py.
PINNED = {
    "a": ("Tokyo", 1, "520"),
    "b": ("Tokyo", 1, "540"),
    "c": ("Tokyo", 2, "500"),
    "d": ("Tokyo", 1, "600"),
    "e": ("Rome", 2, "450"),
    "f": ("Rome", 1, "330"),
}


def draft(destination="Tokyo", travellers=1, budget="520", **extra):
    return TravelRequestDraft(
        destination=destination, travellers=travellers, budget_per_person=budget, **extra
    )


def request(request_id, destination="Tokyo", travellers=1, budget="520", **extra):
    return PlanningRequest(request_id, draft(destination, travellers, budget, **extra))


def snapshot(requests, catalog_version="catalog-v1"):
    return DemandPoolSnapshot("test-pool", "0" * 64, catalog_version, tuple(requests))


def pinned_input():
    """The pinned lot spans two routes: one focus request per route keeps all six units."""
    focus = (request("a", *PINNED["a"]), request("e", *PINNED["e"]))
    pool = snapshot(request(key, *value) for key, value in PINNED.items() if key not in "ae")
    return PlanningInput(focus, pool, REFERENCE)


def fresh_oracle():
    catalog, terms = load_offer_catalog(CATALOG_PATH)
    return catalog, SimulatedNegotiationOracle(catalog, terms, SimulatedOracleConfig(REFERENCE))


@pytest.fixture(scope="module")
def market():
    return open_simulated_market(CATALOG_PATH, REFERENCE)


@pytest.fixture(scope="module")
def pinned_plan(market):
    return plan_lot(pinned_input(), market)


def test_pinned_lot_through_plan_lot_matches_the_pipeline_field_by_field(pinned_plan):
    plan = pinned_plan
    units = tuple(build_travel_unit(key, draft(*value), REFERENCE) for key, value in PINNED.items())
    assert plan.units == units
    catalog, oracle = fresh_oracle()
    expected = run_formation_pipeline(units, catalog, REFERENCE, oracle)
    formation = plan.formation
    for field in fields(type(expected)):  # every field, for a precise diagnosis
        assert getattr(formation, field.name) == getattr(expected, field.name), field.name
    assert formation == expected
    # The intermediate stages equal a direct computation with a fresh oracle.
    lot = lot_admissibility(units, catalog, REFERENCE)
    assert plan.stages.lot == lot
    _, oracle = fresh_oracle()
    assert plan.stages.references == compute_reference_costs(lot, CachingNegotiationOracle(oracle))


def test_pinned_lot_keeps_its_pinned_values(pinned_plan):
    formation = pinned_plan.formation
    assert formation.status == "optimized"
    assert [(b.unit_ids, b.offer_id, b.cost_cents, b.value_cents) for b in formation.blocks] == [
        (("a", "b", "c"), "tyo-northstar-20270310", 187_200, 2_520),
        (("d",), "tyo-skyways-20270312", 54_000, 0),
        (("e", "f"), "rom-cloudwing-20270405", 81_000, 9_000),
    ]
    assert (
        formation.total_reference_cents,
        formation.total_cost_cents,
        formation.total_value_cents,
    ) == (333_720, 322_200, 11_520)
    assert formation.cache_statistics.hits == 10


def test_pinned_lot_satisfies_the_journal_invariants(pinned_plan):
    stats = pinned_plan.formation.cache_statistics
    invariants = pinned_plan.invariants
    assert invariants.journals == invariants.oracle_calls == invariants.distinct_keys
    assert invariants.oracle_calls == stats.oracle_calls
    assert invariants.attempts == invariants.cache_requests == stats.requests
    assert len(pinned_plan.journals) == stats.oracle_calls
    for block in pinned_plan.formation.blocks:  # every retained agreement has its journal
        cost = next(c for c in pinned_plan.formation.evaluations if c.unit_ids == block.unit_ids)
        attempt = next(a for a in cost.attempts if a.offer_id == block.offer_id)
        journal = pinned_plan.journal_for(attempt.request_key)
        assert journal.agreed_total_cents == block.cost_cents
        assert journal.offer_id == block.offer_id


@pytest.mark.parametrize(
    ("parameters", "seed"),
    [
        (ScenarioParameters(unit_count=6, offer_count=3, density_percent=50), 0),
        (ScenarioParameters(unit_count=7), 4),
        (ScenarioParameters(family="mutualisation", unit_count=6), 1),
        (
            ScenarioParameters(
                family="h2_violation", tier_grid="flat", density_percent=100, unit_count=4
            ),
            0,
        ),
    ],
)
def test_journal_invariants_hold_on_exploratory_lots(tmp_path, parameters, seed):
    scenario = build_scenario(parameters, seed, tmp_path)
    session = JournalingNegotiationOracle(scenario.oracle)
    stages = run_formation_stages(
        scenario.units, scenario.catalog, scenario.reference_date, session
    )
    invariants = verify_journal_invariants(stages, session.journals, session.oracle_calls)
    assert invariants.journals == invariants.oracle_calls == invariants.distinct_keys
    assert invariants.attempts == invariants.cache_requests
    # The stages wrapper and the journaling layer change nothing in the formation.
    expected = run_formation_pipeline(
        scenario.units, scenario.catalog, scenario.reference_date, scenario.oracle
    )
    assert stages.formation == expected


def test_verify_journal_invariants_detects_each_violation(pinned_plan):
    stages, journals = pinned_plan.stages, dict(pinned_plan.journals)
    calls = pinned_plan.invariants.oracle_calls
    key = next(iter(journals))
    missing = {k: v for k, v in journals.items() if k != key}
    with pytest.raises(PlanConsistencyError, match="J3: no journal"):
        verify_journal_invariants(stages, missing, calls)
    wrong = dict(journals)
    wrong[key] = SimpleNamespace(**{**vars_of(journals[key]), "router_iterations": -1})
    with pytest.raises(PlanConsistencyError, match="J3: attempt and journal disagree"):
        verify_journal_invariants(stages, wrong, calls)
    extra = {**journals, "f" * 64: journals[key]}
    with pytest.raises(PlanConsistencyError, match="J4"):
        verify_journal_invariants(stages, extra, calls)
    with pytest.raises(PlanConsistencyError, match="J5: journals, oracle calls"):
        verify_journal_invariants(stages, journals, calls + 1)
    stats = stages.formation.cache_statistics
    more_requests = CacheStatistics(stats.requests + 1, stats.hits + 1, stats.oracle_calls)
    for statistics, message in ((more_requests, "attempts for"), (None, "no cache statistics")):
        altered = replace(stages, formation=replace(stages.formation, cache_statistics=statistics))
        with pytest.raises(PlanConsistencyError, match=f"J5: .*{message}"):
            verify_journal_invariants(altered, journals, calls)


def vars_of(journal):
    names = ("request_key", "oracle_configuration_id", "status", "agreed_total_cents")
    return {name: getattr(journal, name) for name in (*names, "router_iterations")}


def test_versioned_pool_plan_is_pinned(market):
    """Regression anchor computed once with the frozen pool v1, then pinned (report I1)."""
    pool = load_demand_pool(POOL_PATH)
    plan = plan_lot(PlanningInput((request("user", "Tokyo", 8, "500"),), pool, REFERENCE), market)
    formation = plan.formation
    assert plan.status == "planned"
    assert plan.pool_unit_ids == ("pool-tyo-01", "pool-tyo-02", "pool-tyo-03", "pool-tyo-04")
    assert [(b.unit_ids, b.offer_id, b.cost_cents, b.value_cents) for b in formation.blocks] == [
        (
            ("pool-tyo-01", "pool-tyo-02", "pool-tyo-04", "user"),
            "tyo-northstar-20270310",
            528_000,
            9_000,
        ),
        (("pool-tyo-03",), "tyo-northstar-20270310", 90_720, 0),
    ]
    assert (
        formation.total_reference_cents,
        formation.total_cost_cents,
        formation.total_value_cents,
    ) == (627_720, 618_720, 9_000)
    stats = formation.cache_statistics
    assert (stats.requests, stats.hits, stats.oracle_calls) == (72, 10, 62)
    assert (plan.pool_version, plan.pool_sha256) == (pool.version, pool.sha256)
    assert (plan.catalog_version, plan.catalog_sha256) == ("catalog-v1", market.catalog.sha256)


def test_plan_is_deterministic(market):
    first, second = plan_lot(pinned_input(), market), plan_lot(pinned_input(), market)
    assert first.formation.result_sha256 == second.formation.result_sha256
    assert {k: j.journal_sha256 for k, j in first.journals.items()} == {
        k: j.journal_sha256 for k, j in second.journals.items()
    }


def test_route_selection_keeps_only_pool_units_on_the_focus_routes(market):
    pool = load_demand_pool(POOL_PATH)
    tokyo = plan_lot(PlanningInput((request("user"),), pool, REFERENCE), market)
    assert tokyo.pool_unit_ids == ("pool-tyo-01", "pool-tyo-02", "pool-tyo-03", "pool-tyo-04")
    both = plan_lot(
        PlanningInput((request("user"), request("user-2", "Rome", 1, "400")), pool, REFERENCE),
        market,
    )
    assert both.pool_unit_ids == tuple(sorted(item.request_id for item in pool.requests))
    assert both.focus_request_ids == ("user", "user-2")
    assert both.lot_unit_ids == tuple(sorted([*both.pool_unit_ids, "user", "user-2"]))


def test_capacity_model_violation_negotiates_nothing(market):
    pool = load_demand_pool(POOL_PATH)
    focus = (request("user", "Rome", 20, "400"), request("user-2", "Rome", 20, "400"))
    plan = plan_lot(PlanningInput(focus, pool, REFERENCE), market)
    assert plan.status == "planned"
    assert plan.formation.status == "capacity_model_violated"
    assert plan.stages.references is None
    assert not plan.journals
    assert (plan.invariants.attempts, plan.invariants.oracle_calls) == (0, 0)


def test_unknown_destination_has_no_admissible_offer(market):
    pool = load_demand_pool(POOL_PATH)
    plan = plan_lot(PlanningInput((request("user", "Paris"),), pool, REFERENCE), market)
    assert plan.pool_unit_ids == ()
    assert plan.formation.status == "no_eligible_units"
    assert [(u.unit_id, u.reason) for u in plan.formation.unserved] == [
        ("user", "no_admissible_offer")
    ]
    assert not plan.journals


def test_budget_below_every_floor_has_no_solo_reference(market):
    pool = load_demand_pool(POOL_PATH)
    plan = plan_lot(PlanningInput((request("user", "Tokyo", 1, "100"),), pool, REFERENCE), market)
    assert ("user", "no_solo_reference") in [(u.unit_id, u.reason) for u in plan.formation.unserved]
    user = next(r for r in plan.stages.references.unit_references if r.unit_id == "user")
    assert user.attempts and all(a.status != "agreement" for a in user.attempts)
    for attempt in user.attempts:  # the failed negotiations are journaled (J3)
        assert plan.journal_for(attempt.request_key).status == attempt.status
    assert all("user" not in block.unit_ids for block in plan.formation.blocks)


def test_request_not_ready_is_rejected_without_negotiation(market):
    pool = load_demand_pool(POOL_PATH)
    incomplete = PlanningRequest("user", TravelRequestDraft(destination="Tokyo", travellers=2))
    plan = plan_lot(PlanningInput((incomplete,), pool, REFERENCE), market)
    assert plan.status == "request_rejected"
    assert plan.stages is None and plan.formation is None and not plan.journals
    (rejection,) = plan.rejections
    assert (rejection.request_id, rejection.reason, rejection.status) == (
        "user",
        "request_not_ready",
        "needs_clarification",
    )
    assert rejection.missing_fields == ("budget_per_person",)


def test_planning_input_validation(market):
    with pytest.raises(PlanningInputError, match="at least one focus"):
        PlanningInput((), None, REFERENCE)
    with pytest.raises(PlanningInputError, match="unique"):
        PlanningInput((request("user"), request("user")), None, REFERENCE)
    with pytest.raises(PlanningInputError, match="both focus and pool"):
        PlanningInput((request("x"),), snapshot([request("x")]), REFERENCE)
    with pytest.raises(PlanningInputError, match="stripped"):
        PlanningRequest(" user", draft())
    with pytest.raises(PlanningInputError, match="unique"):
        snapshot([request("p"), request("p")])
    other_day = PlanningInput((request("user"),), None, REFERENCE.replace(day=20))
    with pytest.raises(PlanningInputError, match="reference dates"):
        plan_lot(other_day, market)
    with pytest.raises(PlanningInputError, match="targets catalog-v0"):
        plan_lot(PlanningInput((request("user"),), snapshot([], "catalog-v0"), REFERENCE), market)


def test_a_pool_request_that_cannot_become_a_unit_is_a_data_error(market):
    past = request("pool-x", departure_after=REFERENCE.replace(year=2025))
    with pytest.raises(PoolRequestError, match="pool-x"):
        plan_lot(PlanningInput((request("user"),), snapshot([past]), REFERENCE), market)


def test_trip_plan_status_and_stages_are_consistent(pinned_plan):
    common = {
        "focus_request_ids": ("a", "e"),
        "units": (),
        "pool_unit_ids": (),
        "journals": MappingProxyType({}),
        "invariants": None,
        "reference_date": REFERENCE,
        "catalog_version": "catalog-v1",
        "catalog_sha256": "0" * 64,
        "oracle_configuration_id": "x",
        "pool_version": None,
        "pool_sha256": None,
    }
    with pytest.raises(PlanConsistencyError):
        TripPlan(status="planned", rejections=(), stages=None, **common)
    with pytest.raises(PlanConsistencyError):
        TripPlan(status="request_rejected", rejections=(), stages=None, **common)
    with pytest.raises(PlanConsistencyError):
        TripPlan(status="planned", rejections=("r",), stages=pinned_plan.stages, **common)


def test_formation_stages_hold_references_exactly_outside_h2_violations(pinned_plan, market):
    stages = pinned_plan.stages
    with pytest.raises(FormationConsistencyError):
        FormationStages(stages.lot, None, stages.formation)
    pool = load_demand_pool(POOL_PATH)
    focus = (request("user", "Rome", 20, "400"), request("user-2", "Rome", 20, "400"))
    violated = plan_lot(PlanningInput(focus, pool, REFERENCE), market).stages
    with pytest.raises(FormationConsistencyError):
        FormationStages(violated.lot, stages.references, violated.formation)


def test_a_session_that_is_not_fresh_is_refused(market):
    used = market.open_session()
    used.negotiate(
        negotiation_request_for(
            (build_travel_unit("x", draft(), REFERENCE),),
            market.catalog.get("tyo-northstar-20270310"),
        )
    )

    class ReusingMarket:
        catalog = market.catalog
        reference_date = market.reference_date
        oracle_configuration_id = market.oracle_configuration_id

        def open_session(self):
            return used

    with pytest.raises(PlanConsistencyError, match="start without journals"):
        plan_lot(PlanningInput((request("user"),), None, REFERENCE), ReusingMarket())
