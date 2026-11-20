"""I4-B: catalogue v2 (C1 to C6, H-forfait), place directory, NON_FINANCIAL_V2, policy
deduction (K9), route validation and the frozen v2 data."""

import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from coalition_travel.application.lot_admissibility import LotInputError, lot_admissibility
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.request_understanding import (
    REQUIRED_FIELDS_V2,
    validate_request_draft,
)
from coalition_travel.application.travel_units import build_travel_unit
from coalition_travel.application.trip_planning import (
    PlanningInput,
    PlanningRequest,
    plan_lot,
    route_key,
)
from coalition_travel.domain.admissibility import (
    RULE_ORDER,
    RULE_ORDER_V2,
    RULE_REGISTRY,
    AdmissibilityPolicy,
    evaluate_unit_offer,
)
from coalition_travel.infrastructure.catalog.json_catalog import (
    CatalogValidationError,
    load_offer_catalog,
)
from coalition_travel.infrastructure.catalog.places import (
    check_catalog_places,
    load_place_directory,
)
from coalition_travel.infrastructure.demand.demand_pool import load_demand_pool
from coalition_travel.infrastructure.negotiation.market import open_simulated_market
from p4_support import REFERENCE

ROOT = Path(__file__).resolve().parents[1]
CATALOG_V1 = ROOT / "data/catalog/catalog_v1.json"
CATALOG_V2 = ROOT / "data/catalog/catalog_v2.json"
PLACES = ROOT / "data/catalog/places_v1.json"
POOL_V2 = ROOT / "data/demand/demand_pool_v2.jsonl"
BRISOLIS, CALANQUA = "lys-alg-brs-20270215", "lys-alg-clq-20270215"
ORVALIS_LATE, VELTRANE, MARSEILLE = (
    "lys-alg-orv-20270215",
    "lys-alg-vlt-20270215",
    "mrs-alg-orv-20270215",
)
ROUND_TRIP = {
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
ONE_WAY = {key: value for key, value in ROUND_TRIP.items() if not key.startswith("return")} | {
    "trip_type": "one_way"
}


@pytest.fixture(scope="module")
def catalog():
    return load_offer_catalog(CATALOG_V2)[0]


def unit(fields=None, unit_id="user", **changes):
    draft = TravelRequestDraft.model_validate((fields or ROUND_TRIP) | changes)
    return build_travel_unit(unit_id, draft, REFERENCE)


def write_catalog(tmp_path, document, name="catalog_v2.json"):
    """A catalogue file with a matching manifest, so that only the tested rule can fail."""
    raw = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    path = tmp_path / name
    path.write_bytes(raw)
    manifest = json.loads((ROOT / "data/catalog/catalog_v2.manifest.json").read_text("utf-8"))
    manifest |= {
        "catalog_file": name,
        "catalog_sha256": hashlib.sha256(raw).hexdigest(),
        "offers": len(document["offers"]),
    }
    (tmp_path / name).with_suffix(".manifest.json").write_text(json.dumps(manifest), "utf-8")
    return path


def base_document():
    return json.loads(CATALOG_V2.read_text("utf-8"))


# --- the frozen v2 data --------------------------------------------------------------------


def test_the_frozen_v2_data_load_and_agree(catalog):
    assert catalog.version == "catalog-v2"
    kinds = {
        offer.offer_id: (offer.trip_type, offer.direct, offer.capacity_seats)
        for offer in catalog.offers
    }
    assert kinds == {
        BRISOLIS: ("round_trip", True, 40),
        CALANQUA: ("round_trip", False, 28),  # C3 and C2 over both legs
        ORVALIS_LATE: ("round_trip", True, 40),
        VELTRANE: ("one_way", True, 30),
        MARSEILLE: ("round_trip", True, 40),
    }
    directory = load_place_directory(PLACES)
    check_catalog_places(catalog, directory)
    assert directory.names == ("Alger", "Lyon", "Marseille")
    pool = load_demand_pool(POOL_V2)
    assert (pool.version, pool.catalog_version, len(pool.requests)) == (
        "demand-pool-v2",
        "catalog-v2",
        6,
    )
    assert load_offer_catalog(CATALOG_V1)[0].sha256.startswith("4b145ecbdbd6")


# --- C1 to C6 and H-forfait at loading -----------------------------------------------------


def mutate(index, change):
    document = base_document()
    change(document["offers"][index])
    return document


def drop_return_key(offer):
    del offer["return"]["leg_ref"]


REFUSED_ROUND_TRIP = {
    "partial return block": drop_return_key,
    "null return block": lambda offer: offer.update({"return": None}),
    "C1 return before outbound": lambda offer: offer["return"].update(
        {
            "departure_date": "2027-02-14",
            "arrival_date": "2027-02-14",
            "leg_ref": "BRS-312-20270214",
        }
    ),
    "C2 declared capacity": lambda offer: offer.update({"capacity_seats": 39}),
    "C4 tier above capacity": lambda offer: offer["tiers"].append(
        {"min_seats": 41, "list_per_seat_cents": 20000, "seller_floor_per_seat_cents": 14000}
    ),
    "C5 lowercase": lambda offer: offer["return"].update({"leg_ref": "brs-312-20270225"}),
    "C5 suffix": lambda offer: offer["return"].update({"leg_ref": "BRS-312-20270226"}),
    "C5 space": lambda offer: offer["return"].update({"leg_ref": "BRS 312-20270225"}),
    "C6 within the package": lambda offer: offer["return"].update(
        {
            "departure_date": "2027-02-15",
            "arrival_date": "2027-02-15",
            "leg_ref": "BRS-311-20270215",
        }
    ),
    "redundant direct field": lambda offer: offer.update({"direct": True}),
}
REFUSED_ONE_WAY = {
    "C1 leg dates": lambda offer: offer["outbound"].update({"arrival_date": "2027-02-14"}),
    "C2 declared capacity": lambda offer: offer.update({"capacity_seats": 31}),
    "C4 tier above capacity": lambda offer: offer["tiers"].append(
        {"min_seats": 31, "list_per_seat_cents": 15000, "seller_floor_per_seat_cents": 10500}
    ),
    "C5 non canonical": lambda offer: offer["outbound"].update({"leg_ref": "VLT_77_20270215"}),
    "C5 suffix": lambda offer: offer["outbound"].update({"leg_ref": "VLT-77-20270216"}),
    "partial outbound block": lambda offer: offer["outbound"].pop("direct"),
}


@pytest.mark.parametrize("name", sorted(REFUSED_ROUND_TRIP))
def test_a_round_trip_package_breaking_a_rule_is_refused(tmp_path, name):
    path = write_catalog(tmp_path, mutate(0, REFUSED_ROUND_TRIP[name]))
    with pytest.raises(CatalogValidationError):
        load_offer_catalog(path)


@pytest.mark.parametrize("name", sorted(REFUSED_ONE_WAY))
def test_a_one_way_package_breaking_a_rule_is_refused(tmp_path, name):
    path = write_catalog(tmp_path, mutate(3, REFUSED_ONE_WAY[name]))
    with pytest.raises(CatalogValidationError):
        load_offer_catalog(path)


def test_c6_a_leg_shared_by_two_packages_is_refused(tmp_path):
    document = base_document()
    document["offers"][4]["outbound"]["leg_ref"] = "BRS-311-20270215"  # Brisolis outbound
    with pytest.raises(CatalogValidationError, match="C6"):
        load_offer_catalog(write_catalog(tmp_path, document))


def test_the_format_key_selects_the_reader(tmp_path):
    document = base_document()
    document["format"] = "offer-catalog-v3"
    with pytest.raises(CatalogValidationError, match="format"):
        load_offer_catalog(write_catalog(tmp_path, document))
    without = base_document()
    del without["format"]
    with pytest.raises(CatalogValidationError):  # read as v1, whose keys differ
        load_offer_catalog(write_catalog(tmp_path, without))


def test_a_valid_variant_with_a_stopover_on_the_outbound_loads(tmp_path):
    document = mutate(0, lambda offer: offer["outbound"].update({"direct": False}))
    offer = load_offer_catalog(write_catalog(tmp_path, document))[0].get(BRISOLIS)
    assert offer.direct is False  # C3, computed by the reader


# --- place directory ------------------------------------------------------------------------


def write_places(tmp_path, document):
    raw = (json.dumps(document) + "\n").encode("utf-8")
    path = tmp_path / "places_v1.json"
    path.write_bytes(raw)
    manifest = json.loads((ROOT / "data/catalog/places_v1.manifest.json").read_text("utf-8"))
    manifest |= {
        "places_sha256": hashlib.sha256(raw).hexdigest(),
        "places": len(document["places"]),
    }
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest), "utf-8")
    return path


