"""Simulated P2 oracle and its private seller execution boundary.

Only this infrastructure module reads seller terms. Prices remain integer cents
until the boundary to the historical float-based agents. Execution captures the
legacy agents' process-global stdout, so calls must be made sequentially.

Inside the negotiation both participants decide on the raw floats they exchange,
exactly like the historical agents (P3-bis); the accepted float is converted to cents
once, at the end. Rounding is monotonic and ``from_agent_amount(to_agent_amount(c))
== c``, so every agreement lies between the seller floor and the reservation in cents.

Statuses keep the P2 contract (``agreement``, ``rejected``, ``turn_limit``). The
journal adds a closed ``terminal_reason`` derived from the terminal message's sender:
``leader_counteroffers_exhausted``, ``seller_rejected`` (impossible with the historical
seller, which never emits REJECT) or ``router_iteration_limit``.
"""

import hashlib
import importlib
import io
import json
from collections.abc import Mapping
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from Agent import Agent
from BuyerAgent import BuyerAgent
from Message import Message
from Negotiation import run_alternating_negotiation
from SellerAgent import SellerAgent

from coalition_travel.domain.money import (
    MAX_CENTS,
    cents_from_budget,
    from_agent_amount,
    to_agent_amount,
)
from coalition_travel.domain.negotiation_request import (
    NegotiationOutcome,
    NegotiationRequest,
    negotiation_request_for,
)
from coalition_travel.domain.offer import (
    OfferCatalog,
    OfferQuote,
    PriceTier,
    SellerFloorTier,
    SellerTerms,
    SellerTermsBook,
    validate_seller_terms_against_catalog,
)
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.infrastructure.negotiation.mandate_leader import (
    MandateLeader,
    MandateLeaderStrategy,
)


class NegotiationOracleError(ValueError):
    """Base class for invalid oracle inputs and seller configuration."""


class InvalidNegotiationRequest(NegotiationOracleError):
    """The request is internally inconsistent or not an exact P2 request."""


class UnknownOfferError(InvalidNegotiationRequest):
    """The requested offer identifier is absent from the configured catalogue."""


class SellerTermsMissingError(NegotiationOracleError):
    """The private book does not contain terms for a configured public offer."""


class CatalogMismatchError(NegotiationOracleError):
    """Public offers and private terms do not describe the same catalogue."""


class InvalidNegotiationConfiguration(NegotiationOracleError):
    """The deterministic simulation configuration is invalid."""


class AgentExecutionError(RuntimeError):
    """A historical participant failed while executing a simulated negotiation."""


class NonDeterministicSimulationError(RuntimeError):
    """Two independent executions of the same mandate produced different results."""


TerminalReason = Literal[
    "leader_counteroffers_exhausted",
    "seller_rejected",
    "router_iteration_limit",
]
# Allowed journal reasons for each P2 status; an agreement has no failure reason.
REASONS_BY_STATUS: Mapping[str, frozenset] = MappingProxyType(
    {
        "agreement": frozenset({None}),
        "rejected": frozenset({"leader_counteroffers_exhausted", "seller_rejected"}),
        "turn_limit": frozenset({"router_iteration_limit"}),
    }
)


@dataclass(frozen=True)
class _SellerExecution:
    """Private, per-request values used only while constructing the seller agent."""

    offer: OfferQuote
    terms: SellerTerms
    price_tier: PriceTier
    floor_tier: SellerFloorTier
    quantity_seats: int
    public_list_total_cents: int
    private_floor_total_cents: int


