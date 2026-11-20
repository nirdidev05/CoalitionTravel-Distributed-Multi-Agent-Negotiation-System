"""P4.5: savings decomposition, tier boundaries, metrics and scenario generator (M7, D8)."""

import dataclasses
import json
import random
from datetime import date

import pytest
from coalition_travel.application.coalition_formation import form_coalitions
from coalition_travel.application.formation_evaluation import (
    RESIDUAL_LABEL,
    BlockMember,
    DecompositionMismatch,
    SavingsDecomposition,
    block_decomposition,
    decompose_block,
    formation_metrics,
    structure_decomposition,
)
from coalition_travel.application.lot_admissibility import lot_admissibility
from coalition_travel.application.negotiation_cache import CachingNegotiationOracle
from coalition_travel.application.reference_costs import compute_reference_costs
from coalition_travel.domain.offer import OfferQuote, PriceTier
from coalition_travel.infrastructure.evaluation.formation_scenarios import (
    ScenarioError,
    ScenarioParameters,
    build_scenario,
    derived_seed,
)
from p4_support import REFERENCE, TableOracle, make_catalog, make_offer, make_unit

GRID = ((1, 10_000), (3, 6_000), (6, 5_000))


def offer(tiers=GRID, offer_id="common", capacity=40):
    return OfferQuote(
        offer_id,
        "v",
        "S",
        "Tokyo",
        date(2027, 1, 1),
        date(2027, 1, 2),
        True,
        capacity,
        tuple(PriceTier(s, p) for s, p in tiers),
    )


def tier_pooling(seats, tiers=GRID):
    common = offer(tiers)
    members = tuple(
        BlockMember(f"u{index}", count, common, common.list_total(count))
        for index, count in enumerate(seats)
    )
    return decompose_block(
        members, common, common.list_total(sum(seats))
    ).savings_public_tier_pooling


@pytest.mark.parametrize(
    "seats,expected",
    [
        ((1, 1), 0),  # 2 seats: just below the threshold 3
        ((1, 2), 12_000),  # exactly at the threshold: 30 000 -> 18 000
        ((2, 2), 16_000),  # just above: 40 000 -> 24 000
        ((2, 2, 1), 20_000),  # 5 seats: 50 000 -> 30 000
        ((3, 3), 6_000),  # threshold 6 from two members already at tier 3
        ((6, 1), 5_000),  # one member already at the top tier
        ((6, 6), 0),  # every member at the top tier
        ((2, 3), 8_000),  # members on different tiers: 20 000 + 18 000 -> 30 000
    ],
)
def test_public_tier_pooling_at_tier_boundaries(seats, expected):
    assert tier_pooling(seats) == expected


def test_total_list_price_is_not_monotone_but_pooling_stays_non_negative():
    common = offer()
    assert common.list_total(2) == 20_000 > common.list_total(3) == 18_000
    assert tier_pooling((1, 1, 1)) == 30_000 - 18_000


def test_single_tier_grid_gives_no_pooling_and_capacity_can_be_reached_exactly():
    assert tier_pooling((2, 3, 4), tiers=((1, 7_000),)) == 0
    common = offer(capacity=7)
    members = (BlockMember("a", 3, common, 18_000), BlockMember("b", 4, common, 24_000))
    assert decompose_block(members, common, 35_000).common_offer_collective_list_cents == 35_000


def test_public_tier_pooling_is_non_negative_on_random_valid_grids():
    rng = random.Random(11)
    for _ in range(500):
        thresholds = sorted(rng.sample(range(2, 12), rng.randint(0, 4)))
        prices = sorted(
            (rng.randint(1_000, 50_000) for _ in range(len(thresholds) + 1)), reverse=True
        )
        tiers = tuple(zip([1, *thresholds], prices))
        seats = [rng.randint(1, 6) for _ in range(rng.randint(1, 5))]
        assert tier_pooling(seats, tiers=tiers) >= 0


def test_identities_are_exact_and_checked():
    common, own = offer(), offer(((1, 12_000),), offer_id="own")
    members = (BlockMember("a", 1, own, 11_000), BlockMember("b", 2, common, 19_000))
    d = decompose_block(members, common, 26_500)
    assert d.individual_list_cents == 12_000 + 20_000
    assert d.common_offer_individual_list_cents == 10_000 + 20_000
    assert d.common_offer_collective_list_cents == 18_000
    assert (
        d.savings_offer_switch + d.savings_public_tier_pooling + d.residual_collective_negotiation
        == (d.reference_cents - d.cost_cents)
    )
    assert (
        d.savings_individual_negotiation
        + d.savings_offer_switch
        + d.savings_public_tier_pooling
        + (d.residual_collective_negotiation)
        == d.individual_list_cents - d.cost_cents
    )
    with pytest.raises(DecompositionMismatch):
        dataclasses.replace(
            d, residual_collective_negotiation=d.residual_collective_negotiation + 1
        )
    with pytest.raises(DecompositionMismatch):
        SavingsDecomposition(("a",), "o", 100, 90, 120, 130, 80, 10, -20, -10, 50 - 10)


