"""Deterministic bipartite graph between indivisible travel units and offers.

Components only contain vertices with at least one admissible edge, so every component
has at least one unit and one offer and can be handed to the optimizer. Units without
any admissible offer and offers without any admissible unit are exposed separately as
diagnostics. A component is not a clique: units of one component may share no offer,
so ``common_offers`` must always be checked for a candidate coalition.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass

from coalition_travel.domain.admissibility import PairAdmissibility
from coalition_travel.domain.offer import OfferQuote
from coalition_travel.domain.travel_unit import TravelUnit


@dataclass(frozen=True)
class AdmissibilityRelation:
    units: tuple[TravelUnit, ...]
    offers: tuple[OfferQuote, ...]
    pair_results: tuple[PairAdmissibility, ...]

    def __post_init__(self):
        if type(self.units) is not tuple or any(
            type(unit) is not TravelUnit for unit in self.units
        ):
            raise TypeError("units must be a tuple of TravelUnit")
        if type(self.offers) is not tuple or any(
            type(offer) is not OfferQuote for offer in self.offers
        ):
            raise TypeError("offers must be a tuple of OfferQuote")
        if type(self.pair_results) is not tuple or any(
            type(result) is not PairAdmissibility for result in self.pair_results
        ):
            raise TypeError("pair_results must be a tuple of PairAdmissibility")
        if tuple(sorted(self.units, key=lambda unit: unit.unit_id)) != self.units:
            raise ValueError("units must be sorted by unit_id")
        if tuple(sorted(self.offers, key=lambda offer: offer.offer_id)) != self.offers:
            raise ValueError("offers must be sorted by offer_id")
        if len({unit.unit_id for unit in self.units}) != len(self.units):
            raise ValueError("unit_id values must be unique")
        if len({offer.offer_id for offer in self.offers}) != len(self.offers):
            raise ValueError("offer_id values must be unique")
        expected = tuple(
            (unit.unit_id, offer.offer_id) for unit in self.units for offer in self.offers
        )
        actual = tuple((result.unit_id, result.offer_id) for result in self.pair_results)
        if actual != expected:
            raise ValueError("pair_results must cover the sorted units × offers product")
        if len({result.policy for result in self.pair_results}) > 1:
            raise ValueError("every pair result of a relation must come from the same policy")

    @property
    def edges(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            (result.unit_id, result.offer_id) for result in self.pair_results if result.admissible
        )

    def decision(self, unit_id: str, offer_id: str) -> PairAdmissibility:
        for result in self.pair_results:
            if result.unit_id == unit_id and result.offer_id == offer_id:
                return result
        raise KeyError(f"unknown pair ({unit_id!r}, {offer_id!r})")

    def offers_for(self, unit_id: str) -> tuple[OfferQuote, ...]:
        if unit_id not in {unit.unit_id for unit in self.units}:
            raise KeyError(f"unknown unit_id {unit_id!r}")
        eligible = {offer_id for candidate, offer_id in self.edges if candidate == unit_id}
        return tuple(offer for offer in self.offers if offer.offer_id in eligible)

    def units_for(self, offer_id: str) -> tuple[TravelUnit, ...]:
        if offer_id not in {offer.offer_id for offer in self.offers}:
            raise KeyError(f"unknown offer_id {offer_id!r}")
        eligible = {unit_id for unit_id, candidate in self.edges if candidate == offer_id}
        return tuple(unit for unit in self.units if unit.unit_id in eligible)

    def common_offers(self, unit_ids: Iterable[str]) -> tuple[OfferQuote, ...]:
        ids = tuple(unit_ids)
        if not ids:
            raise ValueError("common_offers requires at least one unit")
        if len(set(ids)) != len(ids):
            raise ValueError("unit IDs must be unique")
        accessible = [{offer.offer_id for offer in self.offers_for(unit_id)} for unit_id in ids]
        common = set.intersection(*accessible)
        return tuple(offer for offer in self.offers if offer.offer_id in common)

    def units_without_offers(self) -> tuple[TravelUnit, ...]:
        """Isolated units: no admissible offer at all (diagnostic, never optimizable)."""
        connected = {unit_id for unit_id, _ in self.edges}
        return tuple(unit for unit in self.units if unit.unit_id not in connected)

    def offers_without_units(self) -> tuple[OfferQuote, ...]:
        """Isolated offers: admissible to no unit of the lot (diagnostic only)."""
        connected = {offer_id for _, offer_id in self.edges}
        return tuple(offer for offer in self.offers if offer.offer_id not in connected)

    def with_units(self, unit_ids: Iterable[str]) -> "AdmissibilityRelation":
        retained = set(unit_ids)
        if not retained <= {unit.unit_id for unit in self.units}:
            raise ValueError("cannot retain an unknown unit")
        units = tuple(unit for unit in self.units if unit.unit_id in retained)
        results = tuple(result for result in self.pair_results if result.unit_id in retained)
        return AdmissibilityRelation(units, self.offers, results)


@dataclass(frozen=True)
class OfferComponent:
    component_id: str
    units: tuple[TravelUnit, ...]
    offers: tuple[OfferQuote, ...]

    def __post_init__(self):
        if not self.units or not self.offers:
            raise ValueError("an offer component needs at least one unit and one offer")
        if tuple(sorted(self.units, key=lambda unit: unit.unit_id)) != self.units:
            raise ValueError("component units must be sorted")
        if tuple(sorted(self.offers, key=lambda offer: offer.offer_id)) != self.offers:
            raise ValueError("component offers must be sorted")
        expected = _component_id(self.units, self.offers)
        if self.component_id != expected:
            raise ValueError("component_id does not match its vertices")


def _component_id(units: tuple[TravelUnit, ...], offers: tuple[OfferQuote, ...]) -> str:
    payload = {
        "units": [unit.unit_id for unit in units],
        "offers": [offer.offer_id for offer in offers],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def connected_components(relation: AdmissibilityRelation) -> tuple[OfferComponent, ...]:
    """Connected components of the admissible edges only (isolated vertices excluded)."""
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(vertex):
        parent.setdefault(vertex, vertex)
        while parent[vertex] != vertex:
            parent[vertex] = parent[parent[vertex]]
            vertex = parent[vertex]
        return vertex

    def union(left, right):
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            if root_left < root_right:
                parent[root_right] = root_left
            else:
                parent[root_left] = root_right

    for unit_id, offer_id in sorted(relation.edges):
        union(("unit", unit_id), ("offer", offer_id))

    groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for vertex in sorted(parent):
        groups.setdefault(find(vertex), []).append(vertex)
    unit_map = {unit.unit_id: unit for unit in relation.units}
    offer_map = {offer.offer_id: offer for offer in relation.offers}
    components = []
    for group in groups.values():
        unit_ids = sorted(identifier for kind, identifier in group if kind == "unit")
        offer_ids = sorted(identifier for kind, identifier in group if kind == "offer")
        units = tuple(unit_map[identifier] for identifier in unit_ids)
        offers = tuple(offer_map[identifier] for identifier in offer_ids)
        components.append(OfferComponent(_component_id(units, offers), units, offers))
    return tuple(sorted(components, key=lambda component: component.component_id))


def offers_for(relation: AdmissibilityRelation, unit_id: str) -> tuple[OfferQuote, ...]:
    return relation.offers_for(unit_id)


def units_for(relation: AdmissibilityRelation, offer_id: str) -> tuple[TravelUnit, ...]:
    return relation.units_for(offer_id)


def common_offers(
    relation: AdmissibilityRelation, component: OfferComponent | Iterable[str]
) -> tuple[OfferQuote, ...]:
    unit_ids = (
        tuple(unit.unit_id for unit in component.units)
        if isinstance(component, OfferComponent)
        else tuple(component)
    )
    return relation.common_offers(unit_ids)
