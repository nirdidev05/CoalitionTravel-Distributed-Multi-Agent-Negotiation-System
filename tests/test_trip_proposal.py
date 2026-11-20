"""I3-A: the public proposal ``trip-proposal-v1`` built from a TripPlan (scope review §4, §5).

Scenarios use the versioned catalogue v1 and demand pool v1 at the reference date of I1
and I2 (2026-11-19). Every status code comes from the real pipeline, except the two
constructed cases named as such (``projection_active`` and a zero-value coalition):
the catalogue v1 cannot produce them (I3-A4).

The confidentiality tests T-CONF-1 to T-CONF-3 run here on the DTO tree; I3-B repeats
them on the JSON and the text output.
"""

import hashlib
import json
import re
from dataclasses import fields, is_dataclass, replace
from datetime import date
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType

import pytest
from coalition_travel.application.coalition_candidates import FormationLimits
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.savings_allocation import UnallocatedUnit
from coalition_travel.application.trip_planning import (
    DemandPoolSnapshot,
    PlanningInput,
    PlanningRequest,
    plan_lot,
)
from coalition_travel.application.trip_proposal import (
    EXPLANATION_CODES,
    MODIFIER_CODES,
    OFFER_CODES,
    PARAMS_BY_CODE,
    REPLAY_FORMAT_VERSION,
    REQUEST_CODES,
    SIMULATION_NOTICE,
    UNIT_STATUS_CODES,
    Explanation,
    ExtractionProvenance,
    NoSoloReferenceParams,
    ProposalConsistencyError,
    TripProposal,
    build_trip_proposal,
    contract_field_names,
    draft_json_extraction,
    llm_extraction,
    replay_extraction,
)
from coalition_travel.domain.coalition_game import CoalitionGame
from coalition_travel.domain.offer import (
    OfferQuote,
    PriceTier,
    SellerFloorTier,
    SellerTerms,
    SellerTermsBook,
)
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.infrastructure.demand.demand_pool import load_demand_pool
from coalition_travel.infrastructure.negotiation.market import open_simulated_market
from coalition_travel.infrastructure.negotiation.simulated_oracle import NegotiationJournal
from p4_support import REFERENCE

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/catalog/catalog_v1.json"
POOL_PATH = ROOT / "data/demand/demand_pool_v1.jsonl"
NORTHSTAR = "tyo-northstar-20270310"
SKYWAYS = "tyo-skyways-20270312"
CLOUDWING = "rom-cloudwing-20270405"
HEX64 = re.compile(r"[0-9a-f]{64}")


def draft(destination="Tokyo", travellers=1, budget="520", **extra):
    return TravelRequestDraft(
        destination=destination, travellers=travellers, budget_per_person=budget, **extra
    )


E3_DRAFT = draft("Tokyo", 8, "500")


@pytest.fixture(scope="module")
def pool():
    return load_demand_pool(POOL_PATH)


def plan_for(drafts, pool, limits=None):
    """drafts: {request_id: TravelRequestDraft}; one fresh market per plan."""
    market = open_simulated_market(CATALOG_PATH, REFERENCE)
    focus = tuple(PlanningRequest(request_id, item) for request_id, item in drafts.items())
    if limits is None:
        planning = PlanningInput(focus, pool, REFERENCE)
    else:
        planning = PlanningInput(focus, pool, REFERENCE, limits)
    return plan_lot(planning, market)


def proposal_of(plan, request_id, item, extraction=None):
    return build_trip_proposal(
        plan,
        request_id=request_id,
        draft=item,
        extraction=extraction or draft_json_extraction(),
    )


def single(item, pool, limits=None):
    plan = plan_for({"user": item}, pool, limits)
    return plan, proposal_of(plan, "user", item)


@pytest.fixture(scope="module")
def e3(pool):
    return single(E3_DRAFT, pool)


def walk(node, path="$"):
    """(path, leaf) for every leaf of a proposal: dataclasses, mappings and tuples."""
    if is_dataclass(node):
        for item in fields(node):
            yield from walk(getattr(node, item.name), f"{path}.{item.name}")
    elif isinstance(node, MappingProxyType | dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, tuple):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")
    else:
        yield path, node


def node_types(node, found=None):
    found = set() if found is None else found
    found.add(type(node))
    if is_dataclass(node):
        for item in fields(node):
            node_types(getattr(node, item.name), found)
    elif isinstance(node, MappingProxyType | dict):
        for value in node.values():
            node_types(value, found)
    elif isinstance(node, tuple):
        for value in node:
            node_types(value, found)
    return found


def numbers(proposal):
    """Every numeric leaf (int or Fraction, never bool) with its path."""
    return [
        (path, value)
        for path, value in walk(proposal)
        if isinstance(value, int | Fraction) and not isinstance(value, bool)
    ]


def strings(proposal):
    return [(path, value) for path, value in walk(proposal) if isinstance(value, str)]


def frozen_dump(item):
    return {
        key: tuple(value) if isinstance(value, list) else value
        for key, value in item.model_dump(mode="json").items()
    }


# --- I3-A1: the nine elements on E3 ----------------------------------------------------------


