"""Collective negotiated cost c(C) of a candidate coalition through the P3 oracle (M3).

For each common admissible offer o of C, the request is built by the only P2 factory,
``negotiation_request_for(C, o)`` (seats(C), additive reservation R(C), economic
request_key), negotiated through the oracle, and checked against the P2 contract.
c(C) is the lowest agreed total, ties broken by offer_id: exactly the rule used for the
individual references, so c({u}) = ref_u. Without any agreement, C is not feasible.
"""

from dataclasses import dataclass

from coalition_travel.application.coalition_candidates import CoalitionCandidate
from coalition_travel.application.negotiation_cache import ConfiguredNegotiationOracle
from coalition_travel.application.reference_costs import validate_negotiation_outcome
from coalition_travel.domain.negotiation_request import (
    NEGOTIATION_STATUSES,
    NegotiationStatus,
    negotiation_request_for,
)
from coalition_travel.domain.offer_graph import AdmissibilityRelation


class OracleConfigurationMismatch(ValueError):
    """References and coalitions must be negotiated with the same configuration (I2)."""


@dataclass(frozen=True)
class CoalitionAttempt:
    offer_id: str
    request_key: str
    status: NegotiationStatus
    agreed_total_cents: int | None
    turns: int

    def __post_init__(self):
        if self.status not in NEGOTIATION_STATUSES:
            raise ValueError(f"unsupported negotiation status {self.status!r}")
        if (self.status == "agreement") != (self.agreed_total_cents is not None):
            raise ValueError("an amount is present exactly for an agreement")


@dataclass(frozen=True)
class CoalitionCost:
    """All attempts of one coalition and its cost; cost_cents is None when infeasible."""

    unit_ids: tuple[str, ...]
    attempts: tuple[CoalitionAttempt, ...]
    offer_id: str | None
    cost_cents: int | None

    def __post_init__(self):
        if type(self.unit_ids) is not tuple or not self.unit_ids:
            raise ValueError("unit_ids must be a non-empty tuple")
        if self.unit_ids != tuple(sorted(set(self.unit_ids))):
            raise ValueError("unit_ids must be sorted and unique")
        if type(self.attempts) is not tuple or not self.attempts:
            raise ValueError("a coalition cost needs at least one attempt")
        if any(type(item) is not CoalitionAttempt for item in self.attempts):
            raise TypeError("attempts must be CoalitionAttempt instances")
        offers = tuple(item.offer_id for item in self.attempts)
        if offers != tuple(sorted(set(offers))):
            raise ValueError("attempts must be unique and sorted by offer_id")
        agreements = [item for item in self.attempts if item.status == "agreement"]
        if agreements:
            best = min(agreements, key=lambda item: (item.agreed_total_cents, item.offer_id))
            if (self.offer_id, self.cost_cents) != (best.offer_id, best.agreed_total_cents):
                raise ValueError("the cost must be the lowest agreement, ties by offer_id")
        elif (self.offer_id, self.cost_cents) != (None, None):
            raise ValueError("an infeasible coalition carries no offer and no cost")

    @property
    def feasible(self) -> bool:
        return self.cost_cents is not None


def negotiate_candidate(
    candidate: CoalitionCandidate,
    relation: AdmissibilityRelation,
    oracle: ConfiguredNegotiationOracle,
) -> CoalitionCost:
    """Negotiate C on each of its common offers and keep the lowest agreement."""
    if not isinstance(candidate, CoalitionCandidate):
        raise TypeError("candidate must be a CoalitionCandidate")
    configuration = getattr(oracle, "oracle_configuration_id", None)
    if type(configuration) is not str or not configuration.strip():
        raise TypeError("the oracle must expose a non-blank oracle_configuration_id")
    units_by_id = {unit.unit_id: unit for unit in relation.units}
    offers_by_id = {offer.offer_id: offer for offer in relation.offers}
    units = tuple(units_by_id[unit_id] for unit_id in candidate.unit_ids)
    attempts = []
    for offer_id in candidate.common_offer_ids:
        request = negotiation_request_for(units, offers_by_id[offer_id])
        outcome = oracle.negotiate(request)
        validate_negotiation_outcome(
            outcome,
            expected_key=request.request_key,
            reservation_cents=request.reservation_cents,
            expected_configuration=configuration,
        )
        attempts.append(
            CoalitionAttempt(
                offer_id=offer_id,
                request_key=request.request_key,
                status=outcome.status,
                agreed_total_cents=outcome.agreed_total_cents,
                turns=outcome.turns,
            )
        )
    agreements = [item for item in attempts if item.status == "agreement"]
    best = min(agreements, key=lambda item: (item.agreed_total_cents, item.offer_id), default=None)
    return CoalitionCost(
        unit_ids=candidate.unit_ids,
        attempts=tuple(attempts),
        offer_id=None if best is None else best.offer_id,
        cost_cents=None if best is None else best.agreed_total_cents,
    )
