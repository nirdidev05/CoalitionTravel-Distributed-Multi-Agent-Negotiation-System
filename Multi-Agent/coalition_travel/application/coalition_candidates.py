"""Candidate coalitions of one component: every C with a common admissible offer (M1).

The set of common offers is anti-monotone, O(C ∪ {u}) ⊆ O(C), so a depth-first search
over the sorted units of the component can stop a branch as soon as the intersection is
empty. The result is exactly {C ⊆ K : C ≠ ∅, O(C) ≠ ∅}, sorted by (size, identifiers).
Specification: docs/PHASE_P4_SPECIFICATION.md section 6.1 and module card M1.
"""

from dataclasses import dataclass

from coalition_travel.domain.offer_graph import AdmissibilityRelation, OfferComponent


@dataclass(frozen=True)
class FormationLimits:
    """Operational, configurable limits (decision D4); not mathematical properties."""

    max_component_units: int = 14
    max_offer_neighbourhood: int = 14
    brute_force_max_units: int = 9

    def __post_init__(self):
        for name in ("max_component_units", "max_offer_neighbourhood", "brute_force_max_units"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive int")
        if self.brute_force_max_units > 10:
            raise ValueError("brute_force_max_units must not exceed 10 (Bell(11) = 678 570)")


DEFAULT_LIMITS = FormationLimits()


@dataclass(frozen=True)
class CoalitionCandidate:
    unit_ids: tuple[str, ...]
    common_offer_ids: tuple[str, ...]

    def __post_init__(self):
        for name in ("unit_ids", "common_offer_ids"):
            value = getattr(self, name)
            if type(value) is not tuple or not value:
                raise ValueError(f"{name} must be a non-empty tuple")
            if any(type(item) is not str for item in value):
                raise TypeError(f"{name} must contain strings")
            if value != tuple(sorted(set(value))):
                raise ValueError(f"{name} must be sorted and unique")


class ComponentTooLarge(ValueError):
    """The component exceeds an operational limit; it is reported, never optimized."""

    def __init__(self, component_id: str, unit_count: int, largest_neighbourhood: int):
        self.component_id = component_id
        self.unit_count = unit_count
        self.largest_neighbourhood = largest_neighbourhood
        super().__init__(
            f"component {component_id} has {unit_count} units and an offer neighbourhood "
            f"of {largest_neighbourhood} units, above the configured limits"
        )


def check_component_size(
    relation: AdmissibilityRelation, component: OfferComponent, limits: FormationLimits
) -> None:
    """Raise ComponentTooLarge before any negotiation when a limit is exceeded."""
    unit_ids = {unit.unit_id for unit in component.units}
    largest = max(
        len(unit_ids & {unit.unit_id for unit in relation.units_for(offer.offer_id)})
        for offer in component.offers
    )
    if len(unit_ids) > limits.max_component_units or largest > limits.max_offer_neighbourhood:
        raise ComponentTooLarge(component.component_id, len(unit_ids), largest)


def enumerate_candidates(
    relation: AdmissibilityRelation, component: OfferComponent, limits: FormationLimits
) -> tuple[CoalitionCandidate, ...]:
    """All coalitions of the component that share at least one admissible offer."""
    if not isinstance(relation, AdmissibilityRelation):
        raise TypeError("relation must be an AdmissibilityRelation")
    if not isinstance(component, OfferComponent):
        raise TypeError("component must be an OfferComponent")
    if not isinstance(limits, FormationLimits):
        raise TypeError("limits must be FormationLimits")
    check_component_size(relation, component, limits)
    component_offers = {offer.offer_id for offer in component.offers}
    unit_ids = tuple(unit.unit_id for unit in component.units)  # sorted by the component
    offers_of = {
        unit_id: frozenset(offer.offer_id for offer in relation.offers_for(unit_id))
        & component_offers
        for unit_id in unit_ids
    }
    found: list[CoalitionCandidate] = []

    def extend(start: int, members: tuple[str, ...], common: frozenset[str]) -> None:
        for index in range(start, len(unit_ids)):
            unit_id = unit_ids[index]
            shared = offers_of[unit_id] if not members else common & offers_of[unit_id]
            if not shared:
                continue  # anti-monotone: no superset of this coalition can share an offer
            coalition = (*members, unit_id)
            found.append(CoalitionCandidate(coalition, tuple(sorted(shared))))
            extend(index + 1, coalition, shared)

    extend(0, (), frozenset())
    return tuple(sorted(found, key=lambda candidate: (len(candidate.unit_ids), candidate.unit_ids)))
