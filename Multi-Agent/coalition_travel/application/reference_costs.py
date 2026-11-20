"""Compute individual negotiated references through an abstract oracle.

ref_u = c({u}) is the lowest agreed total over u's admissible offers (ties broken by
offer_id), negotiated with the same request constructor as a coalition. Every attempt is
kept with its distinct outcome (agreement, rejected, turn_limit). A unit without any
admissible offer is never negotiated (``no_admissible_offer``); a unit whose solo
negotiations all fail is excluded with ``no_solo_reference`` and its attempt details.
Components are then recomputed on the remaining units.
"""

from dataclasses import dataclass
from typing import Literal

from coalition_travel.application.lot_admissibility import (
    LotAdmissibilityResult,
    UnitExclusion,
)
from coalition_travel.domain.negotiation_request import (
    NEGOTIATION_STATUSES,
    NegotiationOracle,
    NegotiationOutcome,
    NegotiationStatus,
    negotiation_request_for,
)
from coalition_travel.domain.offer_graph import (
    AdmissibilityRelation,
    OfferComponent,
    connected_components,
)

ReferenceStatus = Literal["referenced", "no_admissible_offer", "no_solo_reference"]
REFERENCE_STATUSES = frozenset({"referenced", "no_admissible_offer", "no_solo_reference"})


class NegotiationOracleContractError(ValueError):
    """An oracle response violates the public P2 negotiation contract."""


@dataclass(frozen=True)
class ReferenceAttempt:
    """One solo negotiation of a unit with one admissible offer."""

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
class UnitReferenceCost:
    unit_id: str
    status: ReferenceStatus
    offer_id: str | None = None
    agreed_total_cents: int | None = None
    request_key: str | None = None
    turns: int | None = None
    oracle_configuration_id: str | None = None
    attempts: tuple[ReferenceAttempt, ...] = ()

    def __post_init__(self):
        if self.status not in REFERENCE_STATUSES:
            raise ValueError(f"unsupported reference status {self.status!r}")
        if type(self.attempts) is not tuple or any(
            type(item) is not ReferenceAttempt for item in self.attempts
        ):
            raise TypeError("attempts must be a tuple of ReferenceAttempt")
        offer_ids = tuple(item.offer_id for item in self.attempts)
        if offer_ids != tuple(sorted(set(offer_ids))):
            raise ValueError("attempts must be unique and sorted by offer_id")
        agreements = [item for item in self.attempts if item.status == "agreement"]
        if self.status == "no_admissible_offer" and self.attempts:
            raise ValueError("a unit without admissible offer is never negotiated")
        if self.status == "no_solo_reference" and (not self.attempts or agreements):
            raise ValueError("no_solo_reference needs attempts and no agreement")
        selected = (self.offer_id, self.agreed_total_cents)
        if self.status == "referenced":
            if not agreements:
                raise ValueError("a referenced unit needs at least one agreement")
            best = min(agreements, key=lambda item: (item.agreed_total_cents, item.offer_id))
            if selected != (best.offer_id, best.agreed_total_cents):
                raise ValueError("the reference must be the lowest agreement, ties by offer_id")
        elif selected != (None, None):
            raise ValueError("only a referenced unit carries an offer and an amount")


@dataclass(frozen=True)
class ReferenceCostsResult:
    admissibility_id: str
    oracle_configuration_id: str | None
    unit_references: tuple[UnitReferenceCost, ...]
    exclusions: tuple[UnitExclusion, ...]  # no_solo_reference only
    effective_relation: AdmissibilityRelation
    effective_components: tuple[OfferComponent, ...]

    def reference(self, unit_id: str) -> int:
        """ref_u in cents; KeyError for an unknown or unreferenced unit."""
        for item in self.unit_references:
            if item.unit_id == unit_id and item.status == "referenced":
                return item.agreed_total_cents
        raise KeyError(f"unit {unit_id!r} has no individual reference")


