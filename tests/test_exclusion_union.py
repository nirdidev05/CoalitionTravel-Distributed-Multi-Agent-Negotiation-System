"""P1.2 — union of request and profile exclusions, case-insensitive consolidation."""

import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext

import pytest
from coalition_travel.application.compatibility import evaluate_compatibility
from coalition_travel.application.profiles import (
    build_profiles,
    consolidate_profiles,
    create_buyer_agents,
    negotiation_profile_key,
)
from coalition_travel.application.request_contracts import (
    TravelerProfileDraft,
    TravelRequestDraft,
)
from coalition_travel.domain.traveler_profile import CommonOffer, TravelerProfile


def _draft(request_exclusions, profiles=None, travellers=None):
    profiles = profiles or []
    return TravelRequestDraft(
        destination="Tokyo",
        travellers=travellers or (sum(p.traveller_count for p in profiles) or 2),
        budget_per_person=Decimal(700),
        excluded_suppliers=request_exclusions,
        profiles=profiles,
    )


def _group(profile_id, count=1, exclusions=None, **fields):
    return TravelerProfileDraft(
        profile_id=profile_id, traveller_count=count, excluded_suppliers=exclusions, **fields
    )


def test_profile_exclusions_are_added_to_request_exclusions():
    profiles = build_profiles(_draft(["Ryanair"], [_group("kids", 2, ["EasyJet"])]))
    assert profiles[0].excluded_suppliers == ("Ryanair", "EasyJet")


def test_union_is_case_insensitive_and_keeps_the_first_spelling():
    profiles = build_profiles(_draft(["SkyWays"], [_group("kids", 2, ["skyways", "AeroSun"])]))
    assert profiles[0].excluded_suppliers == ("SkyWays", "AeroSun")


@pytest.mark.parametrize("profile_exclusions", [None, []])
def test_absent_or_empty_profile_list_neither_adds_nor_removes(profile_exclusions):
    profiles = build_profiles(_draft(["Ryanair"], [_group("kids", 2, profile_exclusions)]))
    assert profiles[0].excluded_suppliers == ("Ryanair",)


def test_request_without_profiles_keeps_request_exclusions():
    profiles = build_profiles(_draft(["Ryanair", "EasyJet"], travellers=3))
    assert len(profiles) == 1
    assert profiles[0].profile_id == "all"
    assert profiles[0].excluded_suppliers == ("Ryanair", "EasyJet")


def test_profiles_with_the_same_effective_union_are_consolidated():
    draft = _draft(
        ["Ryanair"],
        [_group("first", 1, ["EasyJet"]), _group("second", 2, ["easyjet"])],
    )
    profiles = build_profiles(draft)
    assert len(profiles) == 1
    assert profiles[0].traveller_count == 3
    assert profiles[0].profile_id.startswith("merged-")
    assert profiles[0].excluded_suppliers == ("Ryanair", "EasyJet")  # first spelling met


def test_exclusions_differing_only_by_case_produce_the_same_key():
    upper = TravelerProfile("a", 1, "Tokyo", Decimal(500), excluded_suppliers=("SkyWays",))
    lower = TravelerProfile("b", 1, "Tokyo", Decimal(500), excluded_suppliers=("skyways",))
    duplicated = TravelerProfile(
        "c", 1, "Tokyo", Decimal(500), excluded_suppliers=("SkyWays", "SKYWAYS")
    )
    assert negotiation_profile_key(upper) == negotiation_profile_key(lower)
    assert negotiation_profile_key(upper) == negotiation_profile_key(duplicated)
    merged = consolidate_profiles((upper, lower))
    assert len(merged) == 1
    assert merged[0].excluded_suppliers == ("SkyWays",)


