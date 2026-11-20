"""Journaling adapter placed under the negotiation cache (plan 3H/P5, §4.4).

``CachingNegotiationOracle`` keeps only ``NegotiationOutcome`` values. To show the
negotiations to a traveller without negotiating twice, this adapter sits between the
cache and the simulated oracle:

    CachingNegotiationOracle ─► JournalingNegotiationOracle ─► SimulatedNegotiationOracle

On every real call it runs, in this order:

1. ``negotiate_detailed`` on the wrapped oracle;
2. the P2 outcome contract check, with the same function as the cache
   (``validate_negotiation_outcome``), so that no journal is ever kept for an outcome the
   cache would refuse;
3. the journal/outcome concordance check (invariant J2);
4. storage of the journal as the canonical journal of its ``request_key`` (J1), or
   deduplication when that key already has a journal (§4.4.2);
5. return of the outcome alone.

A cache hit never reaches this adapter: it reuses the canonical journal stored at the
corresponding miss. The adapter caches no outcome itself; that remains the cache's role.

Journals carry public amounts only (offers exchanged, list price, agreement); no seller
floor or private term is stored here.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Protocol

from coalition_travel.application.reference_costs import validate_negotiation_outcome
from coalition_travel.domain.negotiation_request import NegotiationOutcome, NegotiationRequest
from coalition_travel.infrastructure.negotiation.simulated_oracle import (
    NegotiationJournal,
    NegotiationSimulation,
)


class JournalConsistencyError(RuntimeError):
    """A journal does not describe the outcome returned with it (invariant J2)."""


class NonDeterministicJournalError(RuntimeError):
    """The same request_key produced two different journals or outcomes (§4.4.2)."""


class DetailedNegotiationOracle(Protocol):
    oracle_configuration_id: str

    def negotiate_detailed(self, request: NegotiationRequest) -> NegotiationSimulation: ...


def check_journal_concordance(journal: NegotiationJournal, outcome: NegotiationOutcome) -> None:
    """Invariant J2: the journal describes exactly the outcome of the same negotiation."""
    if type(journal) is not NegotiationJournal:
        raise JournalConsistencyError("the oracle must return a NegotiationJournal")
    mismatches = [
        name
        for name, journal_value, outcome_value in (
            ("request_key", journal.request_key, outcome.request_key),
            (
                "oracle_configuration_id",
                journal.oracle_configuration_id,
                outcome.oracle_configuration_id,
            ),
            ("status", journal.status, outcome.status),
            ("agreed_total_cents", journal.agreed_total_cents, outcome.agreed_total_cents),
            ("router_iterations/turns", journal.router_iterations, outcome.turns),
        )
        if journal_value != outcome_value
    ]
    if mismatches:
        raise JournalConsistencyError("journal and outcome disagree on " + ", ".join(mismatches))


class JournalingNegotiationOracle:
    """Configured P2 oracle that keeps one canonical journal per request_key.

    One instance serves one planning session: create a new one per lot, so that every
    stored journal belongs to an attempt of that lot (invariant J4).
    """

    def __init__(self, oracle: DetailedNegotiationOracle):
        configuration = getattr(oracle, "oracle_configuration_id", None)
        if type(configuration) is not str or not configuration.strip():
            raise TypeError("the oracle must expose a non-blank oracle_configuration_id")
        if not callable(getattr(oracle, "negotiate_detailed", None)):
            raise TypeError("the oracle must provide negotiate_detailed(request)")
        self._oracle = oracle
        self.oracle_configuration_id = configuration
        self._journals: dict[str, NegotiationJournal] = {}
        self._outcomes: dict[str, NegotiationOutcome] = {}
        self._oracle_calls = 0

    def negotiate(self, request: NegotiationRequest) -> NegotiationOutcome:
        if type(request) is not NegotiationRequest:
            raise TypeError("request must be a NegotiationRequest")
        simulation = self._oracle.negotiate_detailed(request)
        self._oracle_calls += 1
        if type(simulation) is not NegotiationSimulation:
            raise JournalConsistencyError("negotiate_detailed must return a NegotiationSimulation")
        outcome, journal = simulation.outcome, simulation.journal
        # Step 2 before any storage: an outcome the cache would refuse leaves no journal.
        validate_negotiation_outcome(
            outcome,
            expected_key=request.request_key,
            reservation_cents=request.reservation_cents,
            expected_configuration=self.oracle_configuration_id,
        )
        check_journal_concordance(journal, outcome)
        key = request.request_key
        canonical = self._journals.get(key)
        if canonical is None:
            self._journals[key] = journal
            self._outcomes[key] = outcome
        elif canonical.journal_sha256 != journal.journal_sha256 or self._outcomes[key] != outcome:
            raise NonDeterministicJournalError(
                f"request_key {key} produced a different journal or outcome on a repeated call"
            )
        # Identical journal: deduplicated, the canonical object stays in place.
        return outcome

    def journal_for(self, request_key: str) -> NegotiationJournal:
        """Canonical journal of a negotiated key; KeyError if it was never negotiated."""
        return self._journals[request_key]

    @property
    def journals(self) -> Mapping[str, NegotiationJournal]:
        """Read-only view of the canonical journals, keyed by request_key."""
        return MappingProxyType(self._journals)

    @property
    def oracle_calls(self) -> int:
        """Real calls made to the wrapped oracle, including those that raised afterwards."""
        return self._oracle_calls
