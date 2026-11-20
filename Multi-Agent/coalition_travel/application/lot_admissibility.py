"""Build the admissibility relation of a lot and enforce the uncoupled_v1 capacity model.

H2 (``uncoupled_v1``): for every offer o, capacity(o) >= sum of the seats of all units
individually admissible to o. It is checked on the whole lot before any reference
negotiation. When it fails, the lot keeps its relation, components and diagnostics, but
``require_optimizable()`` raises ``CapacityModelViolated`` and no negotiation may start.
Accepted MVP restriction: a lot is refused even when a split of the units over several
offers, or a partial service of the lot, would have been feasible. Shared capacity would
require an optimization model with shared resources.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from coalition_travel.domain.admissibility import (
    AdmissibilityPolicy,
    evaluate_unit_offer,
    normalize_supplier_key,
)
from coalition_travel.domain.negotiation_request import unit_economic_digest
from coalition_travel.domain.offer import OfferCatalog
from coalition_travel.domain.offer_graph import (
    AdmissibilityRelation,
    OfferComponent,
    connected_components,
)
from coalition_travel.domain.travel_unit import TravelUnit

CAPACITY_MODEL = "uncoupled_v1"
LotStatus = Literal["optimizable", "capacity_model_violated"]
ExclusionReason = Literal["no_admissible_offer", "no_solo_reference"]
EXCLUSION_REASONS = frozenset({"no_admissible_offer", "no_solo_reference"})
_HEX_DIGITS = frozenset("0123456789abcdef")


class LotAdmissibilityError(ValueError):
    """Base class of lot admissibility errors."""


class LotInputError(LotAdmissibilityError):
    """The lot inputs are empty, of the wrong type or inconsistent."""


class CapacityModelViolated(LotAdmissibilityError):
    """The uncoupled capacity assumption is false for one or more offers."""

    def __init__(self, checks: tuple["CapacityCheck", ...]):
        self.checks = checks
        failed = ", ".join(check.offer_id for check in checks if not check.valid)
        super().__init__(f"{CAPACITY_MODEL} capacity model violated for offers: {failed}")


@dataclass(frozen=True)
class CapacityCheck:
    offer_id: str
    capacity_seats: int
    admissible_unit_seats: int
    unit_ids: tuple[str, ...]  # N(o), sorted
    valid: bool

    def __post_init__(self):
        if type(self.unit_ids) is not tuple or tuple(sorted(self.unit_ids)) != self.unit_ids:
            raise ValueError("unit_ids must be a sorted tuple")
        if self.valid != (self.admissible_unit_seats <= self.capacity_seats):
            raise ValueError("valid must equal admissible_unit_seats <= capacity_seats")


@dataclass(frozen=True)
class UnitExclusion:
    """A unit removed from optimization, always with an explicit reason; never silent."""

    unit_id: str
    reason: ExclusionReason
    details: tuple[str, ...]

    def __post_init__(self):
        if self.reason not in EXCLUSION_REASONS:
            raise ValueError(f"unsupported exclusion reason {self.reason!r}")
        if type(self.details) is not tuple or any(type(item) is not str for item in self.details):
            raise TypeError("details must be a tuple of strings")


@dataclass(frozen=True)
class UnmatchedExclusion:
    """A traveler exclusion naming no supplier of the catalogue (diagnostic, no alias)."""

    unit_id: str
    profile_id: str
    supplier: str


@dataclass(frozen=True)
class LotAdmissibilityResult:
    admissibility_id: str
    policy: AdmissibilityPolicy
    capacity_model: str
    catalog_version: str
    catalog_sha256: str
    reference_date: date
    relation: AdmissibilityRelation
    components: tuple[OfferComponent, ...]
    capacity_checks: tuple[CapacityCheck, ...]
    exclusions: tuple[UnitExclusion, ...]
    unused_offers: tuple[str, ...]
    unmatched_exclusions: tuple[UnmatchedExclusion, ...]
    status: LotStatus

    def __post_init__(self):
        if self.status not in {"optimizable", "capacity_model_violated"}:
            raise ValueError("invalid lot admissibility status")
        violated = any(not check.valid for check in self.capacity_checks)
        if (self.status == "capacity_model_violated") != violated:
            raise ValueError("status must match the capacity checks")
        if self.capacity_model != CAPACITY_MODEL:
            raise ValueError(f"capacity_model must be {CAPACITY_MODEL}")
        if not isinstance(self.policy, AdmissibilityPolicy):
            raise TypeError("policy must be an AdmissibilityPolicy")
        if len(self.admissibility_id) != 64 or not set(self.admissibility_id) <= _HEX_DIGITS:
            raise ValueError("admissibility_id must be a lowercase SHA-256 digest")
        isolated = tuple(unit.unit_id for unit in self.relation.units_without_offers())
        if tuple(item.unit_id for item in self.exclusions) != isolated or any(
            item.reason != "no_admissible_offer" for item in self.exclusions
        ):
            raise ValueError("exclusions must list exactly the units without admissible offer")

    def require_optimizable(self) -> "LotAdmissibilityResult":
        failed = tuple(check for check in self.capacity_checks if not check.valid)
        if failed:
            raise CapacityModelViolated(failed)
        return self


def lot_admissibility(
    units: Iterable[TravelUnit],
    catalog: OfferCatalog,
    reference_date: date,
    policy: AdmissibilityPolicy | None = None,
) -> LotAdmissibilityResult:
    """Evaluate every unit × offer pair, keep the graph and diagnostics, check H2.

    Without an explicit policy, it is deduced from the lot (I4, D-I4-8): NON_FINANCIAL_V1
    for v1 units and offers, NON_FINANCIAL_V2 for route units and packages. A lot that
    mixes both kinds is refused (K9), and so is a policy that contradicts the lot.
    """
    if not isinstance(catalog, OfferCatalog):
        raise LotInputError("catalog must be the public OfferCatalog")
    if isinstance(reference_date, datetime) or not isinstance(reference_date, date):
        raise LotInputError("reference_date must be a datetime.date, not datetime")
    if policy is not None and not isinstance(policy, AdmissibilityPolicy):
        raise LotInputError("policy must be an AdmissibilityPolicy")
    materialized = tuple(units)
    if not materialized:
        raise LotInputError("lot must contain at least one travel unit")
    if any(type(unit) is not TravelUnit for unit in materialized):
        raise LotInputError("lot units must be TravelUnit instances")
    ordered_units = tuple(sorted(materialized, key=lambda unit: unit.unit_id))
    if len({unit.unit_id for unit in ordered_units}) != len(ordered_units):
        raise LotInputError("unit_id values must be unique within a lot")
    offers = catalog.offers
    kinds = {unit.is_route_unit for unit in ordered_units}
    kinds |= {offer.is_route_offer for offer in offers}
    if len(kinds) != 1:
        raise LotInputError("K9: a lot cannot mix v1 and route units or offers")
    deduced = (
        AdmissibilityPolicy.NON_FINANCIAL_V2
        if kinds == {True}
        else AdmissibilityPolicy.NON_FINANCIAL_V1
    )
    if policy is None:
        policy = deduced
    elif policy is not deduced:
        raise LotInputError("the policy contradicts the units and offers of the lot")

    results = tuple(
        evaluate_unit_offer(unit, offer, reference_date, policy)
        for unit in ordered_units
        for offer in offers
    )
    relation = AdmissibilityRelation(ordered_units, offers, results)
    components = connected_components(relation)

    checks = []
    for offer in offers:
        admissible_units = relation.units_for(offer.offer_id)
        demand = sum(unit.seats for unit in admissible_units)
        checks.append(
            CapacityCheck(
                offer_id=offer.offer_id,
                capacity_seats=offer.capacity_seats,
                admissible_unit_seats=demand,
                unit_ids=tuple(unit.unit_id for unit in admissible_units),
                valid=demand <= offer.capacity_seats,
            )
        )
    capacity_checks = tuple(checks)

    exclusions = tuple(
        UnitExclusion(unit.unit_id, "no_admissible_offer", _rejection_details(relation, unit))
        for unit in relation.units_without_offers()
    )
    suppliers = {normalize_supplier_key(offer.supplier_id) for offer in offers}
    unmatched = tuple(
        sorted(
            (
                UnmatchedExclusion(unit.unit_id, profile.profile_id, supplier)
                for unit in ordered_units
                for profile in unit.profiles
                for supplier in profile.excluded_suppliers
                if normalize_supplier_key(supplier) not in suppliers
            ),
            key=lambda item: (item.unit_id, item.profile_id, normalize_supplier_key(item.supplier)),
        )
    )
    status = (
        "capacity_model_violated"
        if any(not check.valid for check in capacity_checks)
        else "optimizable"
    )
    return LotAdmissibilityResult(
        admissibility_id=_admissibility_id(policy, catalog, reference_date, ordered_units),
        policy=policy,
        capacity_model=CAPACITY_MODEL,
        catalog_version=catalog.version,
        catalog_sha256=catalog.sha256,
        reference_date=reference_date,
        relation=relation,
        components=components,
        capacity_checks=capacity_checks,
        exclusions=exclusions,
        unused_offers=tuple(offer.offer_id for offer in relation.offers_without_units()),
        unmatched_exclusions=unmatched,
        status=status,
    )


def _rejection_details(relation: AdmissibilityRelation, unit: TravelUnit) -> tuple[str, ...]:
    """One entry per offer: 'offer_id: reason[@profile], ...' explaining the rejection."""
    details = []
    for offer in relation.offers:
        decision = relation.decision(unit.unit_id, offer.offer_id)
        reasons = ", ".join(
            violation.reason + (f"@{violation.profile_id}" if violation.profile_id else "")
            for violation in decision.violations
        )
        details.append(f"{offer.offer_id}: {reasons}")
    return tuple(details)


def _admissibility_id(
    policy: AdmissibilityPolicy,
    catalog: OfferCatalog,
    reference_date: date,
    units: tuple[TravelUnit, ...],
) -> str:
    """Provenance of one lot evaluation: rules, catalogue, date, and which units with
    which content (the content digest is recomputed, never read from ``fingerprint``)."""
    payload = {
        "policy": policy.value,
        "capacity_model": CAPACITY_MODEL,
        "catalog_sha256": catalog.sha256,
        "reference_date": reference_date.isoformat(),
        "units": [[unit.unit_id, unit_economic_digest(unit)] for unit in units],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
