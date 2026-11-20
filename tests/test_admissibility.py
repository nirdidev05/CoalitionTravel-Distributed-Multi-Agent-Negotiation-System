"""P2 non-financial, indivisible unit × offer policy tests (P2-bis contracts)."""

import ast
import hashlib
import inspect
import random
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest
from coalition_travel.application.compatibility import evaluate_compatibility
from coalition_travel.domain.admissibility import (
    MANDATORY_RULES,
    RULE_ORDER,
    RULE_REASONS,
    RULE_REGISTRY,
    AdmissibilityNote,
    AdmissibilityPolicy,
    AdmissibilityRuleId,
    AdmissibilityViolation,
    PairAdmissibility,
    evaluate_unit_offer,
)
from coalition_travel.domain.destination import normalize_destination_key
from coalition_travel.domain.offer import OfferQuote, PriceTier
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import CommonOffer, TravelerProfile

REFERENCE = date(2026, 11, 19)
POLICY = AdmissibilityPolicy.NON_FINANCIAL_V1


def _profile(profile_id="p1", *, seats=1, destination="Tokyo", **fields):
    return TravelerProfile(profile_id, seats, destination, Decimal("1.00"), **fields)


def _unit(unit_id="u1", *profiles):
    profiles = profiles or (_profile(),)
    profiles = tuple(sorted(profiles, key=lambda profile: profile.profile_id))
    return TravelUnit(
        unit_id,
        normalize_destination_key(profiles[0].destination),
        profiles,
        hashlib.sha256(unit_id.encode()).hexdigest(),
    )


def _offer(
    offer_id="o1",
    *,
    destination="Tokyo",
    departure=date(2027, 3, 10),
    arrival=date(2027, 3, 12),
    direct=True,
    supplier="Northstar",
    capacity=100,
    list_price=90_000,
):
    return OfferQuote(
        offer_id,
        "catalog-v1",
        supplier,
        destination,
        departure,
        arrival,
        direct,
        capacity,
        (PriceTier(1, list_price),),
    )


# --- rules ---------------------------------------------------------------------------


def test_required_direct_and_expensive_offer_are_admissible_without_financial_rules():
    unit = _unit("u1", _profile(direct_flight="required"))
    result = evaluate_unit_offer(unit, _offer(list_price=99_999), REFERENCE)

    assert result.admissible
    assert result.violations == ()
    assert result.notes == ()
    assert result.policy is POLICY


def test_preferred_direct_flight_produces_a_note_and_never_rejects():
    unit = _unit("u1", _profile(direct_flight="preferred"))

    direct = evaluate_unit_offer(unit, _offer(direct=True), REFERENCE)
    connecting = evaluate_unit_offer(unit, _offer(direct=False), REFERENCE)

    assert direct.admissible and direct.notes == ()
    assert connecting.admissible and connecting.violations == ()
    assert connecting.notes == (AdmissibilityNote("direct_preference_not_met", "p1"),)


def test_pair_result_carries_no_preference_score():
    names = {field.name for field in fields(PairAdmissibility)}
    assert names == {"unit_id", "offer_id", "policy", "admissible", "violations", "notes"}


def test_departure_before_reference_is_rejected_even_without_profile_date():
    unit = _unit()
    before = evaluate_unit_offer(
        unit, _offer(departure=date(2026, 11, 18), arrival=date(2026, 11, 20)), REFERENCE
    )
    same_day = evaluate_unit_offer(
        unit, _offer(departure=REFERENCE, arrival=date(2026, 11, 20)), REFERENCE
    )

    assert [(item.reason, item.profile_id) for item in before.violations] == [
        ("offer_departs_before_reference_date", None)
    ]
    assert before.violations[0].rule is AdmissibilityRuleId.OFFER_NOT_BEFORE_REFERENCE
    assert same_day.admissible


def test_date_window_bounds_are_inclusive_for_departure_and_arrival():
    unit = _unit(
        "u1",
        _profile(departure_after=date(2027, 3, 10), arrival_before=date(2027, 3, 12)),
    )
    boundary = evaluate_unit_offer(unit, _offer(), REFERENCE)
    outside = evaluate_unit_offer(
        unit,
        _offer(departure=date(2027, 3, 9), arrival=date(2027, 3, 13)),
        REFERENCE,
    )

    assert boundary.admissible
    assert [(item.reason, item.profile_id) for item in outside.violations] == [
        ("departure_before_window", "p1"),
        ("arrival_after_window", "p1"),
    ]


