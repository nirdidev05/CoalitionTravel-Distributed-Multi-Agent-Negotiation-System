"""Planning of one lot on the 3H path (plan 3H/P5, step I1).

``plan_lot`` chains the existing contracts without changing any of them:

    focus drafts ─► build_travel_unit ─┐
    pool drafts  ─► build_travel_unit ─┴► lot selection (same route)
        ─► run_formation_stages (P2 admissibility and H2, P2/P3 references, P4 formation)
           with one CachingNegotiationOracle over one journaling session
        ─► journal invariants J3 to J5 checked ─► TripPlan

Rules (plan §3.1, §4.3, §4.4, §6.3):

- a *focus* request is a traveller's own request; the CLI v1 sends one, the session mode
  (deferred) will send several. If any focus request cannot become a unit, nothing is
  negotiated and the plan has status ``request_rejected`` (all or nothing, so that the
  composition of a lot never changes silently);
- a *pool* request comes from the versioned synthetic demand pool. A pool request that
  cannot become a unit is a data error (``PoolRequestError``), never a traveller error;
- the lot holds the focus units and the pool units on the same route. In v1 the route
  is the destination key; I4 adds the origin and the trip type;
- references and coalitions share one cache over one journaling session (P4 contract),
  so no mandate is negotiated twice and every attempt finds its canonical journal.

This module imports no infrastructure: the market and its sessions are ports.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Literal, Protocol

from coalition_travel.application.coalition_candidates import DEFAULT_LIMITS, FormationLimits
from coalition_travel.application.coalition_formation import (
    FormationResult,
    FormationStages,
    run_formation_stages,
)
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.travel_units import TravelUnitError, build_travel_unit
from coalition_travel.domain.negotiation_request import NegotiationOutcome, NegotiationRequest
from coalition_travel.domain.offer import OfferCatalog
from coalition_travel.domain.travel_unit import MAX_UNIT_ID_LENGTH, TravelUnit

PLANNING_VERSION = "3h-planning-v1"
PlanStatus = Literal["planned", "request_rejected"]


class PlanningInputError(ValueError):
    """The planning input is inconsistent (identifiers, dates, pool and catalogue)."""


class PoolRequestError(ValueError):
    """A request of the synthetic demand pool cannot become a travel unit (data error)."""


class PlanConsistencyError(RuntimeError):
    """A journal invariant (J3 to J5) does not hold for the planned lot."""


# --- ports -------------------------------------------------------------------------------


class NegotiationJournalView(Protocol):
    """Public fields of a negotiation journal used by the invariants."""

    request_key: str
    oracle_configuration_id: str
    status: str
    agreed_total_cents: int | None
    router_iterations: int
    journal_sha256: str


class JournalingSession(Protocol):
    """Configured oracle that keeps one canonical journal per request_key."""

    oracle_configuration_id: str

    def negotiate(self, request: NegotiationRequest) -> NegotiationOutcome: ...

    def journal_for(self, request_key: str) -> NegotiationJournalView: ...

    @property
    def journals(self) -> Mapping[str, NegotiationJournalView]: ...

    @property
    def oracle_calls(self) -> int: ...


class NegotiationMarket(Protocol):
    """Public catalogue and a factory of fresh journaling sessions."""

    @property
    def catalog(self) -> OfferCatalog: ...

    @property
    def reference_date(self) -> date: ...

    @property
    def oracle_configuration_id(self) -> str: ...

    def open_session(self) -> JournalingSession: ...


# --- input -------------------------------------------------------------------------------


def _require_date(value, name: str) -> None:
    if isinstance(value, datetime) or type(value) is not date:
        raise TypeError(f"{name} must be a datetime.date")


@dataclass(frozen=True)
class PlanningRequest:
    request_id: str
    draft: TravelRequestDraft

    def __post_init__(self):
        if type(self.request_id) is not str:
            raise TypeError("request_id must be a string")
        if (
            not self.request_id
            or self.request_id != self.request_id.strip()
            or len(self.request_id) > MAX_UNIT_ID_LENGTH
        ):
            raise PlanningInputError("request_id must be non-blank, stripped and short")
        if not isinstance(self.draft, TravelRequestDraft):
            raise TypeError("draft must be a TravelRequestDraft")


@dataclass(frozen=True)
class DemandPoolSnapshot:
    """Requests of one versioned synthetic demand pool, with its provenance."""

    version: str
    sha256: str
    catalog_version: str
    requests: tuple[PlanningRequest, ...]

    def __post_init__(self):
        for name in ("version", "sha256", "catalog_version"):
            if type(getattr(self, name)) is not str or not getattr(self, name):
                raise TypeError(f"{name} must be a non-empty string")
        if type(self.requests) is not tuple or any(
            type(item) is not PlanningRequest for item in self.requests
        ):
            raise TypeError("requests must be a tuple of PlanningRequest")
        identifiers = [item.request_id for item in self.requests]
        if len(set(identifiers)) != len(identifiers):
            raise PlanningInputError("pool request identifiers must be unique")


@dataclass(frozen=True)
class PlanningInput:
    focus: tuple[PlanningRequest, ...]
    pool: DemandPoolSnapshot | None
    reference_date: date
    limits: FormationLimits = DEFAULT_LIMITS

    def __post_init__(self):
        if type(self.focus) is not tuple or not self.focus:
            raise PlanningInputError("at least one focus request is required")
        if any(type(item) is not PlanningRequest for item in self.focus):
            raise TypeError("focus must be a tuple of PlanningRequest")
        if self.pool is not None and type(self.pool) is not DemandPoolSnapshot:
            raise TypeError("pool must be a DemandPoolSnapshot or None")
        _require_date(self.reference_date, "reference_date")
        if type(self.limits) is not FormationLimits:
            raise TypeError("limits must be FormationLimits")
        focus_ids = [item.request_id for item in self.focus]
        if len(set(focus_ids)) != len(focus_ids):
            raise PlanningInputError("focus request identifiers must be unique")
        pool_ids = set() if self.pool is None else {r.request_id for r in self.pool.requests}
        shared = sorted(set(focus_ids) & pool_ids)
        if shared:
            raise PlanningInputError(f"identifiers used by both focus and pool: {shared}")


# --- output ------------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestRejection:
    request_id: str
    reason: str
    status: str | None
    missing_fields: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class JournalInvariants:
    """Counts behind J3 to J5, all verified equal where the plan requires it."""

    attempts: int
    distinct_keys: int
    journals: int
    oracle_calls: int
    cache_requests: int


@dataclass(frozen=True)
class TripPlan:
    status: PlanStatus
    focus_request_ids: tuple[str, ...]
    rejections: tuple[RequestRejection, ...]
    units: tuple[TravelUnit, ...]
    pool_unit_ids: tuple[str, ...]
    stages: FormationStages | None
    journals: Mapping[str, NegotiationJournalView]
    invariants: JournalInvariants | None
    reference_date: date
    catalog_version: str
    catalog_sha256: str
    oracle_configuration_id: str
    pool_version: str | None
    pool_sha256: str | None
    planning_version: str = PLANNING_VERSION

    def __post_init__(self):
        if (self.status == "planned") != (self.stages is not None):
            raise PlanConsistencyError("stages are present exactly for a planned lot")
        if (self.status == "request_rejected") != bool(self.rejections):
            raise PlanConsistencyError("rejections are present exactly for a rejected plan")

    @property
    def formation(self) -> FormationResult | None:
        return None if self.stages is None else self.stages.formation

    @property
    def lot_unit_ids(self) -> tuple[str, ...]:
        return tuple(sorted(unit.unit_id for unit in self.units))

    def journal_for(self, request_key: str) -> NegotiationJournalView:
        return self.journals[request_key]


# --- planning ----------------------------------------------------------------------------


def route_key(unit: TravelUnit) -> str:
    """Route of a unit for lot selection. v1: destination key (I4 adds origin and type)."""
    return unit.destination_key


def verify_journal_invariants(
    stages: FormationStages, journals: Mapping[str, NegotiationJournalView], oracle_calls: int
) -> JournalInvariants:
    """Check J3, J4 and J5 on the normal planning path (cache above the journaling session).

    J1 (one canonical journal per key) and J2 (journal/outcome concordance) are enforced by
    the session when it stores a journal.
    """
    attempts = []
    if stages.references is not None:
        for reference in stages.references.unit_references:
            attempts.extend(reference.attempts)
    for cost in stages.formation.evaluations:
        attempts.extend(cost.attempts)
    keys = {attempt.request_key for attempt in attempts}
    for attempt in attempts:  # J3
        journal = journals.get(attempt.request_key)
        if journal is None:
            raise PlanConsistencyError(f"J3: no journal for request_key {attempt.request_key}")
        if (
            journal.request_key,
            journal.status,
            journal.agreed_total_cents,
            journal.router_iterations,
        ) != (attempt.request_key, attempt.status, attempt.agreed_total_cents, attempt.turns):
            raise PlanConsistencyError(
                f"J3: attempt and journal disagree for request_key {attempt.request_key}"
            )
    superfluous = sorted(set(journals) - keys)  # J4
    if superfluous:
        raise PlanConsistencyError(f"J4: journals without attempt: {superfluous[:3]}")
    statistics = stages.formation.cache_statistics
    if statistics is None:
        raise PlanConsistencyError("J5: the formation result carries no cache statistics")
    if not len(journals) == statistics.oracle_calls == len(keys) == oracle_calls:  # J5
        raise PlanConsistencyError(
            "J5: journals, oracle calls and distinct attempt keys differ "
            f"({len(journals)}, {statistics.oracle_calls}, {len(keys)}, {oracle_calls})"
        )
    if len(attempts) != statistics.requests:
        raise PlanConsistencyError(
            f"J5: {len(attempts)} attempts for {statistics.requests} cache requests"
        )
    return JournalInvariants(
        attempts=len(attempts),
        distinct_keys=len(keys),
        journals=len(journals),
        oracle_calls=statistics.oracle_calls,
        cache_requests=statistics.requests,
    )


def plan_lot(planning: PlanningInput, market: NegotiationMarket) -> TripPlan:
    """Plan one lot: units, P2 admissibility and references, P4 formation, journals."""
    if type(planning) is not PlanningInput:
        raise TypeError("planning must be a PlanningInput")
    if market.reference_date != planning.reference_date:
        raise PlanningInputError("the market and the planning use different reference dates")
    catalog = market.catalog
    pool = planning.pool
    if pool is not None and pool.catalog_version != catalog.version:
        raise PlanningInputError(
            f"pool {pool.version} targets {pool.catalog_version}, not {catalog.version}"
        )
    provenance = {
        "reference_date": planning.reference_date,
        "catalog_version": catalog.version,
        "catalog_sha256": catalog.sha256,
        "oracle_configuration_id": market.oracle_configuration_id,
        "pool_version": None if pool is None else pool.version,
        "pool_sha256": None if pool is None else pool.sha256,
    }
    focus_ids = tuple(item.request_id for item in planning.focus)

    focus_units: list[TravelUnit] = []
    rejections: list[RequestRejection] = []
    for item in planning.focus:
        try:
            focus_units.append(
                build_travel_unit(item.request_id, item.draft, planning.reference_date)
            )
        except TravelUnitError as exc:
            rejections.append(
                RequestRejection(
                    item.request_id, exc.reason, exc.status, exc.missing_fields, exc.errors
                )
            )
    if rejections:
        return TripPlan(
            status="request_rejected",
            focus_request_ids=focus_ids,
            rejections=tuple(rejections),
            units=(),
            pool_unit_ids=(),
            stages=None,
            journals=MappingProxyType({}),
            invariants=None,
            **provenance,
        )

    routes = {route_key(unit) for unit in focus_units}
    pool_units: list[TravelUnit] = []
    for item in () if pool is None else pool.requests:
        try:
            unit = build_travel_unit(item.request_id, item.draft, planning.reference_date)
        except TravelUnitError as exc:
            raise PoolRequestError(f"pool request {item.request_id}: {exc}") from exc
        if route_key(unit) in routes:
            pool_units.append(unit)

    session = market.open_session()
    if session.journals or session.oracle_calls:
        raise PlanConsistencyError("a planning session must start without journals or calls")
    if session.oracle_configuration_id != market.oracle_configuration_id:
        raise PlanConsistencyError("the session and the market use different configurations")
    units = tuple(focus_units) + tuple(pool_units)
    stages = run_formation_stages(
        units, catalog, planning.reference_date, session, limits=planning.limits
    )
    journals = MappingProxyType(dict(session.journals))
    invariants = verify_journal_invariants(stages, journals, session.oracle_calls)
    return TripPlan(
        status="planned",
        focus_request_ids=focus_ids,
        rejections=(),
        units=tuple(sorted(units, key=lambda unit: unit.unit_id)),
        pool_unit_ids=tuple(sorted(unit.unit_id for unit in pool_units)),
        stages=stages,
        journals=journals,
        invariants=invariants,
        **provenance,
    )
