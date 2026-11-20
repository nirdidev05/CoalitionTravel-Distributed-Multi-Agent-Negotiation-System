"""P2 oracle contract, request construction and individual references (P2-bis)."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from coalition_travel.application.lot_admissibility import (
    CapacityModelViolated,
    lot_admissibility,
)
from coalition_travel.application.reference_costs import (
    NegotiationOracleContractError,
    ReferenceAttempt,
    UnitReferenceCost,
    compute_reference_costs,
)
from coalition_travel.domain.negotiation_request import (
    NEGOTIATION_STATUSES,
    NegotiationOutcome,
    NegotiationRequest,
    negotiation_request_for,
)
from coalition_travel.domain.offer import OfferCatalog, OfferQuote, PriceTier
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile

REFERENCE = date(2026, 11, 19)


def _unit(identifier, *, seats=1, budget="100", excluded=(), destination="Tokyo"):
    profile = TravelerProfile(
        identifier, seats, destination, Decimal(budget), excluded_suppliers=excluded
    )
    fingerprint = (format(ord(identifier[0]), "x") + format(len(identifier), "x") + "a" * 64)[:64]
    return TravelUnit(identifier, destination.casefold(), (profile,), fingerprint)


def _offer(identifier, *, capacity=10, destination="Tokyo", supplier="Supplier"):
    return OfferQuote(
        identifier,
        "catalog-v1",
        supplier,
        destination,
        date(2027, 1, 1),
        date(2027, 1, 2),
        True,
        capacity,
        (PriceTier(1, 10_000),),
    )


def _catalog(*offers):
    ordered = tuple(sorted(offers, key=lambda offer: offer.offer_id))
    return OfferCatalog("catalog-v1", "c" * 64, ordered)


def _lot(units, offers):
    return lot_admissibility(units, _catalog(*offers), REFERENCE)


def _outcome(request, status="agreement", amount=5_000, turns=2):
    return NegotiationOutcome(
        request.request_key,
        status,
        amount if status == "agreement" else None,
        turns,
        "fake-oracle-v1",
    )


class FakeOracle:
    """Default: agreement at 5000 cents. responses: offer_id -> amount | callable."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.requests = []

    def negotiate(self, request):
        self.requests.append(request)
        response = self.responses.get(request.offer.offer_id, 5_000)
        if callable(response):
            return response(request)
        return _outcome(request, amount=response)


# --- request construction ----------------------------------------------------------------


def test_factory_sorts_units_and_builds_additive_reservation_and_stable_key():
    first, second = _unit("u1", budget="12"), _unit("u2", budget="34")
    offer = _offer("o1")

    request = negotiation_request_for((second, first), offer)
    repeated = negotiation_request_for((first, second), offer)

    assert request.units == (first, second)
    assert request.seats == 2
    assert request.reservation_cents == first.budget_total_cents + second.budget_total_cents
    assert request.request_key == repeated.request_key
    with pytest.raises(TypeError, match="negotiation_request_for"):
        NegotiationRequest((first,), offer, 1, 1, "key")


def test_individual_reservation_equals_the_unit_budget():
    unit = _unit("u1", seats=2, budget="12.34")
    request = negotiation_request_for((unit,), _offer("o1"))
    assert request.reservation_cents == unit.budget_total_cents == 2468


def test_request_key_is_an_economic_key():
    """Identical negotiation inputs share a key; any economic difference changes it."""
    offer = _offer("o1")
    twin_a = TravelUnit("A", "tokyo", (TravelerProfile("p", 2, "Tokyo", Decimal(300)),), "f" * 64)
    twin_b = TravelUnit("B", "tokyo", (TravelerProfile("p", 2, "Tokyo", Decimal(300)),), "f" * 64)
    other = TravelUnit("C", "tokyo", (TravelerProfile("p", 2, "Tokyo", Decimal(301)),), "e" * 64)

    key_a = negotiation_request_for((twin_a,), offer).request_key
    assert negotiation_request_for((twin_b,), offer).request_key == key_a
    assert negotiation_request_for((other,), offer).request_key != key_a
    assert negotiation_request_for((twin_a,), _offer("o2")).request_key != key_a


