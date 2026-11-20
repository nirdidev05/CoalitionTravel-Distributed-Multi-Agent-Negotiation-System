"""P4.2: candidate enumeration (M1) and structural feasibility (M2)."""

import itertools
import random

import pytest
from coalition_travel.application.coalition_candidates import (
    CoalitionCandidate,
    ComponentTooLarge,
    FormationLimits,
    enumerate_candidates,
)
from coalition_travel.application.coalition_feasibility import (
    CandidateInfeasible,
    check_structural_feasibility,
)
from coalition_travel.application.lot_admissibility import (
    CapacityModelViolated,
    lot_admissibility,
)
from coalition_travel.application.negotiation_cache import CachingNegotiationOracle
from coalition_travel.application.reference_costs import compute_reference_costs
from p4_support import REFERENCE, TableOracle, make_catalog, make_offer, make_unit


def lot_from_edges(unit_ids, offer_ids, edges, *, seats=1, capacity=40):
    """Units excluding the suppliers of every offer outside their edges."""
    offers = [make_offer(offer_id, capacity=capacity) for offer_id in offer_ids]
    units = []
    for number, unit_id in enumerate(unit_ids):
        excluded = [offer.supplier_id for offer in offers if (unit_id, offer.offer_id) not in edges]
        units.append(make_unit(unit_id, seats=seats, budget=str(500 + number), excluded=excluded))
    return lot_admissibility(units, make_catalog(offers), REFERENCE)


def naive_candidates(relation, component):
    ids = [unit.unit_id for unit in component.units]
    found = []
    for size in range(1, len(ids) + 1):
        for coalition in itertools.combinations(ids, size):
            common = relation.common_offers(coalition)
            if common:
                found.append((coalition, tuple(offer.offer_id for offer in common)))
    return found


def test_enumeration_equals_naive_enumeration_on_random_relations():
    rng = random.Random(4)
    for _ in range(60):
        unit_ids = [f"u{i}" for i in range(rng.randint(1, 7))]
        offer_ids = [f"o{i}" for i in range(rng.randint(1, 4))]
        edges = {(u, o) for u in unit_ids for o in offer_ids if rng.random() < 0.5}
        lot = lot_from_edges(unit_ids, offer_ids, edges)
        for component in lot.components:
            candidates = enumerate_candidates(lot.relation, component, FormationLimits())
            assert [(c.unit_ids, c.common_offer_ids) for c in candidates] == naive_candidates(
                lot.relation, component
            )


def test_chain_component_has_no_candidate_for_its_two_ends():
    edges = {("u1", "o1"), ("u2", "o1"), ("u2", "o2"), ("u3", "o2")}
    lot = lot_from_edges(["u1", "u2", "u3"], ["o1", "o2"], edges)
    (component,) = lot.components
    coalitions = [
        c.unit_ids for c in enumerate_candidates(lot.relation, component, FormationLimits())
    ]
    assert coalitions == [("u1",), ("u2",), ("u3",), ("u1", "u2"), ("u2", "u3")]


def test_every_subset_of_a_candidate_is_a_candidate():
    rng = random.Random(9)
    for _ in range(30):
        unit_ids = [f"u{i}" for i in range(rng.randint(2, 6))]
        edges = {(u, o) for u in unit_ids for o in ("o1", "o2", "o3") if rng.random() < 0.6}
        lot = lot_from_edges(unit_ids, ["o1", "o2", "o3"], edges)
        for component in lot.components:
            found = {
                c.unit_ids for c in enumerate_candidates(lot.relation, component, FormationLimits())
            }
            for coalition in found:
                for size in range(1, len(coalition)):
                    assert set(itertools.combinations(coalition, size)) <= found


def test_limits_raise_component_too_large_before_any_negotiation():
    unit_ids = [f"u{i:02d}" for i in range(5)]
    lot = lot_from_edges(unit_ids, ["o1"], {(u, "o1") for u in unit_ids})
    (component,) = lot.components
    with pytest.raises(ComponentTooLarge) as error:
        enumerate_candidates(lot.relation, component, FormationLimits(max_component_units=4))
    assert (error.value.unit_count, error.value.largest_neighbourhood) == (5, 5)
    with pytest.raises(ComponentTooLarge):
        enumerate_candidates(lot.relation, component, FormationLimits(max_offer_neighbourhood=4))
    assert len(enumerate_candidates(lot.relation, component, FormationLimits())) == 2**5 - 1


