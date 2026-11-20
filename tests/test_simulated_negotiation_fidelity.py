"""P3-bis: the simulated oracle reproduces the historical agents' decisions exactly.

Reference = the real historical ``CoalitionLeaderAgent.receive_message`` and
``SellerAgent``, given the same reservation R, seller floor F and initial seller price I
as the oracle (``negotiate_for_group`` sets ``budget``, ``current_offer = budget * 0.6``
and ``bid_count = 0`` the same way). Status, amount, router iterations and the full
message sequence must be equal, including at rounding boundaries where converting a
float to cents before comparing would change the decision.

Also covered: status semantics (``rejected`` <=> F > R under the default strategy, at
most 2 * (6 + 1) router iterations, so ``turn_limit`` is unreachable with 30), the
typed terminal reasons and the journal invariants.
"""

import contextlib
import dataclasses
import hashlib
import io
import random
from datetime import date
from decimal import Decimal

import pytest
from Agent import Agent
from BuyerAgent import BuyerAgent
from coalition_travel.domain.money import from_agent_amount, to_agent_amount
from coalition_travel.domain.negotiation_request import negotiation_request_for
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
from coalition_travel.infrastructure.negotiation import simulated_oracle
from coalition_travel.infrastructure.negotiation.mandate_leader import (
    MandateLeader,
    MandateLeaderStrategy,
)
from coalition_travel.infrastructure.negotiation.simulated_oracle import (
    AgentExecutionError,
    SimulatedNegotiationOracle,
    SimulatedOracleConfig,
    seller_concession_factor,
)
from Leader import CoalitionLeaderAgent
from Message import Message
from Negotiation import run_alternating_negotiation
from SellerAgent import SellerAgent

REFERENCE = date(2026, 11, 19)
SHA = "b" * 64
MAX_ROUTER_ITERATIONS = 30
DEFAULT_ITERATION_BOUND = 2 * (MandateLeaderStrategy().max_counteroffers + 1)


# --------------------------------------------------------------------------- harness


def _price_cents(message):
    content = message.content
    if type(content) is not dict or "price" not in content:
        return None
    return from_agent_amount(content["price"])


def _raw_price(message):
    content = message.content
    if type(content) is not dict or "price" not in content:
        return None
    return content["price"]


def _observer(sequence, price_of):
    def observe(agent, actor):
        original = agent.receive_message

        def observed(message):
            reply = original(message)
            sequence.append((actor, reply.type, price_of(reply)))
            return reply

        agent.receive_message = observed

    return observe


def _historical(reservation_cents, floor_cents, initial_cents, *, raw=False):
    """Run the unmodified historical agents with the oracle's R, F and I.

    With ``raw=True`` the sequence keeps the exact floats exchanged, not cents.
    """
    sequence = []
    observe = _observer(sequence, _raw_price if raw else _price_cents)

    with contextlib.redirect_stdout(io.StringIO()):
        member = BuyerAgent("member", 1.0, REFERENCE, reference_date=REFERENCE)
        leader = CoalitionLeaderAgent("Leader", [member], 0.0)
        # Exactly what negotiate_for_group sets before routing (Leader.py).
        leader.budget = to_agent_amount(reservation_cents)
        leader.current_offer = leader.budget * 0.6
        leader.bid_count = 0
        seller = SellerAgent(
            "Seller",
            min_price=to_agent_amount(floor_cents),
            release_date="01-Dec",
            initial_offer=to_agent_amount(initial_cents),
        )
        observe(leader, "leader")
        observe(seller, "seller")
        terminal, turns = run_alternating_negotiation(
            Message(leader, seller, "CFP", {}), seller, max_turns=MAX_ROUTER_ITERATIONS
        )
    return _summary(terminal, turns, sequence)


def _summary(terminal, turns, sequence):
    if terminal is None:
        return "turn_limit", None, turns, tuple(sequence)
    if terminal.type == "REJECT":
        return "rejected", None, turns, tuple(sequence)
    return "agreement", from_agent_amount(terminal.content["price"]), turns, tuple(sequence)


