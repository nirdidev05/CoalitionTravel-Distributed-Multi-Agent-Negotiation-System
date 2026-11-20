"""I4-A: route contracts, package offers, v3 keys (K1 to K10) and the place directory.

K1 is proven twice: the existing pinned digests still pass unchanged (ae759f83…, P1.3,
pinned lot), and the v1 identities below were computed by the code of the I4 baseline
before any change, then pinned here.
"""

import json
import random
import unicodedata
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from coalition_travel.application.profiles import build_profiles, negotiation_profile_key
from coalition_travel.application.request_contracts import (
    TravelRequestDraft,
    draft_document,
    is_route_request,
)
from coalition_travel.application.travel_units import build_travel_unit
from coalition_travel.domain.negotiation_request import (
    REQUEST_KEY_SCHEMA,
    REQUEST_KEY_SCHEMA_V3,
    negotiation_request_for,
    request_key_content,
    unit_economic_content,
    unit_economic_digest,
)
from coalition_travel.domain.offer import OfferCatalog, OfferLeg, OfferQuote, PriceTier
from coalition_travel.domain.places import Place, PlaceDirectory, PlaceDirectoryError
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog
from p4_support import REFERENCE

ROOT = Path(__file__).resolve().parents[1]
CATALOG_V1 = ROOT / "data/catalog/catalog_v1.json"
ROUTE = {
    "origin": "Lyon",
    "destination": "Alger",
    "trip_type": "round_trip",
    "travellers": 2,
    "budget_per_person": "500",
    "departure_after": "2027-02-15",
    "departure_before": "2027-02-15",
    "return_after": "2027-02-25",
    "return_before": "2027-02-25",
}
ROUTE_FIELDS = ("origin", "trip_type", "departure_before", "return_after", "return_before")


def route_draft(**changes):
    return TravelRequestDraft.model_validate(ROUTE | changes)


def unit_of(draft, unit_id="user"):
    return build_travel_unit(unit_id, draft, REFERENCE)


def leg(day, ref, *, direct=True, capacity=40):
    return OfferLeg(day, day, direct, capacity, ref)


def package(offer_id="lys-alg-a", *, origin="Lyon", back=True, **changes):
    outbound = leg(date(2027, 2, 15), "AJ-101-20270215")
    return_leg = leg(date(2027, 2, 25), "AJ-102-20270225") if back else None
    values = {
        "offer_id": offer_id,
        "catalog_version": "catalog-v2",
        "supplier_id": "AtlasJet",
        "destination": "Alger",
        "departure_date": outbound.departure_date,
        "arrival_date": outbound.arrival_date,
        "direct": True,
        "capacity_seats": 40,
        "tiers": (PriceTier(1, 30_000), PriceTier(4, 27_000)),
        "origin": origin,
        "outbound": outbound,
        "return_leg": return_leg,
    }
    values.update(changes)
    return OfferQuote(**values)


def identities(draft, offer=None):
    """The three identities of §6.4 plus the profile consolidation key (B5)."""
    unit = unit_of(draft)
    if offer is None and unit.is_route_unit:
        offer = package(back=unit.trip_type == "round_trip")
    key = None if offer is None else negotiation_request_for((unit,), offer).request_key
    profiles = tuple(negotiation_profile_key(p) for p in build_profiles(draft))
    return {
        "request_key": key,
        "economic_digest": unit_economic_digest(unit),
        "fingerprint": unit.fingerprint,
        "profile_keys": tuple(sorted(profiles)),
    }


# --- request version (D-I4-1) and v1 documents --------------------------------------------


def test_a_request_is_v2_exactly_when_it_has_a_route_field():
    assert not is_route_request(TravelRequestDraft(destination="Tokyo", travellers=1))
    for name in ROUTE_FIELDS:
        value = ROUTE[name]
        assert is_route_request(TravelRequestDraft.model_validate({name: value})), name
    profile = {"profile_id": "a", "traveller_count": 1, "return_before": "2027-02-25"}
    assert is_route_request(TravelRequestDraft(travellers=1, profiles=[profile]))