def test_the_place_directory_aliases():
    directory = load_place_directory(PLACES)
    for spelling, name in (
        ("Algiers", "Alger"),
        ("alg", "Alger"),
        ("LYS", "Lyon"),
        ("Marseilles", "Marseille"),
    ):
        assert directory.resolve(spelling) == name
    assert directory.resolve("Paris") is None


def test_an_invalid_place_directory_is_refused(tmp_path, catalog):
    colliding = {
        "version": "places-v1",
        "places": [{"name": "Alger", "aliases": ["Lyon"]}, {"name": "Lyon", "aliases": []}],
    }
    with pytest.raises(CatalogValidationError, match="share a spelling"):
        load_place_directory(write_places(tmp_path, colliding))
    missing = {"version": "places-v1", "places": [{"name": "Alger", "aliases": []}]}
    directory = load_place_directory(write_places(tmp_path, missing))
    with pytest.raises(CatalogValidationError, match="canonical place name"):
        check_catalog_places(catalog, directory)
    path = write_places(tmp_path, missing)
    path.write_text(path.read_text("utf-8") + " ", "utf-8")
    with pytest.raises(CatalogValidationError, match="does not match"):
        load_place_directory(path)


def test_a_catalogue_naming_a_place_by_an_alias_is_refused(tmp_path):
    document = mutate(0, lambda offer: offer.update({"destination": "Algiers"}))
    catalog = load_offer_catalog(write_catalog(tmp_path, document))[0]
    with pytest.raises(CatalogValidationError, match="canonical"):
        check_catalog_places(catalog, load_place_directory(PLACES))