def test_input_order_does_not_change_the_candidates():
    edges = {("u1", "o1"), ("u2", "o1"), ("u2", "o2"), ("u3", "o2"), ("u3", "o1")}
    first = lot_from_edges(["u1", "u2", "u3"], ["o1", "o2"], edges)
    second = lot_from_edges(["u3", "u1", "u2"], ["o2", "o1"], edges)
    assert [
        enumerate_candidates(first.relation, c, FormationLimits()) for c in first.components
    ] == [enumerate_candidates(second.relation, c, FormationLimits()) for c in second.components]


@pytest.mark.parametrize(
    "kwargs",
    [{"max_component_units": 0}, {"brute_force_max_units": 11}, {"max_offer_neighbourhood": 1.5}],
)
def test_formation_limits_validation(kwargs):
    with pytest.raises(ValueError):
        FormationLimits(**kwargs)


def test_candidate_validation():
    with pytest.raises(ValueError):
        CoalitionCandidate(("b", "a"), ("o1",))
    with pytest.raises(ValueError):
        CoalitionCandidate(("a",), ())


# --- structural feasibility (M2) --------------------------------------------------------------


def references_for(lot, price=lambda ids, offer: 40_000 * len(ids)):
    caching = CachingNegotiationOracle(TableOracle(price))
    return compute_reference_costs(lot, caching), caching


def test_structural_feasibility_accepts_every_enumerated_candidate():
    edges = {("u1", "o1"), ("u2", "o1"), ("u2", "o2"), ("u3", "o2")}
    lot = lot_from_edges(["u1", "u2", "u3"], ["o1", "o2"], edges)
    references, _ = references_for(lot)
    for component in references.effective_components:
        for candidate in enumerate_candidates(
            references.effective_relation, component, FormationLimits()
        ):
            check_structural_feasibility(candidate, lot, references)


def test_structural_feasibility_detects_each_violation():
    edges = {("u1", "o1"), ("u2", "o1"), ("u3", "o2"), ("u4", "o1")}
    lot = lot_from_edges(["u1", "u2", "u3", "u4"], ["o1", "o2"], edges)
    # u4 never reaches an agreement, so it has no individual reference.
    references, _ = references_for(
        lot, lambda ids, offer: None if "u4" in ids else 40_000 * len(ids)
    )
    with pytest.raises(CandidateInfeasible, match="without individual reference"):
        check_structural_feasibility(CoalitionCandidate(("u1", "u4"), ("o1",)), lot, references)
    with pytest.raises(CandidateInfeasible, match="exactly one effective component"):
        check_structural_feasibility(CoalitionCandidate(("u1", "u3"), ("o1",)), lot, references)
    with pytest.raises(CandidateInfeasible, match="differ"):
        check_structural_feasibility(
            CoalitionCandidate(("u1", "u2"), ("o1", "o2")), lot, references
        )
    other_lot = lot_from_edges(["u1", "u2"], ["o1"], {("u1", "o1"), ("u2", "o1")})
    with pytest.raises(CandidateInfeasible, match="another lot"):
        check_structural_feasibility(
            CoalitionCandidate(("u1", "u2"), ("o1",)), other_lot, references
        )


def test_structural_feasibility_refuses_a_lot_that_violates_h2():
    lot = lot_from_edges(["u1", "u2"], ["o1"], {("u1", "o1"), ("u2", "o1")}, seats=3, capacity=5)
    assert lot.status == "capacity_model_violated"
    healthy = lot_from_edges(["u1", "u2"], ["o1"], {("u1", "o1"), ("u2", "o1")})
    references, _ = references_for(healthy)
    with pytest.raises(CapacityModelViolated):
        check_structural_feasibility(CoalitionCandidate(("u1",), ("o1",)), lot, references)