def test_e3_proposal_shows_the_nine_elements(e3):
    plan, proposal = e3
    assert proposal.schema == "trip-proposal-v1"
    assert proposal.simulation.notice == SIMULATION_NOTICE
    assert (proposal.simulation.synthetic_catalog, proposal.simulation.booking) == (True, False)
    # (1) the offers, sorted, with their admissibility
    assert [offer.offer_id for offer in proposal.offers] == [CLOUDWING, NORTHSTAR, SKYWAYS]
    rome = proposal.offers[0]
    assert not rome.admissible and [v.reason for v in rome.violations] == ["destination_mismatch"]
    assert proposal.offers[1].admissible and proposal.offers[2].admissible
    # (2) the members of the block, anonymized, the person first
    block = proposal.block
    assert [(m.label, m.you, m.seats, m.payment_cents) for m in block.members] == [
        ("vous", True, 8, 380_100),
        ("autre demande 1", False, 1, 48_000),
        ("autre demande 2", False, 1, 48_900),
        ("autre demande 3", False, 1, 51_000),
    ]
    # (3) the solo negotiations and the block negotiation
    assert [attempt.offer_id for attempt in proposal.solo.attempts] == [NORTHSTAR, SKYWAYS]
    assert all(a.journal.leader_initial_total_cents is not None for a in proposal.solo.attempts)
    assert proposal.solo.agreed_total_cents == 384_000
    negotiation = block.negotiation
    assert negotiation.leader_initial_total_cents is None
    assert all(m.total_cents is None for m in negotiation.messages if m.actor == "leader")
    # (4) the retained offer, (5) catalogue price and negotiated price, (6) value created
    assert block.offer_id == NORTHSTAR and block.seats == 11
    assert block.price_tier_min_seats == 6
    assert block.catalog_total_cents == 528_000 and block.cost_cents == 528_000
    assert block.reference_total_cents == 537_000 and block.value_cents == 9_000
    # (7) the amounts of the travellers: 4 x 47 513 + 4 x 47 512
    assert sorted(t.amount_cents for t in proposal.travellers) == [47_512] * 4 + [47_513] * 4
    assert sum(t.amount_cents for t in proposal.travellers) == 380_100
    # (8) rejections and explanations, (9) not alone here
    assert [(e.code, e.offer_id) for e in proposal.explanations] == [
        ("served_in_coalition", ""),
        ("offer_rejected", CLOUDWING),
    ]
    params = proposal.explanations[0].params
    assert (params.offer_id, params.other_requests, params.saving_cents) == (NORTHSTAR, 3, 3_900)
    allocation = proposal.allocation
    assert (allocation.reference_cents, allocation.phi_cents, allocation.saving_cents) == (
        384_000,
        Fraction(3_900),
        3_900,
    )
    assert allocation.payment_cents == plan.allocation.payment("user")
    assert proposal.status.modifiers == () and not allocation.projection_active


def test_e3_provenance_carries_versions_and_no_digest(e3):
    plan, proposal = e3
    provenance = proposal.provenance
    assert provenance.reference_date == date(2026, 11, 19)
    assert (provenance.catalog_version, provenance.pool_version) == (
        "catalog-v1",
        plan.pool_version,
    )
    assert provenance.planning_version == "3h-planning-v1"
    assert (provenance.formation_adapter_version, provenance.formation_method) == (
        "p4-formation-v1",
        "idp",
    )
    assert (provenance.allocation_version, provenance.theta_cents) == ("p5-allocation-v1", 0)
    assert provenance.extraction == draft_json_extraction()
    assert {item.name for item in fields(provenance)} == {
        "reference_date",
        "catalog_version",
        "pool_version",
        "planning_version",
        "formation_adapter_version",
        "formation_method",
        "allocation_version",
        "theta_cents",
        "extraction",
    }


def test_the_request_block_is_the_validated_draft_as_is(e3):
    _, proposal = e3
    assert proposal.request.request_id == "user"
    assert dict(proposal.request.draft) == frozen_dump(E3_DRAFT)


def test_pinned_lot_has_a_proposal_for_each_focus_request(pool):
    pinned = {"a": draft("Tokyo", 1, "520"), "e": draft("Rome", 2, "450")}
    others = {"b": ("Tokyo", 1, "540"), "c": ("Tokyo", 2, "500")}
    others |= {"d": ("Tokyo", 1, "600"), "f": ("Rome", 1, "330")}
    snapshot = DemandPoolSnapshot(
        "test-pool",
        "0" * 64,
        "catalog-v1",
        tuple(PlanningRequest(key, draft(*value)) for key, value in others.items()),
    )
    plan = plan_for(pinned, snapshot)
    for request_id, item in pinned.items():
        proposal = proposal_of(plan, request_id, item)
        assert proposal.unit.unit_id == request_id
        assert proposal.status.code in UNIT_STATUS_CODES
        if proposal.block is not None:
            assert proposal.allocation.payment_cents == plan.allocation.payment(request_id)


def test_building_twice_gives_equal_proposals(pool, e3):
    plan, proposal = e3
    assert proposal_of(plan, "user", E3_DRAFT) == proposal
    again, _ = single(E3_DRAFT, pool)
    assert proposal_of(again, "user", E3_DRAFT) == proposal


# --- I3-A2 and I3-A4: exactly one status, one test per code ----------------------------------


def test_no_admissible_offer(pool):
    _, proposal = single(draft("Alger", 2, "500"), pool)
    assert proposal.status.code == "no_admissible_offer"
    assert proposal.explanations[0].params.rejected_offers == 3
    assert all(not o.admissible for o in proposal.offers)
    assert {v.reason for o in proposal.offers for v in o.violations} == {"destination_mismatch"}
    assert proposal.solo.status == "no_admissible_offer" and proposal.solo.attempts == ()
    assert (proposal.block, proposal.allocation, proposal.travellers) == (None, None, ())


def test_no_solo_reference(pool):
    _, proposal = single(draft("Tokyo", 1, "100"), pool)
    assert proposal.status.code == "no_solo_reference"
    assert proposal.explanations[0].params == NoSoloReferenceParams(failed_attempts=2)
    assert proposal.solo.status == "no_solo_reference"
    assert all(a.status != "agreement" for a in proposal.solo.attempts)
    assert proposal.block is None