def _validate_outcome(
    outcome: object,
    *,
    expected_key: str,
    reservation_cents: int,
    expected_configuration: str | None,
) -> str:
    if type(outcome) is not NegotiationOutcome:
        raise NegotiationOracleContractError("oracle must return a NegotiationOutcome")
    if outcome.request_key != expected_key:
        raise NegotiationOracleContractError("oracle returned a different request_key")
    if type(outcome.status) is not str or outcome.status not in NEGOTIATION_STATUSES:
        raise NegotiationOracleContractError(
            f"oracle returned an unsupported status {outcome.status!r}"
        )
    if type(outcome.turns) is not int or outcome.turns < 0:
        raise NegotiationOracleContractError("oracle turns must be a non-negative integer")
    if (
        type(outcome.oracle_configuration_id) is not str
        or not outcome.oracle_configuration_id.strip()
    ):
        raise NegotiationOracleContractError("oracle_configuration_id must not be blank")
    if (
        expected_configuration is not None
        and outcome.oracle_configuration_id != expected_configuration
    ):
        raise NegotiationOracleContractError("oracle configuration changed within one lot")
    if outcome.status == "agreement":
        if type(outcome.agreed_total_cents) is not int:
            raise NegotiationOracleContractError("an agreement needs an integer amount in cents")
        if not 0 < outcome.agreed_total_cents <= reservation_cents:
            raise NegotiationOracleContractError(
                "agreed total must be positive and no greater than the reservation"
            )
    elif outcome.agreed_total_cents is not None:
        raise NegotiationOracleContractError(f"a {outcome.status} outcome must not carry an amount")
    return outcome.oracle_configuration_id


def validate_negotiation_outcome(
    outcome: object,
    *,
    expected_key: str,
    reservation_cents: int,
    expected_configuration: str | None,
) -> str:
    """Public form of the P2 oracle contract check, reused by P4 (decision D7).

    Returns the outcome's oracle_configuration_id; raises NegotiationOracleContractError.
    """
    return _validate_outcome(
        outcome,
        expected_key=expected_key,
        reservation_cents=reservation_cents,
        expected_configuration=expected_configuration,
    )


def compute_reference_costs(
    lot: LotAdmissibilityResult, oracle: NegotiationOracle
) -> ReferenceCostsResult:
    """Negotiate every admissible unit/offer pair alone and keep each unit's lowest agreement."""
    if not isinstance(lot, LotAdmissibilityResult):
        raise TypeError("lot must be a LotAdmissibilityResult")
    lot.require_optimizable()
    if not callable(getattr(oracle, "negotiate", None)):
        raise TypeError("oracle must provide negotiate(request)")

    references: list[UnitReferenceCost] = []
    exclusions: list[UnitExclusion] = []
    retained_units: set[str] = set()
    oracle_configuration = None
    for unit in lot.relation.units:
        admissible_offers = lot.relation.offers_for(unit.unit_id)
        if not admissible_offers:
            references.append(UnitReferenceCost(unit.unit_id, "no_admissible_offer"))
            continue
        attempts: list[ReferenceAttempt] = []
        for offer in admissible_offers:
            request = negotiation_request_for((unit,), offer)
            outcome = oracle.negotiate(request)
            oracle_configuration = _validate_outcome(
                outcome,
                expected_key=request.request_key,
                reservation_cents=request.reservation_cents,
                expected_configuration=oracle_configuration,
            )
            attempts.append(
                ReferenceAttempt(
                    offer_id=offer.offer_id,
                    request_key=outcome.request_key,
                    status=outcome.status,
                    agreed_total_cents=outcome.agreed_total_cents,
                    turns=outcome.turns,
                )
            )
        agreements = [item for item in attempts if item.status == "agreement"]
        if not agreements:
            references.append(
                UnitReferenceCost(unit.unit_id, "no_solo_reference", attempts=tuple(attempts))
            )
            exclusions.append(
                UnitExclusion(
                    unit.unit_id,
                    "no_solo_reference",
                    tuple(
                        f"{item.offer_id}: {item.status} ({item.turns} turns)" for item in attempts
                    ),
                )
            )
            continue
        best = min(agreements, key=lambda item: (item.agreed_total_cents, item.offer_id))
        references.append(
            UnitReferenceCost(
                unit_id=unit.unit_id,
                status="referenced",
                offer_id=best.offer_id,
                agreed_total_cents=best.agreed_total_cents,
                request_key=best.request_key,
                turns=best.turns,
                oracle_configuration_id=oracle_configuration,
                attempts=tuple(attempts),
            )
        )
        retained_units.add(unit.unit_id)

    effective_relation = lot.relation.with_units(retained_units)
    return ReferenceCostsResult(
        admissibility_id=lot.admissibility_id,
        oracle_configuration_id=oracle_configuration,
        unit_references=tuple(references),
        exclusions=tuple(exclusions),
        effective_relation=effective_relation,
        effective_components=connected_components(effective_relation),
    )
