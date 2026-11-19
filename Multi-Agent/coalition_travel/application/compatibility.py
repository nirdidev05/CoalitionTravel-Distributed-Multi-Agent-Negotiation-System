"""Deterministic compatibility checks for a single shared offer."""

from coalition_travel.domain.traveler_profile import (
    CommonOffer,
    CompatibilityResult,
    TravelerProfile,
)


def evaluate_compatibility(
    profiles: tuple[TravelerProfile, ...] | list[TravelerProfile],
    offer: CommonOffer | None = None,
    knowledge_service=None,
) -> CompatibilityResult:
    """Return a conservative decision; no live offer means availability is unknown."""
    profiles = tuple(profiles)
    ids = tuple(profile.profile_id for profile in profiles)
    reasons: list[str] = []
    if len(profiles) < 2:
        return CompatibilityResult("incompatible", ("coalition_requires_multiple_profiles",), ids)

    destinations = {profile.destination.casefold() for profile in profiles}
    if len(destinations) != 1:
        return CompatibilityResult("incompatible", ("destination_mismatch",), ids)

    starts = [profile.departure_after for profile in profiles if profile.departure_after]
    ends = [profile.arrival_before for profile in profiles if profile.arrival_before]
    if starts and ends and max(starts) > min(ends):
        return CompatibilityResult("incompatible", ("travel_windows_do_not_overlap",), ids)

    if offer is None:
        if not starts or not ends:
            reasons.append("travel_window_incomplete")
        reasons.append("common_offer_availability_unknown")
        return _conditional_result(profiles, tuple(reasons), ids, knowledge_service)

    if offer.destination.casefold() not in destinations:
        return CompatibilityResult("incompatible", ("offer_destination_mismatch",), ids)
    if offer.price_per_person <= 0:
        return CompatibilityResult("incompatible", ("offer_price_invalid",), ids)
    if offer.departure_date and offer.arrival_date and offer.arrival_date < offer.departure_date:
        return CompatibilityResult("incompatible", ("offer_dates_invalid",), ids)
    if any(offer.price_per_person > profile.budget_per_person for profile in profiles):
        return CompatibilityResult("incompatible", ("individual_budget_exceeded",), ids)
    needs_departure = any(profile.departure_after for profile in profiles)
    needs_arrival = any(profile.arrival_before for profile in profiles)
    needs_supplier = any(profile.excluded_suppliers for profile in profiles)
    needs_direct = any(profile.direct_flight == "required" for profile in profiles)
    if (
        (needs_departure and offer.departure_date is None)
        or (needs_arrival and offer.arrival_date is None)
        or (needs_supplier and offer.supplier is None)
        or (needs_direct and offer.direct is None)
    ):
        return _conditional_result(profiles, ("offer_details_incomplete",), ids, knowledge_service)

    for profile in profiles:
        if (
            profile.departure_after
            and offer.departure_date
            and offer.departure_date < profile.departure_after
        ):
            return CompatibilityResult("incompatible", ("departure_constraint_violated",), ids)
        if (
            profile.arrival_before
            and offer.arrival_date
            and offer.arrival_date > profile.arrival_before
        ):
            return CompatibilityResult("incompatible", ("arrival_constraint_violated",), ids)
        if offer.supplier and offer.supplier.casefold() in {
            name.casefold() for name in profile.excluded_suppliers
        }:
            return CompatibilityResult("incompatible", ("excluded_supplier",), ids)
        if profile.direct_flight == "required" and offer.direct is False:
            return CompatibilityResult("incompatible", ("direct_flight_required",), ids)
    return CompatibilityResult("compatible", ("common_offer_satisfies_all_profiles",), ids)


def _conditional_result(profiles, reasons, profile_ids, knowledge_service):
    """Attach documentary references to uncertainty without changing its status."""
    sources = ()
    if knowledge_service is not None:
        destinations = sorted({profile.destination for profile in profiles})
        query = "Travel coalition compatibility rules and supplier constraints for " + ", ".join(
            destinations
        )
        hits = []
        for domain in ("business_knowledge", "supplier_knowledge"):
            hits.extend(knowledge_service.retrieve(query, top_k=2, filters={"domain": domain}))
        sources = tuple(dict.fromkeys(hit.chunk.source for hit in hits))
    return CompatibilityResult("conditional", reasons, profile_ids, sources)


def compatibility_matrix(profiles: tuple[TravelerProfile, ...] | list[TravelerProfile]):
    """Pairwise diagnostic matrix; coalition decisions must still validate all members."""
    return {
        (left.profile_id, right.profile_id): evaluate_compatibility((left, right))
        for index, left in enumerate(profiles)
        for right in profiles[index + 1 :]
    }