def test_component_too_large(pool):
    _, proposal = single(draft("Tokyo", 1, "520"), pool, FormationLimits(max_component_units=4))
    assert proposal.status.code == "component_too_large"
    params = proposal.explanations[0].params
    assert (params.component_units, params.max_component_units) == (5, 4)
    assert proposal.block is None and proposal.solo.status == "referenced"


def test_capacity_model_violated_has_no_solo_view(pool):
    drafts = {"user": draft("Rome", 20, "400"), "user-2": draft("Rome", 20, "400")}
    plan = plan_for(drafts, pool)
    proposal = proposal_of(plan, "user", drafts["user"])
    assert proposal.status.code == "capacity_model_violated"
    assert proposal.solo is None and proposal.block is None
    assert proposal.explanations[0].params.offer_ids == (CLOUDWING,)


def test_served_in_coalition(e3):
    assert e3[1].status.code == "served_in_coalition"


def test_alone_no_beneficial_coalition_in_a_singleton_component(pool):
    empty = DemandPoolSnapshot(pool.version, pool.sha256, pool.catalog_version, ())
    _, proposal = single(draft("Tokyo", 2, "500"), empty)
    assert proposal.status.code == "alone_no_beneficial_coalition"
    params = proposal.explanations[0].params
    assert (params.component_units, params.singleton_component) == (1, True)
    assert (params.evaluated, params.without_agreement, params.without_saving) == (0, 0, 0)
    assert proposal.block.members[0].you and len(proposal.block.members) == 1
    assert proposal.block.negotiation is None
    assert proposal.allocation.payment_cents == proposal.solo.agreed_total_cents


def test_alone_social_optimum_describes_the_structure_and_the_alternatives(pool):
    plan, proposal = single(draft("Tokyo", 2, "500"), pool)
    assert proposal.status.code == "alone_social_optimum"
    params = proposal.explanations[0].params
    component = next(c for c in plan.formation.components if "user" in c.unit_ids)
    assert params.component_value_cents == component.solution.value_cents == 2_520
    alternatives = params.alternatives
    assert 1 <= len(alternatives) <= 3
    assert [a.best_total_cents for a in alternatives] == sorted(
        (a.best_total_cents for a in alternatives), reverse=True
    )
    assert all(a.value_cents > 0 and a.gap_cents >= 0 for a in alternatives)
    # a zero gap is an equal total value, decided by the P4 tie-break (scope review §5.4)
    assert alternatives[0].gap_cents == 0 and alternatives[0].size == 3
    # independent recomputation of the three allowed derivations (I3-A3)
    game = component.game
    cover = game.cover_values()
    for alternative in alternatives:
        assert alternative.gap_cents == cover[game.players] - alternative.best_total_cents
    assert proposal.allocation.payment_cents == proposal.solo.agreed_total_cents


def test_the_rome_pattern_is_also_a_social_optimum(pool):
    _, proposal = single(draft("Rome", 3, "450"), pool)
    assert proposal.status.code == "alone_social_optimum"
    assert [a.value_cents for a in proposal.explanations[0].params.alternatives] == [
        9_000,
        6_000,
        3_000,
    ]


def test_a_zero_value_coalition_is_not_beneficial_constructed(pool):
    """Constructed (the catalogue v1 has no such case): v(C) = 0 is not a saving."""
    plan, _ = single(draft("Tokyo", 2, "500"), pool)
    formation = plan.formation
    index, component = next(
        (i, c) for i, c in enumerate(formation.components) if "user" in c.unit_ids
    )
    game = component.game
    shared = [c for c, _ in game.values if "user" in c and len(c) > 1]
    values = tuple((c, (0 if c == shared[0] else -1) if c in shared else v) for c, v in game.values)
    flat = CoalitionGame(
        game.component_id, game.players, game.references, values, game.oracle_configuration_id
    )
    components = list(formation.components)
    components[index] = replace(component, game=flat)
    stages = replace(plan.stages, formation=replace(formation, components=tuple(components)))
    proposal = proposal_of(replace(plan, stages=stages), "user", draft("Tokyo", 2, "500"))
    assert proposal.status.code == "alone_no_beneficial_coalition"
    params = proposal.explanations[0].params
    feasible = [c for c in formation.evaluations if "user" in c.unit_ids and len(c.unit_ids) > 1]
    assert params.evaluated == len(feasible)
    assert params.without_saving == sum(1 for c in feasible if c.cost_cents is not None)
    assert params.without_agreement == sum(1 for c in feasible if c.cost_cents is None)


def test_two_status_rules_holding_at_once_are_refused(e3):
    plan, _ = e3
    allocation = plan.allocation
    unallocated = allocation.unallocated + (UnallocatedUnit("user", "no_solo_reference"),)
    broken = replace(plan, allocation=replace(allocation, unallocated=unallocated))
    with pytest.raises(ProposalConsistencyError, match="exactly one"):
        proposal_of(broken, "user", E3_DRAFT)


# --- modifiers and offer annotations (§5.2, §5.3) -------------------------------------------


def test_budget_cap_active(pool):
    profiles = [
        {"profile_id": "p1", "traveller_count": 1, "budget_per_person": "300"},
        {"profile_id": "p2", "traveller_count": 3, "budget_per_person": "700"},
    ]
    _, proposal = single(draft("Tokyo", 4, "600", profiles=profiles), pool)
    assert proposal.status.modifiers == ("budget_cap_active",)
    params = next(e for e in proposal.explanations if e.code == "budget_cap_active").params
    assert params.saturated_profile_ids == ("p1",)
    assert params.unit_tau_cents == proposal.allocation.unit_tau_cents
    p1 = [t for t in proposal.travellers if t.profile_id == "p1"]
    assert [(t.amount_cents, t.profile_saturated) for t in p1] == [(30_000, True)]


