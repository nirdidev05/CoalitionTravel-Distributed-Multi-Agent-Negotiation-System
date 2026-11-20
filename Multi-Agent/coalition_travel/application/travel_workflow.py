"""Application orchestration from a validated user request to a broker decision."""

import asyncio
from dataclasses import dataclass
from datetime import date

from Message import Message

from coalition_travel.application.coalition_candidates import DEFAULT_LIMITS, FormationLimits
from coalition_travel.application.compatibility import evaluate_compatibility
from coalition_travel.application.profiles import build_profiles, create_buyer_agents
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.request_understanding import (
    RequestUnderstandingResult,
    StructuredRequestExtractor,
    understand_request,
)
from coalition_travel.application.trip_planning import (
    DemandPoolSnapshot,
    NegotiationMarket,
    PlanningInput,
    PlanningRequest,
    TripPlan,
    plan_lot,
)
from coalition_travel.application.trip_proposal import (
    ExtractionProvenance,
    TripProposal,
    build_trip_proposal,
)
from coalition_travel.domain.traveler_profile import CommonOffer, CompatibilityResult


@dataclass(frozen=True)
class TravelWorkflowResult:
    understanding: RequestUnderstandingResult
    buyers: tuple
    compatibility: CompatibilityResult | None


async def process_travel_request(
    text: str,
    extractor: StructuredRequestExtractor,
    request_id: str,
    negotiation_deadline: date,
    reference_date: date,
    broker,
    common_offer: CommonOffer | None = None,
    knowledge_service=None,
) -> TravelWorkflowResult:
    """Extract, validate, create profile buyers and submit a safe cohort to Broker."""
    understanding = await understand_request(
        text, extractor, reference_date, knowledge_service=knowledge_service
    )
    if understanding.status != "ready" or understanding.request is None:
        return TravelWorkflowResult(understanding, (), None)

    request = understanding.request
    profiles = build_profiles(request)
    buyers = create_buyer_agents(request, request_id, negotiation_deadline, reference_date)
    if len(profiles) > 1:
        compatibility = await asyncio.to_thread(
            evaluate_compatibility, profiles, common_offer, knowledge_service
        )
    else:
        compatibility = CompatibilityResult(
            "conditional",
            ("awaiting_compatible_profiles", "common_offer_availability_unknown"),
            tuple(profile.profile_id for profile in profiles),
        )

    # Broker receives an application-created decision with agent IDs, never LLM prose.
    broker_decision = CompatibilityResult(
        compatibility.status,
        compatibility.reasons,
        tuple(buyer.name for buyer in buyers),
        compatibility.knowledge_sources,
    )
    for buyer in buyers:
        broker.receive_message(
            Message(
                buyer,
                broker,
                "SUBSCRIBE",
                {
                    "destination": request.destination,
                    "request_id": request_id,
                    "cohort_size": len(buyers),
                    "compatibility": broker_decision,
                },
            )
        )
    return TravelWorkflowResult(understanding, buyers, compatibility)


# --- 3H path: a validated request to a public proposal (step I3-C) ------------------------


@dataclass(frozen=True)
class TravelPlanningResult:
    plan: TripPlan  # internal: digests and journals stay here
    proposal: TripProposal | None  # None exactly when plan.status == "request_rejected"

    def __post_init__(self):
        if (self.proposal is None) != (self.plan.status == "request_rejected"):
            raise ValueError("a proposal exists exactly for a planned request")


def plan_travel_request(
    request: TravelRequestDraft,
    *,
    market: NegotiationMarket,
    pool: DemandPoolSnapshot,
    reference_date: date,
    extraction: ExtractionProvenance,
    request_id: str = "user",
    limits: FormationLimits = DEFAULT_LIMITS,
) -> TravelPlanningResult:
    """Plan one request already validated by the person, then build its proposal.

    Understanding, clarification and the validation question stay with the caller (ID-10),
    so nothing is negotiated before the person validates the request. No status is added:
    the statuses are those of ``TripPlan`` (scope review §6.1).
    """
    planning = PlanningInput((PlanningRequest(request_id, request),), pool, reference_date, limits)
    plan = plan_lot(planning, market)
    if plan.status == "request_rejected":
        return TravelPlanningResult(plan, None)
    proposal = build_trip_proposal(
        plan, request_id=request_id, draft=request, extraction=extraction
    )
    return TravelPlanningResult(plan, proposal)
