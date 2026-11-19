"""Build technology-independent profiles and legacy buyers from validated requests."""

import hashlib
import json
from datetime import date

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
                excluded_suppliers=(
                    tuple(_field(item, "excluded_suppliers"))
                    if _field(item, "excluded_suppliers") is not None
                    else tuple(request.excluded_suppliers)
                ),
            )
        )
    if sum(profile.traveller_count for profile in result) != request.travellers:
        raise ValueError("profile traveller counts must equal request.travellers")

    # A single request may describe the same homogeneous profile in multiple groups.
    # Consolidate those explicit groups; never combine profiles across request IDs.
    merged = {}
    for profile in result:
        key = _negotiation_profile_key(profile)
        if key in merged:
            existing = merged[key]
            merged[key] = TravelerProfile(
                profile_id=f"merged-{key[:16]}",
                traveller_count=existing.traveller_count + profile.traveller_count,
                destination=existing.destination,
                budget_per_person=existing.budget_per_person,
                departure_after=existing.departure_after,
                arrival_before=existing.arrival_before,
                direct_flight=existing.direct_flight,
                excluded_suppliers=existing.excluded_suppliers,
            )
        else:
            merged[key] = profile
    profiles = tuple(sorted(merged.values(), key=lambda profile: profile.profile_id))
    if len({profile.profile_id for profile in profiles}) != len(profiles):
        raise ValueError("profile identifiers collide after application normalization")
    return profiles


def _negotiation_profile_key(profile: TravelerProfile) -> str:
    """Canonical key for constraints that affect a common negotiation."""
    key = {
        "destination": profile.destination.casefold(),
        "budget_per_person": format(profile.budget_per_person.normalize(), "f"),
        "departure_after": profile.departure_after.isoformat() if profile.departure_after else None,
        "arrival_before": profile.arrival_before.isoformat() if profile.arrival_before else None,
        "direct_flight": profile.direct_flight,
        "excluded_suppliers": sorted(profile.excluded_suppliers, key=str.casefold),
    }
    serialized = json.dumps(key, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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