def test_decomposition_of_real_formation_results(tmp_path):
    for seed in range(6):
        scenario = build_scenario(
            ScenarioParameters(unit_count=8, tier_grid="steep"), seed, tmp_path
        )
        lot = lot_admissibility(scenario.units, scenario.catalog, scenario.reference_date)
        caching = CachingNegotiationOracle(scenario.oracle)
        references = compute_reference_costs(lot, caching)
        result = form_coalitions(lot, references, caching)
        totals = structure_decomposition(result, references)
        assert totals.residual_label == RESIDUAL_LABEL
        assert totals.reference_cents - totals.cost_cents == result.total_value_cents
        for block in result.blocks:
            part = block_decomposition(block, references)
            assert part.value_cents == block.value_cents
            if len(block.unit_ids) == 1:
                assert (
                    part.savings_offer_switch,
                    part.savings_public_tier_pooling,
                    part.residual_collective_negotiation,
                ) == (0, 0, 0)


def test_metrics_on_a_hand_computed_lot():
    units = [
        make_unit("a", budget="500"),
        make_unit("b", budget="501"),
        make_unit("c", budget="502"),
    ]
    units.append(make_unit("z", excluded=("Supplier-o1",)))
    lot = lot_admissibility(units, make_catalog([make_offer("o1")]), REFERENCE)
    prices = {1: 40_000, 2: 76_000, 3: None}
    caching = CachingNegotiationOracle(TableOracle(lambda ids, offer: prices[len(ids)]))
    references = compute_reference_costs(lot, caching)
    result = form_coalitions(lot, references, caching)
    metrics = formation_metrics(result, len(units), references)
    # Pairs save 4 000; the triple has no agreement: one pair + one singleton.
    assert (metrics.social_value_cents, metrics.coalition_count, metrics.block_count) == (
        4_000,
        1,
        2,
    )
    assert (metrics.eligible_units, metrics.unserved_units, metrics.lot_units) == (3, 1, 4)
    assert (metrics.candidates, metrics.feasible_candidates) == (7, 6)
    assert (metrics.negotiations, metrics.agreements) == (7, 6)
    assert metrics.coalition_sizes == ((2, 1),)
    assert metrics.savings_rate * 120_000 == 4_000


# --- scenario generator (D8, D9) -----------------------------------------------------------


def test_scenarios_are_reproducible_and_seeds_independent(tmp_path):
    params = ScenarioParameters(unit_count=5)
    first = build_scenario(params, 2, tmp_path / "a")
    second = build_scenario(params, 2, tmp_path / "b")
    assert first.manifest == second.manifest
    assert first.units == second.units and first.catalog == second.catalog
    assert (
        build_scenario(params, 3, tmp_path).manifest["catalog_sha256"]
        != first.manifest["catalog_sha256"]
    )
    assert derived_seed(params.cell_id, 0) != derived_seed(params.cell_id, 1)


def test_scenario_controls(tmp_path):
    dense = build_scenario(
        ScenarioParameters(
            unit_count=6, offer_count=3, density_percent=100, agreement_target_percent=100
        ),
        0,
        tmp_path,
    )
    lot = lot_admissibility(dense.units, dense.catalog, dense.reference_date)
    assert len(lot.relation.edges) == 6 * 3
    assert lot.status == "optimizable"
    for check in lot.capacity_checks:
        assert check.capacity_seats >= 1.5 * check.admissible_unit_seats
    references = compute_reference_costs(lot, dense.oracle)
    assert all(item.status == "referenced" for item in references.unit_references)
    refused = build_scenario(
        ScenarioParameters(unit_count=6, density_percent=100, agreement_target_percent=0),
        0,
        tmp_path,
    )
    lot = lot_admissibility(refused.units, refused.catalog, refused.reference_date)
    references = compute_reference_costs(lot, refused.oracle)
    assert all(item.status == "no_solo_reference" for item in references.unit_references)
    violated = build_scenario(
        ScenarioParameters(family="h2_violation", tier_grid="flat", density_percent=100),
        0,
        tmp_path,
    )
    assert lot_admissibility(violated.units, violated.catalog, REFERENCE).status == (
        "capacity_model_violated"
    )


def test_scenario_parameter_validation():
    with pytest.raises(ScenarioError):
        ScenarioParameters(tier_grid="spiky")
    with pytest.raises(ScenarioError):
        ScenarioParameters(unit_count=0)
    with pytest.raises(ScenarioError):
        ScenarioParameters(family="h2_violation")  # needs flat grid and density 100


def test_scenario_exposes_no_private_term(tmp_path):
    scenario = build_scenario(ScenarioParameters(unit_count=4), 0, tmp_path)
    field_types = {type(getattr(scenario, f.name)).__name__ for f in dataclasses.fields(scenario)}
    assert not {"SellerTermsBook", "SellerTerms", "SellerFloorTier"} & field_types
    assert "floor" not in json.dumps(scenario.manifest).casefold()