class _SellerExecutionAdapter:
    """Resolve one validated public offer to its matching private seller terms."""

    def __init__(self, catalog: OfferCatalog, terms_book: SellerTermsBook):
        if type(catalog) is not OfferCatalog or type(terms_book) is not SellerTermsBook:
            raise TypeError("catalog and terms_book must be OfferCatalog and SellerTermsBook")
        self._catalog = catalog
        self._terms_book = terms_book

        if (catalog.version, catalog.sha256) != (terms_book.version, terms_book.sha256):
            raise CatalogMismatchError("catalogue and private terms have different provenance")
        offer_ids = {offer.offer_id for offer in catalog.offers}
        term_ids = {terms.offer_id for terms in terms_book.terms}
        missing = offer_ids - term_ids
        if missing:
            raise SellerTermsMissingError("private terms are missing for a catalogue offer")
        if term_ids - offer_ids:
            raise CatalogMismatchError("private terms contain an unknown offer")
        try:
            validate_seller_terms_against_catalog(catalog, terms_book)
        except (TypeError, ValueError) as exc:
            raise CatalogMismatchError("catalogue and private terms are inconsistent") from exc

    @property
    def catalog(self) -> OfferCatalog:
        """Public catalogue provenance; never returns the private terms book."""
        return self._catalog

    def resolve(self, request: NegotiationRequest) -> _SellerExecution:
        if type(request) is not NegotiationRequest:
            raise InvalidNegotiationRequest("request must be an exact NegotiationRequest")
        if (
            type(request.units) is not tuple
            or not request.units
            or any(type(unit) is not TravelUnit for unit in request.units)
        ):
            raise InvalidNegotiationRequest("request units must be a non-empty TravelUnit tuple")
        if type(request.seats) is not int or request.seats <= 0:
            raise InvalidNegotiationRequest("request.seats must be a positive integer")
        if (
            type(request.reservation_cents) is not int
            or not 0 < request.reservation_cents <= MAX_CENTS
        ):
            raise InvalidNegotiationRequest("request reservation must be positive integer cents")
        if type(request.request_key) is not str:
            raise InvalidNegotiationRequest("request_key must be a string")
        if type(request.offer) is not OfferQuote:
            raise InvalidNegotiationRequest("request.offer must be an exact OfferQuote")
        try:
            offer = self._catalog.get(request.offer.offer_id)
        except (AttributeError, KeyError, TypeError) as exc:
            raise UnknownOfferError("requested offer is not in the configured catalogue") from exc
        if request.offer != offer:
            raise CatalogMismatchError("request offer differs from its catalogue entry")

        try:
            rebuilt = negotiation_request_for(request.units, offer)
        except (TypeError, ValueError) as exc:
            raise InvalidNegotiationRequest("request units or offer are inconsistent") from exc
        if (
            request.units != rebuilt.units
            or request.seats != rebuilt.seats
            or request.reservation_cents != rebuilt.reservation_cents
            or request.request_key != rebuilt.request_key
        ):
            raise InvalidNegotiationRequest("request totals or request_key do not match its units")

        try:
            terms = self._terms_book.get(offer.offer_id)
        except KeyError as exc:
            raise SellerTermsMissingError(
                "private terms are missing for the requested offer"
            ) from exc
        if terms.catalog_version != offer.catalog_version:
            raise CatalogMismatchError("offer and private terms have different catalogue versions")
        if request.seats <= 0 or request.seats > offer.capacity_seats:
            raise InvalidNegotiationRequest("request quantity is outside offer capacity")

        price_tier = offer.tier_for(request.seats)
        floor_tier = terms.floor_tier_for(request.seats)
        if price_tier.min_seats != floor_tier.min_seats:
            raise CatalogMismatchError("selected public and private tiers do not match")
        public_total = offer.list_total(request.seats)
        private_floor_total = terms.floor_total(request.seats)
        if private_floor_total > public_total:
            raise CatalogMismatchError("private seller terms exceed the public list total")
        return _SellerExecution(
            offer=offer,
            terms=terms,
            price_tier=price_tier,
            floor_tier=floor_tier,
            quantity_seats=request.seats,
            public_list_total_cents=public_total,
            private_floor_total_cents=private_floor_total,
        )


