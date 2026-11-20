"""request_key = canonical economic identity of a negotiation mandate.

It must ignore technical identifiers and arbitrary orders, change with every economic
or decisional field of the mandate, never trust the stored P1 fingerprint, and stay
independent of the oracle configuration (identified by oracle_configuration_id).
"""

import hashlib
import json
import unicodedata
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from coalition_travel.application.lot_admissibility import lot_admissibility
from coalition_travel.domain.negotiation_request import (
    REQUEST_KEY_SCHEMA,
    negotiation_request_for,
    request_key_content,
    unit_economic_digest,
)
from coalition_travel.domain.offer import (
    OfferCatalog,
    OfferQuote,
    PriceTier,
    SellerFloorTier,
    SellerTerms,
    SellerTermsBook,
)
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile
from coalition_travel.infrastructure.negotiation.simulated_oracle import (
    SimulatedNegotiationOracle,
    SimulatedOracleConfig,
)

REFERENCE = date(2026, 11, 19)


def _fingerprint(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _profile(profile_id="p1", seats=2, budget="500", **constraints):
    return TravelerProfile(profile_id, seats, "Tokyo", Decimal(budget), **constraints)


def _unit(unit_id="u1", *profiles, fingerprint=None, rounded=()):
    profiles = profiles or (_profile(),)
    ordered = tuple(sorted(profiles, key=lambda profile: profile.profile_id))
    return TravelUnit(
        unit_id,
        "tokyo",
        ordered,
        fingerprint or _fingerprint(unit_id),
        rounded_budget_profiles=rounded,
    )


def _offer(**changes):
    offer = OfferQuote(
        "tyo-1",
        "catalog-v1",
        "Northstar",
        "Tokyo",
        date(2027, 3, 10),
        date(2027, 3, 11),
        True,
        20,
        (PriceTier(1, 56_000), PriceTier(3, 52_000)),
    )
    return replace(offer, **changes)


def _key(units, offer=None):
    return negotiation_request_for(tuple(units), offer or _offer()).request_key


# ------------------------------------------------------------------- invariance


def test_unit_order_does_not_change_the_key():
    first = _unit("u1", _profile(budget="500"))
    second = _unit("u2", _profile(budget="450"))
    assert _key([first, second]) == _key([second, first])


def test_technical_identifiers_do_not_change_the_key():
    original = _unit("u1", _profile("p1"), fingerprint=_fingerprint("a"))
    renamed = _unit(
        "request-7f3a",
        _profile("traveller-x"),
        fingerprint=_fingerprint("completely different"),
        rounded=("traveller-x",),
    )
    assert _key([original]) == _key([renamed])


def test_profile_order_and_names_do_not_change_the_key():
    left = _unit("u1", _profile("a", 1, "500"), _profile("b", 2, "400"))
    # Names swapped: the sorted profile order of the unit is reversed.
    right = _unit("u1", _profile("a", 2, "400"), _profile("b", 1, "500"))
    assert _key([left]) == _key([right])


def test_splitting_a_profile_into_identical_parts_does_not_change_the_key():
    split = _unit("u1", _profile("p1", 2, "500"), _profile("p2", 1, "500"))
    merged = _unit("u1", _profile("p", 3, "500"))
    assert _key([split]) == _key([merged])


def test_supplier_exclusion_spellings_are_normalized_like_admissibility():
    composed = unicodedata.normalize("NFC", "Café Air")
    decomposed = unicodedata.normalize("NFD", "café air")
    first = _unit("u1", _profile(excluded_suppliers=(" RyanAir ", composed)))
    second = _unit("u1", _profile(excluded_suppliers=(decomposed, "ryanair", "RYANAIR")))
    assert _key([first]) == _key([second])


# ---------------------------------------------------------------- sensitivity

BASE_PROFILE = {"departure_after": date(2027, 3, 1), "arrival_before": date(2027, 3, 31)}

PROFILE_CHANGES = {
    "seats": {"traveller_count": 3},
    "budget_one_cent": {"budget_per_person": Decimal("500.01")},
    "departure_after": {"departure_after": date(2027, 3, 2)},
    "departure_window_removed": {"departure_after": None},
    "arrival_before": {"arrival_before": date(2027, 3, 30)},
    "direct_preferred": {"direct_flight": "preferred"},
    "direct_required": {"direct_flight": "required"},
    "supplier_excluded": {"excluded_suppliers": ("SkyLow",)},
}


@pytest.mark.parametrize("changes", PROFILE_CHANGES.values(), ids=PROFILE_CHANGES.keys())
def test_every_profile_economic_field_changes_the_key(changes):
    base = _profile(**BASE_PROFILE)
    changed = replace(base, **changes)
    assert _key([_unit("u1", base)]) != _key([_unit("u1", changed)])


OFFER_CHANGES = {
    "offer_id": {"offer_id": "tyo-2"},
    "catalog_version": {"catalog_version": "catalog-v2"},
    "supplier": {"supplier_id": "SkyLow"},
    "departure_date": {"departure_date": date(2027, 3, 9)},
    "arrival_date": {"arrival_date": date(2027, 3, 12)},
    "direct": {"direct": False},
    "capacity": {"capacity_seats": 21},
    "tier_price": {"tiers": (PriceTier(1, 56_001), PriceTier(3, 52_000))},
    "tier_threshold": {"tiers": (PriceTier(1, 56_000), PriceTier(4, 52_000))},
}


@pytest.mark.parametrize("changes", OFFER_CHANGES.values(), ids=OFFER_CHANGES.keys())
def test_every_public_offer_field_changes_the_key(changes):
    units = [_unit("u1")]
    assert _key(units) != _key(units, _offer(**changes))


def test_unit_boundaries_are_part_of_the_mandate():
    two_units = [_unit("a", _profile(seats=2)), _unit("b", _profile(seats=1))]
    one_unit = [_unit("c", _profile(seats=3))]
    first = negotiation_request_for(tuple(two_units), _offer())
    second = negotiation_request_for(tuple(one_unit), _offer())
    # Same seats, same reservation, same offer: still two different mandates.
    assert (first.seats, first.reservation_cents) == (second.seats, second.reservation_cents)
    assert first.request_key != second.request_key


def test_identical_units_are_kept_as_a_multiset():
    twin_a, twin_b = _unit("a"), _unit("b")
    assert _key([twin_a, twin_b]) != _key([twin_a])
    assert _key([twin_a, twin_b]) == _key([_unit("x"), _unit("y")])


def test_a_stale_stored_fingerprint_cannot_hide_or_create_a_difference():
    shared = _fingerprint("same stored fingerprint")
    cheap = _unit("u1", _profile(budget="300"), fingerprint=shared)
    dear = _unit("u1", _profile(budget="301"), fingerprint=shared)
    assert _key([cheap]) != _key([dear])
    other_fingerprint = _unit("u1", _profile(budget="300"), fingerprint=_fingerprint("other"))
    assert _key([cheap]) == _key([other_fingerprint])


# ------------------------------------------------- content, schema and stability


def test_key_content_has_no_identifier_fingerprint_or_private_term():
    unit = _unit("unit-identifier", _profile("profile-identifier"), fingerprint="c" * 64)
    content = request_key_content((unit,), _offer())
    serialized = json.dumps(content)
    assert content["schema"] == REQUEST_KEY_SCHEMA
    for forbidden in ("unit-identifier", "profile-identifier", "c" * 64, "floor", "synthetic"):
        assert forbidden not in serialized
    assert content["seats"] == 2 and content["reservation_cents"] == 100_000


def test_request_key_is_pinned_for_a_fixed_mandate():
    units = (
        _unit("u1", _profile("p1", 2, "500", **BASE_PROFILE)),
        _unit("u2", _profile("p1", 1, "450.50", direct_flight="required")),
    )
    request = negotiation_request_for(units, _offer())
    # Changing this value means changing the key format: bump REQUEST_KEY_SCHEMA.
    assert request.request_key == (
        "ae759f8384309f6941d3f164b7149ad0d2b4e9338debea38a6ed8c9acb280692"
    )


# --------------------------------------------- separation from the oracle identity


def _oracle(config):
    offer = _offer()
    sha = "d" * 64
    catalog = OfferCatalog(offer.catalog_version, sha, (offer,))
    terms = SellerTermsBook(
        offer.catalog_version,
        sha,
        (
            SellerTerms(
                offer.offer_id,
                offer.catalog_version,
                20,
                (SellerFloorTier(1, 40_000), SellerFloorTier(3, 37_000)),
            ),
        ),
    )
    return SimulatedNegotiationOracle(catalog, terms, config)


def test_one_mandate_keeps_its_key_under_several_oracle_configurations():
    request = negotiation_request_for((_unit("u1"),), _offer())
    standard = _oracle(SimulatedOracleConfig(reference_date=REFERENCE))
    slower = _oracle(
        SimulatedOracleConfig(reference_date=REFERENCE, seller_concession_rate=Decimal("0.05"))
    )
    first, second = standard.negotiate(request), slower.negotiate(request)
    assert first.request_key == second.request_key == request.request_key
    assert first.oracle_configuration_id != second.oracle_configuration_id


def test_different_mandates_get_different_keys_under_one_oracle_configuration():
    oracle = _oracle(SimulatedOracleConfig(reference_date=REFERENCE))
    first = oracle.negotiate(negotiation_request_for((_unit("u1"),), _offer()))
    second = oracle.negotiate(
        negotiation_request_for((_unit("u1", _profile(budget="520")),), _offer())
    )
    assert first.request_key != second.request_key
    assert first.oracle_configuration_id == second.oracle_configuration_id


def test_lot_provenance_tracks_unit_content_not_the_stored_fingerprint():
    offer = _offer()
    catalog = OfferCatalog(offer.catalog_version, "d" * 64, (offer,))
    shared = _fingerprint("stale")
    cheap = lot_admissibility(
        [_unit("u1", _profile(budget="300"), fingerprint=shared)], catalog, REFERENCE
    )
    dear = lot_admissibility(
        [_unit("u1", _profile(budget="301"), fingerprint=shared)], catalog, REFERENCE
    )
    same = lot_admissibility(
        [_unit("u1", _profile(budget="300"), fingerprint=_fingerprint("x"))], catalog, REFERENCE
    )
    assert cheap.admissibility_id != dear.admissibility_id
    assert cheap.admissibility_id == same.admissibility_id
    assert unit_economic_digest(cheap.relation.units[0]) != unit_economic_digest(
        dear.relation.units[0]
    )