def test_projection_active_constructed(e3):
    """Constructed: the catalogue v1 never activates the projection (report I2, §5.4)."""
    plan, _ = e3
    allocation = plan.allocation
    blocks = tuple(
        replace(b, projection_active=True, saturated_unit_ids=("user",), lambda_star=Fraction(-100))
        if "user" in b.unit_ids
        else b
        for b in allocation.blocks
    )
    forced = replace(plan, allocation=replace(allocation, blocks=blocks))
    proposal = proposal_of(forced, "user", E3_DRAFT)
    assert proposal.status.modifiers == ("projection_active",)
    params = next(e for e in proposal.explanations if e.code == "projection_active").params
    assert (params.unit_saturated, params.lambda_star_cents) == (True, Fraction(-100))


def test_a_lone_unit_never_carries_projection_active_constructed(pool):
    plan, _ = single(draft("Tokyo", 2, "500"), pool)
    allocation = plan.allocation
    blocks = tuple(
        replace(b, projection_active=True) if b.unit_ids == ("user",) else b
        for b in allocation.blocks
    )
    forced = replace(plan, allocation=replace(allocation, blocks=blocks))
    assert proposal_of(forced, "user", draft("Tokyo", 2, "500")).status.modifiers == ()


def test_offer_rejected_once_per_rejected_offer_in_rule_order(pool):
    _, proposal = single(draft("Alger", 2, "500"), pool)
    rejected = [e for e in proposal.explanations if e.code == "offer_rejected"]
    assert [e.params.offer_id for e in rejected] == [CLOUDWING, NORTHSTAR, SKYWAYS]
    for explanation in rejected:
        offer = next(o for o in proposal.offers if o.offer_id == explanation.params.offer_id)
        assert explanation.params.violations == offer.violations


def test_direct_preference_not_met_on_the_retained_offer(pool):
    item = draft("Tokyo", 1, "700", direct_flight="preferred", excluded_suppliers=["Northstar"])
    plan, proposal = single(item, pool)
    assert proposal.block.offer_id == SKYWAYS
    explanation = next(e for e in proposal.explanations if e.code == "direct_preference_not_met")
    params = explanation.params
    skyways = plan.stages.lot.relation.offers[2]
    assert skyways.offer_id == SKYWAYS
    assert params.offer_id == SKYWAYS and params.profile_ids == ("all",)
    assert params.retained_list_total_cents == skyways.list_total(proposal.block.seats)
    assert params.best_direct is None  # the only direct offer is excluded


def test_a_note_on_another_offer_is_not_an_annotation(pool):
    _, proposal = single(draft("Tokyo", 1, "700", direct_flight="preferred"), pool)
    assert proposal.block.offer_id == NORTHSTAR
    assert all(e.code != "direct_preference_not_met" for e in proposal.explanations)
    skyways = next(o for o in proposal.offers if o.offer_id == SKYWAYS)
    assert [n.code for n in skyways.notes] == ["direct_preference_not_met"]


# --- closed code sets and explanation parameters ---------------------------------------------


def test_the_thirteen_codes_are_leveled_without_addition():
    assert len(EXPLANATION_CODES) == len(set(EXPLANATION_CODES)) == 13
    assert (len(UNIT_STATUS_CODES), len(MODIFIER_CODES), len(OFFER_CODES)) == (7, 2, 2)
    assert set(REQUEST_CODES) == {"needs_clarification", "unknown_place"}
    assert set(PARAMS_BY_CODE) == set(EXPLANATION_CODES) - set(REQUEST_CODES)


def test_an_explanation_refuses_request_codes_and_foreign_parameters():
    with pytest.raises(ProposalConsistencyError):
        Explanation("needs_clarification", "status", NoSoloReferenceParams(0))
    with pytest.raises(ProposalConsistencyError):
        Explanation("no_admissible_offer", "status", NoSoloReferenceParams(0))
    with pytest.raises(ProposalConsistencyError):
        Explanation("no_solo_reference", "modifier", NoSoloReferenceParams(0))


def test_the_proposal_checks_its_own_invariants(e3):
    _, proposal = e3
    with pytest.raises(ProposalConsistencyError, match="canonical order"):
        replace(proposal, explanations=tuple(reversed(proposal.explanations)))
    with pytest.raises(ProposalConsistencyError, match="block and allocation"):
        replace(proposal, allocation=None)
    with pytest.raises(ProposalConsistencyError, match="sum to the negotiated"):
        members = (replace(proposal.block.members[0], payment_cents=0),)
        replace(
            proposal, block=replace(proposal.block, members=members + proposal.block.members[1:])
        )
    with pytest.raises(ProposalConsistencyError, match="schema"):
        replace(proposal, schema="trip-proposal-v2")


def test_duplicate_modifiers_and_annotations_are_refused(pool, e3):
    """Hardening requested by the I3-A review: a hand-built DTO cannot repeat a code."""
    profiles = [
        {"profile_id": "p1", "traveller_count": 1, "budget_per_person": "300"},
        {"profile_id": "p2", "traveller_count": 3, "budget_per_person": "700"},
    ]
    _, capped = single(draft("Tokyo", 4, "600", profiles=profiles), pool)
    modifier = next(e for e in capped.explanations if e.level == "modifier")
    explanations = tuple(sorted(capped.explanations + (modifier,), key=Explanation.sort_key))
    with pytest.raises(ProposalConsistencyError, match="distinct codes"):
        replace(
            capped,
            status=replace(capped.status, modifiers=(modifier.code, modifier.code)),
            explanations=explanations,
        )
    _, proposal = e3
    rejected = next(e for e in proposal.explanations if e.code == "offer_rejected")
    with pytest.raises(ProposalConsistencyError, match="appears twice"):
        replace(proposal, explanations=proposal.explanations + (rejected,))


