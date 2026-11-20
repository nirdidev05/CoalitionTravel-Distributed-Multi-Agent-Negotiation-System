"""P3 seller-term adapter and simulated oracle contracts."""

import hashlib
import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from coalition_travel.domain.negotiation_request import (
    NEGOTIATION_STATUSES,
    NegotiationOutcome,
    negotiation_request_for,
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
from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog
from coalition_travel.infrastructure.negotiation.mandate_leader import (
    MandateLeader,
    MandateLeaderStrategy,
)
from coalition_travel.infrastructure.negotiation.simulated_oracle import (
    AgentExecutionError,
    CatalogMismatchError,
    InvalidNegotiationConfiguration,
    NegotiationJournal,
    NonDeterministicSimulationError,
    SellerTermsMissingError,
    SimulatedNegotiationOracle,
    SimulatedOracleConfig,
    UnknownOfferError,
    _SellerExecutionAdapter,
)
from Message import Message

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/catalog/catalog_v1.json"


def _catalog_and_terms():
    return load_offer_catalog(CATALOG_PATH)


def _unit(unit_id="u1", *, travellers=4, budget_per_person=Decimal(600)):
    profile = TravelerProfile("p1", travellers, "Tokyo", budget_per_person)
    return TravelUnit(
        unit_id,
        "tokyo",
        (profile,),
        hashlib.sha256(unit_id.encode("utf-8")).hexdigest(),
    )


def _oracle(*, reference_date=date(2026, 11, 19), config=None):
    catalog, terms = _catalog_and_terms()
    return SimulatedNegotiationOracle(
        catalog,
        terms,
        config or SimulatedOracleConfig(reference_date=reference_date),
    )


def _custom_oracle(
    *, unit_budget_cents, list_per_seat_cents, floor_per_seat_cents, seats=2, config=None
):
    offer = OfferQuote(
        "custom-offer",
        "custom-v1",
        "CustomSupplier",
        "Tokyo",
        date(2027, 3, 10),
        date(2027, 3, 11),
        True,
        20,
        (PriceTier(1, list_per_seat_cents),),
    )
    sha = "a" * 64
    catalog = OfferCatalog("custom-v1", sha, (offer,))
    terms = SellerTermsBook(
        "custom-v1",
        sha,
        (
            SellerTerms(
                offer.offer_id,
                "custom-v1",
                20,
                (SellerFloorTier(1, floor_per_seat_cents),),
            ),
        ),
    )
    profile = TravelerProfile(
        "custom-profile", seats, "Tokyo", Decimal(unit_budget_cents) / Decimal(100)
    )
    unit = TravelUnit(
        "custom-unit",
        "tokyo",
        (profile,),
        hashlib.sha256(b"custom-unit").hexdigest(),
    )
    request = negotiation_request_for((unit,), offer)
    oracle_config = config or SimulatedOracleConfig(reference_date=date(2026, 11, 19))
    return SimulatedNegotiationOracle(catalog, terms, oracle_config), request


def test_private_adapter_matches_offer_and_uses_total_for_each_price_tier():
    catalog, terms_book = _catalog_and_terms()
    offer = catalog.get("tyo-northstar-20270310")
    request = negotiation_request_for((_unit(),), offer)

    resolved = _SellerExecutionAdapter(catalog, terms_book).resolve(request)

    assert resolved.quantity_seats == request.seats == 4
    assert resolved.price_tier.min_seats == resolved.floor_tier.min_seats == 3
    assert resolved.price_tier.list_per_seat == 52_000
    assert resolved.floor_tier.floor_per_seat == 37_000
    assert resolved.public_list_total_cents == 208_000
    assert resolved.private_floor_total_cents == 148_000
    assert resolved.public_list_total_cents == resolved.price_tier.list_per_seat * request.seats
    assert resolved.private_floor_total_cents == resolved.floor_tier.floor_per_seat * request.seats


def test_private_adapter_rejects_a_terms_book_missing_a_catalogue_entry():
    catalog, terms_book = _catalog_and_terms()
    incomplete = SellerTermsBook(
        terms_book.version,
        terms_book.sha256,
        terms_book.terms[:-1],
    )

    with pytest.raises(SellerTermsMissingError, match="missing"):
        _SellerExecutionAdapter(catalog, incomplete)


def test_private_adapter_rejects_catalogue_hash_or_version_mismatch():
    catalog, terms_book = _catalog_and_terms()
    wrong_provenance = SellerTermsBook(
        terms_book.version,
        "0" * 64,
        terms_book.terms,
    )

    with pytest.raises(CatalogMismatchError, match="provenance"):
        _SellerExecutionAdapter(catalog, wrong_provenance)


def test_adapter_rejects_a_request_offer_that_differs_from_catalogue_entry():
    catalog, terms_book = _catalog_and_terms()
    unit = _unit()
    original = catalog.get("tyo-northstar-20270310")
    from dataclasses import replace

    altered = replace(original, supplier_id="OtherSupplier")
    request = negotiation_request_for((unit,), altered)

    with pytest.raises(CatalogMismatchError, match="differs"):
        _SellerExecutionAdapter(catalog, terms_book).resolve(request)


def test_mandate_leader_uses_additive_total_reservation_not_member_budgets():
    catalog, _ = _catalog_and_terms()
    offer = catalog.get("tyo-northstar-20270310")
    unit_a = _unit("u1", travellers=2, budget_per_person=Decimal(500))
    unit_b = _unit("u2", travellers=2, budget_per_person=Decimal(450))
    request = negotiation_request_for((unit_a, unit_b), offer)
    seller = object()
    leader = MandateLeader("Mandate", request)

    accepted = leader.receive_message(Message(seller, leader, "PROPOSE", {"price": 1900.0}))

    assert request.seats == leader.total_travellers == 4
    assert request.reservation_cents == leader.reservation_cents == 190_000
    assert accepted.type == "ACCEPT"
    assert accepted.content["price"] == 1900.0


def test_mandate_leader_concedes_by_configured_total_rate_and_rejects_after_limit():
    catalog, _ = _catalog_and_terms()
    request = negotiation_request_for((_unit(),), catalog.get("tyo-northstar-20270310"))
    leader = MandateLeader("Mandate", request)
    seller = object()

    first = leader.receive_message(Message(seller, leader, "PROPOSE", {"price": 5000.0}))
    assert first.type == "PROPOSE"
    assert first.content["price"] == pytest.approx(0.60 * request.reservation_cents / 100 * 1.10)
    for _ in range(6):
        response = leader.receive_message(Message(seller, leader, "PROPOSE", {"price": 5000.0}))
    assert response.type == "REJECT"


def test_mandate_leader_has_no_seller_floor_parameter_or_field():
    catalog, _ = _catalog_and_terms()
    request = negotiation_request_for((_unit(),), catalog.get("tyo-northstar-20270310"))
    leader = MandateLeader("x", request)

    assert not any(
        "floor" in name.casefold() for name in inspect.signature(MandateLeader).parameters
    )
    assert not any("floor" in name.casefold() for name in vars(leader))


def test_single_request_returns_exact_p2_outcome_and_suppresses_legacy_console(capsys):
    catalog, _ = _catalog_and_terms()
    request = negotiation_request_for((_unit(),), catalog.get("tyo-northstar-20270310"))
    oracle = _oracle()

    outcome = oracle.negotiate(request)

    assert type(outcome) is NegotiationOutcome
    assert outcome.status in NEGOTIATION_STATUSES
    assert outcome.request_key == request.request_key
    assert type(outcome.turns) is int and outcome.turns >= 0
    assert outcome.oracle_configuration_id == oracle.oracle_configuration_id
    if outcome.status == "agreement":
        assert type(outcome.agreed_total_cents) is int
        assert 0 < outcome.agreed_total_cents <= request.reservation_cents
    else:
        assert outcome.agreed_total_cents is None
    assert capsys.readouterr().out == ""


def test_single_traveler_request_uses_one_seat_and_one_profile_budget():
    catalog, _ = _catalog_and_terms()
    request = negotiation_request_for(
        (_unit("solo", travellers=1, budget_per_person=Decimal(600)),),
        catalog.get("tyo-northstar-20270310"),
    )

    result = _oracle().negotiate_detailed(request)

    assert request.seats == 1
    assert request.reservation_cents == 60_000
    assert result.journal.initial_seller_total_cents == 56_000
    assert result.outcome.status == "agreement"


def test_public_catalogue_list_total_is_the_seller_initial_quote_and_journal_is_expurgated():
    catalog, _ = _catalog_and_terms()
    offer = catalog.get("tyo-northstar-20270310")
    request = negotiation_request_for((_unit(),), offer)
    oracle = _oracle()

    result = oracle.negotiate_detailed(request)

    assert type(result.journal) is NegotiationJournal
    assert result.journal.initial_seller_total_cents == offer.list_total(request.seats)
    assert result.journal.selected_price_tier_min_seats == 3
    assert result.journal.quantity_seats == 4
    assert result.journal.router_iterations == result.outcome.turns
    assert len(result.journal.events) == result.outcome.turns
    assert result.journal.run_id != result.journal.oracle_configuration_id
    assert not any("floor" in name.casefold() for name in result.journal.__dataclass_fields__)
    assert "37000" not in repr(result.journal)


def test_collective_reservation_and_single_unit_reservation_use_same_total_economics():
    catalog, _ = _catalog_and_terms()
    offer = catalog.get("tyo-northstar-20270310")
    unit_a = _unit("u-a", travellers=2, budget_per_person=Decimal(500))
    unit_b = _unit("u-b", travellers=2, budget_per_person=Decimal(450))
    collective = negotiation_request_for((unit_a, unit_b), offer)
    single = negotiation_request_for(
        (_unit("u-single", travellers=4, budget_per_person=Decimal(475)),), offer
    )
    oracle = _oracle()

    collective_result = oracle.negotiate_detailed(collective)
    single_result = oracle.negotiate_detailed(single)

    assert collective.seats == single.seats == 4
    assert collective.units == (unit_a, unit_b)
    assert collective.reservation_cents == single.reservation_cents == 190_000
    assert collective_result.journal.initial_seller_total_cents == 208_000
    assert collective_result.journal.initial_leader_total_cents == 114_000
    assert collective_result.journal.initial_seller_total_cents == 52_000 * 4
    assert collective_result.journal.agreed_total_cents == single_result.journal.agreed_total_cents
    assert collective_result.outcome.status == single_result.outcome.status == "agreement"


def test_multiple_profiles_inside_one_unit_keep_their_seats_and_additive_budgets():
    catalog, _ = _catalog_and_terms()
    offer = catalog.get("tyo-northstar-20270310")
    profiles = (
        TravelerProfile("p-a", 1, "Tokyo", Decimal(500)),
        TravelerProfile("p-b", 3, "Tokyo", Decimal(450)),
    )
    unit = TravelUnit(
        "one-unit",
        "tokyo",
        profiles,
        hashlib.sha256(b"one-unit").hexdigest(),
    )
    request = negotiation_request_for((unit,), offer)
    result = _oracle().negotiate_detailed(request)

    assert len(request.units) == 1
    assert request.seats == 4
    assert request.reservation_cents == 185_000
    assert result.journal.quantity_seats == 4
    assert result.journal.initial_seller_total_cents == 208_000


def test_public_list_total_equal_to_reservation_can_be_accepted_at_reservation():
    oracle, request = _custom_oracle(
        unit_budget_cents=10_000,
        list_per_seat_cents=10_000,
        floor_per_seat_cents=10_000,
        seats=2,
    )

    outcome = oracle.negotiate(request)

    assert outcome.status == "agreement"
    assert outcome.agreed_total_cents == request.reservation_cents == 20_000


def test_floor_above_reservation_ends_as_explicit_rejection_not_turn_limit():
    oracle, request = _custom_oracle(
        unit_budget_cents=10_000,
        list_per_seat_cents=20_000,
        floor_per_seat_cents=15_000,
        seats=2,
    )

    outcome = oracle.negotiate(request)

    assert outcome.status == "rejected"
    assert outcome.agreed_total_cents is None


def test_router_iteration_limit_is_reported_without_claiming_full_rounds():
    config = SimulatedOracleConfig(reference_date=date(2026, 11, 19), max_router_iterations=1)
    oracle, request = _custom_oracle(
        unit_budget_cents=50_000,
        list_per_seat_cents=20_000,
        floor_per_seat_cents=10_000,
        seats=2,
        config=config,
    )

    result = oracle.negotiate_detailed(request)

    assert result.outcome.status == "turn_limit"
    assert result.journal.terminal_reason == "router_iteration_limit"
    assert result.outcome.turns == result.journal.router_iterations == 1
    assert len(result.journal.events) == 1
    assert result.outcome.agreed_total_cents is None


def test_oracle_rejects_unknown_offer_before_running_agents():
    catalog, terms = _catalog_and_terms()
    unknown = OfferQuote(
        "missing-offer",
        "catalog-v1",
        "Supplier",
        "Tokyo",
        date(2027, 3, 10),
        date(2027, 3, 11),
        True,
        20,
        (PriceTier(1, 10_000),),
    )
    request = negotiation_request_for((_unit(),), unknown)
    oracle = SimulatedNegotiationOracle(catalog, terms, SimulatedOracleConfig(date(2026, 11, 19)))

    with pytest.raises(UnknownOfferError):
        oracle.negotiate(request)


@pytest.mark.parametrize("field,invalid", [("seats", True), ("reservation_cents", True)])
def test_oracle_rejects_corrupted_request_scalar_contract(field, invalid):
    catalog, terms = _catalog_and_terms()
    request = negotiation_request_for((_unit(),), catalog.get("tyo-northstar-20270310"))
    object.__setattr__(request, field, invalid)
    oracle = SimulatedNegotiationOracle(catalog, terms, SimulatedOracleConfig(date(2026, 11, 19)))

    from coalition_travel.infrastructure.negotiation.simulated_oracle import (
        InvalidNegotiationRequest,
    )

    with pytest.raises(InvalidNegotiationRequest):
        oracle.negotiate(request)


def test_request_factory_rejects_quantity_above_the_offer_capacity():
    _oracle_instance, request = _custom_oracle(
        unit_budget_cents=10_000,
        list_per_seat_cents=20_000,
        floor_per_seat_cents=10_000,
        seats=2,
    )
    unit = TravelUnit(
        "too-many-seats",
        "tokyo",
        (TravelerProfile("p", 21, "Tokyo", Decimal(10_000)),),
        hashlib.sha256(b"too-many-seats").hexdigest(),
    )

    with pytest.raises(ValueError, match="capacity"):
        negotiation_request_for((unit,), request.offer)


def test_oracle_rejects_reservation_outside_the_supported_money_domain():
    catalog, terms = _catalog_and_terms()
    offer = catalog.get("tyo-northstar-20270310")
    units = tuple(
        TravelUnit(
            f"u{index}",
            "tokyo",
            (TravelerProfile(f"p{index}", 1, "Tokyo", Decimal(1000000000)),),
            hashlib.sha256(f"u{index}".encode()).hexdigest(),
        )
        for index in (1, 2)
    )
    request = negotiation_request_for(units, offer)
    oracle = SimulatedNegotiationOracle(catalog, terms, SimulatedOracleConfig(date(2026, 11, 19)))

    from coalition_travel.infrastructure.negotiation.simulated_oracle import (
        InvalidNegotiationRequest,
    )

    with pytest.raises(InvalidNegotiationRequest, match="reservation"):
        oracle.negotiate(request)


def test_agent_failure_is_not_converted_to_a_negotiation_outcome(monkeypatch):
    from SellerAgent import SellerAgent

    catalog, _ = _catalog_and_terms()
    request = negotiation_request_for((_unit(),), catalog.get("tyo-northstar-20270310"))
    oracle = _oracle()

    def fail(self, message):
        raise RuntimeError("technical agent failure")

    monkeypatch.setattr(SellerAgent, "receive_message", fail)
    with pytest.raises(AgentExecutionError, match="historical negotiation agents failed"):
        oracle.negotiate(request)


@pytest.mark.parametrize("accepted_total", [0.0, -1.0, 10_000.0])
def test_invalid_accepted_agent_amount_is_never_returned_as_an_agreement(
    monkeypatch, accepted_total
):
    from SellerAgent import SellerAgent

    catalog, _ = _catalog_and_terms()
    request = negotiation_request_for((_unit(),), catalog.get("tyo-northstar-20270310"))
    oracle = _oracle()

    def invalid_accept(self, message):
        return Message(self, message.sender, "ACCEPT", {"price": accepted_total})

    monkeypatch.setattr(SellerAgent, "receive_message", invalid_accept)
    with pytest.raises(AgentExecutionError):
        oracle.negotiate(request)


def test_oracle_configuration_and_request_order_are_reproducible():
    catalog, _ = _catalog_and_terms()
    offer = catalog.get("tyo-northstar-20270310")
    request_a = negotiation_request_for((_unit("A"),), offer)
    request_b = negotiation_request_for((_unit("B"),), offer)
    oracle = _oracle()
    matching = _oracle()

    first_a = oracle.negotiate_detailed(request_a)
    result_b = oracle.negotiate_detailed(request_b)
    second_a = oracle.negotiate_detailed(request_a)

    assert oracle.oracle_configuration_id == matching.oracle_configuration_id
    assert first_a.outcome == second_a.outcome
    assert first_a.journal.journal_sha256 == second_a.journal.journal_sha256
    assert first_a.journal.run_id == second_a.journal.run_id
    assert result_b.outcome.oracle_configuration_id == first_a.outcome.oracle_configuration_id


def test_configuration_id_changes_when_a_strategy_parameter_changes():

    standard = _oracle()
    changed_config = SimulatedOracleConfig(
        reference_date=date(2026, 11, 19),
        leader_strategy=MandateLeaderStrategy(initial_offer_fraction=Decimal("0.55")),
    )
    changed = _oracle(config=changed_config)
    changed_seller = _oracle(
        config=SimulatedOracleConfig(
            reference_date=date(2026, 11, 19),
            seller_concession_rate=Decimal("0.05"),
        )
    )

    assert standard.oracle_configuration_id != changed.oracle_configuration_id
    assert standard.oracle_configuration_id != changed_seller.oracle_configuration_id


def test_configuration_rejects_invalid_or_unversioned_commercial_parameters():
    with pytest.raises(ValueError, match="seller_concession_rate"):
        SimulatedOracleConfig(reference_date=date(2026, 11, 19), seller_concession_rate=Decimal(1))
    with pytest.raises(ValueError, match="public-list-total-v1"):
        SimulatedOracleConfig(
            reference_date=date(2026, 11, 19),
            seller_initial_price_policy="floor-times-magic-factor",
        )
    with pytest.raises(InvalidNegotiationConfiguration, match="config"):
        catalog, terms = _catalog_and_terms()
        SimulatedNegotiationOracle(catalog, terms, object())


def test_p2_reference_costs_accept_the_real_oracle_without_contract_changes():
    from coalition_travel.application.lot_admissibility import lot_admissibility
    from coalition_travel.application.reference_costs import compute_reference_costs

    catalog, terms = _catalog_and_terms()
    unit = _unit()
    lot = lot_admissibility((unit,), catalog, date(2026, 11, 19))
    oracle = SimulatedNegotiationOracle(
        catalog,
        terms,
        SimulatedOracleConfig(date(2026, 11, 19)),
    )

    result = compute_reference_costs(lot, oracle)

    assert result.oracle_configuration_id == oracle.oracle_configuration_id
    assert result.unit_references[0].status == "referenced"
    assert result.unit_references[0].agreed_total_cents > 0


def test_money_float_boundary_round_trips_values_including_supported_limit():
    from coalition_travel.domain.money import MAX_CENTS, from_agent_amount, to_agent_amount

    for amount in (1, 12, 38, 100, MAX_CENTS):
        assert from_agent_amount(to_agent_amount(amount)) == amount


def test_public_oracle_result_and_journal_have_no_seller_floor_fields():
    import dataclasses

    catalog, _ = _catalog_and_terms()
    request = negotiation_request_for((_unit(),), catalog.get("tyo-northstar-20270310"))
    result = _oracle().negotiate_detailed(request)
    public_objects = (request, result.outcome, result.journal)

    for public_object in public_objects:
        if dataclasses.is_dataclass(public_object):
            assert not any(
                "floor" in field.name.casefold() for field in dataclasses.fields(public_object)
            )
    assert "SellerTerms" not in repr(result.outcome)
    assert "SellerFloorTier" not in repr(result.journal)


def test_non_deterministic_repeated_execution_is_rejected(monkeypatch):
    from dataclasses import replace

    catalog, _ = _catalog_and_terms()
    request = negotiation_request_for((_unit(),), catalog.get("tyo-northstar-20270310"))
    oracle = _oracle()
    original = oracle._execute_once
    count = 0

    def divergent(request, execution):
        nonlocal count
        count += 1
        outcome, journal = original(request, execution)
        if count == 2:
            outcome = replace(outcome, turns=outcome.turns + 1)
        return outcome, journal

    monkeypatch.setattr(oracle, "_execute_once", divergent)
    with pytest.raises(NonDeterministicSimulationError):
        oracle.negotiate_detailed(request)
