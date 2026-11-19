import asyncio
from datetime import date
from decimal import Decimal

import pytest
from BrokerAgent import BrokerAgent
from coalition_travel.application.compatibility import evaluate_compatibility
from coalition_travel.application.knowledge import (
    EmbeddingIdentity,
    KnowledgeDocument,
    KnowledgeService,
)
from coalition_travel.application.profiles import build_profiles, create_buyer_agents
from coalition_travel.application.request_understanding import understand_request
from coalition_travel.application.travel_workflow import process_travel_request
from coalition_travel.domain.request import TravelerProfileDraft, TravelRequestDraft
from coalition_travel.domain.traveler_profile import (
    CommonOffer,
    CompatibilityResult,
    TravelerProfile,
)
from coalition_travel.infrastructure.knowledge.sqlite_store import SQLiteVectorStore
from Leader import CoalitionLeaderAgent
from pydantic import ValidationError


def _request(profiles=None, travellers=4):
    return TravelRequestDraft(
        destination="Tokyo",
        travellers=travellers,
        budget_per_person=Decimal("500.00"),
        profiles=profiles or [],
    )


def test_request_without_explicit_profiles_maps_everyone_to_one_buyer():
    request = _request(travellers=4)
    profiles = build_profiles(request)
    buyers = create_buyer_agents(request, "req-1", date(2027, 1, 1), date(2026, 1, 1))

    assert len(profiles) == len(buyers) == 1
    assert buyers[0].traveller_count == 4
    assert buyers[0].budget_per_person == Decimal("500.00")
    assert buyers[0].budget == Decimal("2000.00")
    assert buyers[0].name == "req-1:all"


def test_explicit_profiles_preserve_group_counts_and_distinct_budgets():
    request = _request(
        [
            TravelerProfileDraft(
                profile_id="direct",
                traveller_count=2,
                budget_per_person=Decimal(1000),
                direct_flight="required",
            ),
            TravelerProfileDraft(
                profile_id="flex",
                traveller_count=2,
                budget_per_person=Decimal(600),
                direct_flight="any",
            ),
        ]
    )
    profiles = build_profiles(request)
    buyers = create_buyer_agents(request, "req-2", date(2027, 1, 1), date(2026, 1, 1))

    assert [profile.traveller_count for profile in profiles] == [2, 2]
    assert [profile.budget_per_person for profile in profiles] == [Decimal(1000), Decimal(600)]
    assert [buyer.budget for buyer in buyers] == [Decimal(2000), Decimal(1200)]
    assert buyers[0].direct_flight == "required"


def test_repeated_identical_groups_within_one_request_become_one_buyer():
    repeated = [
        TravelerProfileDraft(
            profile_id="direct-a",
            traveller_count=2,
            budget_per_person=Decimal(300),
            departure_after=date(2027, 6, 10),
            direct_flight="required",
        ),
        TravelerProfileDraft(
            profile_id="direct-b",
            traveller_count=2,
            budget_per_person=Decimal("300.00"),
            departure_after=date(2027, 6, 10),
            direct_flight="required",
        ),
        TravelerProfileDraft(
            profile_id="flex",
            traveller_count=1,
            budget_per_person=Decimal(450),
            direct_flight="any",
        ),
    ]
    request = _request(repeated, travellers=5)
    reversed_request = _request(list(reversed(repeated)), travellers=5)

    profiles = build_profiles(request)
    buyers = create_buyer_agents(request, "request-5", date(2027, 1, 1), date(2026, 1, 1))
    reversed_buyers = create_buyer_agents(
        reversed_request, "request-5", date(2027, 1, 1), date(2026, 1, 1)
    )

    assert len(profiles) == len(buyers) == 2
    assert sorted(profile.traveller_count for profile in profiles) == [1, 4]
    assert sorted(buyer.traveller_count for buyer in buyers) == [1, 4]
    assert {buyer.name for buyer in buyers} == {buyer.name for buyer in reversed_buyers}
    merged_profile = next(profile for profile in profiles if profile.traveller_count == 4)
    assert merged_profile.total_budget == Decimal(1200)


def test_profile_total_must_match_request_traveller_count():
    with pytest.raises(ValidationError, match="must equal travellers"):
        _request([TravelerProfileDraft(profile_id="g", traveller_count=2)], travellers=4)


def test_agent_names_are_stable_per_request_and_profiles_do_not_merge_across_requests():
    draft = _request([TravelerProfileDraft(profile_id="group", traveller_count=4)])
    first = create_buyer_agents(draft, "request-A", date(2027, 1, 1), date(2026, 1, 1))[0]
    replay = create_buyer_agents(draft, "request-A", date(2027, 1, 1), date(2026, 1, 1))[0]
    independent = create_buyer_agents(draft, "request-B", date(2027, 1, 1), date(2026, 1, 1))[0]
    broker = BrokerAgent("Broker", negotiate_on_formation=False)

    assert first.name == replay.name
    assert first.name != independent.name
    broker.receive_message(_cohort_message(first, broker, "request-A", 1))
    broker.receive_message(_cohort_message(independent, broker, "request-B", 1))
    assert {item["request_id"] for item in broker.compatibility_history} == {
        "request-A",
        "request-B",
    }