def test_the_builder_refuses_inputs_outside_its_contract(pool, e3):
    plan, _ = e3
    with pytest.raises(ProposalConsistencyError, match="not a focus request"):
        proposal_of(plan, "pool-tyo-01", E3_DRAFT)
    with pytest.raises(ProposalConsistencyError, match="not the request of this unit"):
        proposal_of(plan, "user", draft("Tokyo", 8, "501"))
    rejected = plan_for({"user": draft("Tokyo", 1, "0.001")}, pool)
    assert rejected.status == "request_rejected"
    with pytest.raises(ProposalConsistencyError, match="planned lot"):
        proposal_of(rejected, "user", draft("Tokyo", 1, "0.001"))
    with pytest.raises(TypeError):
        build_trip_proposal(plan, request_id="user", draft=E3_DRAFT, extraction=None)


# --- T-REPLAY, contract level: three forms of extraction provenance (§4.10) ------------------


def test_extraction_provenance_has_exactly_three_forms(e3):
    assert draft_json_extraction() == ExtractionProvenance("draft-json", None, None)
    assert llm_extraction("qwen2.5:7b") == ExtractionProvenance("llm", "ollama", "qwen2.5:7b")
    assert replay_extraction() == ExtractionProvenance("replay", "replay", "replay-v1")
    assert REPLAY_FORMAT_VERSION == "replay-v1"
    digest = hashlib.sha256(b"[]").hexdigest()
    refused = [
        ("replay", "replay", digest),
        ("replay", "replay", None),
        ("draft-json", "ollama", None),
        ("draft-json", None, "model"),
        ("llm", "ollama", "  "),
        ("llm", "replay", "model"),
        ("llm", "ollama", None),
        ("file", None, None),
    ]
    for source, provider, model in refused:
        with pytest.raises(ValueError):
            ExtractionProvenance(source, provider, model)
    plan, _ = e3
    proposal = proposal_of(plan, "user", E3_DRAFT, replay_extraction())
    assert proposal.provenance.extraction == replay_extraction()


# --- T-CONF: confidentiality on the DTO tree (§9.1) ------------------------------------------


def with_budget(item, budget):
    """A validated copy (``model_copy`` would bypass the Pydantic validation)."""
    return TravelRequestDraft.model_validate(
        item.model_dump(mode="json") | {"budget_per_person": budget}
    )


def variant(pool, budget, request_id="pool-tyo-01"):
    """The versioned pool with one budget changed, built in memory (file untouched)."""
    requests = tuple(
        PlanningRequest(r.request_id, with_budget(r.draft, budget))
        if r.request_id == request_id
        else r
        for r in pool.requests
    )
    content = json.dumps(
        [[r.request_id, r.draft.model_dump(mode="json")] for r in requests], sort_keys=True
    )
    digest = hashlib.sha256(content.encode()).hexdigest()
    return DemandPoolSnapshot(pool.version, digest, pool.catalog_version, requests)


@pytest.fixture(scope="module")
def conf(pool):
    plans = {
        name: plan_for({"user": E3_DRAFT}, variant(pool, budget))
        for name, budget in (
            ("A", "520.00"),
            ("B", "521.37"),
        )
    }
    proposals = {name: proposal_of(plan, "user", E3_DRAFT) for name, plan in plans.items()}
    return plans, proposals


def block_journal(plan, unit_id="user"):
    block = next(b for b in plan.formation.blocks if unit_id in b.unit_ids)
    cost = next(c for c in plan.formation.evaluations if c.unit_ids == block.unit_ids)
    attempt = next(a for a in cost.attempts if a.offer_id == block.offer_id)
    return attempt.request_key, plan.journals[attempt.request_key]


def test_t_conf_precondition_same_public_outcome(conf):
    plans, _ = conf
    a, b = plans["A"], plans["B"]
    refs = [(r.unit_id, r.agreed_total_cents) for r in a.stages.references.unit_references]
    assert refs == [(r.unit_id, r.agreed_total_cents) for r in b.stages.references.unit_references]
    costs = [(c.unit_ids, c.offer_id, c.cost_cents) for c in a.formation.evaluations]
    assert costs == [(c.unit_ids, c.offer_id, c.cost_cents) for c in b.formation.evaluations]
    assert a.formation.blocks == b.formation.blocks
    assert [x.payments_cents for x in a.allocation.blocks] == [
        x.payments_cents for x in b.allocation.blocks
    ], "the scenario of T-CONF must be revised, not the test relaxed"


def test_t_conf_1_non_interference(conf):
    plans, proposals = conf
    assert proposals["A"] == proposals["B"]
    a, b = plans["A"], plans["B"]
    key_a, journal_a = block_journal(a)
    key_b, journal_b = block_journal(b)
    differing = {
        "pool_sha256": (a.pool_sha256, b.pool_sha256),
        "request_key": (key_a, key_b),
        "journal_sha256": (journal_a.journal_sha256, journal_b.journal_sha256),
        "leader0": (journal_a.initial_leader_total_cents, journal_b.initial_leader_total_cents),
        "formation_run_id": (a.formation.formation_run_id, b.formation.formation_run_id),
        "allocation_sha256": (a.allocation.allocation_sha256, b.allocation.allocation_sha256),
    }
    assert all(x != y for x, y in differing.values()), differing
    assert differing["leader0"] == (339_600, 339_682)