def test_factory_refuses_an_offer_to_another_destination_or_above_capacity():
    with pytest.raises(ValueError, match="offer destination"):
        negotiation_request_for((_unit("u1"),), _offer("rome", destination="Rome"))
    with pytest.raises(ValueError, match="capacity"):
        negotiation_request_for((_unit("u1", seats=11),), _offer("o1", capacity=10))


# --- references ----------------------------------------------------------------------------


def test_reference_selects_lowest_agreement_breaks_ties_by_offer_id_and_keeps_attempts():
    unit = _unit("u1")
    offers = (_offer("o2"), _offer("o1"), _offer("o3"))
    oracle = FakeOracle({"o1": 3_000, "o2": 3_000, "o3": 4_000})

    result = compute_reference_costs(_lot((unit,), offers), oracle)

    reference = result.unit_references[0]
    assert (reference.status, reference.offer_id, reference.agreed_total_cents) == (
        "referenced",
        "o1",
        3_000,
    )
    assert [
        (item.offer_id, item.status, item.agreed_total_cents) for item in reference.attempts
    ] == [
        ("o1", "agreement", 3_000),
        ("o2", "agreement", 3_000),
        ("o3", "agreement", 4_000),
    ]
    assert [request.offer.offer_id for request in oracle.requests] == ["o1", "o2", "o3"]
    assert result.reference("u1") == 3_000
    assert result.admissibility_id == _lot((unit,), offers).admissibility_id


def test_no_admissible_offer_is_not_sent_to_the_oracle():
    unit = _unit("u1")
    oracle = FakeOracle()

    result = compute_reference_costs(_lot((unit,), (_offer("o1", destination="Rome"),)), oracle)

    assert result.unit_references[0].status == "no_admissible_offer"
    assert result.unit_references[0].attempts == ()
    assert result.effective_relation.units == ()
    assert result.effective_components == ()
    assert oracle.requests == []
    with pytest.raises(KeyError):
        result.reference("u1")


def test_rejected_and_turn_limit_remain_distinct_and_explain_no_solo_reference():
    units = (_unit("u1"), _unit("u2"))
    offers = (_offer("o1"), _offer("o2"))

    def respond(request):
        if request.units[0].unit_id == "u1":
            status = "rejected" if request.offer.offer_id == "o1" else "turn_limit"
            return _outcome(request, status, turns=13 if status == "rejected" else 30)
        return _outcome(request, amount=4_000)

    result = compute_reference_costs(
        _lot(units, offers), FakeOracle({"o1": respond, "o2": respond})
    )

    u1 = result.unit_references[0]
    assert u1.status == "no_solo_reference"
    assert [(item.offer_id, item.status, item.turns) for item in u1.attempts] == [
        ("o1", "rejected", 13),
        ("o2", "turn_limit", 30),
    ]
    assert [(item.unit_id, item.reason, item.details) for item in result.exclusions] == [
        (
            "u1",
            "no_solo_reference",
            ("o1: rejected (13 turns)", "o2: turn_limit (30 turns)"),
        )
    ]
    assert [unit.unit_id for unit in result.effective_relation.units] == ["u2"]


