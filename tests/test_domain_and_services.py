import asyncio
from datetime import date
from decimal import Decimal

import pytest
from coalition_travel.application.evaluation import score_extractions
from coalition_travel.application.optimization import CoalitionOptimizationService
from coalition_travel.application.request_understanding import understand_request
from coalition_travel.domain.coalition_problem import CoalitionProblem
from coalition_travel.domain.request import TravelRequestDraft
from CoalitionStructureSearch import brute_force_search, dp_search, idp_search
from Entry import BUDGETS, DISCOUNT
from pydantic import ValidationError


class StaticExtractor:
    def __init__(self, draft):
        self.draft = draft

    async def extract(self, text, reference_date):
        self.seen_text = text
        self.seen_reference_date = reference_date
        return self.draft


def test_coalition_problem_is_explicit_and_isolated():
    problem_a = CoalitionProblem({"A": 100, "B": 200}, {1: 0, 2: 0.1})
    problem_b = CoalitionProblem({"A": 100, "B": 200}, {1: 0, 2: 0.2})

    assert problem_a.value({"A", "B"}) == 30
    assert problem_b.value({"A", "B"}) == 60
    assert problem_a.value(set()) == 0
    assert problem_a.agents == ("A", "B")


@pytest.mark.parametrize(
    "budgets,discounts,coalition,error",
    [
        ({"A": 0}, {1: 0}, {"A"}, ValueError),
        ({"A": 100}, {1: 1}, {"A"}, ValueError),
        ({"A": 100}, {1: 0}, {"missing"}, ValueError),
        ({"A": True}, {1: 0}, {"A"}, TypeError),
    ],
)
def test_coalition_problem_rejects_invalid_data(budgets, discounts, coalition, error):
    with pytest.raises(error):
        CoalitionProblem(budgets, discounts).value(coalition)


def test_request_schema_rejects_unexpected_fields_and_bad_values():
    with pytest.raises(ValidationError):
        TravelRequestDraft(destination="Paris", travellers=0)
    with pytest.raises(ValidationError):
        TravelRequestDraft(destination="Paris", invented_field="secret")
    with pytest.raises(ValidationError):
        TravelRequestDraft(travellers=True)


def test_request_understanding_asks_for_missing_required_fields():
    extractor = StaticExtractor(TravelRequestDraft(destination="Tokyo"))
    result = asyncio.run(understand_request("   Tokyo trip   ", extractor, date(2026, 1, 1)))

    assert extractor.seen_text == "Tokyo trip"
    assert extractor.seen_reference_date == date(2026, 1, 1)
    assert result.status == "needs_clarification"
    assert result.missing_fields == ("travellers", "budget_per_person")
    assert result.provider == "StaticExtractor"
    assert result.latency_ms >= 0


def test_request_understanding_validates_dates_deterministically():
    extractor = StaticExtractor(
        TravelRequestDraft(
            destination="Tokyo",
            travellers=2,
            budget_per_person=Decimal("500.00"),
            departure_after=date(2026, 3, 10),
            arrival_before=date(2026, 3, 1),
        )
    )
    result = asyncio.run(understand_request("Tokyo, two people", extractor, date(2026, 1, 1)))

    assert result.status == "invalid"
    assert "departure_after must not be after arrival_before" in result.errors


def test_request_understanding_does_not_treat_provider_failure_as_user_error():
    class FailingExtractor:
        async def extract(self, text, reference_date):
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        asyncio.run(understand_request("Tokyo", FailingExtractor(), date(2026, 1, 1)))


def test_request_with_all_required_fields_is_ready():
    extractor = StaticExtractor(
        TravelRequestDraft(destination="Tokyo", travellers=2, budget_per_person=Decimal(500))
    )
    result = asyncio.run(understand_request("Tokyo", extractor, date(2026, 1, 1)))

    assert result.status == "ready"
    assert result.request.budget_per_person == Decimal(500)


def test_partition_solvers_match_the_exhaustive_oracle():
    agents = list(BUDGETS)
    value = lambda coalition: (
        sum(BUDGETS[name] for name in coalition) * DISCOUNT.get(len(coalition), 0)
    )
    expected, _, partitions = brute_force_search(agents, value)
    dp_value, dp_structure, _ = dp_search(agents, value)
    idp_value, idp_structure, _, _ = idp_search(agents, value)

    assert partitions == 52
    assert dp_value == pytest.approx(expected)
    assert idp_value == pytest.approx(expected)
    assert sum(map(len, dp_structure)) == len(agents)
    assert sum(map(len, idp_structure)) == len(agents)


def test_optimization_service_returns_machine_readable_metrics_and_oracle():
    problem = CoalitionProblem({"A": 10, "B": 20, "C": 30}, {1: 0, 2: 0.2, 3: 0.1})
    result = CoalitionOptimizationService(oracle_max_agents=5).optimize(
        problem.agents, problem.value, verify=True
    )

    assert result.algorithm == "IDP"
    assert result.value == pytest.approx(result.oracle_value)
    assert result.oracle_partitions == 5
    assert result.elapsed_ms >= 0
    assert result.structure


def test_oracle_guard_prevents_accidental_large_enumeration():
    service = CoalitionOptimizationService(oracle_max_agents=2)
    budgets = {f"A{i}": 10 for i in range(4)}
    problem = CoalitionProblem(budgets, {1: 0.0, 2: 0.1})

    result = service.optimize(problem.agents, problem.value, verify=True)

    assert result.oracle_value is None
    assert result.oracle_partitions is None


def test_optimization_skips_exhaustive_oracle_by_default():
    problem = CoalitionProblem({"A": 10, "B": 20, "C": 30}, {1: 0, 2: 0.2, 3: 0.1})

    result = CoalitionOptimizationService().optimize(problem.agents, problem.value)

    assert result.oracle_value is None
    assert result.oracle_partitions is None


def test_extraction_metrics_report_field_and_whole_request_exact_match():
    expected = TravelRequestDraft(destination="Tokyo", travellers=2, budget_per_person=Decimal(500))
    prediction = TravelRequestDraft(
        destination="Osaka", travellers=2, budget_per_person=Decimal("500.00")
    )

    metrics = score_extractions([expected], [prediction])

    assert metrics["samples"] == 1
    assert metrics["request_exact_match"] == 0
    assert metrics["field_exact_match"]["destination"] == 0
    assert metrics["field_exact_match"]["budget_per_person"] == 1
