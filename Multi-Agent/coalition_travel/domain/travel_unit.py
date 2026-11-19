"""Indivisible travel unit: one validated request, its profiles and budgets in cents.

A ``TravelUnit`` is the player of the later coalition phases. It is built only by
``application.travel_units.build_travel_unit`` from a request whose status is ``ready``.
All amounts derived here are integer cents; ``TravelerProfile.total_budget`` is never
used because it relies on the caller's global Decimal context.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from coalition_travel.domain.destination import normalize_destination_key
from coalition_travel.domain.money import (
    MAX_CENTS,
    Cents,
    MoneyError,
    cents_from_budget,
    decimal_from_cents,
)
from coalition_travel.domain.traveler_profile import TravelerProfile

MAX_UNIT_ID_LENGTH = 120
_DIRECT_FLIGHT_VALUES = frozenset({"required", "preferred", "any"})
_HEX_DIGITS = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class TravelUnit:
    unit_id: str
    destination_key: str
    profiles: tuple[TravelerProfile, ...]
    fingerprint: str
    rounded_budget_profiles: tuple[str, ...] = ()

    def __post_init__(self):
        _validate_unit_id(self.unit_id)
        if type(self.destination_key) is not str:
            raise TypeError("destination_key must be a string")
        if normalize_destination_key(self.destination_key) != self.destination_key:
            raise ValueError("destination_key must already be normalized")
        if type(self.profiles) is not tuple:
            raise TypeError("profiles must be a tuple")
        if not self.profiles:
            raise ValueError("a travel unit needs at least one profile")
        for profile in self.profiles:
            _validate_profile(profile, self.destination_key)
        identifiers = tuple(profile.profile_id for profile in self.profiles)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("profile identifiers must be unique")
        if identifiers != tuple(sorted(identifiers)):
            raise ValueError("profiles must be sorted by profile_id")
        if self.budget_total_cents > MAX_CENTS:
            raise ValueError("total budget exceeds the supported monetary domain")
        _validate_fingerprint(self.fingerprint)
        _validate_rounded_ids(self.rounded_budget_profiles, set(identifiers))

    @property
    def seats(self) -> int:
        return sum(profile.traveller_count for profile in self.profiles)

    @property
    def budget_total_cents(self) -> Cents:
        """Sum of seats x per-seat budget, computed in integer cents."""
        return sum(
            profile.traveller_count * _exact_cents(profile.budget_per_person)
            for profile in self.profiles
        )

    def budget_per_seat_cents(self, profile_id: str) -> Cents:
        for profile in self.profiles:
            if profile.profile_id == profile_id:
                return _exact_cents(profile.budget_per_person)
        raise KeyError(f"unknown profile {profile_id!r} in unit {self.unit_id!r}")


def _exact_cents(amount: Decimal) -> Cents:
    """Cents of an amount that must already be an exact number of cents."""
    cents = cents_from_budget(amount)
    if decimal_from_cents(cents) != amount:
        raise ValueError(f"budget {amount} is not an exact number of cents")
    return cents


def _validate_unit_id(unit_id) -> None:
    if type(unit_id) is not str:
        raise TypeError("unit_id must be a string")
    if not unit_id or unit_id != unit_id.strip() or len(unit_id) > MAX_UNIT_ID_LENGTH:
        raise ValueError(
            f"unit_id must be non-blank, stripped and at most {MAX_UNIT_ID_LENGTH} characters"
        )


def _validate_profile(profile, destination_key: str) -> None:
    if not isinstance(profile, TravelerProfile):
        raise TypeError("profiles must contain TravelerProfile instances")
    if type(profile.profile_id) is not str:
        raise TypeError("profile_id must be a string")
    if type(profile.traveller_count) is not int or profile.traveller_count < 1:
        raise ValueError("traveller_count must be a positive int")
    if type(profile.excluded_suppliers) is not tuple:
        raise TypeError("excluded_suppliers must be a tuple")
    if any(type(supplier) is not str or not supplier for supplier in profile.excluded_suppliers):
        raise TypeError("excluded_suppliers must contain non-empty strings")
    for value in (profile.departure_after, profile.arrival_before):
        if value is not None and (type(value) is not date or isinstance(value, datetime)):
            raise TypeError("profile dates must be datetime.date values or None")
    if profile.direct_flight not in _DIRECT_FLIGHT_VALUES:
        raise ValueError("direct_flight must be required, preferred or any")
    if not isinstance(profile.budget_per_person, Decimal):
        raise TypeError("budget_per_person must be a Decimal")
    try:
        _exact_cents(profile.budget_per_person)
    except MoneyError as exc:
        raise ValueError(f"profile {profile.profile_id!r} budget is outside the domain") from exc
    if normalize_destination_key(profile.destination) != destination_key:
        raise ValueError("every profile must share the unit destination")


def _validate_fingerprint(fingerprint) -> None:
    if type(fingerprint) is not str:
        raise TypeError("fingerprint must be a string")
    if len(fingerprint) != 64 or not set(fingerprint) <= _HEX_DIGITS:
        raise ValueError("fingerprint must be a lowercase SHA-256 hexadecimal digest")


def _validate_rounded_ids(rounded_ids, profile_ids: set[str]) -> None:
    if type(rounded_ids) is not tuple:
        raise TypeError("rounded_budget_profiles must be a tuple")
    if any(type(identifier) is not str for identifier in rounded_ids):
        raise TypeError("rounded_budget_profiles must contain strings")
    if rounded_ids != tuple(sorted(set(rounded_ids))):
        raise ValueError("rounded_budget_profiles must be sorted and unique")
    if not set(rounded_ids) <= profile_ids:
        raise ValueError("rounded_budget_profiles must reference profiles of the unit")
