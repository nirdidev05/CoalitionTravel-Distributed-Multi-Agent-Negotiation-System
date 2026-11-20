"""Public proposal of one focus unit: contract ``trip-proposal-v1`` (plan 3H/P5, step I3-A).

``build_trip_proposal`` projects an internal ``TripPlan`` onto the frozen public contract
of docs/PHASE_I3_SCOPE_REVIEW.md (revision 4):

- every amount is read from a typed field of P2 to P5. Only three derivations are allowed
  (I3-A3): ``CoalitionGame.cover_values``, the gap V* - total(C) and
  ``OfferQuote.list_total``;
- the unit receives exactly one status among seven (section 5.1), 0 to 2 modifiers
  (section 5.2) and one annotation per rejected offer or unmet direct preference
  (section 5.3). The two request-level codes never appear in a proposal (section 5.5);
- confidentiality (B8, B11, D-I3-18): the other members of a block appear only as
  "autre demande k" with their seats and payment; the leader side of a block journal is
  hidden; the proposal carries no digest at all (no pool, catalogue, oracle, formation,
  allocation, request or journal digest) and no file path.

The French messages and the JSON form belong to the presentation layer (I3-B). Rationals
stay ``Fraction`` here; the JSON renderer writes them as "p/q". This module imports no
infrastructure: journals are read through the ``PublicJournal`` protocol.
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Literal, Protocol

from coalition_travel.application.coalition_formation import (
    FORMATION_ADAPTER_VERSION,
    ComponentFormation,
    FormationResult,
    FormedBlock,
)
from coalition_travel.application.request_contracts import TravelRequestDraft, draft_document
from coalition_travel.application.savings_allocation import (
    ALLOCATION_VERSION,
    BlockAllocation,
    TravelerShare,
)
from coalition_travel.application.travel_units import TravelUnitError, build_travel_unit
from coalition_travel.application.trip_planning import TripPlan
from coalition_travel.domain.coalition_game import Coalition
from coalition_travel.domain.offer import OfferQuote
from coalition_travel.domain.travel_unit import TravelUnit

TRIP_PROPOSAL_SCHEMA = "trip-proposal-v1"
# v2 (scope review I4, D-I4-10): the v1 contract plus the route fields, for route requests
# only. A v1 proposal never carries a route field and keeps its bytes.
TRIP_PROPOSAL_SCHEMA_V2 = "trip-proposal-v2"

# Plan §1.2: the exact notice; it contains no forbidden word.
SIMULATION_NOTICE = (
    "Proposition simulée : catalogue et vendeurs fictifs. Aucune réservation n'est "
    "effectuée et aucun titre de transport n'est délivré."
)

# --- closed code sets (section 5) ---------------------------------------------------------

UnitStatusCode = Literal[
    "no_admissible_offer",
    "no_solo_reference",
    "component_too_large",
    "capacity_model_violated",
    "served_in_coalition",
    "alone_no_beneficial_coalition",
    "alone_social_optimum",
]
UNALLOCATED_STATUS_CODES = (
    "no_admissible_offer",
    "no_solo_reference",
    "component_too_large",
    "capacity_model_violated",
)
UNIT_STATUS_CODES = UNALLOCATED_STATUS_CODES + (
    "served_in_coalition",
    "alone_no_beneficial_coalition",
    "alone_social_optimum",
)
MODIFIER_CODES = ("projection_active", "budget_cap_active")
OFFER_CODES = ("offer_rejected", "direct_preference_not_met")
REQUEST_CODES = ("needs_clarification", "unknown_place")  # never in a proposal (§5.5)
EXPLANATION_CODES = UNIT_STATUS_CODES + MODIFIER_CODES + OFFER_CODES + REQUEST_CODES

ExplanationLevel = Literal["status", "modifier", "offer"]
LEVEL_ORDER = ("status", "modifier", "offer")
EXPLANATION_LEVELS: Mapping[str, str] = MappingProxyType(
    {
        **dict.fromkeys(UNIT_STATUS_CODES, "status"),
        **dict.fromkeys(MODIFIER_CODES, "modifier"),
        **dict.fromkeys(OFFER_CODES, "offer"),
    }
)

# --- extraction provenance (§4.10, D-I3-10) -----------------------------------------------

ExtractionSource = Literal["draft-json", "llm", "replay"]
LLM_PROVIDER = "ollama"
REPLAY_PROVIDER = "replay"
# Version of the replay file format. A constant: it never depends on the file content
# (revision 3). The replay extractor of I3-C imports it from here, since the application
# layer may not import infrastructure.
REPLAY_FORMAT_VERSION = "replay-v1"

ALTERNATIVES_SHOWN = 3  # section 5.4: the three best evaluated alternatives
OTHER_MEMBER_LABEL = "autre demande {k}"  # B8
YOU_LABEL = "vous"


class ProposalConsistencyError(RuntimeError):
    """The plan cannot be projected onto the public contract (an invariant does not hold)."""


@dataclass(frozen=True)
class ExtractionProvenance:
    """How the validated request was obtained: one of exactly three forms (§4.10)."""

    source: ExtractionSource
    provider: str | None
    model: str | None

    def __post_init__(self):
        if self.source == "draft-json":
            valid = self.provider is None and self.model is None
        elif self.source == "llm":
            valid = (
                self.provider == LLM_PROVIDER
                and type(self.model) is str
                and bool(self.model.strip())
            )
        elif self.source == "replay":
            valid = self.provider == REPLAY_PROVIDER and self.model == REPLAY_FORMAT_VERSION
        else:
            valid = False
        if not valid:
            raise ValueError(
                "extraction provenance must be (draft-json, null, null), "
                f"(llm, {LLM_PROVIDER}, <model>) or "
                f"(replay, {REPLAY_PROVIDER}, {REPLAY_FORMAT_VERSION})"
            )


def draft_json_extraction() -> ExtractionProvenance:
    return ExtractionProvenance("draft-json", None, None)


def llm_extraction(model: str) -> ExtractionProvenance:
    return ExtractionProvenance("llm", LLM_PROVIDER, model)


def replay_extraction() -> ExtractionProvenance:
    return ExtractionProvenance("replay", REPLAY_PROVIDER, REPLAY_FORMAT_VERSION)


# --- journal port -------------------------------------------------------------------------


class PublicEvent(Protocol):
    call_index: int
    actor: str
    outgoing_type: str
    outgoing_total_cents: int | None


class PublicJournal(Protocol):
    """Fields of a negotiation journal that the public view reads (and nothing else)."""

    offer_id: str
    quantity_seats: int
    selected_price_tier_min_seats: int
    initial_leader_total_cents: int
    initial_seller_total_cents: int
    events: tuple[PublicEvent, ...]
    status: str
    terminal_reason: str | None
    router_iterations: int
    agreed_total_cents: int | None


# --- contract (section 4) -----------------------------------------------------------------


@dataclass(frozen=True)
class Simulation:
    synthetic_catalog: bool = True
    simulated_sellers: bool = True
    booking: bool = False
    notice: str = SIMULATION_NOTICE


@dataclass(frozen=True)
class ValidatedRequest:
    request_id: str
    draft: Mapping[str, object]  # TravelRequestDraft.model_dump(mode="json"), read-only


@dataclass(frozen=True)
class UnitView:
    unit_id: str
    seats: int
    budget_total_cents: int
    origin_key: str | None = None  # v2 only
    trip_type: str | None = None  # v2 only


@dataclass(frozen=True)
class UnitStatus:
    code: UnitStatusCode
    modifiers: tuple[str, ...]


@dataclass(frozen=True)
class PriceTierView:
    min_seats: int
    list_per_seat_cents: int


@dataclass(frozen=True)
class ViolationView:
    rule: str
    reason: str
    profile_id: str | None


@dataclass(frozen=True)
class NoteView:
    code: str
    profile_id: str


@dataclass(frozen=True)
class LegView:
    departure_date: date
    arrival_date: date
    direct: bool
    capacity_seats: int
    leg_ref: str


@dataclass(frozen=True)
class OfferView:
    offer_id: str
    supplier_id: str
    destination: str
    departure_date: date
    arrival_date: date
    direct: bool
    capacity_seats: int
    tiers: tuple[PriceTierView, ...]
    admissible: bool
    violations: tuple[ViolationView, ...]
    notes: tuple[NoteView, ...]
    origin: str | None = None  # v2 only
    trip_type: str | None = None  # v2 only
    outbound: LegView | None = None  # v2 only
    return_leg: LegView | None = None  # v2 only; JSON key "return"


@dataclass(frozen=True)
class JournalMessage:
    index: int
    actor: str
    type: str
    total_cents: int | None


@dataclass(frozen=True)
class JournalView:
    offer_id: str
    quantity_seats: int
    price_tier_min_seats: int
    catalog_total_cents: int
    leader_initial_total_cents: int | None
    messages: tuple[JournalMessage, ...]
    status: str
    terminal_reason: str | None
    turns: int
    agreed_total_cents: int | None


@dataclass(frozen=True)
class SoloAttemptView:
    offer_id: str
    status: str
    agreed_total_cents: int | None
    turns: int
    journal: JournalView


@dataclass(frozen=True)
class SoloView:
    status: Literal["referenced", "no_admissible_offer", "no_solo_reference"]
    offer_id: str | None
    agreed_total_cents: int | None
    turns: int | None
    attempts: tuple[SoloAttemptView, ...]


@dataclass(frozen=True)
class BlockMemberView:
    label: str
    you: bool
    seats: int
    payment_cents: int


@dataclass(frozen=True)
class BlockView:
    offer_id: str
    seats: int
    price_tier_min_seats: int
    catalog_total_cents: int
    reference_total_cents: int
    cost_cents: int
    value_cents: int
    members: tuple[BlockMemberView, ...]
    negotiation: JournalView | None


@dataclass(frozen=True)
class UnitAllocationView:
    reference_cents: int
    phi_cents: Fraction
    y_cents: Fraction
    saving_cents: int
    payment_cents: int
    projection_active: bool
    unit_saturated: bool
    lambda_star_cents: Fraction
    unit_tau_cents: Fraction


@dataclass(frozen=True)
class TravellerView:
    profile_id: str
    seat_rank: int
    budget_cents: int
    amount_cents: int
    profile_saturated: bool


# --- explanation parameters: one closed class per code ------------------------------------


@dataclass(frozen=True)
class NoAdmissibleOfferParams:
    rejected_offers: int


@dataclass(frozen=True)
class NoSoloReferenceParams:
    failed_attempts: int


@dataclass(frozen=True)
class ComponentTooLargeParams:
    component_units: int
    max_component_units: int


@dataclass(frozen=True)
class CapacityModelViolatedParams:
    offer_ids: tuple[str, ...]


@dataclass(frozen=True)
class ServedInCoalitionParams:
    offer_id: str
    other_requests: int
    saving_cents: int


@dataclass(frozen=True)
class AloneNoBeneficialCoalitionParams:
    component_units: int
    singleton_component: bool
    evaluated: int
    without_agreement: int
    without_saving: int


@dataclass(frozen=True)
class AlternativeView:
    """An evaluated coalition that included the unit, published without its members."""

    size: int
    offer_id: str
    value_cents: int
    best_total_cents: int
    gap_cents: int


@dataclass(frozen=True)
class AloneSocialOptimumParams:
    component_value_cents: int
    alternatives: tuple[AlternativeView, ...]


@dataclass(frozen=True)
class ProjectionActiveParams:
    unit_saturated: bool
    lambda_star_cents: Fraction


@dataclass(frozen=True)
class BudgetCapActiveParams:
    saturated_profile_ids: tuple[str, ...]
    unit_tau_cents: Fraction


@dataclass(frozen=True)
class OfferRejectedParams:
    offer_id: str
    violations: tuple[ViolationView, ...]


@dataclass(frozen=True)
class BestDirectView:
    offer_id: str
    list_total_cents: int


@dataclass(frozen=True)
class DirectPreferenceNotMetParams:
    offer_id: str
    profile_ids: tuple[str, ...]
    retained_list_total_cents: int
    best_direct: BestDirectView | None


PARAMS_BY_CODE: Mapping[str, type] = MappingProxyType(
    {
        "no_admissible_offer": NoAdmissibleOfferParams,
        "no_solo_reference": NoSoloReferenceParams,
        "component_too_large": ComponentTooLargeParams,
        "capacity_model_violated": CapacityModelViolatedParams,
        "served_in_coalition": ServedInCoalitionParams,
        "alone_no_beneficial_coalition": AloneNoBeneficialCoalitionParams,
        "alone_social_optimum": AloneSocialOptimumParams,
        "projection_active": ProjectionActiveParams,
        "budget_cap_active": BudgetCapActiveParams,
        "offer_rejected": OfferRejectedParams,
        "direct_preference_not_met": DirectPreferenceNotMetParams,
    }
)


@dataclass(frozen=True)
class Explanation:
    code: str
    level: ExplanationLevel
    params: object  # the PARAMS_BY_CODE class of ``code``

    def __post_init__(self):
        if self.code not in PARAMS_BY_CODE:
            raise ProposalConsistencyError(f"{self.code!r} cannot appear in a proposal")
        if self.level != EXPLANATION_LEVELS[self.code]:
            raise ProposalConsistencyError(f"{self.code} has level {EXPLANATION_LEVELS[self.code]}")
        if type(self.params) is not PARAMS_BY_CODE[self.code]:
            raise ProposalConsistencyError(
                f"{self.code} needs {PARAMS_BY_CODE[self.code].__name__}"
            )

    @property
    def offer_id(self) -> str:
        return getattr(self.params, "offer_id", "") if self.level == "offer" else ""

    def sort_key(self) -> tuple:
        return (LEVEL_ORDER.index(self.level), self.code, self.offer_id)


@dataclass(frozen=True)
class Provenance:
    reference_date: date
    catalog_version: str
    pool_version: str | None
    planning_version: str
    formation_adapter_version: str
    formation_method: str
    allocation_version: str
    theta_cents: int
    extraction: ExtractionProvenance


@dataclass(frozen=True)
class TripProposal:
    schema: str
    simulation: Simulation
    request: ValidatedRequest
    unit: UnitView
    status: UnitStatus
    offers: tuple[OfferView, ...]
    solo: SoloView | None  # None exactly when H2 fails: nothing was negotiated
    block: BlockView | None
    allocation: UnitAllocationView | None
    travellers: tuple[TravellerView, ...]
    explanations: tuple[Explanation, ...]
    provenance: Provenance

    def __post_init__(self):
        if self.schema not in (TRIP_PROPOSAL_SCHEMA, TRIP_PROPOSAL_SCHEMA_V2):
            raise ProposalConsistencyError(f"schema must be {TRIP_PROPOSAL_SCHEMA}")
        route = self.schema == TRIP_PROPOSAL_SCHEMA_V2
        if route != (self.unit.origin_key is not None):
            raise ProposalConsistencyError("the v2 schema is exactly for a unit with a route")
        if not route and any(
            getattr(item, name) is not None
            for item in (self.unit, *self.offers)
            for name in V2_ONLY_FIELDS[type(item)]
        ):
            raise ProposalConsistencyError("a v1 proposal never carries a route field")
        code = self.status.code
        if code not in UNIT_STATUS_CODES:
            raise ProposalConsistencyError(f"unknown unit status {code!r}")
        placed = code not in UNALLOCATED_STATUS_CODES
        if (self.block is not None, self.allocation is not None) != (placed, placed):
            raise ProposalConsistencyError("block and allocation exist exactly for a placed unit")
        if placed != bool(self.travellers):
            raise ProposalConsistencyError("traveller shares exist exactly for a placed unit")
        if (self.solo is None) != (code == "capacity_model_violated"):
            raise ProposalConsistencyError("solo is absent exactly when H2 fails")
        statuses = [item for item in self.explanations if item.level == "status"]
        if [item.code for item in statuses] != [code]:
            raise ProposalConsistencyError("exactly one status explanation, equal to the status")
        modifiers = tuple(item.code for item in self.explanations if item.level == "modifier")
        if modifiers != self.status.modifiers:
            raise ProposalConsistencyError("modifier explanations differ from the status")
        if len(set(modifiers)) != len(modifiers) or not set(modifiers) <= set(MODIFIER_CODES):
            raise ProposalConsistencyError("modifiers must be distinct codes of the closed set")
        annotations = [(item.code, item.offer_id) for item in self.explanations]
        if len(set(annotations)) != len(annotations):
            raise ProposalConsistencyError("an explanation code appears twice for the same offer")
        if list(self.explanations) != sorted(self.explanations, key=Explanation.sort_key):
            raise ProposalConsistencyError("explanations must be in canonical order")
        if [o.offer_id for o in self.offers] != sorted(o.offer_id for o in self.offers):
            raise ProposalConsistencyError("offers must be sorted by offer_id")
        keys = [(t.profile_id, t.seat_rank) for t in self.travellers]
        if keys != sorted(keys):
            raise ProposalConsistencyError("travellers must be sorted by (profile_id, seat_rank)")
        if self.block is not None:
            members = self.block.members
            if not members or not members[0].you or any(m.you for m in members[1:]):
                raise ProposalConsistencyError("the person comes first and only once in a block")
            if sum(m.payment_cents for m in members) != self.block.cost_cents:
                raise ProposalConsistencyError("payments must sum to the negotiated block cost")


# --- construction -------------------------------------------------------------------------


def build_trip_proposal(
    plan: TripPlan,
    *,
    request_id: str,
    draft: TravelRequestDraft,
    extraction: ExtractionProvenance,
) -> TripProposal:
    """Project a planned ``TripPlan`` onto ``trip-proposal-v1`` for one focus request."""
    if type(plan) is not TripPlan:
        raise TypeError("plan must be a TripPlan")
    if not isinstance(draft, TravelRequestDraft):
        raise TypeError("draft must be a TravelRequestDraft")
    if type(extraction) is not ExtractionProvenance:
        raise TypeError("extraction must be an ExtractionProvenance")
    if plan.status != "planned" or plan.stages is None or plan.allocation is None:
        raise ProposalConsistencyError("only a planned lot with an allocation has a proposal")
    if request_id not in plan.focus_request_ids:
        raise ProposalConsistencyError(f"{request_id!r} is not a focus request of the plan")
    if plan.allocation.allocation_version != ALLOCATION_VERSION:
        raise ProposalConsistencyError("the allocation version is not the one of this contract")
    unit = _unit_of(plan, request_id)
    _check_draft_matches_unit(request_id, draft, plan.reference_date, unit)

    formation = plan.stages.formation
    block = _block_of(formation, unit.unit_id)
    block_allocation = None if block is None else plan.allocation.block_for(unit.unit_id)
    shares = tuple(
        sorted(
            plan.allocation.shares_for(unit.unit_id),
            key=lambda share: (share.profile_id, share.seat_rank),
        )
    )
    code, status_params = _status(plan, unit, block, block_allocation)
    explanations = [Explanation(code, "status", status_params)]
    explanations.extend(_modifiers(unit.unit_id, block, block_allocation, shares))
    offers = _offer_views(plan, unit.unit_id)
    explanations.extend(_offer_annotations(plan, unit, block, offers))
    explanations.sort(key=Explanation.sort_key)
    modifiers = tuple(item.code for item in explanations if item.level == "modifier")
    return TripProposal(
        schema=TRIP_PROPOSAL_SCHEMA_V2 if unit.is_route_unit else TRIP_PROPOSAL_SCHEMA,
        simulation=Simulation(),
        request=ValidatedRequest(request_id, _freeze(draft_document(draft))),
        unit=UnitView(
            unit.unit_id, unit.seats, unit.budget_total_cents, unit.origin_key, unit.trip_type
        ),
        status=UnitStatus(code, modifiers),
        offers=offers,
        solo=_solo_view(plan, unit.unit_id),
        block=None if block is None else _block_view(plan, unit, block, block_allocation),
        allocation=None
        if block is None
        else _allocation_view(unit.unit_id, block_allocation, shares),
        travellers=tuple(
            TravellerView(
                s.profile_id, s.seat_rank, s.budget_cents, s.amount_cents, s.profile_saturated
            )
            for s in shares
        ),
        explanations=tuple(explanations),
        provenance=Provenance(
            reference_date=plan.reference_date,
            catalog_version=plan.catalog_version,
            pool_version=plan.pool_version,
            planning_version=plan.planning_version,
            formation_adapter_version=FORMATION_ADAPTER_VERSION,
            formation_method=formation.method,
            allocation_version=plan.allocation.allocation_version,
            theta_cents=plan.allocation.theta_cents,
            extraction=extraction,
        ),
    )


def _freeze(value):
    """Read-only copy of a JSON value: dicts become mappings, lists become tuples."""
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _unit_of(plan: TripPlan, unit_id: str) -> TravelUnit:
    for unit in plan.units:
        if unit.unit_id == unit_id:
            return unit
    raise ProposalConsistencyError(f"focus unit {unit_id!r} is not in the plan")


def _check_draft_matches_unit(request_id, draft, reference_date, unit: TravelUnit) -> None:
    try:
        rebuilt = build_travel_unit(request_id, draft, reference_date)
    except TravelUnitError as exc:
        raise ProposalConsistencyError("the draft does not build a travel unit") from exc
    if rebuilt.fingerprint != unit.fingerprint:
        raise ProposalConsistencyError("the draft is not the request of this unit")


def _block_of(formation: FormationResult, unit_id: str) -> FormedBlock | None:
    found = [block for block in formation.blocks if unit_id in block.unit_ids]
    if len(found) > 1:
        raise ProposalConsistencyError(f"{unit_id} is in several blocks")
    return found[0] if found else None


def _component_of(formation: FormationResult, unit_id: str) -> ComponentFormation:
    found = [item for item in formation.components if unit_id in item.unit_ids]
    if len(found) != 1:
        raise ProposalConsistencyError(f"{unit_id} must be in exactly one component")
    return found[0]


def _journal(plan: TripPlan, request_key: str) -> PublicJournal:
    try:
        return plan.journals[request_key]
    except KeyError as exc:
        raise ProposalConsistencyError("an attempt has no journal (J3)") from exc


# --- status (section 5.1) -----------------------------------------------------------------


def _status(plan, unit, block, block_allocation):
    """Evaluate the four rules independently and require exactly one to hold."""
    formation = plan.stages.formation
    unit_id = unit.unit_id
    unallocated = [item for item in plan.allocation.unallocated if item.unit_id == unit_id]
    in_shared_block = block is not None and len(block.unit_ids) > 1
    alone = block is not None and len(block.unit_ids) == 1
    evaluated, positive = (), ()
    if alone:
        evaluated, positive = _evaluated_coalitions(formation, unit_id)
    rules = {
        "unallocated": bool(unallocated),
        "served_in_coalition": in_shared_block,
        "alone_no_beneficial_coalition": alone and not positive,
        "alone_social_optimum": alone and bool(positive),
    }
    holding = [name for name, holds in rules.items() if holds]
    if len(holding) != 1:
        raise ProposalConsistencyError(f"{unit_id}: status rules {holding} (exactly one needed)")
    if holding[0] == "unallocated":
        if len(unallocated) != 1 or unallocated[0].reason not in UNALLOCATED_STATUS_CODES:
            raise ProposalConsistencyError(f"{unit_id}: unexpected unallocated entry")
        reason = unallocated[0].reason
        return reason, _unallocated_params(plan, unit_id, reason)
    if holding[0] == "served_in_coalition":
        saving = dict(block_allocation.y_rounded)[unit_id]
        return "served_in_coalition", ServedInCoalitionParams(
            block.offer_id, len(block.unit_ids) - 1, saving
        )
    component = _component_of(formation, unit_id)
    if holding[0] == "alone_no_beneficial_coalition":
        without_agreement = sum(1 for cost in evaluated if cost.cost_cents is None)
        params = AloneNoBeneficialCoalitionParams(
            component_units=len(component.unit_ids),
            singleton_component=component.status == "singleton_component",
            evaluated=len(evaluated),
            without_agreement=without_agreement,
            without_saving=len(evaluated) - without_agreement,
        )
        return "alone_no_beneficial_coalition", params
    return "alone_social_optimum", _social_optimum_params(component, positive)


def _evaluated_coalitions(formation: FormationResult, unit_id: str):
    """Coalitions evaluated by P4 that contain the unit and have at least two units."""
    evaluated = tuple(
        cost
        for cost in formation.evaluations
        if unit_id in cost.unit_ids and len(cost.unit_ids) > 1
    )
    game = _component_of(formation, unit_id).game
    positive = tuple(
        cost for cost in evaluated if cost.cost_cents is not None and game.value(cost.unit_ids) > 0
    )
    return evaluated, positive


def _social_optimum_params(component: ComponentFormation, positive) -> AloneSocialOptimumParams:
    game, solution = component.game, component.solution
    if game is None or solution is None:
        raise ProposalConsistencyError("an optimized component needs its game and solution")
    cover = game.cover_values()  # once per component concerned (B6)
    players = game.players
    component_value = cover[players]
    if component_value != solution.value_cents:
        raise ProposalConsistencyError("V* differs from the value of the P4 solution")
    alternatives = []
    for cost in positive:
        coalition: Coalition = cost.unit_ids
        rest = tuple(player for player in players if player not in coalition)
        value = game.value(coalition)
        total = value + (cover[rest] if rest else 0)
        gap = component_value - total
        if gap < 0:
            raise ProposalConsistencyError("an alternative exceeds the optimal value V*")
        alternatives.append(
            (coalition, AlternativeView(len(coalition), cost.offer_id, value, total, gap))
        )
    alternatives.sort(key=lambda item: (-item[1].best_total_cents, len(item[0]), item[0]))
    return AloneSocialOptimumParams(
        component_value_cents=component_value,
        alternatives=tuple(view for _, view in alternatives[:ALTERNATIVES_SHOWN]),
    )


def _unallocated_params(plan: TripPlan, unit_id: str, reason: str):
    stages = plan.stages
    if reason == "no_admissible_offer":
        rejected = sum(
            1
            for result in stages.lot.relation.pair_results
            if result.unit_id == unit_id and not result.admissible
        )
        return NoAdmissibleOfferParams(rejected)
    if reason == "no_solo_reference":
        return NoSoloReferenceParams(len(_unit_reference(plan, unit_id).attempts))
    if reason == "component_too_large":
        component = _component_of(stages.formation, unit_id)
        return ComponentTooLargeParams(
            len(component.unit_ids), stages.formation.limits.max_component_units
        )
    offer_ids = tuple(
        check.offer_id
        for check in stages.lot.capacity_checks
        if not check.valid and unit_id in check.unit_ids
    )
    return CapacityModelViolatedParams(offer_ids)


# --- modifiers and offer annotations (sections 5.2 and 5.3) -------------------------------


def _modifiers(unit_id, block, block_allocation, shares):
    items = []
    if block is not None and len(block.unit_ids) > 1 and block_allocation.projection_active:
        items.append(
            Explanation(
                "projection_active",
                "modifier",
                ProjectionActiveParams(
                    unit_id in block_allocation.saturated_unit_ids, block_allocation.lambda_star
                ),
            )
        )
    saturated = tuple(sorted({share.profile_id for share in shares if share.profile_saturated}))
    if saturated:
        items.append(
            Explanation(
                "budget_cap_active",
                "modifier",
                BudgetCapActiveParams(saturated, _unit_tau(shares)),
            )
        )
    return items


def _offer_annotations(plan, unit: TravelUnit, block, offers: tuple[OfferView, ...]):
    items = [
        Explanation("offer_rejected", "offer", OfferRejectedParams(view.offer_id, view.violations))
        for view in offers
        if not view.admissible
    ]
    if block is None:
        return items
    retained = next(view for view in offers if view.offer_id == block.offer_id)
    profile_ids = tuple(
        sorted(
            {note.profile_id for note in retained.notes if note.code == "direct_preference_not_met"}
        )
    )
    if profile_ids:
        catalog = {offer.offer_id: offer for offer in plan.stages.lot.relation.offers}
        items.append(
            Explanation(
                "direct_preference_not_met",
                "offer",
                DirectPreferenceNotMetParams(
                    offer_id=block.offer_id,
                    profile_ids=profile_ids,
                    retained_list_total_cents=catalog[block.offer_id].list_total(block.seats),
                    best_direct=_best_direct(offers, catalog, block.seats),
                ),
            )
        )
    return items


def _best_direct(offers, catalog: Mapping[str, OfferQuote], seats: int) -> BestDirectView | None:
    """Cheapest direct offer admissible for the unit, priced for the block's seats.

    An offer whose capacity is below the block's seats has no list price for them and is
    not a candidate. Ties go to the smallest offer_id.
    """
    candidates = [
        (catalog[view.offer_id].list_total(seats), view.offer_id)
        for view in offers
        if view.admissible and view.direct and seats <= view.capacity_seats
    ]
    if not candidates:
        return None
    total, offer_id = min(candidates)
    return BestDirectView(offer_id, total)


def _offer_views(plan: TripPlan, unit_id: str) -> tuple[OfferView, ...]:
    relation = plan.stages.lot.relation
    views = []
    for offer in relation.offers:
        decision = relation.decision(unit_id, offer.offer_id)
        views.append(
            OfferView(
                offer_id=offer.offer_id,
                supplier_id=offer.supplier_id,
                destination=offer.destination,
                departure_date=offer.departure_date,
                arrival_date=offer.arrival_date,
                direct=offer.direct,
                capacity_seats=offer.capacity_seats,
                tiers=tuple(PriceTierView(t.min_seats, t.list_per_seat) for t in offer.tiers),
                admissible=decision.admissible,
                violations=tuple(
                    ViolationView(v.rule.value, v.reason, v.profile_id) for v in decision.violations
                ),
                notes=tuple(
                    sorted(
                        (NoteView(n.code, n.profile_id) for n in decision.notes),
                        key=lambda note: (note.code, note.profile_id),
                    )
                ),
                origin=offer.origin,
                trip_type=offer.trip_type,
                outbound=_leg_view(offer.outbound),
                return_leg=_leg_view(offer.return_leg),
            )
        )
    return tuple(sorted(views, key=lambda view: view.offer_id))


def _leg_view(leg) -> LegView | None:
    if leg is None:
        return None
    return LegView(
        leg.departure_date, leg.arrival_date, leg.direct, leg.capacity_seats, leg.leg_ref
    )


# --- negotiation, block and allocation views ----------------------------------------------


def _journal_view(journal: PublicJournal, *, block: bool) -> JournalView:
    """Public view; in a block journal the leader side is hidden (B11)."""
    return JournalView(
        offer_id=journal.offer_id,
        quantity_seats=journal.quantity_seats,
        price_tier_min_seats=journal.selected_price_tier_min_seats,
        catalog_total_cents=journal.initial_seller_total_cents,
        leader_initial_total_cents=None if block else journal.initial_leader_total_cents,
        messages=tuple(
            JournalMessage(
                event.call_index,
                event.actor,
                event.outgoing_type,
                None if block and event.actor == "leader" else event.outgoing_total_cents,
            )
            for event in sorted(journal.events, key=lambda event: event.call_index)
        ),
        status=journal.status,
        terminal_reason=journal.terminal_reason,
        turns=journal.router_iterations,
        agreed_total_cents=journal.agreed_total_cents,
    )


def _unit_reference(plan: TripPlan, unit_id: str):
    references = plan.stages.references
    if references is None:
        raise ProposalConsistencyError("no references: H2 failed")
    found = [item for item in references.unit_references if item.unit_id == unit_id]
    if len(found) != 1:
        raise ProposalConsistencyError(f"{unit_id} needs exactly one solo reference entry")
    return found[0]


def _solo_view(plan: TripPlan, unit_id: str) -> SoloView | None:
    if plan.stages.references is None:
        return None
    reference = _unit_reference(plan, unit_id)
    attempts = tuple(
        SoloAttemptView(
            attempt.offer_id,
            attempt.status,
            attempt.agreed_total_cents,
            attempt.turns,
            _journal_view(_journal(plan, attempt.request_key), block=False),
        )
        for attempt in reference.attempts
    )
    return SoloView(
        reference.status,
        reference.offer_id,
        reference.agreed_total_cents,
        reference.turns,
        attempts,
    )


def _agreement_journal(plan: TripPlan, block: FormedBlock) -> PublicJournal:
    for cost in plan.stages.formation.evaluations:
        if cost.unit_ids == block.unit_ids:
            for attempt in cost.attempts:
                if attempt.offer_id == block.offer_id and attempt.status == "agreement":
                    return _journal(plan, attempt.request_key)
    raise ProposalConsistencyError(f"no agreement journal for block {block.unit_ids}")


def _block_view(plan, unit: TravelUnit, block: FormedBlock, allocation: BlockAllocation):
    journal = _agreement_journal(plan, block)
    if journal.agreed_total_cents != block.cost_cents:
        raise ProposalConsistencyError("the agreement journal differs from the block cost")
    payments = dict(allocation.payments_cents)
    seats = {item.unit_id: item.seats for item in plan.units}
    others = sorted(unit_id for unit_id in block.unit_ids if unit_id != unit.unit_id)
    members = [BlockMemberView(YOU_LABEL, True, unit.seats, payments[unit.unit_id])]
    members.extend(
        BlockMemberView(OTHER_MEMBER_LABEL.format(k=k), False, seats[other], payments[other])
        for k, other in enumerate(others, start=1)
    )
    shared = len(block.unit_ids) > 1
    return BlockView(
        offer_id=block.offer_id,
        seats=block.seats,
        price_tier_min_seats=journal.selected_price_tier_min_seats,
        catalog_total_cents=journal.initial_seller_total_cents,
        reference_total_cents=block.reference_total_cents,
        cost_cents=block.cost_cents,
        value_cents=block.value_cents,
        members=tuple(members),
        negotiation=_journal_view(journal, block=True) if shared else None,
    )


def _unit_tau(shares: tuple[TravelerShare, ...]) -> Fraction:
    taus = {share.unit_tau for share in shares}
    if len(taus) != 1:
        raise ProposalConsistencyError("tau must be the same for every seat of a unit")
    return taus.pop()


def _allocation_view(unit_id, allocation: BlockAllocation, shares) -> UnitAllocationView:
    return UnitAllocationView(
        reference_cents=dict(allocation.references_cents)[unit_id],
        phi_cents=Fraction(dict(allocation.phi)[unit_id]),
        y_cents=Fraction(dict(allocation.y)[unit_id]),
        saving_cents=dict(allocation.y_rounded)[unit_id],
        payment_cents=dict(allocation.payments_cents)[unit_id],
        projection_active=allocation.projection_active,
        unit_saturated=unit_id in allocation.saturated_unit_ids,
        lambda_star_cents=Fraction(allocation.lambda_star),
        unit_tau_cents=_unit_tau(shares),
    )


# --- schema introspection (T-CONF-3) ------------------------------------------------------


# Fields that exist in trip-proposal-v2 only, and their JSON names when they differ.
V2_ONLY_FIELDS: Mapping[type, tuple[str, ...]] = MappingProxyType(
    {
        UnitView: ("origin_key", "trip_type"),
        OfferView: ("origin", "trip_type", "outbound", "return_leg"),
    }
)
JSON_NAMES: Mapping[str, str] = MappingProxyType({"return_leg": "return"})


def public_fields(value) -> list[tuple[str, object]]:
    """(JSON name, value) of a contract object, in field order; a v1 object omits the
    v2-only fields (they are None there, see TripProposal.__post_init__)."""
    hidden = () if _route_view(value) else V2_ONLY_FIELDS.get(type(value), ())
    return [
        (JSON_NAMES.get(item.name, item.name), getattr(value, item.name))
        for item in fields(value)
        if item.name not in hidden
    ]


def _route_view(value) -> bool:
    if type(value) is UnitView:
        return value.origin_key is not None
    if type(value) is OfferView:
        return value.origin is not None
    return True


def contract_field_names(schema: str = TRIP_PROPOSAL_SCHEMA) -> frozenset[str]:
    """Every JSON field name of the public contract, for the closed-schema tests."""
    if schema not in (TRIP_PROPOSAL_SCHEMA, TRIP_PROPOSAL_SCHEMA_V2):
        raise ValueError(f"unknown schema {schema!r}")
    names: set[str] = set()
    pending: list[type] = [TripProposal, *PARAMS_BY_CODE.values()]
    seen: set[type] = set()
    while pending:
        cls = pending.pop()
        if cls in seen:
            continue
        seen.add(cls)
        hidden = V2_ONLY_FIELDS.get(cls, ()) if schema == TRIP_PROPOSAL_SCHEMA else ()
        for item in fields(cls):
            if item.name in hidden:
                continue
            names.add(JSON_NAMES.get(item.name, item.name))
            pending.extend(_dataclasses_in(item.type))
    return frozenset(names)


def _dataclasses_in(annotation) -> list[type]:
    found = []
    if isinstance(annotation, type) and is_dataclass(annotation):
        found.append(annotation)
    for argument in getattr(annotation, "__args__", ()) or ():
        found.extend(_dataclasses_in(argument))
    return found