def test_a_v1_document_never_shows_a_route_field():
    v1 = TravelRequestDraft(
        destination="Tokyo",
        travellers=2,
        budget_per_person="500",
        profiles=[{"profile_id": "a", "traveller_count": 2}],
    )
    document = draft_document(v1)
    assert list(document) == [
        "destination",
        "travellers",
        "budget_per_person",
        "currency",
        "departure_after",
        "arrival_before",
        "direct_flight",
        "excluded_suppliers",
        "profiles",
    ]
    assert set(document["profiles"][0]) == {
        "profile_id",
        "traveller_count",
        "budget_per_person",
        "departure_after",
        "arrival_before",
        "direct_flight",
        "excluded_suppliers",
    }
    assert set(ROUTE_FIELDS) <= set(draft_document(route_draft()))


# --- K1: absence ------------------------------------------------------------------------------

BASELINE_PINS = {  # computed by the I4 baseline code, before any change
    "e3": (
        {"destination": "Tokyo", "travellers": 8, "budget_per_person": "500"},
        "b46385592bd617f90dedc3f471e8073c5a7a58555c4e65534418a1c6f85b8266",
        "c84036fa949e1b6720925b3238f21e8cf5eb231ef31ef58de16ab213c3ddd3f0",
        "a05b620d1765617e121ba55244f27482202bb4f6015c3811fb956e91acb2a220",
        ("01322bf4b6ad0675e4d9284a3d2f6fd9e09ef10d4440bed5b7f000dbb94aacd0",),
    ),
    "windows": (
        {
            "destination": "Tokyo",
            "travellers": 3,
            "budget_per_person": "560.5",
            "departure_after": "2027-01-01",
            "arrival_before": "2027-06-30",
            "direct_flight": "preferred",
            "excluded_suppliers": ["SkyWays"],
        },
        "e29ed243f2427b8fe785a16b0966246cf0a0eb0ffb6e88c5850965c600d214c6",
        "32486f72e7d3f187fdcd40a573ec146f4277facc1271170d50f7ee30a25a2faf",
        "b98aeaad32cf541c53e829488aa04e654c2907d5396d7094ee4a33e8779be792",
        ("9104cf902f6510d1d62f7a59948618528710e81118d4dea70a62431985af7070",),
    ),
    "profiles": (
        {
            "destination": "Tokyo",
            "travellers": 4,
            "budget_per_person": "600",
            "profiles": [
                {"profile_id": "p1", "traveller_count": 1, "budget_per_person": "300"},
                {"profile_id": "p2", "traveller_count": 3, "direct_flight": "required"},
            ],
        },
        "eacfb1d56e0e0637416c6616b87c9e49948a12fd4edb8234d251cd60400486ea",
        "131cad8230caf81a0806340aff4e721ee08ed0eab27babd66eb133ffd5fcc96b",
        "b0d872b3130814dbd69e5478d5b28ab269c43199cbd07212c201ee973d5754fa",
        (
            "3b31ffe020d20b159e3bb76bebed22529829daca91aa5ee7b94e62bc64c32e3c",
            "03038323a00a3db067448b6cb07d5946604d8ae777341a471a8bc33304bb5bd3",
        ),
    ),
}


@pytest.mark.parametrize("name", sorted(BASELINE_PINS))
def test_k1_v1_identities_equal_the_baseline_byte_for_byte(name):
    fields, fingerprint, digest, key, profile_keys = BASELINE_PINS[name]
    draft = TravelRequestDraft.model_validate(fields)
    unit = unit_of(draft)
    northstar = load_offer_catalog(CATALOG_V1)[0].get("tyo-northstar-20270310")
    content = request_key_content((unit,), northstar)
    assert content["schema"] == REQUEST_KEY_SCHEMA
    assert unit.fingerprint == fingerprint
    assert unit_economic_digest(unit) == digest
    assert negotiation_request_for((unit,), northstar).request_key == key
    assert tuple(negotiation_profile_key(p) for p in build_profiles(draft)) == profile_keys


# --- K2: sensitivity, K7: separation of routes ---------------------------------------------