# --- NON_FINANCIAL_V2: one test per rule and per reason -------------------------------------


def reasons(pair):
    return [(item.rule.value, item.reason, item.profile_id) for item in pair.violations]


def evaluate(unit_, offer):
    return evaluate_unit_offer(unit_, offer, REFERENCE, AdmissibilityPolicy.NON_FINANCIAL_V2)


def test_the_v2_registry_keeps_v1_unchanged():
    assert RULE_REGISTRY[AdmissibilityPolicy.NON_FINANCIAL_V1] is RULE_ORDER
    assert RULE_REGISTRY[AdmissibilityPolicy.NON_FINANCIAL_V2] is RULE_ORDER_V2
    assert [rule for rule in RULE_ORDER_V2 if rule in RULE_ORDER] == list(RULE_ORDER)


def test_the_reference_unit_is_admissible_on_the_reference_package(catalog):
    pair = evaluate(unit(), catalog.get(BRISOLIS))
    assert pair.admissible and pair.notes == ()


def test_route_mismatches_are_the_only_violations_reported(catalog):
    assert reasons(evaluate(unit(origin="Marseille"), catalog.get(BRISOLIS))) == [
        ("origin", "origin_mismatch", None)
    ]
    marseille = replace(catalog.get(MARSEILLE), destination="Oran")
    assert reasons(evaluate(unit(), marseille)) == [
        ("destination", "destination_mismatch", None),
        ("origin", "origin_mismatch", None),
    ]


