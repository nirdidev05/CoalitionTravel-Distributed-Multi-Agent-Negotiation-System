"""Versioned, non-financial unit-to-offer admissibility policy.

The policy reads hard constraints only: destination, offer departure versus the lot
reference date, date windows, required direct flights, supplier exclusions and unit
capacity. Prices, seller floors and traveler budgets are never read here. A preferred
direct flight never rejects an offer; when the offer is not direct it produces the
qualitative note ``direct_preference_not_met`` and no score or weight.

The set of policies is closed: callers can only choose a member of
``AdmissibilityPolicy``; rules live in a read-only registry and every registered policy
must contain all mandatory rules. Changing the rules requires a new policy version.
"""

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from types import MappingProxyType
from typing import Literal

from coalition_travel.domain.destination import normalize_destination_key
from coalition_travel.domain.offer import OfferQuote
from coalition_travel.domain.travel_unit import TravelUnit


class AdmissibilityPolicy(str, Enum):
    """Closed set of supported admissibility policies."""

    NON_FINANCIAL_V1 = "non_financial_v1"
    NON_FINANCIAL_V2 = "non_financial_v2"  # route packages (plan §6.2, I4)


class AdmissibilityRuleId(str, Enum):
    DESTINATION = "destination"
    OFFER_NOT_BEFORE_REFERENCE = "offer_not_before_reference"
    DEPARTURE_WINDOW = "departure_window"
    ARRIVAL_WINDOW = "arrival_window"
    DIRECT_FLIGHT = "direct_flight"
    SUPPLIER_EXCLUSION = "supplier_exclusion"
    UNIT_CAPACITY = "unit_capacity"
    ORIGIN = "origin"  # v2 only
    TRIP_TYPE = "trip_type"  # v2 only
    RETURN_WINDOW = "return_window"  # v2 only


RULE_ORDER = (
    AdmissibilityRuleId.DESTINATION,
    AdmissibilityRuleId.OFFER_NOT_BEFORE_REFERENCE,
    AdmissibilityRuleId.DEPARTURE_WINDOW,
    AdmissibilityRuleId.ARRIVAL_WINDOW,
    AdmissibilityRuleId.DIRECT_FLIGHT,
    AdmissibilityRuleId.SUPPLIER_EXCLUSION,
    AdmissibilityRuleId.UNIT_CAPACITY,
)
# Hard constraints that no registered policy may drop.
MANDATORY_RULES = frozenset(RULE_ORDER)
# v2 (plan §6.2): the v1 rules in the same relative order, plus the route rules.
RULE_ORDER_V2 = (
    AdmissibilityRuleId.DESTINATION,
    AdmissibilityRuleId.ORIGIN,
    AdmissibilityRuleId.TRIP_TYPE,
    AdmissibilityRuleId.OFFER_NOT_BEFORE_REFERENCE,
    AdmissibilityRuleId.DEPARTURE_WINDOW,
    AdmissibilityRuleId.ARRIVAL_WINDOW,
    AdmissibilityRuleId.RETURN_WINDOW,
    AdmissibilityRuleId.DIRECT_FLIGHT,
    AdmissibilityRuleId.SUPPLIER_EXCLUSION,
    AdmissibilityRuleId.UNIT_CAPACITY,
)
MANDATORY_RULES_V2 = frozenset(RULE_ORDER_V2)

# MappingProxyType plus tuple/Enum values makes both the registry and its values read-only.
RULE_REGISTRY: Mapping[AdmissibilityPolicy, tuple[AdmissibilityRuleId, ...]] = MappingProxyType(
    {
        AdmissibilityPolicy.NON_FINANCIAL_V1: RULE_ORDER,
        AdmissibilityPolicy.NON_FINANCIAL_V2: RULE_ORDER_V2,
    }
)
_EXPECTED_RULES = MappingProxyType(
    {
        AdmissibilityPolicy.NON_FINANCIAL_V1: (RULE_ORDER, MANDATORY_RULES),
        AdmissibilityPolicy.NON_FINANCIAL_V2: (RULE_ORDER_V2, MANDATORY_RULES_V2),
    }
)

RejectionReason = Literal[
    "destination_mismatch",
    "offer_departs_before_reference_date",
    "departure_before_window",
    "arrival_after_window",
    "direct_flight_required",
    "excluded_supplier",
    "unit_exceeds_offer_capacity",
    "origin_mismatch",
    "trip_type_mismatch",
    "departure_after_window",
    "return_before_window",
    "return_after_window",
]
NoteCode = Literal["direct_preference_not_met"]

