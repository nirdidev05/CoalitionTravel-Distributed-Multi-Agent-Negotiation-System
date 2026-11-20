"""P2 lot-level H2 capacity, provenance, diagnostics and input contract (P2-bis)."""

import dataclasses
import hashlib
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from coalition_travel.application.lot_admissibility import (
    CAPACITY_MODEL,
    CapacityModelViolated,
    LotAdmissibilityError,
    LotInputError,
    lot_admissibility,
)
from coalition_travel.application.request_contracts import (
    TravelerProfileDraft,
    TravelRequestDraft,
)
from coalition_travel.application.travel_units import build_travel_unit
from coalition_travel.domain.admissibility import AdmissibilityPolicy
from coalition_travel.domain.offer import OfferCatalog, OfferQuote, PriceTier
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile
from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog

REFERENCE = date(2026, 11, 19)
CATALOG_PATH = Path(__file__).resolve().parents[1] / "data/catalog/catalog_v1.json"


def _unit(identifier, seats, excluded=(), destination="Tokyo", **profile_fields):
    profile = TravelerProfile(
        "all", seats, destination, Decimal(100), excluded_suppliers=excluded, **profile_fields
    )
    return TravelUnit(
        identifier,
        destination.casefold(),
        (profile,),
        hashlib.sha256(identifier.encode()).hexdigest(),
    )


def _offer(identifier, capacity, destination="Tokyo", supplier="Northstar"):
    return OfferQuote(
        identifier,
        "v1",
        supplier,
        destination,
        date(2027, 1, 1),
        date(2027, 1, 2),
        True,
        capacity,
        (PriceTier(1, 100),),
    )


def _catalog(*offers, sha="a" * 64):
    ordered = tuple(sorted(offers, key=lambda offer: offer.offer_id))
    return OfferCatalog(ordered[0].catalog_version, sha, ordered)


def _lot(units, offers, **kwargs):
    return lot_admissibility(units, _catalog(*offers), REFERENCE, **kwargs)


# --- H2 (uncoupled_v1) -----------------------------------------------------------------


def test_h2_boundary_demand_equal_to_capacity_is_optimizable():
    lot = _lot((_unit("u1", 2), _unit("u2", 3)), (_offer("o1", 5),))

    assert lot.status == "optimizable"
    check = lot.capacity_checks[0]
    assert (check.admissible_unit_seats, check.unit_ids, check.valid) == (5, ("u1", "u2"), True)
    assert lot.require_optimizable() is lot


def test_h2_boundary_one_seat_over_capacity_is_violated():
    lot = _lot((_unit("u1", 3), _unit("u2", 3)), (_offer("o1", 5),))

    assert lot.status == "capacity_model_violated"
    with pytest.raises(CapacityModelViolated) as error:
        lot.require_optimizable()
    assert [check.offer_id for check in error.value.checks] == ["o1"]
    assert isinstance(error.value, LotAdmissibilityError)


def test_h2_refuses_a_lot_that_a_split_over_two_offers_could_have_served():
    """Accepted MVP restriction: 70 travelers, two offers of 60 seats, all units admissible
    to both. H2 fails for each offer although a 35/35 split would fit."""
    units = tuple(_unit(f"u{index}", 10) for index in range(7))
    lot = _lot(units, (_offer("o1", 60), _offer("o2", 60)))

    assert lot.status == "capacity_model_violated"
    assert [(check.admissible_unit_seats, check.valid) for check in lot.capacity_checks] == [
        (70, False),
        (70, False),
    ]
    assert lot.components  # the graph stays inspectable


def test_h2_refuses_the_whole_lot_even_when_partial_service_was_possible():
    """70 travelers and one offer of 60 seats: no unit is served, not even 60 seats."""
    units = tuple(_unit(f"u{index}", 10) for index in range(7))
    lot = _lot(units, (_offer("o1", 60),))

    assert lot.status == "capacity_model_violated"
    with pytest.raises(CapacityModelViolated):
        lot.require_optimizable()


def test_h2_counts_all_individually_admissible_units_70_60_60_against_100():
    lot = _lot((_unit("u1", 70), _unit("u2", 60), _unit("u3", 60)), (_offer("o1", 100),))

    assert lot.status == "capacity_model_violated"
    assert lot.capacity_checks[0].admissible_unit_seats == 190
    assert len(lot.relation.edges) == 3


# --- exclusions and diagnostics ---------------------------------------------------------


def test_unit_larger_than_every_offer_is_excluded_at_lot_level_with_details():
    lot = _lot((_unit("u1", 4),), (_offer("o1", 3),))

    assert lot.relation.edges == frozenset()
    assert lot.status == "optimizable"
    assert lot.components == ()
    assert [(item.unit_id, item.reason, item.details) for item in lot.exclusions] == [
        ("u1", "no_admissible_offer", ("o1: unit_exceeds_offer_capacity",))
    ]


def test_no_admissible_offer_is_visible_even_when_h2_fails():
    lot = _lot(
        (_unit("u1", 7), _unit("u2", 7), _unit("lisbon", 1, destination="Lisbon")),
        (_offer("o1", 10),),
    )

    assert lot.status == "capacity_model_violated"
    assert [(item.unit_id, item.reason) for item in lot.exclusions] == [
        ("lisbon", "no_admissible_offer")
    ]
    assert lot.exclusions[0].details == ("o1: destination_mismatch",)


def test_unused_offers_are_reported_and_kept_out_of_components():
    lot = _lot((_unit("u1", 1),), (_offer("o1", 2), _offer("rome", 2, destination="Rome")))

    assert lot.unused_offers == ("rome",)
    assert [[offer.offer_id for offer in item.offers] for item in lot.components] == [["o1"]]