def test_trip_type_mismatch_both_ways(catalog):
    assert reasons(evaluate(unit(), catalog.get(VELTRANE))) == [
        ("trip_type", "trip_type_mismatch", None)
    ]
    assert reasons(evaluate(unit(ONE_WAY), catalog.get(BRISOLIS))) == [
        ("trip_type", "trip_type_mismatch", None)
    ]
    assert evaluate(unit(ONE_WAY), catalog.get(VELTRANE)).admissible


def test_departure_window_both_bounds(catalog):
    early = unit(departure_after="2027-02-16", departure_before="2027-02-20")
    late = unit(departure_after="2027-02-01", departure_before="2027-02-14")
    assert reasons(evaluate(early, catalog.get(BRISOLIS))) == [
        ("departure_window", "departure_before_window", "all")
    ]
    assert reasons(evaluate(late, catalog.get(BRISOLIS))) == [
        ("departure_window", "departure_after_window", "all")
    ]


def test_return_window_both_bounds(catalog):
    assert reasons(evaluate(unit(), catalog.get(ORVALIS_LATE))) == [
        ("return_window", "return_after_window", "all")
    ]
    later = unit(return_after="2027-02-26", return_before="2027-02-28")
    assert reasons(evaluate(later, catalog.get(BRISOLIS))) == [
        ("return_window", "return_before_window", "all")
    ]
    assert evaluate(later, catalog.get(ORVALIS_LATE)).admissible


def test_offer_before_reference_and_arrival_window(catalog):
    after = evaluate_unit_offer(
        unit(), catalog.get(BRISOLIS), date(2026, 11, 19), AdmissibilityPolicy.NON_FINANCIAL_V2
    )
    assert after.admissible
    arrival = unit(arrival_before="2027-02-14", departure_after="2027-02-01")
    assert ("arrival_window", "arrival_after_window", "all") in reasons(
        evaluate(arrival, catalog.get(BRISOLIS))
    )
    later_reference = evaluate_unit_offer(
        build_travel_unit("user", TravelRequestDraft.model_validate(ROUND_TRIP), REFERENCE),
        catalog.get(BRISOLIS),
        date(2027, 2, 16),
        AdmissibilityPolicy.NON_FINANCIAL_V2,
    )
    assert ("offer_not_before_reference", "offer_departs_before_reference_date", None) in reasons(
        later_reference
    )


def test_direct_flight_supplier_and_capacity(catalog):
    required = unit(direct_flight="required")
    assert reasons(evaluate(required, catalog.get(CALANQUA))) == [
        ("direct_flight", "direct_flight_required", "all")
    ]
    preferred = evaluate(unit(direct_flight="preferred"), catalog.get(CALANQUA))
    assert preferred.admissible and [note.code for note in preferred.notes] == [
        "direct_preference_not_met"
    ]
    excluded = unit(excluded_suppliers=["calanqua"])
    assert reasons(evaluate(excluded, catalog.get(CALANQUA))) == [
        ("supplier_exclusion", "excluded_supplier", "all")
    ]
    with pytest.raises(ValueError, match="C2"):  # not the smallest leg capacity
        replace(catalog.get(CALANQUA), capacity_seats=19)
    assert evaluate(unit(travellers=20), catalog.get(CALANQUA)).admissible  # 20 <= 28


def test_capacity_violation_on_a_package(catalog):
    offer = catalog.get(CALANQUA)
    legs = (
        replace(offer.outbound, capacity_seats=10),
        replace(offer.return_leg, capacity_seats=10),
    )
    tight = replace(offer, outbound=legs[0], return_leg=legs[1], capacity_seats=10)
    assert reasons(evaluate(unit(travellers=12), tight)) == [
        ("unit_capacity", "unit_exceeds_offer_capacity", None)
    ]


