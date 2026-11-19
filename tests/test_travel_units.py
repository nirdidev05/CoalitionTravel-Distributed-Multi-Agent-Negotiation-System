"""P1.3 — indivisible travel units with budgets in cents and a content fingerprint."""

import dataclasses
import unicodedata
from datetime import date, datetime
from decimal import Decimal, localcontext

import pytest
from coalition_travel.application.request_contracts import (
    TravelerProfileDraft,
    TravelRequestDraft,
)
from coalition_travel.application.travel_units import (
    TravelUnitError,
    build_travel_unit,
    unit_fingerprint,
)
from coalition_travel.domain.destination import normalize_destination_key
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile

REFERENCE = date(2026, 11, 19)
VALID_FINGERPRINT = "0" * 64


def _draft(budget="700", travellers=2, profiles=None, **fields):
    return TravelRequestDraft(
        destination=fields.pop("destination", "Tokyo"),
        travellers=travellers,
        budget_per_person=None if budget is None else Decimal(budget),
        profiles=profiles or [],
        **fields,
    )


def _group(profile_id, count, budget=None, **fields):
    return TravelerProfileDraft(
        profile_id=profile_id,
        traveller_count=count,
        budget_per_person=None if budget is None else Decimal(budget),
        **fields,
    )


def _profile(profile_id="a", count=1, budget="500.00", destination="Tokyo", **fields):
    return TravelerProfile(profile_id, count, destination, Decimal(budget), **fields)


# --- construction from a ready request -----------------------------------------------


def test_single_group_request_becomes_one_unit_with_one_profile():
    unit = build_travel_unit("  request-1 ", _draft("700", 2), REFERENCE)
    assert unit.unit_id == "request-1"
    assert unit.destination_key == "tokyo"
    assert [profile.profile_id for profile in unit.profiles] == ["all"]
    assert unit.seats == 2
    assert unit.budget_total_cents == 140_000
    assert unit.budget_per_seat_cents("all") == 70_000
    assert unit.rounded_budget_profiles == ()


def test_family_with_two_budgets_keeps_seats_and_total_in_cents():
    draft = _draft("900", 4, [_group("adults", 2, "900"), _group("teens", 2, "500")])
    unit = build_travel_unit("family", draft, REFERENCE)
    assert unit.seats == 4
    assert unit.budget_total_cents == 280_000
    assert unit.budget_per_seat_cents("teens") == 50_000


def test_unknown_profile_budget_lookup_raises_key_error():
    unit = build_travel_unit("request-1", _draft(), REFERENCE)
    with pytest.raises(KeyError):
        unit.budget_per_seat_cents("missing")


@pytest.mark.parametrize(
    "draft,status,detail",
    [
        (_draft(budget=None, travellers=4), "needs_clarification", "budget_per_person"),
        (
            _draft(departure_after=date(2026, 10, 1)),
            "invalid",
            "departure_after must not be before the reference date",
        ),
    ],
)
def test_requests_that_are_not_ready_are_refused_with_their_reason(draft, status, detail):
    with pytest.raises(TravelUnitError) as error:
        build_travel_unit("request-1", draft, REFERENCE)
    assert error.value.reason == "request_not_ready"
    assert error.value.status == status
    assert detail in error.value.missing_fields + error.value.errors


# --- rounded budgets (R1-R6) ---------------------------------------------------------


def test_r1_inherited_sub_cent_request_budget_is_rounded_and_flagged():
    unit = build_travel_unit("r1", _draft("333.335", 2), REFERENCE)
    assert unit.budget_per_seat_cents("all") == 33_333
    assert unit.profiles[0].budget_per_person == Decimal("333.33")
    assert unit.rounded_budget_profiles == ("all",)


def test_r2_overridden_request_budget_is_neither_rounded_nor_flagged():
    draft = _draft("333.335", 4, [_group("a", 2, "500"), _group("b", 2, "900")])
    unit = build_travel_unit("r2", draft, REFERENCE)
    assert unit.rounded_budget_profiles == ()
    assert unit.budget_total_cents == 280_000


def test_r2b_unused_request_budget_below_one_cent_raises_nothing():
    draft = _draft("0.004", 4, [_group("a", 2, "500"), _group("b", 2, "900")])
    unit = build_travel_unit("r2b", draft, REFERENCE)
    assert unit.rounded_budget_profiles == ()