def test_unmatched_exclusions_name_the_profile_without_changing_admissibility():
    lot = _lot((_unit("u1", 1, ("Unknown Air",)),), (_offer("o1", 2),))

    assert lot.relation.edges == frozenset({("u1", "o1")})
    assert [
        (item.unit_id, item.profile_id, item.supplier) for item in lot.unmatched_exclusions
    ] == [("u1", "all", "Unknown Air")]


def test_each_pair_is_evaluated_and_destination_mismatch_short_circuits():
    lot = _lot((_unit("u1", 1),), (_offer("o1", 2), _offer("o2", 2, destination="Rome")))

    assert [(pair.unit_id, pair.offer_id) for pair in lot.relation.pair_results] == [
        ("u1", "o1"),
        ("u1", "o2"),
    ]
    assert [item.reason for item in lot.relation.pair_results[1].violations] == [
        "destination_mismatch"
    ]


# --- provenance and identity ------------------------------------------------------------


def test_lot_result_carries_full_provenance():
    lot = _lot((_unit("u1", 1),), (_offer("o1", 2),))

    assert lot.policy is AdmissibilityPolicy.NON_FINANCIAL_V1
    assert lot.capacity_model == CAPACITY_MODEL == "uncoupled_v1"
    assert (lot.catalog_version, lot.catalog_sha256, lot.reference_date) == (
        "v1",
        "a" * 64,
        REFERENCE,
    )
    assert len(lot.admissibility_id) == 64


def test_admissibility_id_depends_on_inputs_not_on_their_order():
    units = (_unit("u1", 1), _unit("u2", 1))
    offers = (_offer("o1", 5),)
    base = lot_admissibility(units, _catalog(*offers), REFERENCE).admissibility_id

    assert lot_admissibility(units[::-1], _catalog(*offers), REFERENCE).admissibility_id == base
    assert lot_admissibility(units, _catalog(*offers), date(2026, 11, 20)).admissibility_id != base
    assert (
        lot_admissibility(units, _catalog(*offers, sha="b" * 64), REFERENCE).admissibility_id
        != base
    )
    assert lot_admissibility(units[:1], _catalog(*offers), REFERENCE).admissibility_id != base


def test_status_cannot_contradict_the_capacity_checks():
    lot = _lot((_unit("u1", 3), _unit("u2", 3)), (_offer("o1", 5),))
    with pytest.raises(ValueError, match="status must match"):
        dataclasses.replace(lot, status="optimizable")


# --- input contract ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "units,catalog,reference,policy",
    [
        ((), "catalog", REFERENCE, AdmissibilityPolicy.NON_FINANCIAL_V1),
        (("not a unit",), "catalog", REFERENCE, AdmissibilityPolicy.NON_FINANCIAL_V1),
        ("duplicates", "catalog", REFERENCE, AdmissibilityPolicy.NON_FINANCIAL_V1),
        ("units", "offers", REFERENCE, AdmissibilityPolicy.NON_FINANCIAL_V1),
        ("units", "catalog", datetime(2026, 11, 19), AdmissibilityPolicy.NON_FINANCIAL_V1),
        ("units", "catalog", REFERENCE, "non_financial_v1"),
    ],
)
def test_invalid_lot_inputs_raise_lot_input_error(units, catalog, reference, policy):
    offers = (_offer("o1", 5),)
    resolved_units = {
        "units": (_unit("u1", 1),),
        "duplicates": (_unit("u1", 1), _unit("u1", 2)),
    }.get(units, units)
    resolved_catalog = {"catalog": _catalog(*offers), "offers": offers}[catalog]
    with pytest.raises(LotInputError):
        lot_admissibility(resolved_units, resolved_catalog, reference, policy)


# --- integration with the versioned catalogue -------------------------------------------


def test_catalogue_v1_lot_with_family_exclusion_and_lisbon_request():
    catalog, _ = load_offer_catalog(CATALOG_PATH)

    def unit(request_id, seats, budget, destination="Tokyo", **fields):
        draft = TravelRequestDraft(
            destination=destination,
            travellers=seats,
            budget_per_person=Decimal(budget),
            **fields,
        )
        return build_travel_unit(request_id, draft, REFERENCE)

    units = (
        unit("R1", 2, "600", direct_flight="preferred"),
        unit("R2", 1, "550", excluded_suppliers=["SkyWays"]),
        unit(
            "R3",
            4,
            "900",
            profiles=[
                TravelerProfileDraft(profile_id="adults", traveller_count=2),
                TravelerProfileDraft(
                    profile_id="teens", traveller_count=2, budget_per_person=Decimal(500)
                ),
            ],
        ),
        unit("R4", 2, "400", destination="Lisbonne"),
    )
    lot = lot_admissibility(units, catalog, REFERENCE)

    assert lot.status == "optimizable"
    assert lot.catalog_sha256 == catalog.sha256
    assert [
        ([u.unit_id for u in item.units], [o.offer_id for o in item.offers])
        for item in lot.components
    ] == [(["R1", "R2", "R3"], ["tyo-northstar-20270310", "tyo-skyways-20270312"])]
    assert lot.unused_offers == ("rom-cloudwing-20270405",)
    assert [(item.unit_id, item.reason) for item in lot.exclusions] == [
        ("R4", "no_admissible_offer")
    ]
    skyways = lot.relation.decision("R2", "tyo-skyways-20270312")
    assert [(item.reason, item.profile_id) for item in skyways.violations] == [
        ("excluded_supplier", "all")
    ]
    preferred = lot.relation.decision("R1", "tyo-skyways-20270312")
    assert preferred.admissible
    assert [(note.code, note.profile_id) for note in preferred.notes] == [
        ("direct_preference_not_met", "all")
    ]