def _p3_agents_raw(request, floor_cents, initial_cents):
    """Route the P3 agents exactly as the oracle does, keeping the exact floats."""
    sequence = []
    observe = _observer(sequence, _raw_price)
    leader = MandateLeader("MandateLeader", request)
    seller = simulated_oracle._ConfiguredSellerAgent(
        name="Seller",
        min_price=to_agent_amount(floor_cents),
        release_date=date(2027, 3, 10),
        initial_offer=to_agent_amount(initial_cents),
        concession_rate=Decimal("0.10"),
    )
    observe(leader, "leader")
    observe(seller, "seller")
    with contextlib.redirect_stdout(io.StringIO()):
        terminal, turns = run_alternating_negotiation(
            Message(leader, seller, "CFP", {}), seller, max_turns=MAX_ROUTER_ITERATIONS
        )
    return _summary(terminal, turns, sequence)


def _assert_bit_identical_floats(seats, budget_per_person_cents, list_per_seat, floor_per_seat):
    _oracle, request = _oracle_for(
        seats=seats,
        budget_per_person_cents=budget_per_person_cents,
        list_per_seat=list_per_seat,
        floor_per_seat=floor_per_seat,
    )
    floor, initial = floor_per_seat * seats, list_per_seat * seats
    observed = _p3_agents_raw(request, floor, initial)
    assert observed == _historical(request.reservation_cents, floor, initial, raw=True)


def _oracle_for(*, seats, budget_per_person_cents, list_per_seat, floor_per_seat, config=None):
    offer = OfferQuote(
        "fidelity-offer",
        "fidelity-v1",
        "FidelitySupplier",
        "Tokyo",
        date(2027, 3, 10),
        date(2027, 3, 11),
        True,
        20,
        (PriceTier(1, list_per_seat),),
    )
    catalog = OfferCatalog("fidelity-v1", SHA, (offer,))
    terms = SellerTermsBook(
        "fidelity-v1",
        SHA,
        (SellerTerms(offer.offer_id, "fidelity-v1", 20, (SellerFloorTier(1, floor_per_seat),)),),
    )
    profile = TravelerProfile(
        "fidelity-profile", seats, "Tokyo", Decimal(budget_per_person_cents) / Decimal(100)
    )
    unit = TravelUnit(
        "fidelity-unit", "tokyo", (profile,), hashlib.sha256(b"fidelity-unit").hexdigest()
    )
    request = negotiation_request_for((unit,), offer)
    oracle = SimulatedNegotiationOracle(
        catalog, terms, config or SimulatedOracleConfig(reference_date=REFERENCE)
    )
    return oracle, request


def _p3(seats, budget_per_person_cents, list_per_seat, floor_per_seat):
    oracle, request = _oracle_for(
        seats=seats,
        budget_per_person_cents=budget_per_person_cents,
        list_per_seat=list_per_seat,
        floor_per_seat=floor_per_seat,
    )
    result = oracle.negotiate_detailed(request)
    sequence = tuple(
        (event.actor, event.outgoing_type, event.outgoing_total_cents)
        for event in result.journal.events
    )
    outcome = result.outcome
    observed = (outcome.status, outcome.agreed_total_cents, outcome.turns, sequence)
    parameters = (request.reservation_cents, floor_per_seat * seats, list_per_seat * seats)
    return observed, parameters, result


def _assert_same_as_historical(seats, budget_per_person_cents, list_per_seat, floor_per_seat):
    observed, (reservation, floor, initial), result = _p3(
        seats, budget_per_person_cents, list_per_seat, floor_per_seat
    )
    assert observed == _historical(reservation, floor, initial)
    return observed, (reservation, floor, initial), result


# ------------------------------------------------------- fixed deterministic scenarios

# (name, seats, budget per person, list per seat, floor per seat, expected historical)
SCENARIOS = [
    ("one_traveller", 1, 50_000, 56_000, 40_000, ("agreement", 45_360, 6)),
    ("four_travellers", 4, 50_000, 52_000, 37_000, ("agreement", 187_200, 4)),
    ("floor_above_reservation", 1, 35_000, 56_000, 40_000, ("rejected", None, 14)),
    ("list_equals_reservation", 1, 56_000, 56_000, 40_000, ("agreement", 56_000, 2)),
    # Leader offer 0.6 * 1.1 * 2424.24 = 1599.9984 < 1600.00 but rounds to 160000 cents.
    ("seller_rounding_boundary", 1, 242_424, 400_000, 160_000, ("agreement", 176_000, 5)),
    # Seller price 1000.09 * 0.9 = 900.081 > 900.08 but rounds to 90008 cents.
    ("leader_rounding_boundary", 1, 90_008, 100_009, 70_000, ("agreement", 81_007, 6)),
]


