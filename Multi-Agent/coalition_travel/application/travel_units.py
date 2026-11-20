"""Build an indivisible TravelUnit from one validated travel request."""

import dataclasses
import hashlib
import json
from datetime import date, datetime

from coalition_travel.application.profiles import (
    build_profiles,
    consolidate_profiles,
    negotiation_profile_key,
)
from coalition_travel.application.request_contracts import TravelRequestDraft, is_route_request
from coalition_travel.application.request_understanding import validate_request_draft
from coalition_travel.domain.destination import normalize_destination_key
from coalition_travel.domain.money import (
    CENT,
    MAX_CENTS,
    MoneyError,
    cents_from_budget,
    decimal_from_cents,
)
from coalition_travel.domain.travel_unit import MAX_UNIT_ID_LENGTH, TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile


class TravelUnitError(ValueError):
    """A request cannot become a travel unit; carries a machine-readable reason."""

    def __init__(
        self,
        reason: str,
        *,
        status: str | None = None,
        profile_id: str | None = None,
        missing_fields: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
    ):
        self.reason = reason
        self.status = status
        self.profile_id = profile_id
        self.missing_fields = tuple(missing_fields)
        self.errors = tuple(errors)
        details = [reason]
        if status:
            details.append(f"status={status}")
        if profile_id:
            details.append(f"profile_id={profile_id}")
        if self.missing_fields:
            details.append(f"missing={','.join(self.missing_fields)}")
        if self.errors:
            details.append(f"errors={'; '.join(self.errors)}")
        super().__init__(" | ".join(details))


def build_travel_unit(
    request_id: str, draft: TravelRequestDraft, reference_date: date
) -> TravelUnit:
    """Validate, resolve profiles, round effective budgets down to cents, then fingerprint.

    Only budgets actually used by a profile are rounded or checked: a request-level budget
    overridden by every profile neither raises nor appears in ``rounded_budget_profiles``.
    The draft is never copied with ``model_copy`` (it would bypass Pydantic validation).
    """
    unit_id = _validate_request_id(request_id)
    if not isinstance(draft, TravelRequestDraft):
        raise TypeError("draft must be a TravelRequestDraft")
    if not isinstance(reference_date, date) or isinstance(reference_date, datetime):
        raise TypeError("reference_date must be a datetime.date")

    understanding = validate_request_draft(draft, reference_date)
    if understanding.status != "ready":
        raise TravelUnitError(
            "request_not_ready",
            status=understanding.status,
            missing_fields=understanding.missing_fields,
            errors=understanding.errors,
        )

    floored: list[TravelerProfile] = []
    rounded_keys: set[str] = set()
    for profile in build_profiles(draft):
        try:
            cents = cents_from_budget(profile.budget_per_person)
        except MoneyError as exc:
            reason = (
                "budget_below_one_cent"
                if profile.budget_per_person < CENT
                else "budget_out_of_range"
            )
            raise TravelUnitError(reason, profile_id=profile.profile_id) from exc
        exact = decimal_from_cents(cents)
        adjusted = dataclasses.replace(profile, budget_per_person=exact)
        if exact != profile.budget_per_person:
            rounded_keys.add(negotiation_profile_key(adjusted))
        floored.append(adjusted)

    # Budgets that become equal once rounded describe the same negotiation group.
    profiles = consolidate_profiles(floored)
    rounded_ids = tuple(
        sorted(
            profile.profile_id
            for profile in profiles
            if negotiation_profile_key(profile) in rounded_keys
        )
    )
    total = sum(
        profile.traveller_count * cents_from_budget(profile.budget_per_person)
        for profile in profiles
    )
    if total > MAX_CENTS:
        raise TravelUnitError("budget_total_out_of_range")

    destination_key = normalize_destination_key(draft.destination)
    origin_key = trip_type = None
    if is_route_request(draft):  # v2 (I4): the origin is the resolved place name
        if draft.origin is None or draft.trip_type is None:
            raise TravelUnitError("route_incomplete")
        origin_key = normalize_destination_key(draft.origin)
        trip_type = draft.trip_type
    return TravelUnit(
        unit_id=unit_id,
        destination_key=destination_key,
        profiles=profiles,
        fingerprint=unit_fingerprint(
            destination_key, profiles, origin_key=origin_key, trip_type=trip_type
        ),
        rounded_budget_profiles=rounded_ids,
        origin_key=origin_key,
        trip_type=trip_type,
    )


def unit_fingerprint(
    destination_key: str,
    profiles: tuple[TravelerProfile, ...],
    *,
    origin_key: str | None = None,
    trip_type: str | None = None,
) -> str:
    """SHA-256 of the unit's negotiation content, without technical identifiers.

    Profile and unit identifiers are excluded, so equivalent drafts ("500" / "500.00",
    reordered or renamed profiles) share a fingerprint, while any change of seats,
    budget, dates, flight requirement or exclusions changes it. The route (origin, trip
    type, effective route windows) enters only for a v2 unit, so a v1 fingerprint is
    unchanged byte for byte (plan §6.4, K1).
    """
    route = origin_key is not None
    entries = []
    for profile in profiles:
        entry = {
            "traveller_count": profile.traveller_count,
            "budget_cents": cents_from_budget(profile.budget_per_person),
            "departure_after": _iso(profile.departure_after),
            "arrival_before": _iso(profile.arrival_before),
            "direct_flight": profile.direct_flight,
            "excluded_suppliers": sorted(
                {supplier.casefold() for supplier in profile.excluded_suppliers}
            ),
        }
        if route:
            entry["departure_before"] = _iso(profile.departure_before)
            entry["return_after"] = _iso(profile.return_after)
            entry["return_before"] = _iso(profile.return_before)
        entries.append(entry)
    entries.sort(key=_canonical_json)
    document = {"destination_key": destination_key, "profiles": entries}
    if route:
        document["origin_key"] = origin_key
        document["trip_type"] = trip_type
    payload = _canonical_json(document)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _validate_request_id(request_id) -> str:
    if not isinstance(request_id, str):
        raise TypeError("request_id must be a string")
    cleaned = request_id.strip()
    if not cleaned or len(cleaned) > MAX_UNIT_ID_LENGTH:
        raise TravelUnitError("invalid_request_id")
    return cleaned