def test_leader_uses_traveler_quantity_and_strictest_per_person_budget(monkeypatch):
    request = _request(
        [
            TravelerProfileDraft(
                profile_id="premium", traveller_count=2, budget_per_person=Decimal(1000)
            ),
            TravelerProfileDraft(
                profile_id="standard", traveller_count=4, budget_per_person=Decimal(600)
            ),
        ],
        travellers=6,
    )
    buyers = create_buyer_agents(request, "req", date(2027, 1, 1), date(2026, 1, 1))
    leader = CoalitionLeaderAgent("leader", buyers, 0.1, group_min_fare=400)
    captured = {}

    class SellerSpy:
        def __init__(self, name, min_price, release_date, initial_offer):
            captured["min_price"] = min_price
            self.name = name
            self.min_price = min_price

    monkeypatch.setattr("Leader.SellerAgent", SellerSpy)
    monkeypatch.setattr("Leader.run_alternating_negotiation", lambda *args, **kwargs: (None, 0))

    leader.negotiate_for_group()

    assert leader.total_travellers == 6
    assert leader.budget == pytest.approx(3600)
    assert captured["min_price"] == pytest.approx(400 * 6 * 0.9)


def _cohort_message(buyer, broker, request_id, cohort_size):
    from Message import Message

    return Message(
        buyer,
        broker,
        "SUBSCRIBE",
        {
            "destination": "Tokyo",
            "request_id": request_id,
            "cohort_size": cohort_size,
            "compatibility": CompatibilityResult(
                "conditional", ("availability_unknown",), (buyer.name,)
            ),
        },
    )


def _profile(profile_id, destination="Tokyo", budget="700", **kwargs):
    return TravelerProfile(profile_id, 1, destination, Decimal(budget), **kwargs)


def test_profiles_without_live_offer_are_conditional_even_if_structurally_aligned():
    result = evaluate_compatibility((_profile("a"), _profile("b", budget="500")))
    assert result.status == "conditional"
    assert "common_offer_availability_unknown" in result.reasons


def test_common_offer_checks_individual_budget_and_allows_soft_direct_preference():
    profiles = (
        _profile("must-direct", budget="1000", direct_flight="required"),
        _profile("prefers-direct", budget="600", direct_flight="preferred"),
    )
    offer = CommonOffer("Tokyo", Decimal(550), direct=True, supplier="Carrier")
    assert evaluate_compatibility(profiles, offer).status == "compatible"
    over_budget = CommonOffer("Tokyo", Decimal(650), direct=True, supplier="Carrier")
    assert evaluate_compatibility(profiles, over_budget).reasons == ("individual_budget_exceeded",)


def test_common_offer_rejects_destination_date_direct_and_exclusion_conflicts():
    base = _profile(
        "a",
        departure_after=date(2027, 6, 10),
        arrival_before=date(2027, 6, 20),
        direct_flight="required",
        excluded_suppliers=("Carrier X",),
    )
    second = _profile("b", departure_after=date(2027, 6, 12), arrival_before=date(2027, 6, 18))
    assert (
        evaluate_compatibility((base, _profile("c", destination="Rome"))).status == "incompatible"
    )
    assert evaluate_compatibility(
        (base, second),
        CommonOffer(
            "Tokyo",
            Decimal(400),
            departure_date=date(2027, 6, 9),
            arrival_date=date(2027, 6, 15),
            direct=True,
            supplier="Carrier Y",
        ),
    ).reasons == ("departure_constraint_violated",)
    assert evaluate_compatibility(
        (base, second),
        CommonOffer(
            "Tokyo",
            Decimal(400),
            departure_date=date(2027, 6, 12),
            arrival_date=date(2027, 6, 15),
            direct=False,
            supplier="Carrier Y",
        ),
    ).reasons == ("direct_flight_required",)
    assert evaluate_compatibility(
        (base, second),
        CommonOffer(
            "Tokyo",
            Decimal(400),
            departure_date=date(2027, 6, 12),
            arrival_date=date(2027, 6, 15),
            direct=True,
            supplier="Carrier X",
        ),
    ).reasons == ("excluded_supplier",)


def test_application_workflow_creates_buyers_and_broker_records_conditional_candidate():
    request = _request(
        [
            TravelerProfileDraft(
                profile_id="direct",
                traveller_count=2,
                budget_per_person=Decimal(1000),
                direct_flight="required",
            ),
            TravelerProfileDraft(
                profile_id="flex", traveller_count=2, budget_per_person=Decimal(600)
            ),
        ]
    )

    class Extractor:
        async def extract(self, text, reference_date):
            return request

    broker = BrokerAgent("Broker", negotiate_on_formation=True)
    result = asyncio.run(
        process_travel_request(
            "Four travelers to Tokyo",
            Extractor(),
            "request-3",
            date(2027, 1, 1),
            date(2026, 1, 1),
            broker,
        )
    )

    assert result.understanding.status == "ready"
    assert len(result.buyers) == 2
    assert result.compatibility.status == "conditional"
    assert broker.compatibility_history[0]["status"] == "conditional"
    assert broker.formation_history == []


