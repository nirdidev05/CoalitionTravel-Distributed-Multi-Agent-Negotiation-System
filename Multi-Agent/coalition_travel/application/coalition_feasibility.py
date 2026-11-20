"""Independent structural feasibility check of a candidate, before any negotiation (M2).

Structural feasibility is what can be decided without the oracle: the lot satisfies H2,
every member has an individual reference, the members lie in one effective component,
the declared common offers are exactly the recomputed intersection, and the coalition's
seats fit in each common offer. Economic feasibility (an agreement) is decided by the
negotiation (M3). The check recomputes everything from P2 objects instead of trusting
the generator (M1): a disagreement is a defect and raises CandidateInfeasible.
Specification: docs/PHASE_P4_SPECIFICATION.md module card M2.
"""

from coalition_travel.application.coalition_candidates import CoalitionCandidate
from coalition_travel.application.lot_admissibility import LotAdmissibilityResult
from coalition_travel.application.reference_costs import ReferenceCostsResult


class CandidateInfeasible(ValueError):
    """A candidate contradicts the P2 relation; this is a defect, never a status."""


def check_structural_feasibility(
    candidate: CoalitionCandidate,
    lot: LotAdmissibilityResult,
    references: ReferenceCostsResult,
) -> None:
    if not isinstance(candidate, CoalitionCandidate):
        raise TypeError("candidate must be a CoalitionCandidate")
    if not isinstance(lot, LotAdmissibilityResult):
        raise TypeError("lot must be a LotAdmissibilityResult")
    if not isinstance(references, ReferenceCostsResult):
        raise TypeError("references must be a ReferenceCostsResult")
    lot.require_optimizable()  # H2; raises CapacityModelViolated
    if references.admissibility_id != lot.admissibility_id:
        raise CandidateInfeasible("references were computed for another lot")
    referenced = {
        item.unit_id for item in references.unit_references if item.status == "referenced"
    }
    missing = [unit for unit in candidate.unit_ids if unit not in referenced]
    if missing:
        raise CandidateInfeasible(f"units without individual reference: {missing}")
    containing = [
        component
        for component in references.effective_components
        if set(candidate.unit_ids) <= {unit.unit_id for unit in component.units}
    ]
    if len(containing) != 1:
        raise CandidateInfeasible("a candidate must lie inside exactly one effective component")
    relation = references.effective_relation
    common = tuple(offer.offer_id for offer in relation.common_offers(candidate.unit_ids))
    if common != candidate.common_offer_ids:
        raise CandidateInfeasible(
            f"declared common offers {candidate.common_offer_ids} differ from {common}"
        )
    units = {unit.unit_id: unit for unit in relation.units}
    seats = sum(units[unit_id].seats for unit_id in candidate.unit_ids)
    for offer in relation.common_offers(candidate.unit_ids):
        if seats > offer.capacity_seats:
            raise CandidateInfeasible(
                f"{seats} seats exceed the capacity of {offer.offer_id} ({offer.capacity_seats})"
            )