@pytest.mark.parametrize(
    "seats,budget,list_per_seat,floor_per_seat,expected",
    [scenario[1:] for scenario in SCENARIOS],
    ids=[scenario[0] for scenario in SCENARIOS],
)
def test_fixed_scenarios_match_historical_agents_exactly(
    seats, budget, list_per_seat, floor_per_seat, expected
):
    observed, _parameters, _result = _assert_same_as_historical(
        seats, budget, list_per_seat, floor_per_seat
    )
    assert observed[:3] == expected
    # Message level: the P3 agents exchange the very same floats as the historical ones.
    _assert_bit_identical_floats(seats, budget, list_per_seat, floor_per_seat)


def test_seller_boundary_scenario_really_sits_on_a_rounding_boundary():
    # The leader's first proposal is below the floor as a float but equal in cents:
    # a cents comparison would accept it, the historical seller counter-offers.
    first_offer = to_agent_amount(242_424) * 0.6 * MandateLeaderStrategy().concession_factor
    assert first_offer < to_agent_amount(160_000)
    assert from_agent_amount(first_offer) == 160_000
    observed, _parameters, _result = _assert_same_as_historical(1, 242_424, 400_000, 160_000)
    assert observed[3][1] == ("leader", "PROPOSE", 160_000)
    assert observed[3][2][:2] == ("seller", "PROPOSE")


def test_leader_boundary_scenario_really_sits_on_a_rounding_boundary():
    seller_price = to_agent_amount(100_009) * seller_concession_factor(Decimal("0.10"))
    assert seller_price > to_agent_amount(90_008)
    assert from_agent_amount(seller_price) == 90_008
    observed, _parameters, _result = _assert_same_as_historical(1, 90_008, 100_009, 70_000)
    assert observed[3][2] == ("seller", "PROPOSE", 90_008)
    assert observed[3][3][:2] == ("leader", "PROPOSE")


# ----------------------------------------------------- generated boundary families


def _leader_boundary_cases(count, seed):
    """Seller price after k concessions lies strictly above the cap but rounds onto it."""
    generator = random.Random(seed)
    factor = seller_concession_factor(Decimal("0.10"))
    cases = []
    while len(cases) < count:
        concessions = generator.randint(1, 5)
        initial = generator.randint(50_000, 5_000_000)
        price = to_agent_amount(initial)
        for _ in range(concessions):
            price *= factor
        reservation = from_agent_amount(price)
        if not price > to_agent_amount(reservation):
            continue
        # Above every leader offer made before (at most 0.6 * 1.1**5 R < 0.97 R).
        floor = reservation * 98 // 100
        cases.append((reservation, floor, initial))
    return cases


def _seller_boundary_cases(count, seed):
    """Leader's j-th proposal lies strictly below the floor but rounds onto it."""
    generator = random.Random(seed)
    strategy = MandateLeaderStrategy()
    cases = []
    while len(cases) < count:
        proposals = generator.randint(1, 5)
        reservation = generator.randint(50_000, 5_000_000)
        cap = to_agent_amount(reservation)
        offer = cap * float(strategy.initial_offer_fraction)
        for _ in range(proposals):
            offer = min(cap, offer * strategy.concession_factor)
        floor = from_agent_amount(offer)
        if not offer < to_agent_amount(floor):
            continue
        # Seller prices stay above the cap until the boundary proposal is received.
        initial = int(reservation * 1.5 / 0.9 ** (proposals - 1)) + 1
        cases.append((reservation, floor, initial))
    return cases


@pytest.mark.parametrize(
    "family,seed",
    [(_leader_boundary_cases, 11), (_seller_boundary_cases, 12)],
    ids=["leader_boundary", "seller_boundary"],
)
def test_generated_rounding_boundaries_match_historical_agents(family, seed):
    for reservation, floor, initial in family(60, seed):
        # One seat, so R, F and I are the per-seat values.
        _assert_same_as_historical(1, reservation, initial, floor)
        _assert_bit_identical_floats(1, reservation, initial, floor)