@pytest.mark.parametrize(
    ("name", "other"),
    [
        ("origin", "Marseille"),
        ("trip_type", "one_way"),
        ("departure_before", "2027-02-16"),
        ("return_after", "2027-02-24"),
        ("return_before", "2027-02-26"),
    ],
)
def test_k2_every_route_field_changes_every_identity(name, other):
    changes = {name: other}
    if other == "one_way":
        changes |= {"return_after": None, "return_before": None}
    base = identities(route_draft())
    offer = package(back=other != "one_way", origin="Marseille" if name == "origin" else "Lyon")
    changed = identities(route_draft(**changes), offer)
    for identity in ("economic_digest", "fingerprint", "request_key"):
        assert base[identity] != changed[identity], (name, identity)
    if name not in ("origin", "trip_type"):  # profile-level fields
        assert base["profile_keys"] != changed["profile_keys"], name


def test_k2_every_public_package_field_changes_the_request_key():
    unit = unit_of(route_draft())
    base = negotiation_request_for((unit,), package()).request_key
    variants = [
        package(outbound=leg(date(2027, 2, 15), "AJ-101-20270215", capacity=41)),
        package(outbound=leg(date(2027, 2, 15), "AJ-109-20270215")),
        package(return_leg=leg(date(2027, 2, 25), "AJ-108-20270225")),
        package(return_leg=leg(date(2027, 2, 25), "AJ-102-20270225", capacity=41)),
        package(return_leg=leg(date(2027, 2, 25), "AJ-102-20270225", direct=False), direct=False),
    ]
    keys = {negotiation_request_for((unit,), offer).request_key for offer in variants}
    assert base not in keys and len(keys) == len(variants)


def test_k7_identical_economics_on_two_routes_never_share_a_key():
    lyon = identities(route_draft())
    marseille = identities(route_draft(origin="Marseille"), package(origin="Marseille"))
    assert lyon["economic_digest"] != marseille["economic_digest"]
    v1 = unit_of(TravelRequestDraft(destination="Alger", travellers=2, budget_per_person="500"))
    assert unit_economic_digest(v1) != lyon["economic_digest"]


# --- K3: normalization, K4: absent value, K5: inheritance, K6: invariances ----------------


def test_k3_spellings_and_aliases_of_a_place_give_the_same_key():
    base = identities(route_draft())
    for spelling in (" Lyon", "LYON", "lyon", unicodedata.normalize("NFD", "Lyon")):
        assert identities(route_draft(origin=spelling)) == base, spelling
    directory = PlaceDirectory("places-test", (Place("Alger", ("Algiers", "ALG")),))
    resolved = route_draft(destination=directory.resolve("Algiers"))
    assert identities(resolved) == base
    accented = route_draft(destination=unicodedata.normalize("NFD", "Alger"))
    assert identities(accented)["economic_digest"] == base["economic_digest"]


def test_k4_an_omitted_field_and_an_explicit_null_give_the_same_key():
    one_way = {key: value for key, value in ROUTE.items() if not key.startswith("return")}
    one_way["trip_type"] = "one_way"
    omitted = one_way
    explicit = one_way | {"return_after": None, "return_before": None, "arrival_before": None}
    left = identities(TravelRequestDraft.model_validate(omitted))
    right = identities(TravelRequestDraft.model_validate(explicit))
    assert left == right


def test_k5_an_inherited_window_equals_the_same_window_on_the_profile():
    inherited = route_draft(profiles=[{"profile_id": "a", "traveller_count": 2}])
    overridden = route_draft(
        return_after=None,
        return_before=None,
        profiles=[
            {
                "profile_id": "a",
                "traveller_count": 2,
                "return_after": "2027-02-25",
                "return_before": "2027-02-25",
            }
        ],
    )
    assert identities(inherited) == identities(overridden)


def test_k6_identifiers_order_and_identical_splits_do_not_change_the_key():
    split = route_draft(
        travellers=3,
        profiles=[
            {"profile_id": "x", "traveller_count": 1},
            {"profile_id": "y", "traveller_count": 2, "budget_per_person": "450"},
        ],
    )
    renamed = route_draft(
        travellers=3,
        profiles=[
            {"profile_id": "b", "traveller_count": 2, "budget_per_person": "450"},
            {"profile_id": "a", "traveller_count": 1},
        ],
    )
    whole = route_draft(travellers=2)
    halves = route_draft(
        travellers=2,
        profiles=[
            {"profile_id": "h1", "traveller_count": 1},
            {"profile_id": "h2", "traveller_count": 1},
        ],
    )
    for left, right in ((split, renamed), (whole, halves)):
        a, b = identities(left), identities(right)
        for name in ("request_key", "economic_digest", "fingerprint"):
            assert a[name] == b[name], name
    assert unit_of(split, "u1").fingerprint == unit_of(split, "u2").fingerprint