PUBLIC_NODE_TYPES = {
    str,
    int,
    bool,
    type(None),
    date,
    Fraction,
    tuple,
    MappingProxyType,
}


def test_t_conf_2a_no_private_object(conf):
    _, proposals = conf
    found = node_types(proposals["B"])
    private = {SellerTerms, SellerFloorTier, SellerTermsBook, TravelUnit, NegotiationJournal}
    assert not found & private
    contract = {t for t in found if is_dataclass(t)}
    assert all(t.__module__.endswith("trip_proposal") for t in contract), contract
    assert found - contract <= PUBLIC_NODE_TYPES


def private_digests(plan):
    digests = {
        plan.catalog_sha256,
        plan.oracle_configuration_id,
        plan.pool_sha256,
        plan.formation.formation_run_id,
        plan.formation.result_sha256,
        plan.allocation.allocation_sha256,
    }
    for key, journal in plan.journals.items():
        digests |= {key, journal.run_id, journal.journal_sha256}
    return digests


def test_t_conf_2b_no_digest(conf):
    plans, proposals = conf
    for name in ("A", "B"):
        leaves = strings(proposals[name])
        assert not [(p, s) for p, s in leaves if HEX64.search(s)]
        digests = private_digests(plans[name])
        assert not [(p, s) for p, s in leaves if any(d in s for d in digests)]


def b_private_values(plan):
    block = next(b for b in plan.formation.blocks if "user" in b.unit_ids)
    budgets = {u.unit_id: u.budget_total_cents for u in plan.units}
    total = sum(budgets[u] for u in block.unit_ids)
    return {
        "tyo01_budget": budgets["pool-tyo-01"],
        "block_budget_sum": total,
        "others_budget_sum": total - budgets["user"],
        "leader0": (total * 60) // 100,
    }


def catalog_amounts(plan):
    amounts = set()
    for offer in plan.stages.lot.relation.offers:
        amounts |= {offer.capacity_seats}
        amounts |= {t.list_per_seat for t in offer.tiers} | {t.min_seats for t in offer.tiers}
    return amounts


def test_t_conf_2c_no_private_value_of_the_other_members_on_b(conf):
    plans, proposals = conf
    private = b_private_values(plans["B"])
    assert private == {
        "tyo01_budget": 52_137,
        "block_budget_sum": 566_137,
        "others_budget_sum": 166_137,
        "leader0": 339_682,
    }
    assert not set(private.values()) & catalog_amounts(plans["B"]), "change the values of B"
    published = {value for _, value in numbers(proposals["B"])}
    assert not set(private.values()) & published


def test_t_conf_2d_seller_counteroffers_stay_visible(conf):
    plans, proposals = conf
    plan, proposal = plans["B"], proposals["B"]
    _, journal = block_journal(plan)
    seller = [e for e in journal.events if e.actor == "seller"]
    published = [m for m in proposal.block.negotiation.messages if m.actor == "seller"]
    assert seller and [m.total_cents for m in published] == [e.outgoing_total_cents for e in seller]
    assert all(m.total_cents is not None for m in published)
    for attempt in proposal.solo.attempts:
        key = next(
            a.request_key
            for r in plan.stages.references.unit_references
            if r.unit_id == "user"
            for a in r.attempts
            if a.offer_id == attempt.offer_id
        )
        internal = plan.journals[key].events
        assert [m.total_cents for m in attempt.journal.messages] == [
            e.outgoing_total_cents for e in internal
        ]


# T-CONF-2 (e): the marked pool M (revision 4) --------------------------------------------------

MARKED_BUDGETS = {
    "pool-tyo-01": "521.37",
    "pool-tyo-02": "541.29",
    "pool-tyo-03": "501.43",
    "pool-tyo-04": "601.17",
    "pool-rom-01": "451.61",
    "pool-rom-02": "331.53",
}
MARKED_DEPARTURE, MARKED_ARRIVAL = "2027-01-07", "2027-12-29"
MARKED_SUPPLIER = "Zq Fournisseur Fictif"


def marked_pool(pool):
    requests = []
    for request in pool.requests:
        source = request.draft
        profile = {
            "profile_id": f"zq-membre-{request.request_id}",
            "traveller_count": source.travellers,
            "departure_after": MARKED_DEPARTURE,
            "arrival_before": MARKED_ARRIVAL,
            "excluded_suppliers": [MARKED_SUPPLIER],
        }
        marked = TravelRequestDraft(
            destination=source.destination,
            travellers=source.travellers,
            budget_per_person=MARKED_BUDGETS[request.request_id],
            profiles=[profile],
        )
        requests.append(PlanningRequest(request.request_id, marked))
    return DemandPoolSnapshot(pool.version, "f" * 64, pool.catalog_version, tuple(requests))


@pytest.fixture(scope="module")
def marked(pool):
    snapshot = marked_pool(pool)
    plan = plan_for({"user": E3_DRAFT}, snapshot)
    return snapshot, plan, proposal_of(plan, "user", E3_DRAFT)


