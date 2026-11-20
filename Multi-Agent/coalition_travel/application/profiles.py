"""Build technology-independent profiles and legacy buyers from validated requests."""

import hashlib
import json
from collections.abc import Iterable
from datetime import date
from decimal import Context, Decimal, localcontext

from BuyerAgent import BuyerAgent

from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.domain.traveler_profile import TravelerProfile


def build_profiles(request: TravelRequestDraft) -> tuple[TravelerProfile, ...]:
    """Resolve explicit profile overrides; absent profiles mean one shared group."""
    if (
        request.destination is None
        or request.travellers is None
        or request.budget_per_person is None
    ):
        raise ValueError("request must have destination, travellers and budget_per_person")

    source_profiles = request.profiles or [
        {
            "profile_id": "all",
            "traveller_count": request.travellers,
            "budget_per_person": request.budget_per_person,
        }
    ]
    result = []
    for item in source_profiles:
        result.append(
            TravelerProfile(
                profile_id=_field(item, "profile_id"),
                traveller_count=_field(item, "traveller_count"),
                destination=request.destination,
                budget_per_person=(_field(item, "budget_per_person") or request.budget_per_person),
                departure_after=_field(item, "departure_after") or request.departure_after,
                arrival_before=_field(item, "arrival_before") or request.arrival_before,
                direct_flight=_field(item, "direct_flight") or request.direct_flight,
                # Exclusions are hard constraints: a profile adds to the request-level list
                # and can never remove from it (an empty or absent profile list adds nothing).
                excluded_suppliers=_union_suppliers(
                    request.excluded_suppliers, _field(item, "excluded_suppliers")
                ),
                # Route windows (I4): the profile value, otherwise the request value.
                departure_before=_field(item, "departure_before") or request.departure_before,
                return_after=_field(item, "return_after") or request.return_after,
                return_before=_field(item, "return_before") or request.return_before,
            )
        )
    if sum(profile.traveller_count for profile in result) != request.travellers:
        raise ValueError("profile traveller counts must equal request.travellers")

    # A single request may describe the same homogeneous profile in multiple groups.
    # Consolidate those explicit groups; never combine profiles across request IDs.
    return consolidate_profiles(result)


def consolidate_profiles(profiles: Iterable[TravelerProfile]) -> tuple[TravelerProfile, ...]:
    """Merge profiles of one request whose negotiation constraints are identical.

    The first profile met keeps its field values (including supplier spellings); merged
    groups receive the identifier ``merged-<key prefix>``. The result is sorted by
    profile identifier. Applying the function twice returns the same tuple.
    """
    merged: dict[str, TravelerProfile] = {}
    for profile in profiles:
        if not isinstance(profile, TravelerProfile):
            raise TypeError("consolidate_profiles expects TravelerProfile instances")
        key = negotiation_profile_key(profile)
        existing = merged.get(key)
        if existing is None:
            merged[key] = profile
            continue
        merged[key] = TravelerProfile(
            profile_id=f"merged-{key[:16]}",
            traveller_count=existing.traveller_count + profile.traveller_count,
            destination=existing.destination,
            budget_per_person=existing.budget_per_person,
            departure_after=existing.departure_after,
            arrival_before=existing.arrival_before,
            direct_flight=existing.direct_flight,
            excluded_suppliers=existing.excluded_suppliers,
            departure_before=existing.departure_before,
            return_after=existing.return_after,
            return_before=existing.return_before,
        )
    consolidated = tuple(sorted(merged.values(), key=lambda profile: profile.profile_id))
    if len({profile.profile_id for profile in consolidated}) != len(consolidated):
        raise ValueError("profile identifiers collide after application normalization")
    return consolidated


def negotiation_profile_key(profile: TravelerProfile) -> str:
    """Canonical key for constraints that affect a common negotiation.

    Supplier exclusions are compared case-insensitively. The budget is serialized exactly,
    independently of the caller's global Decimal context.
    """
    key = {
        "destination": profile.destination.casefold(),
        "budget_per_person": _canonical_decimal(profile.budget_per_person),
        "departure_after": profile.departure_after.isoformat() if profile.departure_after else None,
        "arrival_before": profile.arrival_before.isoformat() if profile.arrival_before else None,
        "direct_flight": profile.direct_flight,
        "excluded_suppliers": sorted(
            {supplier.casefold() for supplier in profile.excluded_suppliers}
        ),
    }
    if any(window is not None for window in profile.route_windows):
        # Route windows enter only when present, so a v1 key is unchanged (I4, B5).
        key["departure_before"] = _iso(profile.departure_before)
        key["return_after"] = _iso(profile.return_after)
        key["return_before"] = _iso(profile.return_before)
    serialized = json.dumps(key, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _canonical_decimal(value: Decimal) -> str:
    """Exact trailing-zero-free form; normalize() would round under a reduced context."""
    with localcontext(Context(prec=max(28, len(value.as_tuple().digits)))):
        return format(value.normalize(), "f")


def _union_suppliers(*supplier_lists: Iterable[str] | None) -> tuple[str, ...]:
    """Union preserving order and the first spelling met, compared case-insensitively."""
    seen: set[str] = set()
    union: list[str] = []
    for suppliers in supplier_lists:
        for supplier in suppliers or ():
            folded = supplier.casefold()
            if folded not in seen:
                seen.add(folded)
                union.append(supplier)
    return tuple(union)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _field(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def create_buyer_agents(
    request: TravelRequestDraft,
    request_id: str,
    negotiation_deadline: date,
    reference_date: date,
) -> tuple[BuyerAgent, ...]:
    """Create one legacy agent per explicit profile without passing Pydantic objects."""
    if not request_id.strip():
        raise ValueError("request_id must not be blank")
    profiles = build_profiles(request)
    agents = []
    for profile in profiles:
        agents.append(
            BuyerAgent(
                name=f"{request_id}:{profile.profile_id}",
                budget=profile.total_budget,
                deadline=negotiation_deadline,
                blacklist=list(profile.excluded_suppliers),
                reference_date=reference_date,
                traveller_count=profile.traveller_count,
                budget_per_person=profile.budget_per_person,
                departure_after=profile.departure_after,
                arrival_before=profile.arrival_before,
                direct_flight=profile.direct_flight,
            )
        )
    return tuple(agents)