def test_k6_profiles_with_different_windows_are_not_merged():
    draft = route_draft(
        profiles=[
            {"profile_id": "a", "traveller_count": 1},
            {"profile_id": "b", "traveller_count": 1, "return_before": "2027-02-26"},
        ]
    )
    assert len(build_profiles(draft)) == 2


# --- K8: label, K9 (keys): mixed request ---------------------------------------------------


def test_k8_v3_document_is_labeled_and_v2_has_no_route_field():
    v3 = request_key_content((unit_of(route_draft()),), package())
    assert v3["schema"] == REQUEST_KEY_SCHEMA_V3 == "negotiation-request-key-v3"
    serialized_v3 = json.dumps(v3)
    for name in ("origin_key", "trip_type", "outbound", "return", "departure_before"):
        assert f'"{name}"' in serialized_v3
    northstar = load_offer_catalog(CATALOG_V1)[0].get("tyo-northstar-20270310")
    v1_unit = unit_of(
        TravelRequestDraft(destination="Tokyo", travellers=2, budget_per_person="500")
    )
    serialized_v2 = json.dumps(request_key_content((v1_unit,), northstar))
    for name in ("origin", "trip_type", "outbound", "return", "leg_ref", "departure_before"):
        assert name not in serialized_v2


def test_k9_a_unit_and_an_offer_of_different_routes_cannot_be_negotiated():
    v1_unit = unit_of(
        TravelRequestDraft(destination="Alger", travellers=2, budget_per_person="500")
    )
    with pytest.raises(ValueError, match="route"):
        negotiation_request_for((v1_unit,), package())
    with pytest.raises(ValueError, match="route"):
        negotiation_request_for((unit_of(route_draft()),), package(back=False))
    with pytest.raises(ValueError, match="route"):
        negotiation_request_for((unit_of(route_draft(origin="Marseille")),), package())


# --- K10: property ------------------------------------------------------------------------


def test_k10_same_key_if_and_only_if_same_canonical_document():
    generator = random.Random(20261120)
    choices = {
        "origin": ["Lyon", "LYON", "Marseille"],
        "trip_type": ["round_trip", "one_way"],
        "departure_before": ["2027-02-15", "2027-02-16"],
        "return_before": ["2027-02-25", "2027-02-26"],
        "budget_per_person": ["500", "500.00", "510"],
        "travellers": [1, 2],
    }
    samples = []
    for _ in range(80):
        fields = {name: generator.choice(values) for name, values in choices.items()}
        if fields["trip_type"] == "one_way":
            fields |= {"return_after": None, "return_before": None}
        unit = unit_of(route_draft(**fields))
        samples.append(unit)
    for left in samples:
        for right in samples:
            same_document = unit_economic_content(left) == unit_economic_content(right)
            assert (unit_economic_digest(left) == unit_economic_digest(right)) == same_document
            assert (left.fingerprint == right.fingerprint) == same_document


# --- package offers: C1 to C6 in the domain -----------------------------------------------


def test_a_round_trip_and_a_one_way_package_are_valid():
    round_trip, one_way = package(), package("lys-alg-b", back=False)
    assert (round_trip.trip_type, one_way.trip_type) == ("round_trip", "one_way")
    assert round_trip.origin_key == "lyon" and round_trip.is_route_offer
    v1 = load_offer_catalog(CATALOG_V1)[0].offers[0]
    assert (v1.trip_type, v1.origin_key, v1.is_route_offer) == (None, None, False)


