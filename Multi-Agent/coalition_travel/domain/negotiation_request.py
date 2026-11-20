"""Public negotiation request and oracle protocol; seller floors are not represented.

``negotiation_request_for`` is the only way to build a request, for one unit (individual
reference) or several (coalition): the quantity and the additive reservation
R(C) = sum of unit budgets are always derived the same way, so individual and collective
negotiations are strictly comparable by construction.

``request_key`` is the canonical *economic identity* of a negotiation mandate: the
SHA-256 of a canonical JSON document (``request_key_content``) recomputed from the
request's own data, never from a stored fingerprint. It contains:

- the negotiated offer: catalogue version, offer_id (it also selects the seller's
  private terms) and every public field that can change the negotiation (supplier,
  destination, dates, direct flag, capacity, price tiers);
- the participating units as a sorted multiset; each unit is its normalized
  destination and its profiles' economic content (seats, budget per seat in cents,
  date windows, direct-flight requirement, normalized supplier exclusions), profiles
  with identical constraints being merged by adding their seats;
- the seat count and the additive reservation.

It excludes technical identifiers and provenance: unit_id, profile_id, the stored
P1 ``fingerprint``, ``rounded_budget_profiles``, the ``synthetic`` catalogue flag,
timestamps and session identifiers. Permuting units or profiles, renaming them or
splitting a profile into identical parts leaves the key unchanged; any change of a
listed field changes it. Unit boundaries are kept: two units are never merged into one.

Everything that configures how the mandate is negotiated (strategies, protocol and
limits, seller private terms, catalogue and terms digests, code) belongs to the
oracle's ``oracle_configuration_id``, so one mandate keeps its key under every oracle
configuration.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Protocol

from coalition_travel.domain.admissibility import normalize_supplier_key
from coalition_travel.domain.destination import normalize_destination_key
from coalition_travel.domain.money import cents_from_budget
from coalition_travel.domain.offer import OfferQuote
from coalition_travel.domain.travel_unit import TravelUnit

_CREATION_TOKEN = object()
# Version of the canonical document; change it whenever its content or layout changes.
REQUEST_KEY_SCHEMA = "negotiation-request-key-v2"

# Three distinct terminal outcomes of the legacy alternating-offers protocol:
# ACCEPT message, REJECT message, or the max_turns limit reached without a terminal message.
NegotiationStatus = Literal["agreement", "rejected", "turn_limit"]
NEGOTIATION_STATUSES = frozenset({"agreement", "rejected", "turn_limit"})


@dataclass(frozen=True, init=False)
class NegotiationRequest:
    units: tuple[TravelUnit, ...]
    offer: OfferQuote
    seats: int
    reservation_cents: int
    request_key: str

    def __init__(
        self,
        units: tuple[TravelUnit, ...],
        offer: OfferQuote,
        seats: int,
        reservation_cents: int,
        request_key: str,
        *,
        _token: object = None,
    ):
        if _token is not _CREATION_TOKEN:
            raise TypeError("construct NegotiationRequest with negotiation_request_for")
        object.__setattr__(self, "units", units)
        object.__setattr__(self, "offer", offer)
        object.__setattr__(self, "seats", seats)
        object.__setattr__(self, "reservation_cents", reservation_cents)
        object.__setattr__(self, "request_key", request_key)


def negotiation_request_for(
    units: tuple[TravelUnit, ...] | list[TravelUnit], offer: OfferQuote
) -> NegotiationRequest:
    """Build the only supported public request; reservation is the additive unit budget."""
    if not isinstance(offer, OfferQuote):
        raise TypeError("offer must be an OfferQuote")
    materialized = tuple(units)
    if not materialized or any(not isinstance(unit, TravelUnit) for unit in materialized):
        raise TypeError("units must contain at least one TravelUnit")
    ordered = tuple(sorted(materialized, key=lambda unit: unit.unit_id))
    if len({unit.unit_id for unit in ordered}) != len(ordered):
        raise ValueError("unit IDs must be unique")
    for unit in ordered:
        if normalize_destination_key(unit.destination_key) != offer.destination_key:
            raise ValueError(
                f"unit {unit.unit_id!r} travels to {unit.destination_key!r}, "
                f"not to the offer destination {offer.destination_key!r}"
            )
    seats = sum(unit.seats for unit in ordered)
    if seats > offer.capacity_seats:
        raise ValueError("negotiation request exceeds offer capacity")
    reservation = sum(unit.budget_total_cents for unit in ordered)
    content = request_key_content(ordered, offer)
    if content["seats"] != seats or content["reservation_cents"] != reservation:
        raise RuntimeError("request key content disagrees with the request totals")
    key = hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest()
    return NegotiationRequest(ordered, offer, seats, reservation, key, _token=_CREATION_TOKEN)


def request_key_content(units: tuple[TravelUnit, ...], offer: OfferQuote) -> dict:
    """Canonical economic document hashed into ``request_key`` (see module docstring)."""
    unit_documents = sorted((unit_economic_content(unit) for unit in units), key=_canonical_json)
    return {
        "schema": REQUEST_KEY_SCHEMA,
        "offer": offer_economic_content(offer),
        "units": unit_documents,
        "seats": sum(unit.seats for unit in units),
        "reservation_cents": sum(unit.budget_total_cents for unit in units),
    }


def unit_economic_content(unit: TravelUnit) -> dict:
    """Identifier-free content of one indivisible unit, recomputed from its profiles."""
    seats_by_constraints: dict[str, int] = {}
    constraints_by_signature: dict[str, dict] = {}
    for profile in unit.profiles:
        constraints = {
            "budget_per_seat_cents": cents_from_budget(profile.budget_per_person),
            "departure_after": _iso(profile.departure_after),
            "arrival_before": _iso(profile.arrival_before),
            "direct_flight": profile.direct_flight,
            "excluded_suppliers": sorted(
                {normalize_supplier_key(supplier) for supplier in profile.excluded_suppliers}
            ),
        }
        signature = _canonical_json(constraints)
        constraints_by_signature[signature] = constraints
        seats_by_constraints[signature] = (
            seats_by_constraints.get(signature, 0) + profile.traveller_count
        )
    profiles = [
        {**constraints_by_signature[signature], "seats": seats_by_constraints[signature]}
        for signature in sorted(constraints_by_signature)
    ]
    return {
        "destination_key": normalize_destination_key(unit.destination_key),
        "profiles": profiles,
    }


def unit_economic_digest(unit: TravelUnit) -> str:
    """SHA-256 of ``unit_economic_content``; used where a unit's content must be pinned."""
    return hashlib.sha256(_canonical_json(unit_economic_content(unit)).encode("utf-8")).hexdigest()


