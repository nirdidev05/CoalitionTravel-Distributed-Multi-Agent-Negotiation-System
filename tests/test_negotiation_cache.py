"""P4.2: economic negotiation cache and collective costs (M3)."""

import pytest
from coalition_travel.application.coalition_candidates import (
    CoalitionCandidate,
    FormationLimits,
    enumerate_candidates,
)
from coalition_travel.application.coalition_costs import (
    CoalitionAttempt,
    CoalitionCost,
    negotiate_candidate,
)
from coalition_travel.application.lot_admissibility import lot_admissibility
from coalition_travel.application.negotiation_cache import CachingNegotiationOracle
from coalition_travel.application.reference_costs import (
    NegotiationOracleContractError,
    compute_reference_costs,
)
from coalition_travel.domain.negotiation_request import NegotiationOutcome, negotiation_request_for
from coalition_travel.infrastructure.evaluation.formation_scenarios import (
    ScenarioParameters,
    build_scenario,
)
from p4_support import REFERENCE, TableOracle, make_catalog, make_offer, make_unit


def test_economically_identical_requests_share_one_oracle_call():
    offer = make_offer("o1")
    twin_a = make_unit("a", seats=2, budget="500")
    twin_b = make_unit("b", seats=2, budget="500")  # same content, another identifier
    table = TableOracle(lambda ids, offer_id: 90_000)
    caching = CachingNegotiationOracle(table)
    first = caching.negotiate(negotiation_request_for((twin_a,), offer))
    second = caching.negotiate(negotiation_request_for((twin_b,), offer))
    assert first is second
    assert len(table.calls) == 1
    stats = caching.statistics
    assert (stats.requests, stats.hits, stats.oracle_calls) == (2, 1, 1)


def test_distinct_mandates_are_not_shared():
    offer = make_offer("o1")
    table = TableOracle(lambda ids, offer_id: 40_000)
    caching = CachingNegotiationOracle(table)
    caching.negotiate(negotiation_request_for((make_unit("a", budget="500"),), offer))
    caching.negotiate(negotiation_request_for((make_unit("a", budget="501"),), offer))
    assert len(table.calls) == 2


def test_cache_refuses_oracles_without_configuration_and_bad_requests():
    class Anonymous:
        def negotiate(self, request):
            raise AssertionError("never called")

    with pytest.raises(TypeError, match="oracle_configuration_id"):
        CachingNegotiationOracle(Anonymous())
    caching = CachingNegotiationOracle(TableOracle(lambda ids, offer: 1))
    with pytest.raises(TypeError, match="NegotiationRequest"):
        caching.negotiate("not a request")


def test_contract_violations_are_raised_and_never_cached():
    offer = make_offer("o1")
    unit = make_unit("a", budget="500")
    table = TableOracle(lambda ids, offer_id: 50_001)  # above the 500.00 reservation
    caching = CachingNegotiationOracle(table)
    request = negotiation_request_for((unit,), offer)
    for _ in range(2):
        with pytest.raises(NegotiationOracleContractError, match="reservation"):
            caching.negotiate(request)
    assert len(table.calls) == 2

    class WrongConfiguration(TableOracle):
        def negotiate(self, request):
            return NegotiationOutcome(request.request_key, "agreement", 100, 1, "other")

    with pytest.raises(NegotiationOracleContractError, match="configuration"):
        CachingNegotiationOracle(WrongConfiguration(None)).negotiate(request)


def test_collective_cost_is_the_lowest_agreement_with_offer_id_tie_break():
    offers = [make_offer("o1"), make_offer("o2"), make_offer("o3")]
    units = [make_unit("a", budget="500"), make_unit("b", budget="501")]
    lot = lot_admissibility(units, make_catalog(offers), REFERENCE)
    prices = {"o1": 70_000, "o2": 60_000, "o3": 60_000}
    table = TableOracle(lambda ids, offer_id: prices[offer_id] if len(ids) == 2 else 40_000)
    candidate = CoalitionCandidate(("a", "b"), ("o1", "o2", "o3"))
    cost = negotiate_candidate(candidate, lot.relation, CachingNegotiationOracle(table))
    assert (cost.offer_id, cost.cost_cents, cost.feasible) == ("o2", 60_000, True)
    assert [attempt.offer_id for attempt in cost.attempts] == ["o1", "o2", "o3"]


def test_a_coalition_without_agreement_is_infeasible():
    offers = [make_offer("o1")]
    units = [make_unit("a", budget="500"), make_unit("b", budget="501")]
    lot = lot_admissibility(units, make_catalog(offers), REFERENCE)
    table = TableOracle(lambda ids, offer_id: None if len(ids) == 2 else 40_000)
    cost = negotiate_candidate(
        CoalitionCandidate(("a", "b"), ("o1",)), lot.relation, CachingNegotiationOracle(table)
    )
    assert (cost.feasible, cost.offer_id, cost.cost_cents) == (False, None, None)
    assert cost.attempts[0].status == "rejected"


def test_coalition_cost_invariants():
    agreement = CoalitionAttempt("o1", "k1", "agreement", 100, 2)
    rejection = CoalitionAttempt("o2", "k2", "rejected", None, 14)
    CoalitionCost(("a",), (agreement, rejection), "o1", 100)
    with pytest.raises(ValueError, match="lowest agreement"):
        CoalitionCost(("a",), (agreement,), "o1", 99)
    with pytest.raises(ValueError, match="no offer"):
        CoalitionCost(("a",), (rejection,), "o2", 5)
    with pytest.raises(ValueError, match="sorted"):
        CoalitionCost(("a",), (rejection, agreement), "o1", 100)
    with pytest.raises(ValueError, match="amount"):
        CoalitionAttempt("o1", "k", "agreement", None, 1)


def test_results_are_identical_with_and_without_the_cache(tmp_path):
    scenario = build_scenario(
        ScenarioParameters(unit_count=6, offer_count=2, density_percent=90), 3, tmp_path
    )
    lot = lot_admissibility(scenario.units, scenario.catalog, scenario.reference_date)
    caching = CachingNegotiationOracle(scenario.oracle)
    references = compute_reference_costs(lot, caching)
    for component in references.effective_components:
        for candidate in enumerate_candidates(
            references.effective_relation, component, FormationLimits()
        ):
            cached = negotiate_candidate(candidate, references.effective_relation, caching)
            direct = negotiate_candidate(candidate, references.effective_relation, scenario.oracle)
            assert cached == direct
    assert caching.statistics.hits >= len(references.effective_relation.units)
