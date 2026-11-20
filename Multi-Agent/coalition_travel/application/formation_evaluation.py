"""Metrics and savings decomposition of a formation result (M7, specification §11.4-11.5).

Savings decomposition of a block C negotiated on o_C, member u having its reference on
o_u, with L(o, s) = offer.list_total(s) the public list total:

    A  = sum_u L(o_u, s_u)        individual list totals on the reference offers
    B  = sum_u ref_u              individual negotiated references
    C1 = sum_u L(o_C, s_u)        common offer, individual tiers
    C2 = L(o_C, s_C)              common offer, collective tier
    D  = c(C)                     collective negotiated cost

    savings_individual_negotiation   = A - B
    savings_offer_switch             = A - C1          (any sign)
    savings_public_tier_pooling      = C1 - C2         (>= 0, proof in §11.5)
    residual_collective_negotiation  = (C2 - D) - (A - B)

Exact identities (telescoping sums, integer cents):
    v(C)  = B - D = offer_switch + public_tier_pooling + residual
    A - D = individual_negotiation + offer_switch + public_tier_pooling + residual

The residual mixes the private floor of the collective tier, the negotiation advantage
and the budget artefact of the historical strategy: it is an accounting residual, not
causally identifiable, and every report must say so (RESIDUAL_LABEL). Only public list
prices and agreed amounts are read; no seller floor.
"""

from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from coalition_travel.application.coalition_formation import FormationResult, FormedBlock
from coalition_travel.application.reference_costs import ReferenceCostsResult
from coalition_travel.domain.offer import OfferQuote

RESIDUAL_LABEL = "résidu comptable, non identifiable causalement"


class DecompositionMismatch(ValueError):
    """A definition or an identity of the savings decomposition does not hold."""


@dataclass(frozen=True)
class SavingsDecomposition:
    unit_ids: tuple[str, ...]
    offer_id: str
    individual_list_cents: int  # A
    reference_cents: int  # B
    common_offer_individual_list_cents: int  # C1
    common_offer_collective_list_cents: int  # C2
    cost_cents: int  # D
    savings_individual_negotiation: int
    savings_offer_switch: int
    savings_public_tier_pooling: int
    residual_collective_negotiation: int

    def __post_init__(self):
        a, b = self.individual_list_cents, self.reference_cents
        c1, c2 = self.common_offer_individual_list_cents, self.common_offer_collective_list_cents
        d = self.cost_cents
        expected = (a - b, a - c1, c1 - c2, (c2 - d) - (a - b))
        actual = (
            self.savings_individual_negotiation,
            self.savings_offer_switch,
            self.savings_public_tier_pooling,
            self.residual_collective_negotiation,
        )
        if actual != expected:
            raise DecompositionMismatch("a term differs from its definition")
        if (
            self.savings_offer_switch
            + self.savings_public_tier_pooling
            + (self.residual_collective_negotiation)
            != b - d
        ):
            raise DecompositionMismatch("v(C) = B - D is not the sum of its three terms")
        if self.savings_public_tier_pooling < 0:
            raise DecompositionMismatch(
                "public tier pooling is negative: a precondition T1-T5 does not hold"
            )

    @property
    def value_cents(self) -> int:
        return self.reference_cents - self.cost_cents

    @property
    def total_savings_vs_list_cents(self) -> int:
        return self.individual_list_cents - self.cost_cents


@dataclass(frozen=True)
class BlockMember:
    """One member of a block: seats, reference offer and reference amount."""

    unit_id: str
    seats: int
    reference_offer: OfferQuote
    reference_cents: int


def decompose_block(
    members: tuple[BlockMember, ...], common_offer: OfferQuote, cost_cents: int
) -> SavingsDecomposition:
    """Pure decomposition of one block from public offers and agreed amounts."""
    if not members:
        raise DecompositionMismatch("a block needs at least one member")
    unit_ids = tuple(member.unit_id for member in members)
    if unit_ids != tuple(sorted(set(unit_ids))):
        raise DecompositionMismatch("members must be unique and sorted by unit_id")
    a = sum(m.reference_offer.list_total(m.seats) for m in members)
    b = sum(m.reference_cents for m in members)
    c1 = sum(common_offer.list_total(m.seats) for m in members)
    c2 = common_offer.list_total(sum(m.seats for m in members))
    d = cost_cents
    return SavingsDecomposition(
        unit_ids=unit_ids,
        offer_id=common_offer.offer_id,
        individual_list_cents=a,
        reference_cents=b,
        common_offer_individual_list_cents=c1,
        common_offer_collective_list_cents=c2,
        cost_cents=d,
        savings_individual_negotiation=a - b,
        savings_offer_switch=a - c1,
        savings_public_tier_pooling=c1 - c2,
        residual_collective_negotiation=(c2 - d) - (a - b),
    )