RULE_REASONS: Mapping[AdmissibilityRuleId, str] = MappingProxyType(
    {
        AdmissibilityRuleId.DESTINATION: "destination_mismatch",
        AdmissibilityRuleId.OFFER_NOT_BEFORE_REFERENCE: "offer_departs_before_reference_date",
        AdmissibilityRuleId.DEPARTURE_WINDOW: "departure_before_window",
        AdmissibilityRuleId.ARRIVAL_WINDOW: "arrival_after_window",
        AdmissibilityRuleId.DIRECT_FLIGHT: "direct_flight_required",
        AdmissibilityRuleId.SUPPLIER_EXCLUSION: "excluded_supplier",
        AdmissibilityRuleId.UNIT_CAPACITY: "unit_exceeds_offer_capacity",
    }
)
# Every reason a rule may give, v1 and v2. The v1 mapping above is unchanged; a v2 window
# rule has two reasons: the code says where the offer lies relative to the window.
RULE_REASONS_V2: Mapping[AdmissibilityRuleId, tuple[str, ...]] = MappingProxyType(
    {
        **{rule: (reason,) for rule, reason in RULE_REASONS.items()},
        AdmissibilityRuleId.DEPARTURE_WINDOW: ("departure_before_window", "departure_after_window"),
        AdmissibilityRuleId.ORIGIN: ("origin_mismatch",),
        AdmissibilityRuleId.TRIP_TYPE: ("trip_type_mismatch",),
        AdmissibilityRuleId.RETURN_WINDOW: ("return_before_window", "return_after_window"),
    }
)
PROFILE_LEVEL_RULES = frozenset(
    {
        AdmissibilityRuleId.DEPARTURE_WINDOW,
        AdmissibilityRuleId.ARRIVAL_WINDOW,
        AdmissibilityRuleId.DIRECT_FLIGHT,
        AdmissibilityRuleId.SUPPLIER_EXCLUSION,
        AdmissibilityRuleId.RETURN_WINDOW,
    }
)
NOTE_CODES = frozenset({"direct_preference_not_met"})


def _violation_sort_key(violation: "AdmissibilityViolation") -> tuple:
    """Rule order, then unit-level (no profile) before profile-level, then profile_id."""
    return (  # RULE_ORDER_V2 keeps the relative order of the v1 rules
        RULE_ORDER_V2.index(violation.rule),
        violation.profile_id is not None,
        violation.profile_id or "",
    )


@dataclass(frozen=True)
class AdmissibilityViolation:
    rule: AdmissibilityRuleId
    reason: RejectionReason
    profile_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.rule, AdmissibilityRuleId):
            raise TypeError("rule must be an AdmissibilityRuleId")
        if self.reason not in RULE_REASONS_V2[self.rule]:
            raise ValueError(f"reason {self.reason!r} does not belong to rule {self.rule.value}")
        if self.rule in PROFILE_LEVEL_RULES:
            if type(self.profile_id) is not str or not self.profile_id:
                raise ValueError(
                    f"{self.rule.value} is a profile-level rule and needs a profile_id"
                )
        elif self.profile_id is not None:
            raise ValueError(f"{self.rule.value} is a unit-level rule and takes no profile_id")


@dataclass(frozen=True)
class AdmissibilityNote:
    """Qualitative remark that never changes admissibility or any economic value."""

    code: NoteCode
    profile_id: str

    def __post_init__(self):
        if self.code not in NOTE_CODES:
            raise ValueError(f"unsupported admissibility note {self.code!r}")
        if type(self.profile_id) is not str or not self.profile_id:
            raise ValueError("a note needs a profile_id")


@dataclass(frozen=True)
class PairAdmissibility:
    unit_id: str
    offer_id: str
    policy: AdmissibilityPolicy
    admissible: bool
    violations: tuple[AdmissibilityViolation, ...]
    notes: tuple[AdmissibilityNote, ...] = ()

    def __post_init__(self):
        if not isinstance(self.policy, AdmissibilityPolicy):
            raise TypeError("policy must be an AdmissibilityPolicy")
        if type(self.admissible) is not bool:
            raise TypeError("admissible must be a bool")
        if type(self.violations) is not tuple or any(
            type(item) is not AdmissibilityViolation for item in self.violations
        ):
            raise TypeError("violations must be a tuple of AdmissibilityViolation")
        if type(self.notes) is not tuple or any(
            type(item) is not AdmissibilityNote for item in self.notes
        ):
            raise TypeError("notes must be a tuple of AdmissibilityNote")
        if self.admissible == bool(self.violations):
            raise ValueError("a pair is admissible exactly when it has no violation")
        if tuple(sorted(self.violations, key=_violation_sort_key)) != self.violations:
            raise ValueError("violations must be sorted by rule order, then profile_id")
        if tuple(sorted(self.notes, key=lambda note: (note.code, note.profile_id))) != self.notes:
            raise ValueError("notes must be sorted by code, then profile_id")