def test_profile_level_windows_are_reported_per_profile(catalog):
    split = unit(
        profiles=[
            {"profile_id": "a", "traveller_count": 1},
            {
                "profile_id": "b",
                "traveller_count": 1,
                "return_after": "2027-02-20",
                "return_before": "2027-02-24",
            },
        ]
    )
    pair = evaluate(split, catalog.get(BRISOLIS))
    assert reasons(pair) == [("return_window", "return_after_window", "b")]


# --- policy deduction and K9 ------------------------------------------------------------------


def test_the_policy_is_deduced_from_the_lot(catalog):
    lot = lot_admissibility((unit(),), catalog, REFERENCE)
    assert lot.policy is AdmissibilityPolicy.NON_FINANCIAL_V2
    v1_catalog = load_offer_catalog(CATALOG_V1)[0]
    tokyo = build_travel_unit(
        "user",
        TravelRequestDraft(destination="Tokyo", travellers=1, budget_per_person="520"),
        REFERENCE,
    )
    assert (
        lot_admissibility((tokyo,), v1_catalog, REFERENCE).policy
        is AdmissibilityPolicy.NON_FINANCIAL_V1
    )


def test_k9_mixed_lots_and_contradicting_policies_are_refused(catalog):
    v1_catalog = load_offer_catalog(CATALOG_V1)[0]
    tokyo = build_travel_unit(
        "tokyo",
        TravelRequestDraft(destination="Tokyo", travellers=1, budget_per_person="520"),
        REFERENCE,
    )
    for units, offers in (((unit(), tokyo), catalog), ((unit(),), v1_catalog), ((tokyo,), catalog)):
        with pytest.raises(LotInputError, match="K9"):
            lot_admissibility(units, offers, REFERENCE)
    with pytest.raises(LotInputError, match="contradicts"):
        lot_admissibility((unit(),), catalog, REFERENCE, AdmissibilityPolicy.NON_FINANCIAL_V1)
    with pytest.raises(ValueError, match="NON_FINANCIAL_V2"):
        evaluate_unit_offer(unit(), catalog.get(BRISOLIS), REFERENCE)
    with pytest.raises(ValueError, match="NON_FINANCIAL_V2"):
        evaluate_unit_offer(
            tokyo, v1_catalog.offers[1], REFERENCE, AdmissibilityPolicy.NON_FINANCIAL_V2
        )


def test_route_selection_keeps_one_route_per_lot():
    pool = load_demand_pool(POOL_V2)
    market = open_simulated_market(CATALOG_V2, REFERENCE)
    request = PlanningRequest("user", TravelRequestDraft.model_validate(ROUND_TRIP))
    plan = plan_lot(PlanningInput((request,), pool, REFERENCE), market)
    assert plan.status == "planned"
    assert plan.pool_unit_ids == (
        "pool-lys-alg-01",
        "pool-lys-alg-02",
        "pool-lys-alg-03",
        "pool-lys-alg-04",
    )
    keys = {route_key(item) for item in plan.units}
    assert keys == {"lyon>alger|round_trip"}
    assert plan.stages.lot.policy is AdmissibilityPolicy.NON_FINANCIAL_V2
    tokyo = build_travel_unit(
        "t",
        TravelRequestDraft(destination="Tokyo", travellers=1, budget_per_person="520"),
        REFERENCE,
    )
    assert route_key(tokyo) == "tokyo"


# --- route validation (D-I4-3, D-I4-4) ------------------------------------------------------