def test_r3_only_the_profile_using_the_rounded_budget_is_flagged():
    draft = _draft("333.335", 3, [_group("inherits", 2), _group("own", 1, "400")])
    unit = build_travel_unit("r3", draft, REFERENCE)
    assert unit.rounded_budget_profiles == ("inherits",)
    assert unit.budget_per_seat_cents("inherits") == 33_333
    assert unit.budget_per_seat_cents("own") == 40_000


def test_r4_budgets_equal_after_rounding_are_consolidated_and_flagged():
    draft = _draft("700", 3, [_group("a", 2, "333.335"), _group("b", 1, "333.33")])
    unit = build_travel_unit("r4", draft, REFERENCE)
    assert len(unit.profiles) == 1
    merged = unit.profiles[0]
    assert merged.profile_id.startswith("merged-")
    assert merged.traveller_count == 3
    assert unit.rounded_budget_profiles == (merged.profile_id,)
    assert unit.budget_total_cents == 99_999


def test_r5_profile_budget_below_one_cent_is_refused():
    draft = _draft("700", 2, [_group("tiny", 1, "0.004"), _group("ok", 1, "500")])
    with pytest.raises(TravelUnitError) as error:
        build_travel_unit("r5", draft, REFERENCE)
    assert error.value.reason == "budget_below_one_cent"
    assert error.value.profile_id == "tiny"


def test_r6_no_rounding_gives_an_empty_tuple():
    unit = build_travel_unit("r6", _draft("500.00", 2), REFERENCE)
    assert unit.rounded_budget_profiles == ()


def test_budget_above_the_domain_is_refused():
    with pytest.raises(TravelUnitError) as error:
        build_travel_unit("big", _draft("2000000000", 1), REFERENCE)
    assert error.value.reason == "budget_out_of_range"


def test_total_budget_above_the_domain_is_refused():
    with pytest.raises(TravelUnitError) as error:
        build_travel_unit("total", _draft("999999999.99", 20), REFERENCE)
    assert error.value.reason == "budget_total_out_of_range"


def test_total_budget_is_exact_under_a_reduced_global_decimal_context():
    draft = _draft("123456.78", 7)
    with localcontext() as context:
        context.prec = 5  # TravelerProfile.total_budget would give 8.6420E+5 here
        unit = build_travel_unit("context", draft, REFERENCE)
        assert unit.budget_total_cents == 86_419_746
    assert unit.budget_total_cents == 86_419_746


# --- fingerprint ---------------------------------------------------------------------


def test_fingerprint_ignores_identifiers_order_and_decimal_spelling():
    first = _draft("700", 4, [_group("adults", 2, "900"), _group("teens", 2, "500")])
    second = _draft("700.00", 4, [_group("x-teens", 2, "500.00"), _group("y-adults", 2, "900")])
    unit_a = build_travel_unit("request-a", first, REFERENCE)
    unit_b = build_travel_unit("request-b", second, REFERENCE)
    assert unit_a.fingerprint == unit_b.fingerprint


def test_implicit_and_explicit_single_group_share_a_fingerprint():
    implicit = build_travel_unit("i", _draft("500", 2), REFERENCE)
    explicit = build_travel_unit("e", _draft("500", 2, [_group("shared", 2)]), REFERENCE)
    assert implicit.fingerprint == explicit.fingerprint


@pytest.mark.parametrize(
    "changed",
    [
        _draft("700", 3),
        _draft("701", 2),
        _draft("700", 2, departure_after=date(2027, 3, 1)),
        _draft("700", 2, arrival_before=date(2027, 3, 1)),
        _draft("700", 2, direct_flight="required"),
        _draft("700", 2, excluded_suppliers=["SkyWays"]),
        _draft("700", 2, destination="Rome"),
    ],
)
def test_fingerprint_changes_with_any_negotiation_content(changed):
    base = build_travel_unit("base", _draft("700", 2), REFERENCE)
    assert build_travel_unit("other", changed, REFERENCE).fingerprint != base.fingerprint


def test_fingerprint_is_case_insensitive_for_exclusions():
    upper = build_travel_unit("u", _draft("700", 2, excluded_suppliers=["SkyWays"]), REFERENCE)
    lower = build_travel_unit("l", _draft("700", 2, excluded_suppliers=["skyways"]), REFERENCE)
    assert upper.fingerprint == lower.fingerprint
    assert upper.fingerprint == unit_fingerprint(upper.destination_key, upper.profiles)


