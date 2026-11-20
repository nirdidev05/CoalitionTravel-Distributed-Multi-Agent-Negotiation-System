"""P2 bipartite graph, exact intersections and deterministic components (P2-bis)."""

import hashlib
import random
from datetime import date
from decimal import Decimal
from enum import Enum

import pytest
from coalition_travel.application.lot_admissibility import lot_admissibility
from coalition_travel.domain.admissibility import (
    AdmissibilityPolicy,
    AdmissibilityRuleId,
    AdmissibilityViolation,
    PairAdmissibility,
)
from coalition_travel.domain.offer import OfferCatalog, OfferQuote, PriceTier
from coalition_travel.domain.offer_graph import (
    AdmissibilityRelation,
    OfferComponent,
    common_offers,
    connected_components,
    offers_for,
    units_for,
)
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile

REFERENCE = date(2026, 11, 19)
POLICY = AdmissibilityPolicy.NON_FINANCIAL_V1
NON_EDGE = AdmissibilityViolation(AdmissibilityRuleId.DESTINATION, "destination_mismatch")


def _unit(identifier, destination="Tokyo"):
    profile = TravelerProfile(identifier, 1, destination, Decimal(100))
    return TravelUnit(
        identifier,
        destination.casefold(),
        (profile,),
        hashlib.sha256(identifier.encode()).hexdigest(),
    )


def _offer(identifier, destination="Tokyo"):
    return OfferQuote(
        identifier,
        "v1",
        "Supplier",
        destination,
        date(2027, 1, 1),
        date(2027, 1, 2),
        True,
        20,
        (PriceTier(1, 100),),
    )


def _pair(unit_id, offer_id, edge, policy=POLICY):
    return PairAdmissibility(unit_id, offer_id, policy, edge, () if edge else (NON_EDGE,))


def _relation(unit_ids, offer_ids, edges):
    units = tuple(sorted((_unit(item) for item in unit_ids), key=lambda unit: unit.unit_id))
    offers = tuple(sorted((_offer(item) for item in offer_ids), key=lambda offer: offer.offer_id))
    results = tuple(
        _pair(unit.unit_id, offer.offer_id, (unit.unit_id, offer.offer_id) in edges)
        for unit in units
        for offer in offers
    )
    return AdmissibilityRelation(units, offers, results)


def _shape(components):
    return sorted(
        (tuple(unit.unit_id for unit in item.units), tuple(offer.offer_id for offer in item.offers))
        for item in components
    )


def test_common_offers_is_exact_intersection_not_component_membership():
    relation = _relation(
        ["u1", "u2"],
        ["o1", "o2", "o3"],
        {("u1", "o1"), ("u1", "o2"), ("u2", "o2"), ("u2", "o3")},
    )
    components = connected_components(relation)

    assert _shape(components) == [(("u1", "u2"), ("o1", "o2", "o3"))]
    assert [offer.offer_id for offer in common_offers(relation, components[0])] == ["o2"]
    assert [offer.offer_id for offer in offers_for(relation, "u1")] == ["o1", "o2"]
    assert [unit.unit_id for unit in units_for(relation, "o3")] == ["u2"]


def test_chain_is_one_component_whose_ends_share_no_offer():
    relation = _relation(
        ["u1", "u2", "u3"],
        ["o1", "o2"],
        {("u1", "o1"), ("u2", "o1"), ("u2", "o2"), ("u3", "o2")},
    )
    assert _shape(connected_components(relation)) == [(("u1", "u2", "u3"), ("o1", "o2"))]
    assert relation.common_offers(["u1", "u3"]) == ()
    assert [offer.offer_id for offer in relation.common_offers(["u1", "u2"])] == ["o1"]


def test_isolated_vertices_are_diagnostics_not_components():
    relation = _relation(["u1", "u2"], ["o1", "o2"], {("u1", "o1")})

    assert _shape(connected_components(relation)) == [(("u1",), ("o1",))]
    assert [unit.unit_id for unit in relation.units_without_offers()] == ["u2"]
    assert [offer.offer_id for offer in relation.offers_without_units()] == ["o2"]


def test_relation_without_any_edge_has_no_component():
    relation = _relation(["u1"], ["o1"], set())
    assert connected_components(relation) == ()


def test_every_component_has_at_least_one_unit_and_one_offer():
    with pytest.raises(ValueError, match="at least one unit and one offer"):
        OfferComponent("x", (), (_offer("o1"),))
    with pytest.raises(ValueError, match="at least one unit and one offer"):
        OfferComponent("x", (_unit("u1"),), ())


