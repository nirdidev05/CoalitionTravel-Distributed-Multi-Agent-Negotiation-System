"""P4.3: formation of a lot, component by component (M9)."""

import hashlib
import itertools
import random
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from coalition_travel.application.coalition_candidates import CoalitionCandidate, FormationLimits
from coalition_travel.application.coalition_costs import (
    OracleConfigurationMismatch,
    negotiate_candidate,
)
from coalition_travel.application.coalition_formation import (
    form_coalitions,
    run_formation_pipeline,
)
from coalition_travel.application.lot_admissibility import lot_admissibility
from coalition_travel.application.negotiation_cache import CachingNegotiationOracle
from coalition_travel.application.reference_costs import compute_reference_costs
from coalition_travel.domain.coalition_game import GameConsistencyError
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile
from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog
from coalition_travel.infrastructure.evaluation.formation_scenarios import (
    ScenarioParameters,
    build_scenario,
)
from coalition_travel.infrastructure.negotiation.simulated_oracle import (
    SimulatedNegotiationOracle,
    SimulatedOracleConfig,
)
from p4_support import REFERENCE, TableOracle, make_catalog, make_offer, make_unit, set_partitions

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data/catalog/catalog_v1.json"


def catalog_v1_lot():
    catalog, terms = load_offer_catalog(CATALOG_PATH)
    oracle = SimulatedNegotiationOracle(catalog, terms, SimulatedOracleConfig(date(2026, 11, 19)))

    def unit(unit_id, seats, budget, destination="Tokyo"):
        profile = TravelerProfile("p1", seats, destination, Decimal(budget))
        return TravelUnit(
            unit_id,
            destination.casefold(),
            (profile,),
            hashlib.sha256(unit_id.encode()).hexdigest(),
        )

    units = [
        unit("a", 1, 520),
        unit("b", 1, 540),
        unit("c", 2, 500),
        unit("d", 1, 600),
        unit("e", 2, 450, "Rome"),
        unit("f", 1, 330, "Rome"),
    ]
    return units, catalog, oracle


def test_catalogue_v1_lot_is_pinned():
    """Regression anchor computed with the real P3 oracle; any change must be explained."""
    units, catalog, oracle = catalog_v1_lot()
    result = run_formation_pipeline(units, catalog, REFERENCE, oracle)
    assert result.status == "optimized"
    assert [(b.unit_ids, b.offer_id, b.cost_cents, b.value_cents) for b in result.blocks] == [
        (("a", "b", "c"), "tyo-northstar-20270310", 187_200, 2_520),
        (("d",), "tyo-skyways-20270312", 54_000, 0),
        (("e", "f"), "rom-cloudwing-20270405", 81_000, 9_000),
    ]
    assert (result.total_reference_cents, result.total_cost_cents, result.total_value_cents) == (
        333_720,
        322_200,
        11_520,
    )
    for component in result.components:
        assert component.solution.checks == ("dp", "brute_force")
    stats = result.cache_statistics
    assert stats.hits == 10  # every solo negotiation of P2 is reused by the singletons


def test_component_decomposition_equals_a_whole_lot_optimum(tmp_path):
    """Theorem of section 5: optimizing per component equals optimizing the whole lot."""
    for seed in range(12):
        scenario = build_scenario(
            ScenarioParameters(
                unit_count=6, offer_count=3, density_percent=50, profiles_per_unit=1
            ),
            seed,
            tmp_path,
        )
        lot = lot_admissibility(scenario.units, scenario.catalog, scenario.reference_date)
        caching = CachingNegotiationOracle(scenario.oracle)
        references = compute_reference_costs(lot, caching)
        result = form_coalitions(lot, references, caching)
        relation = references.effective_relation
        players = [unit.unit_id for unit in relation.units]
        values = {}
        for size in range(1, len(players) + 1):
            for coalition in itertools.combinations(players, size):
                common = relation.common_offers(coalition)
                if not common:
                    continue
                cost = negotiate_candidate(
                    CoalitionCandidate(coalition, tuple(o.offer_id for o in common)),
                    relation,
                    caching,
                )
                if cost.feasible:
                    values[coalition] = (
                        sum(references.reference(u) for u in coalition) - cost.cost_cents
                    )
        best = None
        for partition in set_partitions(players):
            blocks = [tuple(sorted(block)) for block in partition]
            if all(block in values for block in blocks):
                key = (sum(values[block] for block in blocks), len(blocks))
                best = key if best is None or key > best else best
        assert best == (result.total_value_cents, len(result.blocks))


def test_h2_violation_is_refused_without_any_oracle_call(tmp_path):
    scenario = build_scenario(
        ScenarioParameters(
            family="h2_violation", tier_grid="flat", density_percent=100, unit_count=4
        ),
        0,
        tmp_path,
    )

    class Counting:
        oracle_configuration_id = scenario.oracle.oracle_configuration_id
        calls = 0

        def negotiate(self, request):
            Counting.calls += 1
            return scenario.oracle.negotiate(request)

    result = run_formation_pipeline(
        scenario.units, scenario.catalog, scenario.reference_date, Counting()
    )
    assert result.status == "capacity_model_violated"
    assert Counting.calls == 0
    assert result.blocks == ()
    assert result.unresolved_unit_ids == tuple(sorted(u.unit_id for u in scenario.units))