def test_v2_required_fields_in_order():
    assert REQUIRED_FIELDS_V2[:5] == (
        "origin",
        "destination",
        "travellers",
        "budget_per_person",
        "trip_type",
    )
    partial = validate_request_draft(TravelRequestDraft(origin="Lyon"), REFERENCE)
    assert partial.missing_fields == (
        "destination",
        "travellers",
        "budget_per_person",
        "trip_type",
        "departure_after",
        "departure_before",
    )
    round_trip = {key: value for key, value in ROUND_TRIP.items() if not key.startswith("return")}
    result = validate_request_draft(TravelRequestDraft.model_validate(round_trip), REFERENCE)
    assert result.missing_fields == ("return_after", "return_before")
    assert (
        validate_request_draft(TravelRequestDraft.model_validate(ONE_WAY), REFERENCE).status
        == "ready"
    )
    v1 = validate_request_draft(TravelRequestDraft(destination="Tokyo"), REFERENCE)
    assert v1.missing_fields == ("travellers", "budget_per_person")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"departure_before": "2026-11-01", "departure_after": None},
            "departure_before must not be before the reference date",
        ),
        ({"return_after": "2026-11-01"}, "return_after must not be before the reference date"),
        ({"departure_after": "2027-02-16"}, "departure_after must not be after departure_before"),
        ({"return_after": "2027-02-26"}, "return_after must not be after return_before"),
        ({"trip_type": "one_way"}, "a one_way request must not have a return window"),
        (
            {"return_after": "2027-02-10", "return_before": "2027-02-12"},
            "the return window must not end before the departure window starts",
        ),
    ],
)
def test_route_validation_messages(changes, message):
    fields = ROUND_TRIP | changes
    result = validate_request_draft(
        TravelRequestDraft.model_validate(
            {key: value for key, value in fields.items() if value is not None}
        ),
        REFERENCE,
    )
    assert result.status in ("invalid", "needs_clarification")
    if result.status == "invalid":
        assert message in result.errors
    else:  # a removed bound is first a missing field
        assert "departure_after" in result.missing_fields


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        (
            {"return_before": "2027-02-20", "return_after": "2027-02-21"},
            "profile a: the return window is empty",
        ),
        ({"departure_before": "2027-02-14"}, "profile a: the departure window is empty"),
        ({"return_before": "2026-11-01"}, "profile a: return_before is before reference date"),
        (
            {"return_before": "2027-02-10"},
            "profile a: the return window ends before the departure window starts",
        ),
    ],
)
def test_profile_route_validation_messages(profile, message):
    draft = TravelRequestDraft.model_validate(
        ROUND_TRIP | {"profiles": [{"profile_id": "a", "traveller_count": 2} | profile]}
    )
    assert message in validate_request_draft(draft, REFERENCE).errors


def test_a_one_way_profile_with_a_return_window_is_invalid():
    draft = TravelRequestDraft.model_validate(
        ONE_WAY
        | {"profiles": [{"profile_id": "a", "traveller_count": 2, "return_before": "2027-02-25"}]}
    )
    assert (
        "profile a: a one_way request must not have a return window"
        in validate_request_draft(draft, REFERENCE).errors
    )


def test_the_frozen_pool_requests_are_valid_route_requests():
    pool = load_demand_pool(POOL_V2)
    directory = load_place_directory(PLACES)
    for request in pool.requests:
        assert validate_request_draft(request.draft, REFERENCE).status == "ready"
        assert directory.resolve(request.draft.origin) == request.draft.origin
        assert directory.resolve(request.draft.destination) == request.draft.destination


def test_a_window_set_on_every_profile_satisfies_the_requirement():
    base = {key: value for key, value in ROUND_TRIP.items() if not key.startswith("return")}
    window = {"return_after": "2027-02-25", "return_before": "2027-02-25"}
    everyone = TravelRequestDraft.model_validate(
        base
        | {
            "profiles": [
                {"profile_id": "a", "traveller_count": 1} | window,
                {"profile_id": "b", "traveller_count": 1} | window,
            ]
        }
    )
    assert validate_request_draft(everyone, REFERENCE).status == "ready"
    one = TravelRequestDraft.model_validate(
        base
        | {
            "profiles": [
                {"profile_id": "a", "traveller_count": 1} | window,
                {"profile_id": "b", "traveller_count": 1},
            ]
        }
    )
    assert validate_request_draft(one, REFERENCE).missing_fields == (
        "return_after",
        "return_before",
    )
