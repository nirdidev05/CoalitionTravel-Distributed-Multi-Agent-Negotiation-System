"""Collective representative for one already-formed P2 negotiation request.

Fidelity to the historical ``CoalitionLeaderAgent.receive_message`` (P3-bis): every
price decision compares the raw float exchanged with the seller against the float
cap ``to_agent_amount(reservation_cents)``, exactly like ``seller_price <= self.budget``.
Converting the seller's price to cents before comparing would accept a price such as
900.081 against a 900.08 cap and change the whole trajectory. Cents are used only to
validate incoming prices and, by the oracle, to convert the final accepted price.
"""

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite

from Agent import Agent
from Message import Message

from coalition_travel.domain.money import from_agent_amount, to_agent_amount
from coalition_travel.domain.negotiation_request import NegotiationRequest


@dataclass(frozen=True)
class MandateLeaderStrategy:
    """Explicit versioned settings adapted from the historical group leader."""

    version: str = "mandate-leader-total-v1"
    initial_offer_fraction: Decimal = Decimal("0.60")
    concession_rate: Decimal = Decimal("0.10")
    max_counteroffers: int = 6

    def __post_init__(self):
        if type(self.version) is not str or not self.version.strip():
            raise ValueError("strategy version must be non-empty")
        for name in ("initial_offer_fraction", "concession_rate"):
            value = getattr(self, name)
            if type(value) is not Decimal or not value.is_finite():
                raise TypeError(f"{name} must be a finite Decimal")
        if not Decimal(0) < self.initial_offer_fraction <= Decimal(1):
            raise ValueError("initial_offer_fraction must be in (0, 1]")
        if not Decimal(0) <= self.concession_rate <= Decimal(1):
            raise ValueError("concession_rate must be in [0, 1]")
        if type(self.max_counteroffers) is not int or self.max_counteroffers < 0:
            raise ValueError("max_counteroffers must be a non-negative integer")

    @property
    def concession_factor(self) -> float:
        """Float multiplier applied to each counter-offer, rounded once from Decimal.

        For the default 10 % it is exactly the historical literal ``1.10``.
        """
        return float(Decimal(1) + self.concession_rate)


class MandateLeader(Agent):
    """Negotiate one total price for all units in a validated P2 request.

    ``members`` are historical BuyerAgent instances retained as profile-level
    representatives. Their budgets do not influence the mandate's cap; only
    ``request.reservation_cents`` is used for price decisions.
    """

    def __init__(
        self,
        name: str,
        request: NegotiationRequest,
        *,
        members: tuple[object, ...] = (),
        strategy: MandateLeaderStrategy = MandateLeaderStrategy(),
    ):
        if type(request) is not NegotiationRequest:
            raise TypeError("request must be a NegotiationRequest")
        if type(members) is not tuple:
            raise TypeError("members must be a tuple")
        if type(strategy) is not MandateLeaderStrategy:
            raise TypeError("strategy must be a MandateLeaderStrategy")
        if type(request.seats) is not int or request.seats <= 0:
            raise ValueError("request.seats must be positive")
        if type(request.reservation_cents) is not int or request.reservation_cents <= 0:
            raise ValueError("request.reservation_cents must be positive")

        super().__init__(name)
        self.request = request
        self.members = members
        self.total_travellers = request.seats
        self.reservation_cents = request.reservation_cents
        # Agent-boundary cap: the double nearest to reservation_cents / 100, i.e. the
        # historical ``self.budget`` float. All price decisions compare against it.
        self.reservation_amount = to_agent_amount(self.reservation_cents)
        # Internal starting point (historical ``budget * 0.6``). It is never sent: the
        # first proposal the seller receives is already one concession above it.
        self.current_offer = self.reservation_amount * float(strategy.initial_offer_fraction)
        self.initial_offer_cents = from_agent_amount(self.current_offer)
        self.bid_count = 0
        self.strategy = strategy
        self._concession_factor = strategy.concession_factor

    def receive_message(self, message: Message) -> Message:
        """Accept within the additive cap, otherwise concede using named settings."""
        if message.type != "PROPOSE":
            raise ValueError("MandateLeader expects a PROPOSE message")
        if type(message.content) is not dict or "price" not in message.content:
            raise ValueError("seller proposal must contain a total price")
        price = message.content["price"]
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not isfinite(price):
            raise TypeError("seller total must be a finite number")
        # Validation only (domain and at least one cent); never used for the decision.
        if from_agent_amount(price) <= 0:
            raise ValueError("seller total must be positive")
        # Historical rule ``seller_price <= self.budget``: raw float against float cap.
        if price <= self.reservation_amount:
            return Message(self, message.sender, "ACCEPT", {"price": price})

        self.bid_count += 1
        if self.bid_count > self.strategy.max_counteroffers:
            return Message(self, message.sender, "REJECT", {"reason": "Max bids reached"})

        self.current_offer = min(
            self.reservation_amount,
            self.current_offer * self._concession_factor,
        )
        return Message(self, message.sender, "PROPOSE", {"price": self.current_offer})

    @property
    def counteroffers_exhausted(self) -> bool:
        """True once the leader has refused the seller more times than its strategy allows."""
        return self.bid_count > self.strategy.max_counteroffers