def block_decomposition(
    block: FormedBlock, references: ReferenceCostsResult
) -> SavingsDecomposition:
    relation = references.effective_relation
    offers = {offer.offer_id: offer for offer in relation.offers}
    seats = {unit.unit_id: unit.seats for unit in relation.units}
    reference_offer = {
        item.unit_id: item.offer_id
        for item in references.unit_references
        if item.status == "referenced"
    }
    members = tuple(
        BlockMember(
            unit_id=unit_id,
            seats=seats[unit_id],
            reference_offer=offers[reference_offer[unit_id]],
            reference_cents=references.reference(unit_id),
        )
        for unit_id in block.unit_ids
    )
    return decompose_block(members, offers[block.offer_id], block.cost_cents)


@dataclass(frozen=True)
class DecompositionTotals:
    individual_list_cents: int
    reference_cents: int
    cost_cents: int
    savings_individual_negotiation: int
    savings_offer_switch: int
    savings_public_tier_pooling: int
    residual_collective_negotiation: int
    residual_label: str = RESIDUAL_LABEL

    def __post_init__(self):
        if (
            self.savings_offer_switch
            + self.savings_public_tier_pooling
            + self.residual_collective_negotiation
            != self.reference_cents - self.cost_cents
        ):
            raise DecompositionMismatch("structure totals break v = B - D")
        if (
            self.savings_individual_negotiation
            + self.savings_offer_switch
            + self.savings_public_tier_pooling
            + self.residual_collective_negotiation
            != self.individual_list_cents - self.cost_cents
        ):
            raise DecompositionMismatch("structure totals break A - D")


def structure_decomposition(
    result: FormationResult, references: ReferenceCostsResult
) -> DecompositionTotals:
    parts = [block_decomposition(block, references) for block in result.blocks]
    return DecompositionTotals(
        individual_list_cents=sum(p.individual_list_cents for p in parts),
        reference_cents=sum(p.reference_cents for p in parts),
        cost_cents=sum(p.cost_cents for p in parts),
        savings_individual_negotiation=sum(p.savings_individual_negotiation for p in parts),
        savings_offer_switch=sum(p.savings_offer_switch for p in parts),
        savings_public_tier_pooling=sum(p.savings_public_tier_pooling for p in parts),
        residual_collective_negotiation=sum(p.residual_collective_negotiation for p in parts),
    )


def _ratio(numerator: int, denominator: int) -> Fraction | None:
    return Fraction(numerator, denominator) if denominator else None


@dataclass(frozen=True)
class FormationMetrics:
    lot_units: int
    eligible_units: int  # players: units with an individual reference
    unserved_units: int  # P2 exclusions
    unresolved_units: int  # components above the limits
    served_rate: Fraction | None  # eligible / lot units
    block_count: int
    coalition_count: int  # blocks of two units or more
    units_in_coalitions: int
    coalition_sizes: tuple[tuple[int, int], ...]  # (size, count) for blocks of size >= 2
    total_reference_cents: int
    total_cost_cents: int
    social_value_cents: int
    savings_rate: Fraction | None  # V / sum ref
    candidates: int
    feasible_candidates: int
    feasibility_rate: Fraction | None
    negotiations: int  # (C, o) attempts
    agreements: int
    agreement_rate: Fraction | None
    decomposition: DecompositionTotals | None


def formation_metrics(
    result: FormationResult, lot_unit_count: int, references: ReferenceCostsResult | None
) -> FormationMetrics:
    attempts = [attempt for cost in result.evaluations for attempt in cost.attempts]
    agreements = sum(1 for attempt in attempts if attempt.status == "agreement")
    feasible = sum(1 for cost in result.evaluations if cost.feasible)
    eligible = sum(len(item.unit_ids) for item in result.components)
    sizes = Counter(len(block.unit_ids) for block in result.blocks if len(block.unit_ids) > 1)
    return FormationMetrics(
        lot_units=lot_unit_count,
        eligible_units=eligible,
        unserved_units=len(result.unserved),
        unresolved_units=len(result.unresolved_unit_ids),
        served_rate=_ratio(eligible, lot_unit_count),
        block_count=len(result.blocks),
        coalition_count=sum(sizes.values()),
        units_in_coalitions=sum(size * count for size, count in sizes.items()),
        coalition_sizes=tuple(sorted(sizes.items())),
        total_reference_cents=result.total_reference_cents,
        total_cost_cents=result.total_cost_cents,
        social_value_cents=result.total_value_cents,
        savings_rate=_ratio(result.total_value_cents, result.total_reference_cents),
        candidates=len(result.evaluations),
        feasible_candidates=feasible,
        feasibility_rate=_ratio(feasible, len(result.evaluations)),
        negotiations=len(attempts),
        agreements=agreements,
        agreement_rate=_ratio(agreements, len(attempts)),
        decomposition=None
        if references is None or not result.blocks
        else structure_decomposition(result, references),
    )
