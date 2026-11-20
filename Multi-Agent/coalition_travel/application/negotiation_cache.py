"""Negotiation cache keyed by (request_key, oracle_configuration_id) (M3, section 10).

The key is economic: request_key identifies the mandate (offer, units' content, seats,
reservation) and oracle_configuration_id identifies the oracle. Two coalitions made of
different units but economically identical share one result, which is correct because a
deterministic, stateless oracle (hypothesis I1, verified for P3) depends on nothing else.

The cache implements the P2 NegotiationOracle protocol, so it plugs unchanged into
``compute_reference_costs``: references and coalitions share it, which guarantees
c({u}) = ref_u. It never stores an outcome that violates the P2 contract.
"""

from dataclasses import dataclass
from typing import Protocol

from coalition_travel.application.reference_costs import validate_negotiation_outcome
from coalition_travel.domain.negotiation_request import NegotiationOutcome, NegotiationRequest


class ConfiguredNegotiationOracle(Protocol):
    """An oracle that exposes its configuration identity before negotiating."""

    oracle_configuration_id: str

    def negotiate(self, request: NegotiationRequest) -> NegotiationOutcome: ...


@dataclass(frozen=True)
class CacheStatistics:
    requests: int
    hits: int
    oracle_calls: int


class CachingNegotiationOracle:
    """Memoize a configured oracle; the cache lives as long as this object."""

    def __init__(self, oracle: ConfiguredNegotiationOracle):
        configuration = getattr(oracle, "oracle_configuration_id", None)
        if type(configuration) is not str or not configuration.strip():
            raise TypeError("the oracle must expose a non-blank oracle_configuration_id")
        if not callable(getattr(oracle, "negotiate", None)):
            raise TypeError("the oracle must provide negotiate(request)")
        self._oracle = oracle
        self.oracle_configuration_id = configuration
        self._entries: dict[tuple[str, str], NegotiationOutcome] = {}
        self._requests = 0
        self._hits = 0

    def negotiate(self, request: NegotiationRequest) -> NegotiationOutcome:
        if type(request) is not NegotiationRequest:
            raise TypeError("request must be a NegotiationRequest")
        self._requests += 1
        key = (request.request_key, self.oracle_configuration_id)
        cached = self._entries.get(key)
        if cached is not None:
            self._hits += 1
            return cached
        outcome = self._oracle.negotiate(request)
        validate_negotiation_outcome(
            outcome,
            expected_key=request.request_key,
            reservation_cents=request.reservation_cents,
            expected_configuration=self.oracle_configuration_id,
        )
        self._entries[key] = outcome
        return outcome

    @property
    def statistics(self) -> CacheStatistics:
        return CacheStatistics(
            requests=self._requests,
            hits=self._hits,
            oracle_calls=self._requests - self._hits,
        )