def test_original_draft_is_not_modified():
    draft = _draft("333.335", 3, [_group("inherits", 2), _group("own", 1, "400")])
    before = draft.model_dump(mode="json")
    build_travel_unit("r3", draft, REFERENCE)
    assert draft.model_dump(mode="json") == before


# --- input types ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "request_id,draft,reference,error",
    [
        (123, _draft(), REFERENCE, TypeError),
        ("request", {"destination": "Tokyo"}, REFERENCE, TypeError),
        ("request", _draft(), datetime(2026, 11, 19), TypeError),
        ("request", _draft(), "2026-11-19", TypeError),
    ],
)
def test_builder_validates_input_types(request_id, draft, reference, error):
    with pytest.raises(error):
        build_travel_unit(request_id, draft, reference)


@pytest.mark.parametrize("request_id", ["", "   ", "x" * 121])
def test_builder_refuses_blank_or_oversized_request_ids(request_id):
    with pytest.raises(TravelUnitError) as error:
        build_travel_unit(request_id, _draft(), REFERENCE)
    assert error.value.reason == "invalid_request_id"


# --- deep immutability and direct construction invariants ----------------------------


def test_unit_and_contained_profiles_are_deeply_immutable():
    unit = build_travel_unit("frozen", _draft("700", 2, excluded_suppliers=["SkyWays"]), REFERENCE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        unit.unit_id = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        unit.profiles[0].budget_per_person = Decimal(1)
    assert type(unit.profiles) is tuple
    assert type(unit.profiles[0].excluded_suppliers) is tuple
    assert isinstance(hash(unit), int)  # fails if a list or dict hides inside the unit


def _unit(**overrides):
    fields = {
        "unit_id": "unit",
        "destination_key": "tokyo",
        "profiles": (_profile(),),
        "fingerprint": VALID_FINGERPRINT,
        "rounded_budget_profiles": (),
    }
    fields.update(overrides)
    return TravelUnit(**fields)


def test_direct_construction_accepts_a_valid_unit():
    unit = _unit(rounded_budget_profiles=("a",))
    assert unit.seats == 1
    assert unit.budget_total_cents == 50_000


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"profiles": [_profile()]}, TypeError),
        ({"profiles": ()}, ValueError),
        ({"profiles": ({"profile_id": "a"},)}, TypeError),
        ({"profiles": (_profile(excluded_suppliers=["SkyWays"]),)}, TypeError),
        ({"profiles": (_profile(departure_after=datetime(2027, 1, 1)),)}, TypeError),
        ({"profiles": (_profile(direct_flight="sometimes"),)}, ValueError),
        ({"profiles": (_profile(budget="500.005"),)}, ValueError),
        ({"profiles": (_profile(destination="Rome"),)}, ValueError),
        ({"profiles": (_profile("b"), _profile("a"))}, ValueError),
        ({"profiles": (_profile("a"), _profile("a"))}, ValueError),
        ({"destination_key": "Tokyo"}, ValueError),
        ({"destination_key": None}, TypeError),
        ({"unit_id": " unit "}, ValueError),
        ({"unit_id": 7}, TypeError),
        ({"fingerprint": "ABC"}, ValueError),
        ({"fingerprint": "G" * 64}, ValueError),
        ({"rounded_budget_profiles": ["a"]}, TypeError),
        ({"rounded_budget_profiles": ("missing",)}, ValueError),
        ({"rounded_budget_profiles": ("a", "a")}, ValueError),
    ],
)
def test_direct_construction_rejects_invalid_content(overrides, error):
    with pytest.raises(error):
        _unit(**overrides)


# --- destination keys ----------------------------------------------------------------


def test_destination_key_is_nfc_stripped_casefolded_and_idempotent():
    composed = "  Montréal "
    decomposed = unicodedata.normalize("NFD", "MONTRÉAL")
    key = normalize_destination_key(composed)
    assert key == "montréal"
    assert normalize_destination_key(decomposed) == key
    assert normalize_destination_key(key) == key
    assert normalize_destination_key("Lisbonne") != normalize_destination_key("Lisbon")


@pytest.mark.parametrize("value,error", [("   ", ValueError), (None, TypeError), (3, TypeError)])
def test_destination_key_rejects_blank_or_non_string(value, error):
    with pytest.raises(error):
        normalize_destination_key(value)
