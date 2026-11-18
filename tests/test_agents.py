from datetime import date, timedelta

import pytest
from Agent import Agent
from BrokerAgent import BrokerAgent
from BuyerAgent import BuyerAgent
from Leader import _bounded_equal_allocation
from Message import Message
from Negotiation import run_alternating_negotiation
from SellerAgent import SellerAgent


def test_buyer_honors_blacklist_before_price():
    buyer = BuyerAgent("Alice", 500, date(2027, 1, 1), blacklist=["AirFrance"])
    seller = SellerAgent("AirFrance", 400, "01-Dec", initial_offer=450)

    response = buyer.receive_message(Message(seller, buyer, "PROPOSE", {"price": 350}))

    assert response.type == "REJECT"
    assert "blacklisted" in response.content["reason"]


def test_buyer_accepts_offer_within_budget():
    buyer = BuyerAgent("Alice", 500, date(2027, 1, 1))
    seller = SellerAgent("AirFrance", 400, "01-Dec", initial_offer=450)

    response = buyer.receive_message(Message(seller, buyer, "PROPOSE", {"price": 500}))

    assert response.type == "ACCEPT"
    assert response.content["price"] == 500


def test_deadline_pressure_is_reproducible_from_fixed_reference_date():
    reference = date(2026, 11, 18)
    urgent = BuyerAgent("Urgent", 500, reference + timedelta(days=5), reference_date=reference)
    patient = BuyerAgent("Patient", 500, reference + timedelta(days=180), reference_date=reference)

    assert urgent._compute_concession_rate() > patient._compute_concession_rate()


def test_seller_counter_offer_never_falls_below_floor():
    seller = SellerAgent("AirFrance", 400, "01-Dec", initial_offer=560)
    buyer = BuyerAgent("Alice", 500, date(2027, 1, 1))

    response = seller.receive_message(Message(buyer, seller, "PROPOSE", {"price": 100}))

    assert response.type == "PROPOSE"
    assert response.content["price"] >= seller.min_price


def test_broker_forms_one_coalition_and_deduplicates_replayed_subscription():
    broker = BrokerAgent("Broker", negotiate_on_formation=False)
    members = [BuyerAgent(name, 500, date(2027, 1, 1)) for name in ("A", "B", "C")]
    for buyer in members:
        broker.receive_message(Message(buyer, broker, "SUBSCRIBE", {"destination": "Tokyo"}))

    # Re-delivery after formation must not create a second agreement.
    broker.receive_message(Message(members[0], broker, "SUBSCRIBE", {"destination": "Tokyo"}))

    assert len(broker.formation_history) == 1
    assert len(broker.formation_history[0][1]) == 3
    assert broker.subscriptions["Tokyo"] == []


def test_broker_rejects_invalid_subscription_payload():
    broker = BrokerAgent("Broker", negotiate_on_formation=False)
    buyer = BuyerAgent("A", 500, date(2027, 1, 1))

    with pytest.raises(ValueError, match="destination"):
        broker.receive_message(Message(buyer, broker, "SUBSCRIBE", {}))


def test_pending_coalition_can_be_finalized():
    broker = BrokerAgent("Broker", negotiate_on_formation=False)
    members = [BuyerAgent(name, 500, date(2027, 1, 1)) for name in ("A", "B")]
    for buyer in members:
        broker.receive_message(Message(buyer, broker, "SUBSCRIBE", {"destination": "Rome"}))

    formed = broker.finalize_pending("Rome")

    assert formed == members
    assert broker.subscriptions["Rome"] == []
    assert len(broker.formation_history) == 1


def test_equal_allocation_respects_member_caps_and_preserves_total():
    payments = _bounded_equal_allocation(100, {"low": 20, "high": 100})

    assert payments == pytest.approx({"low": 20, "high": 80})
    assert sum(payments.values()) == pytest.approx(100)


def test_negotiation_rejects_message_routed_to_wrong_agent():
    first = Agent("first")
    second = Agent("second")
    message = Message(first, second, "CFP", {})

    with pytest.raises(ValueError, match="receiver"):
        run_alternating_negotiation(message, first)


def test_negotiation_enforces_turn_limit():
    class AlwaysPropose(Agent):
        def receive_message(self, message):
            return Message(self, message.sender, "PROPOSE", {})

    first = AlwaysPropose("first")
    second = AlwaysPropose("second")
    result, turns = run_alternating_negotiation(
        Message(first, second, "CFP", {}), second, max_turns=2
    )

    assert result is None
    assert turns == 2