def test_destinations_are_renormalized_with_unicode_nfc_at_evaluation():
    unit = _unit("u1", _profile(destination="Café"))
    assert evaluate_unit_offer(unit, _offer(destination="CAFÉ"), REFERENCE).admissible


def test_no_linguistic_alias_lisbonne_is_not_lisbon():
    unit = _unit("u1", _profile(destination="Lisbonne"))
    result = evaluate_unit_offer(unit, _offer(destination="Lisbon"), REFERENCE)
    assert [item.reason for item in result.violations] == ["destination_mismatch"]


def test_destination_mismatch_is_the_only_reported_violation_and_has_no_note():
    unit = _unit(
        "u1",
        _profile(direct_flight="preferred", excluded_suppliers=("Northstar",)),
    )
    result = evaluate_unit_offer(
        unit,
        _offer(destination="Rome", departure=date(2020, 1, 1), direct=False, capacity=1),
        REFERENCE,
    )

    assert [(item.reason, item.profile_id) for item in result.violations] == [
        ("destination_mismatch", None)
    ]
    assert result.notes == ()


def test_supplier_exclusions_use_nfc_strip_and_casefold():
    unit = _unit("u1", _profile(excluded_suppliers=("  SKYWAYS  ",)))
    result = evaluate_unit_offer(unit, _offer(supplier="SkyWays"), REFERENCE)

    assert not result.admissible
    assert [(item.reason, item.profile_id) for item in result.violations] == [
        ("excluded_supplier", "p1")
    ]


def test_supplier_exclusion_is_attributed_to_the_excluding_profile_only():
    unit = _unit(
        "family",
        _profile("adults", seats=2),
        _profile("teens", seats=2, excluded_suppliers=("SkyWays",)),
    )
    result = evaluate_unit_offer(unit, _offer(supplier="skyways"), REFERENCE)

    assert not result.admissible  # the indivisible unit cannot take the offer
    assert [(item.reason, item.profile_id) for item in result.violations] == [
        ("excluded_supplier", "teens")
    ]


def test_all_violations_are_accumulated_in_rule_order_and_profile_order():
    shared = {
        "seats": 1,
        "departure_after": date(2027, 3, 15),
        "arrival_before": date(2027, 3, 11),
        "direct_flight": "required",
    }
    unit = _unit(
        "u1",
        _profile("z-profile", excluded_suppliers=("Northstar",), **shared),
        _profile("a-profile", excluded_suppliers=("northstar",), **shared),
    )
    result = evaluate_unit_offer(
        unit,
        _offer(departure=date(2027, 3, 10), arrival=date(2027, 3, 12), direct=False, capacity=1),
        REFERENCE,
    )

    assert [(item.rule, item.profile_id) for item in result.violations] == [
        (AdmissibilityRuleId.DEPARTURE_WINDOW, "a-profile"),
        (AdmissibilityRuleId.DEPARTURE_WINDOW, "z-profile"),
        (AdmissibilityRuleId.ARRIVAL_WINDOW, "a-profile"),
        (AdmissibilityRuleId.ARRIVAL_WINDOW, "z-profile"),
        (AdmissibilityRuleId.DIRECT_FLIGHT, "a-profile"),
        (AdmissibilityRuleId.DIRECT_FLIGHT, "z-profile"),
        (AdmissibilityRuleId.SUPPLIER_EXCLUSION, "a-profile"),
        (AdmissibilityRuleId.SUPPLIER_EXCLUSION, "z-profile"),
        (AdmissibilityRuleId.UNIT_CAPACITY, None),
    ]
    assert all(item.reason == RULE_REASONS[item.rule] for item in result.violations)


def test_unit_capacity_rule_rejects_an_indivisible_unit_larger_than_the_offer():
    result = evaluate_unit_offer(_unit("u1", _profile(seats=4)), _offer(capacity=3), REFERENCE)

    assert not result.admissible
    assert [(item.rule, item.profile_id) for item in result.violations] == [
        (AdmissibilityRuleId.UNIT_CAPACITY, None)
    ]