def test_seeded_random_scenarios_match_historical_agents():
    generator = random.Random(20261119)
    statuses = set()
    for _ in range(300):
        seats = generator.randint(1, 6)
        list_per_seat = generator.randint(20_000, 80_000)
        floor_per_seat = generator.randint(list_per_seat // 2, list_per_seat)
        budget = generator.randint(floor_per_seat * 8 // 10, list_per_seat * 12 // 10)
        observed, _parameters, _result = _assert_same_as_historical(
            seats, budget, list_per_seat, floor_per_seat
        )
        _assert_bit_identical_floats(seats, budget, list_per_seat, floor_per_seat)
        statuses.add(observed[0])
    assert statuses == {"agreement", "rejected"}


def test_seller_accept_returns_the_raw_buyer_float_like_the_historical_seller():
    with contextlib.redirect_stdout(io.StringIO()):
        configured = simulated_oracle._ConfiguredSellerAgent(
            name="S",
            min_price=1600.0,
            release_date=date(2027, 3, 10),
            initial_offer=4000.0,
            concession_rate=Decimal("0.10"),
        )
        historical = SellerAgent("S", min_price=1600.0, release_date="x", initial_offer=4000.0)
        buyer = Agent("Buyer")
        for price in (1600.004, 1759.9976000000001, 1599.9984, 1600.0):
            ours = configured.receive_message(
                Message(buyer, configured, "PROPOSE", {"price": price})
            )
            theirs = historical.receive_message(
                Message(buyer, historical, "PROPOSE", {"price": price})
            )
            assert (ours.type, ours.content) == (theirs.type, theirs.content)


# ------------------------------------------------------------- status semantics


def test_concession_factors_are_exactly_the_historical_literals():
    strategy = MandateLeaderStrategy()
    assert strategy.concession_factor == 1.10
    assert seller_concession_factor(Decimal("0.10")) == 0.90
    assert float(strategy.initial_offer_fraction) == 0.6
    # Six counter-offers reach the cap: 0.6 * 1.1**6 >= 1, hence the ZOPA property.
    assert 0.6 * 1.1**6 >= 1


def test_default_strategy_rejects_exactly_when_floor_exceeds_reservation():
    generator = random.Random(7)
    cases = [(1, 40_000, 56_000, 40_000), (1, 39_999, 56_000, 40_000)]  # F = R, F = R + 1
    for _ in range(200):
        seats = generator.randint(1, 6)
        list_per_seat = generator.randint(20_000, 80_000)
        floor_per_seat = generator.randint(list_per_seat // 2, list_per_seat)
        budget = generator.randint(floor_per_seat * 8 // 10, list_per_seat * 12 // 10)
        cases.append((seats, budget, list_per_seat, floor_per_seat))
    for seats, budget, list_per_seat, floor_per_seat in cases:
        observed, (reservation, floor, _initial), result = _p3(
            seats, budget, list_per_seat, floor_per_seat
        )
        status, agreed, turns, _sequence = observed
        assert status == ("rejected" if floor > reservation else "agreement")
        assert turns <= DEFAULT_ITERATION_BOUND < MAX_ROUTER_ITERATIONS
        if status == "agreement":
            assert floor <= agreed <= reservation
            assert result.journal.terminal_reason is None
        else:
            assert result.journal.terminal_reason == "leader_counteroffers_exhausted"


def test_floor_above_reservation_is_leader_exhaustion_after_fourteen_iterations():
    observed, _parameters, result = _p3(1, 35_000, 56_000, 40_000)
    assert observed[0] == "rejected"
    assert observed[2] == DEFAULT_ITERATION_BOUND == 14
    assert result.journal.terminal_reason == "leader_counteroffers_exhausted"
    assert result.journal.events[-1].actor == "leader"
    assert result.journal.events[-1].outgoing_type == "REJECT"


def test_initial_leader_amount_is_internal_and_first_proposal_is_one_concession_higher():
    _observed, (reservation, _floor, _initial), result = _p3(1, 50_000, 56_000, 40_000)
    journal = result.journal
    assert journal.initial_leader_total_cents == 30_000  # 0.6 R, never sent
    first_leader = next(event for event in journal.events if event.actor == "leader")
    assert first_leader.outgoing_total_cents == from_agent_amount(
        to_agent_amount(reservation) * 0.6 * 1.10
    )
    assert first_leader.outgoing_total_cents != journal.initial_leader_total_cents


def test_router_limit_is_the_only_source_of_turn_limit():
    config = SimulatedOracleConfig(reference_date=REFERENCE, max_router_iterations=3)
    oracle, request = _oracle_for(
        seats=1,
        budget_per_person_cents=35_000,
        list_per_seat=56_000,
        floor_per_seat=40_000,
        config=config,
    )
    result = oracle.negotiate_detailed(request)
    assert result.outcome.status == "turn_limit"
    assert result.journal.terminal_reason == "router_iteration_limit"
    assert result.outcome.turns == 3


def test_seller_rejection_is_reported_as_seller_rejected(monkeypatch):
    def rejecting(self, message):
        if message.type == "CFP":
            return SellerAgent.receive_message(self, message)
        return Message(self, message.sender, "REJECT", {"reason": "commercial refusal"})

    monkeypatch.setattr(simulated_oracle._ConfiguredSellerAgent, "receive_message", rejecting)
    oracle, request = _oracle_for(
        seats=1, budget_per_person_cents=50_000, list_per_seat=56_000, floor_per_seat=40_000
    )
    result = oracle.negotiate_detailed(request)
    assert result.outcome.status == "rejected"
    assert result.journal.terminal_reason == "seller_rejected"
    assert result.journal.events[-1].actor == "seller"


def test_leader_rejection_before_exhaustion_is_an_agent_error(monkeypatch):
    def premature(self, message):
        return Message(self, message.sender, "REJECT", {"reason": "premature"})

    monkeypatch.setattr(MandateLeader, "receive_message", premature)
    oracle, request = _oracle_for(
        seats=1, budget_per_person_cents=50_000, list_per_seat=56_000, floor_per_seat=40_000
    )
    with pytest.raises(AgentExecutionError, match="before exhausting"):
        oracle.negotiate(request)


def test_rejection_from_an_unknown_sender_is_an_agent_error(monkeypatch):
    def foreign(self, message):
        if message.type == "CFP":
            return SellerAgent.receive_message(self, message)
        return Message(object(), message.sender, "REJECT", {})

    monkeypatch.setattr(simulated_oracle._ConfiguredSellerAgent, "receive_message", foreign)
    oracle, request = _oracle_for(
        seats=1, budget_per_person_cents=50_000, list_per_seat=56_000, floor_per_seat=40_000
    )
    with pytest.raises(AgentExecutionError, match="unknown participant"):
        oracle.negotiate(request)


def test_agreement_below_the_seller_floor_is_an_agent_error(monkeypatch):
    def accept_anything(self, message):
        if message.type == "CFP":
            return SellerAgent.receive_message(self, message)
        return Message(self, message.sender, "ACCEPT", {"price": message.content["price"]})

    monkeypatch.setattr(simulated_oracle._ConfiguredSellerAgent, "receive_message", accept_anything)
    # The leader's first proposal (330.00) is below the 400.00 floor.
    oracle, request = _oracle_for(
        seats=1, budget_per_person_cents=50_000, list_per_seat=56_000, floor_per_seat=40_000
    )
    with pytest.raises(AgentExecutionError, match="below the seller floor"):
        oracle.negotiate(request)


def test_router_stop_without_terminal_before_limit_is_an_agent_error(monkeypatch):
    monkeypatch.setattr(
        simulated_oracle, "run_alternating_negotiation", lambda *args, **kwargs: (None, 0)
    )
    oracle, request = _oracle_for(
        seats=1, budget_per_person_cents=50_000, list_per_seat=56_000, floor_per_seat=40_000
    )
    with pytest.raises(AgentExecutionError, match="before its limit"):
        oracle.negotiate(request)


def test_journal_rejects_inconsistent_status_reason_amount_or_events():
    _observed, _parameters, result = _p3(1, 50_000, 56_000, 40_000)
    journal = result.journal
    assert journal.status == "agreement" and journal.terminal_reason is None
    invalid_changes = [
        {"terminal_reason": "router_iteration_limit"},
        {"status": "rejected", "agreed_total_cents": None},
        {"status": "rejected", "agreed_total_cents": None, "terminal_reason": "participant"},
        {"status": "turn_limit", "agreed_total_cents": None, "terminal_reason": "seller_rejected"},
        {"agreed_total_cents": None},
        {"events": journal.events[:-1]},
        {"status": "unknown"},
    ]
    for changes in invalid_changes:
        with pytest.raises(ValueError):
            dataclasses.replace(journal, **changes)