def _legacy_key(profile):
    """Key formula before P1.2, kept here to prove no-exclusion keys are unchanged."""
    key = {
        "destination": profile.destination.casefold(),
        "budget_per_person": format(profile.budget_per_person.normalize(), "f"),
        "departure_after": profile.departure_after.isoformat() if profile.departure_after else None,
        "arrival_before": profile.arrival_before.isoformat() if profile.arrival_before else None,
        "direct_flight": profile.direct_flight,
        "excluded_suppliers": sorted(profile.excluded_suppliers, key=str.casefold),
    }
    return hashlib.sha256(
        json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize(
    "profile",
    [
        TravelerProfile("all", 4, "Tokyo", Decimal("500.00")),
        TravelerProfile("d", 2, "Rome", Decimal(300), date(2027, 6, 10), None, "required"),
        TravelerProfile("e", 1, "Montréal", Decimal("1000.5"), None, date(2027, 1, 2), "any"),
        TravelerProfile("f", 3, "Lisbon", Decimal(450), excluded_suppliers=("easyjet",)),
    ],
)
def test_keys_are_unchanged_for_profiles_without_uppercase_exclusions(profile):
    assert negotiation_profile_key(profile) == _legacy_key(profile)


def test_build_profiles_output_is_unchanged_for_duplicates_without_exclusions():
    repeated = [
        _group("direct-a", 2, budget_per_person=Decimal(300), direct_flight="required"),
        _group("direct-b", 2, budget_per_person=Decimal("300.00"), direct_flight="required"),
        _group("flex", 1, budget_per_person=Decimal(450), direct_flight="any"),
    ]
    profiles = build_profiles(_draft([], repeated, travellers=5))
    merged = next(profile for profile in profiles if profile.traveller_count == 4)
    legacy_id = f"merged-{_legacy_key(merged)[:16]}"
    assert merged.profile_id == legacy_id
    assert [profile.profile_id for profile in profiles] == sorted([legacy_id, "flex"])


def test_consolidate_profiles_is_idempotent_and_sorted():
    profiles = (
        TravelerProfile("z", 1, "Tokyo", Decimal(500)),
        TravelerProfile("a", 2, "Tokyo", Decimal(400)),
        TravelerProfile("m", 1, "Tokyo", Decimal("500.00")),
    )
    once = consolidate_profiles(profiles)
    assert consolidate_profiles(once) == once
    assert [profile.profile_id for profile in once] == sorted(p.profile_id for p in once)
    assert sum(profile.traveller_count for profile in once) == 4


def test_consolidate_profiles_rejects_foreign_objects():
    with pytest.raises(TypeError):
        consolidate_profiles([{"profile_id": "a"}])


def test_key_is_exact_under_a_reduced_global_decimal_context():
    first = TravelerProfile("a", 1, "Tokyo", Decimal("123456.78"))
    second = TravelerProfile("b", 1, "Tokyo", Decimal("123456.79"))
    expected_first = negotiation_profile_key(first)
    with localcontext() as context:
        context.prec = 5  # Decimal.normalize() alone would round both budgets to 1.2346E+5
        assert negotiation_profile_key(first) == expected_first
        assert negotiation_profile_key(first) != negotiation_profile_key(second)
        assert len(consolidate_profiles((first, second))) == 2


def test_buyer_agents_receive_the_union_as_blacklist():
    draft = _draft(["Ryanair"], [_group("kids", 2, ["EasyJet"])])
    buyers = create_buyer_agents(draft, "request-1", date(2027, 1, 1), date(2026, 11, 19))
    assert buyers[0].blacklist == ["Ryanair", "EasyJet"]


def test_request_level_exclusion_still_blocks_an_offer_when_profiles_have_their_own_list():
    draft = _draft(
        ["Ryanair"],
        [_group("adults", 2, ["EasyJet"]), _group("kids", 2, ["AeroSun"])],
    )
    profiles = build_profiles(draft)
    offer = CommonOffer("Tokyo", Decimal(400), direct=True, supplier="ryanair")
    result = evaluate_compatibility(profiles, offer)
    assert result.status == "incompatible"
    assert result.reasons == ("excluded_supplier",)