def _catalog(*offers):
    ordered = tuple(sorted(offers, key=lambda offer: offer.offer_id))
    return OfferCatalog(ordered[0].catalog_version, "a" * 64, ordered)


def test_input_order_does_not_change_edges_components_or_lot_identity():
    catalog = _catalog(_offer("o2"), _offer("o1"))
    units = [_unit("u2"), _unit("u1")]
    first = lot_admissibility(units, catalog, REFERENCE)
    second = lot_admissibility(list(reversed(units)), catalog, REFERENCE)

    assert first.relation.edges == second.relation.edges
    assert [item.component_id for item in first.components] == [
        item.component_id for item in second.components
    ]
    assert first.admissibility_id == second.admissibility_id
    assert first == second


def test_union_find_matches_reference_bfs_on_seeded_random_relations():
    generator = random.Random(240219)
    for _ in range(60):
        unit_ids = [f"u{index}" for index in range(generator.randint(1, 6))]
        offer_ids = [f"o{index}" for index in range(generator.randint(1, 5))]
        edges = {
            (unit_id, offer_id)
            for unit_id in unit_ids
            for offer_id in offer_ids
            if generator.random() < 0.35
        }
        relation = _relation(unit_ids, offer_ids, edges)
        components = connected_components(relation)
        actual = {
            frozenset(
                [
                    *(f"unit:{unit.unit_id}" for unit in component.units),
                    *(f"offer:{offer.offer_id}" for offer in component.offers),
                ]
            )
            for component in components
        }
        assert actual == _bfs_components(unit_ids, offer_ids, edges)
        # I1: both ends of every edge lie in the same component.
        location = {}
        for index, component in enumerate(components):
            location.update({("unit", unit.unit_id): index for unit in component.units})
            location.update({("offer", offer.offer_id): index for offer in component.offers})
        assert all(location[("unit", u)] == location[("offer", o)] for u, o in edges)
        # I2/I3: components partition exactly the vertices that have an edge.
        assert set(location) == {("unit", u) for u, _ in edges} | {("offer", o) for _, o in edges}
        # I4: any coalition with a common offer lies inside one component.
        for offer_id in offer_ids:
            members = [unit.unit_id for unit in relation.units_for(offer_id)]
            assert len({location[("unit", member)] for member in members}) <= 1


def _bfs_components(unit_ids, offer_ids, edges):
    adjacency = {f"unit:{item}": set() for item in unit_ids}
    adjacency.update({f"offer:{item}": set() for item in offer_ids})
    for unit_id, offer_id in edges:
        left, right = f"unit:{unit_id}", f"offer:{offer_id}"
        adjacency[left].add(right)
        adjacency[right].add(left)
    result = set()
    unseen = {vertex for vertex, neighbours in adjacency.items() if neighbours}
    while unseen:
        start = min(unseen)
        stack, component = [start], set()
        while stack:
            vertex = stack.pop()
            if vertex in component:
                continue
            component.add(vertex)
            stack.extend(adjacency[vertex] - component)
        unseen -= component
        result.add(frozenset(component))
    return result


def test_common_offers_rejects_empty_duplicate_or_unknown_units():
    relation = _relation(["u1", "u2"], ["o1"], {("u1", "o1"), ("u2", "o1")})
    with pytest.raises(ValueError, match="at least one unit"):
        relation.common_offers([])
    with pytest.raises(ValueError, match="unique"):
        relation.common_offers(["u1", "u1"])
    with pytest.raises(KeyError):
        relation.common_offers(["u1", "unknown"])


def test_decision_accessor_returns_the_pair_result():
    relation = _relation(["u1"], ["o1", "o2"], {("u1", "o2")})
    assert relation.decision("u1", "o2").admissible
    assert relation.decision("u1", "o1").violations == (NON_EDGE,)
    with pytest.raises(KeyError):
        relation.decision("u1", "o3")


def test_relation_rejects_pair_result_product_with_wrong_order_or_missing_pair():
    units = (_unit("u1"),)
    offers = (_offer("o1"), _offer("o2"))
    with pytest.raises(ValueError, match="cover the sorted"):
        AdmissibilityRelation(units, offers, (_pair("u1", "o1", True),))


def test_relation_rejects_pair_results_from_mixed_policies():
    class OtherPolicy(str, Enum):
        OTHER = "other"

    units = (_unit("u1"),)
    offers = (_offer("o1"), _offer("o2"))
    first = _pair("u1", "o1", True)
    second = _pair("u1", "o2", True)
    # Simulate a second policy value on one result without constructing an invalid object.
    object.__setattr__(second, "policy", OtherPolicy.OTHER)
    with pytest.raises(ValueError, match="same policy"):
        AdmissibilityRelation(units, offers, (first, second))