def normalize_supplier_key(value: str) -> str:
    """Normalize supplier names using NFC, strip, casefold, then NFC again."""
    if not isinstance(value, str):
        raise TypeError("supplier name must be a string")
    normalized = unicodedata.normalize(
        "NFC", unicodedata.normalize("NFC", value).strip().casefold()
    )
    if not normalized:
        raise ValueError("supplier name must not be blank")
    return normalized


def evaluate_unit_offer(
    unit: TravelUnit,
    offer: OfferQuote,
    reference_date: date,
    policy: AdmissibilityPolicy = AdmissibilityPolicy.NON_FINANCIAL_V1,
) -> PairAdmissibility:
    """Evaluate every hard non-financial constraint for one indivisible unit and offer.

    A destination mismatch is the only violation reported for its pair. Otherwise all
    rules are evaluated and every violation is reported, in rule order then profile order.
    """
    if not isinstance(unit, TravelUnit):
        raise TypeError("unit must be a TravelUnit")
    if not isinstance(offer, OfferQuote):
        raise TypeError("offer must be an OfferQuote")
    if isinstance(reference_date, datetime) or not isinstance(reference_date, date):
        raise TypeError("reference_date must be a datetime.date, not datetime")
    if not isinstance(policy, AdmissibilityPolicy):
        raise TypeError("policy must be an AdmissibilityPolicy")
    rules = RULE_REGISTRY[policy]
    expected, mandatory = _EXPECTED_RULES[policy]
    if not mandatory <= set(rules) or rules != expected:
        raise RuntimeError("admissibility rule registry is inconsistent")
    route = unit.is_route_unit or offer.is_route_offer
    if (policy is AdmissibilityPolicy.NON_FINANCIAL_V2) != route:
        raise ValueError("a route unit or package needs NON_FINANCIAL_V2, and only them")
    if route:
        return _evaluate_route(unit, offer, reference_date, policy)

    # Re-normalize both inputs here rather than trusting constructors or cached keys.
    if normalize_destination_key(unit.destination_key) != normalize_destination_key(
        offer.destination
    ):
        return PairAdmissibility(
            unit.unit_id,
            offer.offer_id,
            policy,
            False,
            (AdmissibilityViolation(AdmissibilityRuleId.DESTINATION, "destination_mismatch"),),
        )

    profiles = tuple(sorted(unit.profiles, key=lambda profile: profile.profile_id))
    violations: list[AdmissibilityViolation] = []
    if offer.departure_date < reference_date:
        violations.append(
            AdmissibilityViolation(
                AdmissibilityRuleId.OFFER_NOT_BEFORE_REFERENCE,
                "offer_departs_before_reference_date",
            )
        )
    for profile in profiles:
        if profile.departure_after is not None and offer.departure_date < profile.departure_after:
            violations.append(
                AdmissibilityViolation(
                    AdmissibilityRuleId.DEPARTURE_WINDOW,
                    "departure_before_window",
                    profile.profile_id,
                )
            )
    for profile in profiles:
        if profile.arrival_before is not None and offer.arrival_date > profile.arrival_before:
            violations.append(
                AdmissibilityViolation(
                    AdmissibilityRuleId.ARRIVAL_WINDOW, "arrival_after_window", profile.profile_id
                )
            )
    for profile in profiles:
        if profile.direct_flight == "required" and not offer.direct:
            violations.append(
                AdmissibilityViolation(
                    AdmissibilityRuleId.DIRECT_FLIGHT, "direct_flight_required", profile.profile_id
                )
            )
    supplier = normalize_supplier_key(offer.supplier_id)
    for profile in profiles:
        excluded = {normalize_supplier_key(item) for item in profile.excluded_suppliers}
        if supplier in excluded:
            violations.append(
                AdmissibilityViolation(
                    AdmissibilityRuleId.SUPPLIER_EXCLUSION, "excluded_supplier", profile.profile_id
                )
            )
    if unit.seats > offer.capacity_seats:
        violations.append(
            AdmissibilityViolation(AdmissibilityRuleId.UNIT_CAPACITY, "unit_exceeds_offer_capacity")
        )

    notes = tuple(
        AdmissibilityNote("direct_preference_not_met", profile.profile_id)
        for profile in profiles
        if profile.direct_flight == "preferred" and not offer.direct
    )
    return PairAdmissibility(
        unit.unit_id, offer.offer_id, policy, not violations, tuple(violations), notes
    )