def offer_economic_content(offer: OfferQuote) -> dict:
    """Public offer fields that identify what is negotiated (private terms excluded)."""
    return {
        "offer_id": offer.offer_id,
        "catalog_version": offer.catalog_version,
        "supplier_id": offer.supplier_id,
        "destination_key": offer.destination_key,
        "departure_date": offer.departure_date.isoformat(),
        "arrival_date": offer.arrival_date.isoformat(),
        "direct": offer.direct,
        "capacity_seats": offer.capacity_seats,
        "price_tiers": [[tier.min_seats, tier.list_per_seat] for tier in offer.tiers],
    }


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _canonical_json(value) -> str:
    """Unambiguous serialization: sorted keys, fixed separators, ASCII escapes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class NegotiationOutcome:
    """Value-only oracle response, with no seller reservation or floor fields.

    Contract (checked at the oracle boundary by ``compute_reference_costs``):
    ``agreement`` carries a positive amount not above the reservation; ``rejected`` and
    ``turn_limit`` carry no amount.
    """

    request_key: str
    status: NegotiationStatus
    agreed_total_cents: int | None
    turns: int
    oracle_configuration_id: str


class NegotiationOracle(Protocol):
    """Abstract negotiation boundary; P2 supplies no real seller simulator."""

    def negotiate(self, request: NegotiationRequest) -> NegotiationOutcome: ...