@dataclass(frozen=True)
class SimulatedOracleConfig:
    """Versioned controls for the historical alternating-offers simulation."""

    reference_date: date
    max_router_iterations: int = 30
    leader_strategy: MandateLeaderStrategy = field(default_factory=MandateLeaderStrategy)
    protocol_version: str = "legacy-alternating-offers-v1"
    seller_strategy_version: str = "legacy-seller-agent-configurable-concession-v1"
    seller_concession_rate: Decimal = Decimal("0.10")
    seller_initial_price_policy: str = "public-list-total-v1"
    verify_reproducibility: bool = True

    def __post_init__(self):
        if isinstance(self.reference_date, datetime) or type(self.reference_date) is not date:
            raise TypeError("reference_date must be a datetime.date")
        if type(self.max_router_iterations) is not int or self.max_router_iterations < 1:
            raise ValueError("max_router_iterations must be a positive integer")
        if type(self.leader_strategy) is not MandateLeaderStrategy:
            raise TypeError("leader_strategy must be a MandateLeaderStrategy")
        if (
            type(self.seller_concession_rate) is not Decimal
            or not self.seller_concession_rate.is_finite()
        ):
            raise TypeError("seller_concession_rate must be a finite Decimal")
        if not Decimal(0) <= self.seller_concession_rate < Decimal(1):
            raise ValueError("seller_concession_rate must be in [0, 1)")
        for name in ("protocol_version", "seller_strategy_version"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.seller_initial_price_policy != "public-list-total-v1":
            raise ValueError("only the public-list-total-v1 initial price policy is supported")
        if type(self.verify_reproducibility) is not bool:
            raise TypeError("verify_reproducibility must be a bool")


@dataclass(frozen=True)
class NegotiationEvent:
    """One sanitized agent invocation; all optional prices are total cents."""

    call_index: int
    actor: Literal["seller", "leader"]
    incoming_type: str
    incoming_total_cents: int | None
    outgoing_type: str
    outgoing_total_cents: int | None


@dataclass(frozen=True)
class NegotiationJournal:
    """Public audit journal. It contains no private seller terms or floor values."""

    request_key: str
    oracle_configuration_id: str
    run_id: str
    offer_id: str
    quantity_seats: int
    selected_price_tier_min_seats: int
    initial_leader_total_cents: int
    initial_seller_total_cents: int
    events: tuple[NegotiationEvent, ...]
    status: Literal["agreement", "rejected", "turn_limit"]
    terminal_reason: TerminalReason | None
    router_iterations: int
    agreed_total_cents: int | None
    journal_sha256: str

    def __post_init__(self):
        allowed = REASONS_BY_STATUS.get(self.status)
        if allowed is None:
            raise ValueError(f"unsupported negotiation status {self.status!r}")
        if self.terminal_reason not in allowed:
            raise ValueError(
                f"terminal_reason {self.terminal_reason!r} is not valid for status {self.status!r}"
            )
        if (self.status == "agreement") != (self.agreed_total_cents is not None):
            raise ValueError("an amount is present exactly for an agreement")
        if len(self.events) != self.router_iterations:
            raise ValueError("one journal event is recorded per router iteration")


@dataclass(frozen=True)
class NegotiationSimulation:
    """Detailed result available to auditors; ``negotiate`` still returns P2 only."""

    outcome: NegotiationOutcome
    journal: NegotiationJournal


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _agent_source_hashes() -> dict[str, str]:
    """Hash every historical and P3 implementation that affects an execution."""
    modules = (
        "Agent",
        "BuyerAgent",
        "Message",
        "Negotiation",
        "SellerAgent",
        "coalition_travel.domain.money",
        "coalition_travel.domain.negotiation_request",
        "coalition_travel.domain.offer",
        "coalition_travel.domain.travel_unit",
        "coalition_travel.infrastructure.catalog.json_catalog",
        "coalition_travel.infrastructure.negotiation.mandate_leader",
    )
    hashes = {}
    for module_name in modules:
        module = importlib.import_module(module_name)
        source = getattr(module, "__file__", None)
        if source is None:
            raise InvalidNegotiationConfiguration(f"cannot determine source for {module_name}")
        path = Path(source)
        hashes[module_name] = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes["coalition_travel.infrastructure.negotiation.simulated_oracle"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    return hashes


def _configuration_id(adapter: _SellerExecutionAdapter, config: SimulatedOracleConfig) -> str:
    strategy = config.leader_strategy
    payload = {
        "protocol_version": config.protocol_version,
        "seller_strategy_version": config.seller_strategy_version,
        "seller_concession_rate": str(config.seller_concession_rate),
        "seller_initial_price_policy": config.seller_initial_price_policy,
        "reference_date": config.reference_date.isoformat(),
        "max_router_iterations": config.max_router_iterations,
        "verify_reproducibility": config.verify_reproducibility,
        "leader_strategy": {
            "version": strategy.version,
            "initial_offer_fraction": str(strategy.initial_offer_fraction),
            "concession_rate": str(strategy.concession_rate),
            "max_counteroffers": strategy.max_counteroffers,
        },
        "catalog_version": adapter.catalog.version,
        "catalog_sha256": adapter.catalog.sha256,
        "seller_terms_sha256": adapter._terms_book.sha256,
        "code_sha256": _agent_source_hashes(),
    }
    return _canonical_digest(payload)


class SimulatedNegotiationOracle:
    """Run isolated legacy agents while preserving the exact P2 oracle contract.

    The configured catalogue and private terms are immutable. Calls use global
    stdout capture to suppress legacy prints and therefore must be sequential;
    this class does not claim thread safety.
    """

    def __init__(
        self,
        catalog: OfferCatalog,
        terms_book: SellerTermsBook,
        config: SimulatedOracleConfig,
    ):
        if type(config) is not SimulatedOracleConfig:
            raise InvalidNegotiationConfiguration("config must be SimulatedOracleConfig")
        self._seller_adapter = _SellerExecutionAdapter(catalog, terms_book)
        self.config = config
        self.oracle_configuration_id = _configuration_id(self._seller_adapter, config)

    def negotiate(self, request: NegotiationRequest):
        """Implement the P2 NegotiationOracle protocol; return NegotiationOutcome only."""
        return self.negotiate_detailed(request).outcome

    def negotiate_detailed(self, request: NegotiationRequest) -> NegotiationSimulation:
        """Run (and optionally repeat) a mandate, returning an expurgated journal."""
        execution = self._seller_adapter.resolve(request)
        first_outcome, first_journal = self._execute_once(request, execution)
        if not self.config.verify_reproducibility:
            return NegotiationSimulation(first_outcome, first_journal)

        second_outcome, second_journal = self._execute_once(request, execution)
        if (
            first_outcome != second_outcome
            or first_journal.journal_sha256 != second_journal.journal_sha256
        ):
            raise NonDeterministicSimulationError(
                "independent executions of the same request did not match"
            )
        return NegotiationSimulation(first_outcome, first_journal)

    def _execute_once(self, request: NegotiationRequest, execution: _SellerExecution):
        """Create fresh participants and route one complete isolated negotiation."""
        events: list[NegotiationEvent] = []
        try:
            # Historical agents print their reasoning, including the seller minimum.
            # Capture construction and execution. Never forward raw diagnostics to
            # a caller or public journal. The process-global stream requires serial use.
            with redirect_stdout(io.StringIO()):
                buyers = tuple(
                    self._buyer_for(unit.unit_id, profile)
                    for unit in request.units
                    for profile in unit.profiles
                )
                leader = MandateLeader(
                    "MandateLeader",
                    request,
                    members=buyers,
                    strategy=self.config.leader_strategy,
                )
                seller = _ConfiguredSellerAgent(
                    name=execution.offer.supplier_id,
                    min_price=to_agent_amount(execution.private_floor_total_cents),
                    release_date=execution.offer.departure_date,
                    initial_offer=to_agent_amount(execution.public_list_total_cents),
                    concession_rate=self.config.seller_concession_rate,
                )
                _observe_agent(leader, "leader", events)
                _observe_agent(seller, "seller", events)
                initial_message = Message(
                    leader,
                    seller,
                    "CFP",
                    {"destination": execution.offer.destination},
                )
                terminal, router_iterations = run_alternating_negotiation(
                    initial_message,
                    seller,
                    max_turns=self.config.max_router_iterations,
                )
            if type(router_iterations) is not int or router_iterations < 0:
                raise AgentExecutionError("legacy router returned an invalid iteration count")
            if len(events) != router_iterations:
                raise AgentExecutionError("journal event count differs from router iterations")
            terminal_reason: TerminalReason | None
            if terminal is None:
                # A silent agent already raised in the observer, so None can only mean
                # the router limit; check it instead of assuming it.
                if router_iterations != self.config.max_router_iterations:
                    raise AgentExecutionError(
                        "router stopped without a terminal message before its limit"
                    )
                status: Literal["agreement", "rejected", "turn_limit"] = "turn_limit"
                terminal_reason = "router_iteration_limit"
                agreed = None
            elif terminal.type == "REJECT":
                status = "rejected"
                terminal_reason = _rejection_reason(terminal, leader, seller)
                agreed = None
            elif terminal.type == "ACCEPT":
                status = "agreement"
                terminal_reason = None
                if terminal.sender is not leader and terminal.sender is not seller:
                    raise AgentExecutionError("ACCEPT was sent by an unknown participant")
                try:
                    agreed = from_agent_amount(terminal.content["price"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise AgentExecutionError(
                        "legacy agent returned an invalid accepted total"
                    ) from exc
                if not 0 < agreed <= request.reservation_cents:
                    raise AgentExecutionError("accepted total exceeds the mandate reservation")
                # Guaranteed by the float rules and monotonic rounding; checked anyway.
                if agreed < execution.private_floor_total_cents:
                    raise AgentExecutionError("accepted total is below the seller floor")
            else:
                raise AgentExecutionError("legacy router returned an unknown terminal message")

            outcome = self._outcome(request, status, agreed, router_iterations)
            journal = _make_journal(
                request,
                execution,
                leader,
                events,
                status,
                router_iterations,
                agreed,
                terminal_reason,
                self.oracle_configuration_id,
            )
            return outcome, journal
        except NegotiationOracleError:
            raise
        except AgentExecutionError:
            raise
        except Exception as exc:
            raise AgentExecutionError("historical negotiation agents failed") from exc

    def _buyer_for(self, unit_id, profile):
        budget_cents = cents_from_budget(profile.budget_per_person) * profile.traveller_count
        return BuyerAgent(
            name=f"{unit_id}:{profile.profile_id}",
            budget=to_agent_amount(budget_cents),
            deadline=self.config.reference_date,
            blacklist=list(profile.excluded_suppliers),
            preferred=(),
            reference_date=self.config.reference_date,
            traveller_count=profile.traveller_count,
            budget_per_person=profile.budget_per_person,
            departure_after=profile.departure_after,
            arrival_before=profile.arrival_before,
            direct_flight=profile.direct_flight,
        )

    def _outcome(self, request, status, agreed, router_iterations) -> NegotiationOutcome:
        return NegotiationOutcome(
            request_key=request.request_key,
            status=status,
            agreed_total_cents=agreed,
            turns=router_iterations,
            oracle_configuration_id=self.oracle_configuration_id,
        )


def _message_total(message: Message) -> int | None:
    content = message.content
    if type(content) is not dict or "price" not in content:
        return None
    try:
        return from_agent_amount(content["price"])
    except (TypeError, ValueError) as exc:
        raise AgentExecutionError("historical agent emitted an invalid total price") from exc


def _observe_agent(agent: Agent, actor: Literal["leader", "seller"], events):
    """Wrap one fresh instance to record only message types and total amounts."""
    original = agent.receive_message

    def observed(message):
        reply = original(message)
        if reply is None:
            raise AgentExecutionError("historical agent returned no message")
        events.append(
            NegotiationEvent(
                call_index=len(events) + 1,
                actor=actor,
                incoming_type=message.type,
                incoming_total_cents=_message_total(message),
                outgoing_type=reply.type,
                outgoing_total_cents=_message_total(reply),
            )
        )
        return reply

    agent.receive_message = observed


def _rejection_reason(terminal: Message, leader: MandateLeader, seller: SellerAgent):
    """Name who refused, from the terminal message's sender; never guessed."""
    if terminal.sender is leader:
        if not leader.counteroffers_exhausted:
            raise AgentExecutionError("leader rejected before exhausting its counter-offers")
        return "leader_counteroffers_exhausted"
    if terminal.sender is seller:
        return "seller_rejected"
    raise AgentExecutionError("REJECT was sent by an unknown participant")


def seller_concession_factor(concession_rate: Decimal) -> float:
    """Float multiplier for each seller concession, rounded once from Decimal.

    For the default 10 % it is exactly the historical literal ``0.90``.
    """
    return float(Decimal(1) - concession_rate)


class _ConfiguredSellerAgent(SellerAgent):
    """Historical ``SellerAgent`` decision rule with an explicit concession rate.

    Same as ``SellerAgent.receive_message`` for a PROPOSE: accept when the raw buyer
    float is at least ``self.min_price`` and return that raw price, otherwise concede
    to ``max(min_price, current_offer * factor)``. Only the 0.90 literal is replaced by
    the configured factor (identical for the default rate). Like the historical
    seller, it never emits REJECT.
    """

    def __init__(self, *args, concession_rate: Decimal, **kwargs):
        super().__init__(*args, **kwargs)
        self._concession_factor = seller_concession_factor(concession_rate)

    def receive_message(self, message: Message) -> Message:
        if message.type != "PROPOSE":
            return super().receive_message(message)
        if type(message.content) is not dict or "price" not in message.content:
            raise AgentExecutionError("leader proposal must contain a total price")
        buyer_price = message.content["price"]
        try:
            # Validation only (type, finiteness, money domain); not used to decide.
            from_agent_amount(buyer_price)
        except (TypeError, ValueError) as exc:
            raise AgentExecutionError("leader proposed an invalid total") from exc
        # Historical rule ``buyer_offer >= self.min_price`` on raw floats.
        if buyer_price >= self.min_price:
            return Message(self, message.sender, "ACCEPT", {"price": buyer_price})

        self.current_offer = max(self.min_price, self.current_offer * self._concession_factor)
        return Message(self, message.sender, "PROPOSE", {"price": self.current_offer})


def _make_journal(
    request,
    execution,
    leader,
    events,
    status,
    router_iterations,
    agreed,
    terminal_reason,
    configuration_id,
):
    tier = execution.price_tier
    run_id = _canonical_digest(
        {
            "oracle_configuration_id": configuration_id,
            "request_key": request.request_key,
            "offer_id": execution.offer.offer_id,
            "quantity_seats": execution.quantity_seats,
            "price_tier_min_seats": tier.min_seats,
            "public_list_per_seat_cents": tier.list_per_seat,
            "public_list_total_cents": execution.public_list_total_cents,
        }
    )
    journal_payload = {
        "request_key": request.request_key,
        "oracle_configuration_id": configuration_id,
        "run_id": run_id,
        "offer_id": execution.offer.offer_id,
        "quantity_seats": execution.quantity_seats,
        "selected_price_tier_min_seats": tier.min_seats,
        "initial_leader_total_cents": leader.initial_offer_cents,
        "initial_seller_total_cents": execution.public_list_total_cents,
        "events": [
            {
                "call_index": event.call_index,
                "actor": event.actor,
                "incoming_type": event.incoming_type,
                "incoming_total_cents": event.incoming_total_cents,
                "outgoing_type": event.outgoing_type,
                "outgoing_total_cents": event.outgoing_total_cents,
            }
            for event in events
        ],
        "status": status,
        "terminal_reason": terminal_reason,
        "router_iterations": router_iterations,
        "agreed_total_cents": agreed,
    }
    digest = _canonical_digest(journal_payload)
    return NegotiationJournal(
        request_key=request.request_key,
        oracle_configuration_id=configuration_id,
        run_id=run_id,
        offer_id=execution.offer.offer_id,
        quantity_seats=execution.quantity_seats,
        selected_price_tier_min_seats=tier.min_seats,
        initial_leader_total_cents=leader.initial_offer_cents,
        initial_seller_total_cents=execution.public_list_total_cents,
        events=tuple(events),
        status=status,
        terminal_reason=terminal_reason,
        router_iterations=router_iterations,
        agreed_total_cents=agreed,
        journal_sha256=digest,
    )