def test_input_order_and_repetition_do_not_change_the_result(tmp_path):
    scenario = build_scenario(ScenarioParameters(unit_count=7), 4, tmp_path)
    first = run_formation_pipeline(scenario.units, scenario.catalog, REFERENCE, scenario.oracle)
    shuffled = list(scenario.units)
    random.Random(0).shuffle(shuffled)
    second = run_formation_pipeline(shuffled, scenario.catalog, REFERENCE, scenario.oracle)
    assert first.result_sha256 == second.result_sha256
    assert first.formation_run_id == second.formation_run_id
    assert first.blocks == second.blocks


def test_references_and_formation_must_share_the_configuration():
    units = [make_unit("a", budget="500"), make_unit("b", budget="501")]
    lot = lot_admissibility(units, make_catalog([make_offer("o1")]), REFERENCE)
    price = lambda ids, offer: 40_000 * len(ids)
    references = compute_reference_costs(lot, CachingNegotiationOracle(TableOracle(price, "X")))
    with pytest.raises(OracleConfigurationMismatch):
        form_coalitions(lot, references, CachingNegotiationOracle(TableOracle(price, "Y")))
    with pytest.raises(TypeError, match="CachingNegotiationOracle"):
        form_coalitions(lot, references, TableOracle(price, "X"))


def test_a_singleton_cost_different_from_its_reference_is_refused():
    units = [make_unit("a", budget="500"), make_unit("b", budget="501")]
    lot = lot_admissibility(units, make_catalog([make_offer("o1")]), REFERENCE)
    references = compute_reference_costs(
        lot, CachingNegotiationOracle(TableOracle(lambda ids, offer: 40_000 * len(ids)))
    )
    drifting = TableOracle(lambda ids, offer: 39_000 * len(ids))  # same configuration id
    with pytest.raises(GameConsistencyError, match="differs from ref"):
        form_coalitions(lot, references, CachingNegotiationOracle(drifting))


def test_component_too_large_makes_the_result_incomplete_without_negotiation():
    units = [make_unit(f"u{i:02d}", budget=str(500 + i)) for i in range(5)]
    units.append(make_unit("z", budget="500", destination="Rome"))
    offers = [make_offer("o1"), make_offer("r1", destination="Rome")]
    lot = lot_admissibility(units, make_catalog(offers), REFERENCE)
    table = TableOracle(lambda ids, offer: 40_000 * len(ids))
    caching = CachingNegotiationOracle(table)
    references = compute_reference_costs(lot, caching)
    solo_calls = len(table.calls)
    result = form_coalitions(
        lot, references, caching, limits=FormationLimits(max_component_units=4)
    )
    assert result.status == "incomplete"
    assert result.unresolved_unit_ids == ("u00", "u01", "u02", "u03", "u04")
    assert [block.unit_ids for block in result.blocks] == [("z",)]
    assert len(table.calls) == solo_calls  # the large component was never negotiated
    too_large = [c for c in result.components if c.status == "component_too_large"]
    assert len(too_large) == 1 and too_large[0].solution is None


def test_no_eligible_units_status():
    units = [make_unit("a", excluded=("Supplier-o1",))]
    lot = lot_admissibility(units, make_catalog([make_offer("o1")]), REFERENCE)
    caching = CachingNegotiationOracle(TableOracle(lambda ids, offer: 1))
    references = compute_reference_costs(lot, caching)
    result = form_coalitions(lot, references, caching)
    assert result.status == "no_eligible_units"
    assert [item.reason for item in result.unserved] == ["no_admissible_offer"]


def test_blocks_respect_the_identities_and_the_common_offers(tmp_path):
    for seed in range(5):
        scenario = build_scenario(ScenarioParameters(unit_count=8), seed, tmp_path)
        lot = lot_admissibility(scenario.units, scenario.catalog, scenario.reference_date)
        caching = CachingNegotiationOracle(scenario.oracle)
        references = compute_reference_costs(lot, caching)
        result = form_coalitions(lot, references, caching)
        relation = references.effective_relation
        for block in result.blocks:
            assert block.offer_id in {o.offer_id for o in relation.common_offers(block.unit_ids)}
            assert block.value_cents == block.reference_total_cents - block.cost_cents
            assert len(block.unit_ids) == 1 or block.value_cents > 0
        assert result.total_value_cents == sum(b.value_cents for b in result.blocks)
        served = sorted(u for b in result.blocks for u in b.unit_ids)
        assert served == sorted(u.unit_id for u in relation.units)


def test_a_defective_candidate_generator_is_caught_before_negotiation(monkeypatch):
    """The structural check (M2) recomputes what M1 declares (defence in depth)."""
    from coalition_travel.application import coalition_formation
    from coalition_travel.application.coalition_feasibility import CandidateInfeasible

    units = [make_unit("a", budget="500"), make_unit("b", budget="501")]
    lot = lot_admissibility(units, make_catalog([make_offer("o1"), make_offer("o2")]), REFERENCE)
    table = TableOracle(lambda ids, offer: 40_000 * len(ids))
    caching = CachingNegotiationOracle(table)
    references = compute_reference_costs(lot, caching)
    solo_calls = len(table.calls)

    def defective(relation, component, limits):
        return (CoalitionCandidate(("a", "b"), ("o1",)),)  # o2 is also common: wrong

    monkeypatch.setattr(coalition_formation, "enumerate_candidates", defective)
    with pytest.raises(CandidateInfeasible, match="differ"):
        form_coalitions(lot, references, caching)
    assert len(table.calls) == solo_calls  # nothing was negotiated