def test_single_profile_request_is_registered_as_conditional_broker_candidate():
    request = _request(travellers=4)

    class Extractor:
        async def extract(self, text, reference_date):
            return request

    broker = BrokerAgent("Broker", negotiate_on_formation=True)
    result = asyncio.run(
        process_travel_request(
            "Four travelers to Tokyo",
            Extractor(),
            "single-profile-request",
            date(2027, 1, 1),
            date(2026, 1, 1),
            broker,
        )
    )

    assert len(result.buyers) == 1
    assert result.compatibility.status == "conditional"
    assert len(broker.candidate_history) == 1
    assert broker.candidate_history[0]["members"] == result.buyers
    assert broker.formation_history == []


def test_application_only_forms_coalition_when_shared_offer_passes_all_profiles():
    request = _request(
        [
            TravelerProfileDraft(
                profile_id="direct",
                traveller_count=2,
                budget_per_person=Decimal(1000),
                direct_flight="required",
            ),
            TravelerProfileDraft(
                profile_id="flex", traveller_count=2, budget_per_person=Decimal(600)
            ),
        ]
    )

    class Extractor:
        async def extract(self, text, reference_date):
            return request

    broker = BrokerAgent("Broker", negotiate_on_formation=False)
    offer = CommonOffer("Tokyo", Decimal(550), direct=True, supplier="Carrier")
    result = asyncio.run(
        process_travel_request(
            "Four travelers to Tokyo",
            Extractor(),
            "request-with-offer",
            date(2027, 1, 1),
            date(2026, 1, 1),
            broker,
            common_offer=offer,
        )
    )

    assert result.compatibility.status == "compatible"
    assert len(broker.formation_history) == 1


def test_conditional_compatibility_retrieves_shared_business_and_supplier_sources(tmp_path):
    class Embedder:
        identity = EmbeddingIdentity("test", "profile-test-v1", "counts-v1")

        def embed(self, text):
            lowered = text.casefold()
            return [
                float(lowered.count("travel")),
                float(lowered.count("supplier")),
                float(len(lowered)),
            ]

    knowledge = KnowledgeService(Embedder(), SQLiteVectorStore(str(tmp_path / "kb.sqlite")))
    knowledge.index_document(
        KnowledgeDocument(
            "business-rules",
            "Travel groups require one compatible offer.",
            {"domain": "business_knowledge"},
            "business.md",
        )
    )
    knowledge.index_document(
        KnowledgeDocument(
            "supplier-policy",
            "Supplier policies describe restrictions, not live flight inventory.",
            {"domain": "supplier_knowledge", "supplier_id": "S1"},
            "supplier.md",
        )
    )
    request = _request(
        [
            TravelerProfileDraft(profile_id="one", traveller_count=2),
            TravelerProfileDraft(profile_id="two", traveller_count=2, direct_flight="preferred"),
        ]
    )

    class ContextExtractor:
        async def extract(self, text, reference_date):
            raise AssertionError("context-aware extraction should be used")

        async def extract_with_context(self, text, reference_date, knowledge_context):
            assert "source=business.md" in knowledge_context
            return request

    result = asyncio.run(
        process_travel_request(
            "Four travelers to Tokyo",
            ContextExtractor(),
            "request-knowledge",
            date(2027, 1, 1),
            date(2026, 1, 1),
            BrokerAgent("Broker", negotiate_on_formation=False),
            knowledge_service=knowledge,
        )
    )

    assert result.compatibility.status == "conditional"
    assert set(result.compatibility.knowledge_sources) == {"business.md", "supplier.md"}


def test_request_understanding_can_use_shared_business_knowledge_retrieval(tmp_path):
    class Embedder:
        identity = EmbeddingIdentity("test", "request-test-v1", "counts-v1")

        def embed(self, text):
            return [float(text.lower().count("business")), float(len(text))]

    knowledge = KnowledgeService(Embedder(), SQLiteVectorStore(str(tmp_path / "kb.sqlite")))
    knowledge.index_document(
        KnowledgeDocument(
            "rules",
            "business rule: traveler groups must be explicitly stated",
            {"domain": "business_knowledge"},
            "rules.md",
        )
    )
    expected = TravelRequestDraft(destination="Tokyo", travellers=1, budget_per_person=Decimal(500))

    class ContextExtractor:
        async def extract(self, text, reference_date):
            raise AssertionError("context-aware path should be selected")

        async def extract_with_context(self, text, reference_date, knowledge_context):
            self.context = knowledge_context
            return expected

    extractor = ContextExtractor()
    result = asyncio.run(
        understand_request("Tokyo", extractor, date(2026, 1, 1), knowledge_service=knowledge)
    )

    assert result.status == "ready"
    assert "source=rules.md" in extractor.context