def test_t_conf_2e_marks_do_not_change_the_scenario(e3, marked):
    plan_e3, _ = e3
    _, plan_m, proposal_m = marked
    block_e3 = next(b for b in plan_e3.formation.blocks if "user" in b.unit_ids)
    block_m = next(b for b in plan_m.formation.blocks if "user" in b.unit_ids)
    assert block_m == block_e3
    assert block_m.unit_ids == ("pool-tyo-01", "pool-tyo-02", "pool-tyo-04", "user")
    assert len(proposal_m.block.members) > 1  # otherwise (e) would prove nothing
    allocation_e3 = plan_e3.allocation.block_for("user")
    allocation_m = plan_m.allocation.block_for("user")
    for name in ("references_cents", "phi", "payments_cents"):
        assert getattr(allocation_m, name) == getattr(allocation_e3, name)


def check_structure(plan, proposal, item):
    block = next(b for b in plan.formation.blocks if "user" in b.unit_ids)
    seats = {u.unit_id: u.seats for u in plan.units}
    payments = dict(plan.allocation.block_for("user").payments_cents)
    others = sorted(u for u in block.unit_ids if u != "user")
    members = proposal.block.members
    assert [(m.label, m.you, m.seats, m.payment_cents) for m in members[1:]] == [
        (f"autre demande {k}", False, seats[u], payments[u]) for k, u in enumerate(others, 1)
    ]
    assert all(
        {f.name for f in fields(m)} == {"label", "you", "seats", "payment_cents"} for m in members
    )
    unit = next(u for u in plan.units if u.unit_id == "user")
    assert proposal.unit.unit_id == "user"
    profile_ids = {p.profile_id for p in unit.profiles}
    assert {t.profile_id for t in proposal.travellers} <= profile_ids
    assert len(proposal.travellers) == unit.seats
    assert proposal.allocation.payment_cents == payments["user"]
    reference = next(r for r in plan.stages.references.unit_references if r.unit_id == "user")
    assert [a.offer_id for a in proposal.solo.attempts] == [a.offer_id for a in reference.attempts]
    assert dict(proposal.request.draft) == frozen_dump(item)


def test_t_conf_2e1_structure_on_e3_and_on_m(e3, marked):
    check_structure(*e3, E3_DRAFT)
    _, plan_m, proposal_m = marked
    check_structure(plan_m, proposal_m, E3_DRAFT)


def other_private_data(snapshot, plan):
    """(request_id, kind) -> value, from the pool and the internal plan, for every other request."""
    data = {}
    for request in snapshot.requests:
        rid, source = request.request_id, request.draft
        data[(rid, "request_id")] = rid
        data[(rid, "budget_per_person")] = int(Fraction(str(source.budget_per_person)) * 100)
        for profile in source.profiles:
            data[(rid, "profile_id")] = profile.profile_id
            data[(rid, "departure_after")] = profile.departure_after
            data[(rid, "arrival_before")] = profile.arrival_before
            data[(rid, "excluded_supplier")] = profile.excluded_suppliers[0]
    for unit in plan.units:
        if unit.unit_id != "user":
            data[(unit.unit_id, "budget_total")] = unit.budget_total_cents
            for profile_id in unit.rounded_budget_profiles:
                data[(unit.unit_id, "rounded_profile")] = profile_id
    for reference in plan.stages.references.unit_references:
        if reference.unit_id != "user" and reference.agreed_total_cents is not None:
            data[(reference.unit_id, "reference")] = reference.agreed_total_cents
    for block in plan.allocation.blocks:
        phi, y, saving = dict(block.phi), dict(block.y), dict(block.y_rounded)
        for unit_id in block.unit_ids:
            if unit_id != "user":
                data[(unit_id, "phi")] = Fraction(phi[unit_id])
                data[(unit_id, "y")] = Fraction(y[unit_id])
                data[(unit_id, "saving")] = saving[unit_id]
    for share in plan.allocation.shares:
        if share.unit_id != "user":
            data[(share.unit_id, "amount")] = share.amount_cents
            data[(share.unit_id, "share_budget")] = share.budget_cents
            data[(share.unit_id, "tau")] = Fraction(share.unit_tau)
    return data


def public_source_values(plan):
    """Values the proposal publishes from public sources or from the person's own data,
    read from those sources (catalogue, person's unit, allocation row and journals, block
    aggregates and the seller side of the block journal), never from the proposal."""
    values = set(catalog_amounts(plan))
    unit = next(u for u in plan.units if u.unit_id == "user")
    values |= {unit.seats, unit.budget_total_cents}
    allocation = plan.allocation.block_for("user")
    for name in ("references_cents", "phi", "y", "y_rounded", "payments_cents"):
        values.add(Fraction(dict(getattr(allocation, name))["user"]))
    values.add(Fraction(allocation.lambda_star))
    for share in plan.allocation.shares_for("user"):
        values |= {share.budget_cents, share.amount_cents, Fraction(share.unit_tau)}
    reference = next(r for r in plan.stages.references.unit_references if r.unit_id == "user")
    for attempt in reference.attempts:
        journal = plan.journals[attempt.request_key]
        values |= {
            journal.quantity_seats,
            journal.selected_price_tier_min_seats,
            journal.initial_seller_total_cents,
            journal.initial_leader_total_cents,
            journal.router_iterations,
        }
        values |= {e.outgoing_total_cents for e in journal.events} | {journal.agreed_total_cents}
    block = next(b for b in plan.formation.blocks if "user" in b.unit_ids)
    values |= {block.seats, block.cost_cents, block.value_cents, block.reference_total_cents}
    values.add(len(block.unit_ids) - 1)
    _, journal = block_journal(plan)
    values |= {
        journal.quantity_seats,
        journal.selected_price_tier_min_seats,
        journal.initial_seller_total_cents,
        journal.router_iterations,
        journal.agreed_total_cents,
    }
    values |= {e.outgoing_total_cents for e in journal.events if e.actor == "seller"}
    return {Fraction(v) for v in values if v is not None and not isinstance(v, bool)}