@pytest.mark.parametrize("back", [True, False])
def test_c1_to_c5_are_package_invariants(back):
    late = leg(date(2027, 2, 14), "AJ-102-20270214")
    cases = {
        "C1 leg": lambda: OfferLeg(date(2027, 2, 16), date(2027, 2, 15), True, 40, "AJ-1-20270216"),
        "C2": lambda: package(back=back, capacity_seats=39),
        "C3": lambda: package(back=back, direct=False),
        "C4": lambda: package(
            back=back,
            outbound=leg(date(2027, 2, 15), "AJ-101-20270215", capacity=3),
            return_leg=leg(date(2027, 2, 25), "AJ-102-20270225", capacity=3) if back else None,
            capacity_seats=3,
        ),
        "C5 form": lambda: leg(date(2027, 2, 15), "aj-101-20270215"),
        "C5 suffix": lambda: leg(date(2027, 2, 15), "AJ-101-20270216"),
        "outbound dates": lambda: package(back=back, departure_date=date(2027, 2, 14)),
    }
    if back:
        cases["C1 order"] = lambda: package(return_leg=late)
        cases["C6 in a package"] = lambda: package(
            return_leg=leg(date(2027, 2, 15), "AJ-101-20270215")
        )
    for name, build in cases.items():
        with pytest.raises(ValueError):
            build()
            pytest.fail(name)


def test_c3_and_c2_take_both_legs_of_a_round_trip():
    stop = leg(date(2027, 2, 25), "AJ-102-20270225", direct=False, capacity=12)
    offer = package(return_leg=stop, direct=False, capacity_seats=12)
    assert (offer.direct, offer.capacity_seats) == (False, 12)


def test_c6_a_leg_ref_appears_once_in_a_catalogue_and_kinds_are_not_mixed():
    first = package("lys-alg-a")
    second = package(
        "lys-alg-b",
        outbound=leg(date(2027, 2, 15), "AJ-101-20270215"),
        return_leg=leg(date(2027, 2, 25), "AJ-202-20270225"),
    )
    with pytest.raises(ValueError, match="C6"):
        OfferCatalog("catalog-v2", "0" * 64, (first, second))
    v1 = replace(load_offer_catalog(CATALOG_V1)[0].offers[0], catalog_version="catalog-v2")
    with pytest.raises(ValueError, match="v1 offers only or v2"):
        OfferCatalog("catalog-v2", "0" * 64, (first, v1))


# --- travel units with a route --------------------------------------------------------------


def test_a_route_unit_carries_its_origin_trip_type_and_windows():
    unit = unit_of(route_draft(origin=" LYON "))
    assert (unit.origin_key, unit.trip_type, unit.destination_key) == (
        "lyon",
        "round_trip",
        "alger",
    )
    profile = unit.profiles[0]
    assert profile.route_windows == (date(2027, 2, 15), date(2027, 2, 25), date(2027, 2, 25))


def test_route_invariants_of_a_unit():
    unit = unit_of(route_draft())
    with pytest.raises(ValueError):
        replace(unit, trip_type=None)
    with pytest.raises(ValueError):
        replace(unit, origin_key="Lyon")
    with pytest.raises(ValueError):
        replace(unit, trip_type="multi_city")
    with pytest.raises(ValueError):
        replace(unit, trip_type="one_way")  # its profiles carry a return window
    with pytest.raises(ValueError):
        replace(unit, origin_key=None, trip_type=None)  # windows without a route
    assert isinstance(unit, TravelUnit)


# --- place directory ------------------------------------------------------------------------


def test_the_place_directory_resolves_names_and_aliases():
    directory = PlaceDirectory(
        "places-test",
        (Place("Alger", ("Algiers", "ALG")), Place("Lyon", ("LYS",)), Place("Marseille", ())),
    )
    for spelling in ("Alger", " algiers ", "ALG", unicodedata.normalize("NFD", "Alger")):
        assert directory.resolve(spelling) == "Alger"
    assert directory.resolve("lys") == "Lyon"
    assert directory.resolve("Paris") is None and directory.resolve("  ") is None
    assert directory.names == ("Alger", "Lyon", "Marseille")


def test_an_inconsistent_place_directory_is_refused():
    with pytest.raises(PlaceDirectoryError, match="share a spelling"):
        PlaceDirectory("p", (Place("Alger", ("Lyon",)), Place("Lyon", ())))
    with pytest.raises(PlaceDirectoryError, match="sorted"):
        PlaceDirectory("p", (Place("Lyon", ()), Place("Alger", ())))
    with pytest.raises(PlaceDirectoryError):
        PlaceDirectory("p", (Place("Alger", ("  ",)),))
    with pytest.raises(PlaceDirectoryError):
        Place(" Alger", ())