def test_family_with_non_overlapping_windows_is_admissible_to_no_offer():
    unit = _unit(
        "family",
        _profile("early", arrival_before=date(2027, 3, 5)),
        _profile("late", departure_after=date(2027, 3, 20)),
    )
    for departure in (date(2027, 3, 1), date(2027, 3, 10), date(2027, 3, 25)):
        offer = _offer(departure=departure, arrival=departure + timedelta(days=1))
        assert not evaluate_unit_offer(unit, offer, REFERENCE).admissible


def test_datetime_reference_is_rejected_explicitly():
    with pytest.raises(TypeError, match="not datetime"):
        evaluate_unit_offer(_unit(), _offer(), datetime(2026, 11, 19))


# --- closed, non-bypassable policy ----------------------------------------------------


def test_policy_registry_is_closed_read_only_and_contains_every_mandatory_rule():
    assert tuple(rule.value for rule in RULE_ORDER) == (
        "destination",
        "offer_not_before_reference",
        "departure_window",
        "arrival_window",
        "direct_flight",
        "supplier_exclusion",
        "unit_capacity",
    )
    assert isinstance(RULE_REGISTRY, MappingProxyType)
    assert RULE_REGISTRY[POLICY] is RULE_ORDER
    for rules in RULE_REGISTRY.values():
        assert MANDATORY_RULES <= set(rules)
    with pytest.raises(TypeError):
        RULE_REGISTRY[POLICY] = ()
    with pytest.raises(ValueError):
        AdmissibilityPolicy("custom")


@pytest.mark.parametrize("policy", ["non_financial_v1", ("destination",), None, 1])
def test_a_policy_cannot_be_given_as_a_string_or_rule_list(policy):
    with pytest.raises(TypeError):
        evaluate_unit_offer(_unit(), _offer(), REFERENCE, policy)


# --- contract invariants of the result types -------------------------------------------


@pytest.mark.parametrize(
    "rule,reason,profile_id",
    [
        (AdmissibilityRuleId.DESTINATION, "excluded_supplier", None),
        (AdmissibilityRuleId.SUPPLIER_EXCLUSION, "excluded_supplier", None),
        (AdmissibilityRuleId.UNIT_CAPACITY, "unit_exceeds_offer_capacity", "p1"),
        (AdmissibilityRuleId.OFFER_NOT_BEFORE_REFERENCE, "offer_before_reference", None),
        ("destination", "destination_mismatch", None),
    ],
)
def test_violations_must_use_the_validated_reason_and_level(rule, reason, profile_id):
    with pytest.raises((TypeError, ValueError)):
        AdmissibilityViolation(rule, reason, profile_id)


def test_pair_results_enforce_admissibility_ordering_and_note_codes():
    capacity = AdmissibilityViolation(
        AdmissibilityRuleId.UNIT_CAPACITY, "unit_exceeds_offer_capacity"
    )
    window = AdmissibilityViolation(
        AdmissibilityRuleId.DEPARTURE_WINDOW, "departure_before_window", "p1"
    )
    with pytest.raises(ValueError, match="exactly when"):
        PairAdmissibility("u1", "o1", POLICY, True, (capacity,))
    with pytest.raises(ValueError, match="exactly when"):
        PairAdmissibility("u1", "o1", POLICY, False, ())
    with pytest.raises(ValueError, match="sorted"):
        PairAdmissibility("u1", "o1", POLICY, False, (capacity, window))
    with pytest.raises(TypeError):
        PairAdmissibility("u1", "o1", "non_financial_v1", False, (capacity,))
    with pytest.raises(ValueError):
        AdmissibilityNote("preference_met", "p1")


# --- T-EQ: same final verdict as the legacy policy on the common domain ---------------