def _evaluate_route(unit, offer, reference_date, policy) -> PairAdmissibility:
    """NON_FINANCIAL_V2 (plan §6.2): the v1 rules on the outbound leg, plus the route.

    A route mismatch (destination and/or origin) is the only violation reported for its
    pair, as the destination mismatch is in v1. Return windows apply to a round trip.
    """
    if not (unit.is_route_unit and offer.is_route_offer):
        raise ValueError("NON_FINANCIAL_V2 compares a route unit with a package")
    rule = AdmissibilityRuleId
    route = []
    if normalize_destination_key(unit.destination_key) != offer.destination_key:
        route.append(AdmissibilityViolation(rule.DESTINATION, "destination_mismatch"))
    if normalize_destination_key(unit.origin_key) != offer.origin_key:
        route.append(AdmissibilityViolation(rule.ORIGIN, "origin_mismatch"))
    if route:
        return PairAdmissibility(unit.unit_id, offer.offer_id, policy, False, tuple(route))

    profiles = tuple(sorted(unit.profiles, key=lambda profile: profile.profile_id))
    violations: list[AdmissibilityViolation] = []
    if unit.trip_type != offer.trip_type:
        violations.append(AdmissibilityViolation(rule.TRIP_TYPE, "trip_type_mismatch"))
    if offer.departure_date < reference_date:
        violations.append(
            AdmissibilityViolation(
                rule.OFFER_NOT_BEFORE_REFERENCE, "offer_departs_before_reference_date"
            )
        )
    for profile in profiles:
        if profile.departure_after is not None and offer.departure_date < profile.departure_after:
            violations.append(
                AdmissibilityViolation(
                    rule.DEPARTURE_WINDOW, "departure_before_window", profile.profile_id
                )
            )
        elif (
            profile.departure_before is not None and offer.departure_date > profile.departure_before
        ):
            violations.append(
                AdmissibilityViolation(
                    rule.DEPARTURE_WINDOW, "departure_after_window", profile.profile_id
                )
            )
    for profile in profiles:
        if profile.arrival_before is not None and offer.arrival_date > profile.arrival_before:
            violations.append(
                AdmissibilityViolation(
                    rule.ARRIVAL_WINDOW, "arrival_after_window", profile.profile_id
                )
            )
    back = offer.return_leg
    for profile in profiles if back is not None else ():
        if profile.return_after is not None and back.departure_date < profile.return_after:
            violations.append(
                AdmissibilityViolation(
                    rule.RETURN_WINDOW, "return_before_window", profile.profile_id
                )
            )
        elif profile.return_before is not None and back.departure_date > profile.return_before:
            violations.append(
                AdmissibilityViolation(
                    rule.RETURN_WINDOW, "return_after_window", profile.profile_id
                )
            )
    for profile in profiles:
        if profile.direct_flight == "required" and not offer.direct:
            violations.append(
                AdmissibilityViolation(
                    rule.DIRECT_FLIGHT, "direct_flight_required", profile.profile_id
                )
            )
    supplier = normalize_supplier_key(offer.supplier_id)
    for profile in profiles:
        excluded = {normalize_supplier_key(item) for item in profile.excluded_suppliers}
        if supplier in excluded:
            violations.append(
                AdmissibilityViolation(
                    rule.SUPPLIER_EXCLUSION, "excluded_supplier", profile.profile_id
                )
            )
    if unit.seats > offer.capacity_seats:
        violations.append(AdmissibilityViolation(rule.UNIT_CAPACITY, "unit_exceeds_offer_capacity"))
    notes = tuple(
        AdmissibilityNote("direct_preference_not_met", profile.profile_id)
        for profile in profiles
        if profile.direct_flight == "preferred" and not offer.direct
    )
    return PairAdmissibility(
        unit.unit_id, offer.offer_id, policy, not violations, tuple(violations), notes
    )