def b8_values(plan):
    block = next(b for b in plan.formation.blocks if "user" in b.unit_ids)
    seats = {u.unit_id: u.seats for u in plan.units}
    payments = dict(plan.allocation.block_for("user").payments_cents)
    return {u: {Fraction(payments[u]), Fraction(seats[u])} for u in block.unit_ids if u != "user"}


EXPECTED_EXCLUSIONS = {
    ("pool-tyo-04", "reference", 2),
    ("pool-tyo-01", "amount", 1),
    ("pool-tyo-01", "tau", 1),
    ("pool-tyo-02", "amount", 1),
    ("pool-tyo-02", "tau", 1),
    ("pool-tyo-04", "amount", 1),
    ("pool-tyo-04", "tau", 1),
    ("pool-tyo-03", "phi", 3),
    ("pool-tyo-03", "y", 3),
    ("pool-tyo-03", "saving", 3),
}


def test_t_conf_2e2_no_value_of_the_other_members_on_m(marked):
    snapshot, plan, proposal = marked
    private = other_private_data(snapshot, plan)
    public = public_source_values(plan)
    b8 = b8_values(plan)
    exclusions, compared = set(), {}
    for (rid, kind), value in private.items():
        if isinstance(value, int | Fraction) and Fraction(value) == 0:
            exclusions.add((rid, kind, 3))
        elif isinstance(value, int | Fraction) and Fraction(value) in b8.get(rid, set()):
            exclusions.add((rid, kind, 1))
        elif isinstance(value, int | Fraction) and Fraction(value) in public:
            exclusions.add((rid, kind, 2))
        else:
            compared[(rid, kind)] = value
    assert exclusions == EXPECTED_EXCLUSIONS, "a new exclusion must be reviewed"
    texts = [s.casefold() for _, s in strings(proposal)]
    published_numbers = {Fraction(v) for _, v in numbers(proposal)}
    published_dates = {v for _, v in walk(proposal) if isinstance(v, date)}
    leaks = []
    for key, value in compared.items():
        if isinstance(value, str):
            if any(value.casefold() in text for text in texts):
                leaks.append(key)
        elif isinstance(value, date):
            if value in published_dates or any(value.isoformat() in t for t in texts):
                leaks.append(key)
        elif Fraction(value) in published_numbers:
            leaks.append(key)
    assert not leaks
    kinds = {kind for _, kind in compared}
    assert {"request_id", "profile_id", "budget_per_person", "reference", "phi"} <= kinds


def test_t_conf_3_closed_field_names():
    names = contract_field_names()
    assert names == EXPECTED_FIELD_NAMES
    forbidden = ("floor", "seller_terms", "request_key", "sha256", "run_id", "configuration")
    assert not [n for n in names if any(fragment in n for fragment in forbidden)]
    assert {n for n in names if "budget" in n} == {"budget_total_cents", "budget_cents"}
    public = {f.name for cls in (OfferQuote, PriceTier) for f in fields(cls)}
    private = {f.name for cls in (SellerTerms, SellerFloorTier) for f in fields(cls)} - public
    assert private == {"floor_tiers", "floor_per_seat"} and not names & private


EXPECTED_FIELD_NAMES = frozenset(
    {
        "actor",
        "admissible",
        "agreed_total_cents",
        "allocation",
        "allocation_version",
        "alternatives",
        "amount_cents",
        "arrival_date",
        "attempts",
        "best_direct",
        "best_total_cents",
        "block",
        "booking",
        "budget_cents",
        "budget_total_cents",
        "capacity_seats",
        "catalog_total_cents",
        "catalog_version",
        "code",
        "component_units",
        "component_value_cents",
        "cost_cents",
        "departure_date",
        "destination",
        "direct",
        "draft",
        "evaluated",
        "explanations",
        "extraction",
        "failed_attempts",
        "formation_adapter_version",
        "formation_method",
        "gap_cents",
        "index",
        "journal",
        "label",
        "lambda_star_cents",
        "leader_initial_total_cents",
        "level",
        "list_per_seat_cents",
        "list_total_cents",
        "max_component_units",
        "members",
        "messages",
        "min_seats",
        "model",
        "modifiers",
        "negotiation",
        "notes",
        "notice",
        "offer_id",
        "offer_ids",
        "offers",
        "other_requests",
        "params",
        "payment_cents",
        "phi_cents",
        "planning_version",
        "pool_version",
        "price_tier_min_seats",
        "profile_id",
        "profile_ids",
        "profile_saturated",
        "projection_active",
        "provenance",
        "provider",
        "quantity_seats",
        "reason",
        "reference_cents",
        "reference_date",
        "reference_total_cents",
        "rejected_offers",
        "request",
        "request_id",
        "retained_list_total_cents",
        "rule",
        "saturated_profile_ids",
        "saving_cents",
        "schema",
        "seat_rank",
        "seats",
        "simulated_sellers",
        "simulation",
        "singleton_component",
        "size",
        "solo",
        "source",
        "status",
        "supplier_id",
        "synthetic_catalog",
        "terminal_reason",
        "theta_cents",
        "tiers",
        "total_cents",
        "travellers",
        "turns",
        "type",
        "unit",
        "unit_id",
        "unit_saturated",
        "unit_tau_cents",
        "value_cents",
        "violations",
        "without_agreement",
        "without_saving",
        "y_cents",
        "you",
    }
)


def test_the_proposal_type_is_a_frozen_projection(e3):
    _, proposal = e3
    assert isinstance(proposal, TripProposal)
    with pytest.raises(TypeError):
        proposal.request.draft["destination"] = "Rome"