def test_non_financial_v1_matches_legacy_final_verdict_on_the_common_domain():
    """Common domain: >= 2 profiles, complete offer, price neutralized (0.01 EUR against
    budgets of 1.00 EUR), ASCII names, capacity >= seats, offer not before the reference
    date. Only the final verdict is compared: the legacy policy stops at its first reason
    while the new one collects them all."""
    generator = random.Random(20261119)
    suppliers = ("Northstar", "SkyWays", "CloudWing")
    verdicts = {True: 0, False: 0}
    for case in range(2_000):
        departure = REFERENCE + timedelta(days=generator.randint(0, 120))
        arrival = departure + timedelta(days=generator.randint(0, 2))
        offer = _offer(
            f"o{case}",
            departure=departure,
            arrival=arrival,
            direct=generator.choice((True, False)),
            supplier=generator.choice(suppliers),
        )
        profiles = []
        for index in range(generator.randint(2, 4)):
            start = (
                departure + timedelta(days=generator.randint(-4, 3))
                if generator.random() < 0.6
                else None
            )
            end = (
                arrival + timedelta(days=generator.randint(-3, 4))
                if generator.random() < 0.6
                else None
            )
            excluded = tuple(
                name.upper() if generator.random() < 0.5 else name.lower()
                for name in suppliers
                if generator.random() < 0.25
            )
            profiles.append(
                _profile(
                    f"p{index}",
                    seats=generator.randint(1, 3),
                    departure_after=start,
                    arrival_before=end,
                    direct_flight=generator.choice(("required", "preferred", "any")),
                    excluded_suppliers=excluded,
                )
            )
        legacy_offer = CommonOffer(
            destination=offer.destination,
            price_per_person=Decimal("0.01"),
            departure_date=offer.departure_date,
            arrival_date=offer.arrival_date,
            direct=offer.direct,
            supplier=offer.supplier_id,
        )
        legacy = evaluate_compatibility(tuple(profiles), legacy_offer)
        current = evaluate_unit_offer(_unit(f"u{case}", *profiles), offer, REFERENCE)
        assert legacy.status in {"compatible", "incompatible"}, legacy
        assert (legacy.status == "compatible") is current.admissible, (case, legacy, current)
        verdicts[current.admissible] += 1
    assert verdicts[True] > 100 and verdicts[False] > 100, verdicts


# --- seller-floor confidentiality ------------------------------------------------------


def test_p2_modules_do_not_reference_private_seller_floor_api():
    root = Path(__file__).resolve().parents[1] / "Multi-Agent/coalition_travel"
    modules = (
        root / "domain/admissibility.py",
        root / "domain/offer_graph.py",
        root / "domain/negotiation_request.py",
        root / "application/lot_admissibility.py",
        root / "application/reference_costs.py",
    )
    forbidden = {
        "SellerTerms",
        "SellerTermsBook",
        "SellerFloorTier",
        "validate_seller_terms_against_catalog",
        "load_offer_catalog",
        "floor_total",
        "floor_tier_for",
        "floor_tiers",
        "floor_per_seat",
    }
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        referenced |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        modules_imported = {
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert not (forbidden & (referenced | imported)), path
        assert not any("infrastructure.catalog" in name for name in modules_imported | imported)

    from coalition_travel.application.lot_admissibility import (
        CapacityCheck,
        LotAdmissibilityResult,
        UnitExclusion,
        UnmatchedExclusion,
        lot_admissibility,
    )
    from coalition_travel.application.reference_costs import (
        ReferenceAttempt,
        ReferenceCostsResult,
        UnitReferenceCost,
        compute_reference_costs,
    )
    from coalition_travel.domain.negotiation_request import (
        NegotiationOutcome,
        NegotiationRequest,
        negotiation_request_for,
    )
    from coalition_travel.domain.offer import OfferCatalog
    from coalition_travel.domain.offer_graph import AdmissibilityRelation, OfferComponent

    for function in (lot_admissibility, compute_reference_costs, negotiation_request_for):
        assert not any(
            "floor" in parameter.name.casefold()
            for parameter in inspect.signature(function).parameters.values()
        )
    assert inspect.signature(lot_admissibility).parameters["catalog"].annotation is OfferCatalog

    public_types = (
        CapacityCheck,
        LotAdmissibilityResult,
        UnitExclusion,
        UnmatchedExclusion,
        ReferenceAttempt,
        ReferenceCostsResult,
        UnitReferenceCost,
        AdmissibilityViolation,
        AdmissibilityNote,
        PairAdmissibility,
        NegotiationOutcome,
        NegotiationRequest,
        AdmissibilityRelation,
        OfferComponent,
    )
    for public_type in public_types:
        assert is_dataclass(public_type)
        assert not any("floor" in item.name.casefold() for item in fields(public_type))