def test_removing_a_bridge_unit_splits_the_effective_component():
    """u1 only fits o1 (excludes Beta), u3 only fits o2 (excludes Alpha), u2 fits both."""
    units = (
        _unit("u1", excluded=("Beta",)),
        _unit("u2"),
        _unit("u3", excluded=("Alpha",)),
    )
    offers = (_offer("o1", supplier="Alpha"), _offer("o2", supplier="Beta"))
    lot = _lot(units, offers)
    assert [[unit.unit_id for unit in item.units] for item in lot.components] == [
        ["u1", "u2", "u3"]
    ]

    def bridge_fails(request):
        if request.units[0].unit_id == "u2":
            return _outcome(request, "rejected")
        return _outcome(request, amount=4_000)

    result = compute_reference_costs(lot, FakeOracle({"o1": bridge_fails, "o2": bridge_fails}))

    assert sorted(
        ([unit.unit_id for unit in item.units], [offer.offer_id for offer in item.offers])
        for item in result.effective_components
    ) == [(["u1"], ["o1"]), (["u3"], ["o2"])]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda outcome, request: replace(outcome, request_key="wrong"),
        lambda outcome, request: replace(outcome, agreed_total_cents=0),
        lambda outcome, request: replace(outcome, agreed_total_cents=-1),
        lambda outcome, request: replace(outcome, agreed_total_cents=request.reservation_cents + 1),
        lambda outcome, request: replace(outcome, agreed_total_cents=None),
        lambda outcome, request: replace(outcome, agreed_total_cents=True),
        lambda outcome, request: replace(outcome, status="agreed"),
        lambda outcome, request: replace(outcome, status="no_agreement", agreed_total_cents=None),
        lambda outcome, request: replace(outcome, status="unknown"),
        lambda outcome, request: replace(outcome, status="rejected", agreed_total_cents=1),
        lambda outcome, request: replace(outcome, status="turn_limit", agreed_total_cents=1),
        lambda outcome, request: replace(outcome, turns=True),
        lambda outcome, request: replace(outcome, turns=-1),
        lambda outcome, request: replace(outcome, oracle_configuration_id="  "),
        lambda outcome, request: {"status": "agreement"},
    ],
)
def test_invalid_oracle_outcomes_are_rejected(mutate):
    class InvalidOracle:
        def negotiate(self, request):
            return mutate(_outcome(request, turns=0), request)

    with pytest.raises(NegotiationOracleContractError):
        compute_reference_costs(_lot((_unit("u1"),), (_offer("o1"),)), InvalidOracle())


def test_only_the_three_protocol_statuses_are_supported():
    assert frozenset({"agreement", "rejected", "turn_limit"}) == NEGOTIATION_STATUSES


def test_h2_failure_prevents_any_oracle_call():
    oracle = FakeOracle()
    lot = _lot((_unit("u1", seats=7), _unit("u2", seats=7)), (_offer("o1", capacity=10),))

    with pytest.raises(CapacityModelViolated):
        compute_reference_costs(lot, oracle)
    assert oracle.requests == []


def test_oracle_configuration_must_be_stable_across_the_lot():
    class ChangingOracle:
        calls = 0

        def negotiate(self, request):
            self.calls += 1
            return NegotiationOutcome(
                request.request_key, "agreement", 5_000, 0, f"configuration-{self.calls}"
            )

    with pytest.raises(NegotiationOracleContractError, match="configuration changed"):
        compute_reference_costs(
            _lot((_unit("u1"),), (_offer("o1"), _offer("o2"))), ChangingOracle()
        )


# --- result invariants -----------------------------------------------------------------------


def test_reference_results_enforce_their_invariants():
    agreement = ReferenceAttempt("o1", "k", "agreement", 3_000, 2)
    rejected = ReferenceAttempt("o2", "k", "rejected", None, 13)
    with pytest.raises(ValueError):
        ReferenceAttempt("o1", "k", "rejected", 3_000, 2)
    with pytest.raises(ValueError):
        ReferenceAttempt("o1", "k", "agreed", 3_000, 2)
    with pytest.raises(ValueError):
        UnitReferenceCost("u1", "no_admissible_offer", attempts=(rejected,))
    with pytest.raises(ValueError):
        UnitReferenceCost("u1", "no_solo_reference", attempts=(agreement,))
    with pytest.raises(ValueError):
        UnitReferenceCost("u1", "referenced", "o2", 3_000, attempts=(agreement, rejected))
    with pytest.raises(ValueError):
        UnitReferenceCost("u1", "referenced", "o1", 3_000, attempts=(rejected, agreement))
    assert UnitReferenceCost("u1", "referenced", "o1", 3_000, attempts=(agreement, rejected))
