"""Characterization tests for the historical coalition search API."""

import inspect
import subprocess
import sys
from pathlib import Path

import CoalitionStructureSearch as legacy_search
import pytest
from CoalitionStructureSearch import (
    brute_force_search,
    dp_search,
    format_structure,
    idp_search,
    ip_search,
    print_result,
    print_shapley_transfers,
    shapley_value,
    validate_partition,
)

PUBLIC_PARAMETERS = {
    "dp_search": ("agents", "v"),
    "idp_search": ("agents", "v"),
    "ip_search": ("agents", "v"),
    "brute_force_search": ("agents", "v", "max_agents"),
    "validate_partition": ("agents", "structure"),
    "shapley_value": ("agent", "coalition", "v"),
    "format_structure": ("struct",),
    "print_result": ("algo_name", "val", "struct", "stat_label", "stat_val", "extra"),
    "print_shapley_transfers": ("coalition", "v", "total_price", "budgets"),
}


def assert_partition_shape(agents, structure):
    assert isinstance(structure, list)
    assert all(isinstance(coalition, frozenset) for coalition in structure)
    assert validate_partition(agents, structure) is True


def test_historical_public_signatures_and_exports_are_preserved():
    for name, parameter_names in PUBLIC_PARAMETERS.items():
        function = getattr(legacy_search, name)
        assert callable(function)
        signature = inspect.signature(function)
        assert tuple(signature.parameters) == parameter_names
        for parameter_name, parameter in signature.parameters.items():
            expected_default = {
                ("brute_force_search", "max_agents"): 10,
                ("print_result", "extra"): None,
                ("print_shapley_transfers", "budgets"): None,
            }.get((name, parameter_name), inspect.Parameter.empty)
            assert parameter.default == expected_default


def test_legacy_consumers_import_the_same_public_functions():
    import Entry
    import Leader
    from coalition_travel.application import optimization

    assert Entry.dp_search is legacy_search.dp_search
    assert Entry.idp_search is legacy_search.idp_search
    assert Entry.ip_search is legacy_search.ip_search
    assert Leader.print_shapley_transfers is legacy_search.print_shapley_transfers
    assert optimization.idp_search is legacy_search.idp_search
    assert optimization.brute_force_search is legacy_search.brute_force_search
    assert optimization.validate_partition is legacy_search.validate_partition


@pytest.mark.parametrize(
    "search, expected_length, expected_metrics",
    [
        (dp_search, 3, (0,)),
        (idp_search, 4, (0, 0)),
        (ip_search, 3, (0,)),
        (brute_force_search, 3, (1,)),
    ],
)
def test_empty_agent_result_shapes_are_historical(search, expected_length, expected_metrics):
    result = search([], lambda coalition: 10)

    assert isinstance(result, tuple)
    assert len(result) == expected_length
    assert result[0] == 0.0
    assert result[1] == []
    assert result[2:] == expected_metrics


@pytest.mark.parametrize("search", [dp_search, idp_search, ip_search, brute_force_search])
def test_single_agent_search_returns_one_frozenset(search):
    result = search(["A"], lambda coalition: 4.5)

    assert result[0] == pytest.approx(4.5)
    assert result[1] == [frozenset({"A"})]
    assert_partition_shape(["A"], result[1])


def test_result_counters_measure_subsets_and_reference_partitions():
    agents = ["A", "B", "C"]
    value = lambda coalition: len(coalition)

    _, dp_structure, dp_count = dp_search(agents, value)
    _, idp_structure, idp_count, pruned_pairs = idp_search(agents, value)
    _, ip_structure, ip_count = ip_search(agents, value)
    _, oracle_structure, oracle_partition_count = brute_force_search(agents, value)

    assert dp_count == 2 ** len(agents) - 1
    assert idp_count == 2 ** len(agents) - 1
    assert ip_count == 2 ** len(agents) - 1
    assert pruned_pairs >= 0
    assert oracle_partition_count == 5  # Bell number B(3).
    for structure in (dp_structure, idp_structure, ip_structure, oracle_structure):
        assert_partition_shape(agents, structure)


@pytest.mark.parametrize(
    "value, expected_value, expected_structure",
    [
        (
            lambda coalition: {
                frozenset({"A"}): 1,
                frozenset({"B"}): 1,
                frozenset({"C"}): 1,
                frozenset({"A", "B"}): 10,
                frozenset({"A", "C"}): 2,
                frozenset({"B", "C"}): 2,
                frozenset({"A", "B", "C"}): 9,
            }[coalition],
            11,
            {frozenset({"A", "B"}), frozenset({"C"})},
        ),
        (lambda coalition: 0, 0, {frozenset({"A", "B", "C"})}),
        (lambda coalition: -len(coalition), -3, {frozenset({"A", "B", "C"})}),
        (
            lambda coalition: 0 if len(coalition) == 1 else -100,
            0,
            {frozenset({"A"}), frozenset({"B"}), frozenset({"C"})},
        ),
    ],
)
def test_dp_idp_ip_and_oracle_agree_on_small_games(value, expected_value, expected_structure):
    agents = ["A", "B", "C"]
    results = [
        dp_search(agents, value),
        idp_search(agents, value),
        ip_search(agents, value),
        brute_force_search(agents, value),
    ]

    for result in results:
        assert result[0] == pytest.approx(expected_value)
        assert_partition_shape(agents, result[1])

    # DP and the oracle use strict-improvement tie handling and keep the first
    # optimum found. Do not impose that implementation detail on HiGHS/IP.
    assert set(results[0][1]) == expected_structure
    assert set(results[1][1]) == expected_structure
    assert set(results[3][1]) == expected_structure


def test_all_zero_game_characterizes_dp_idp_and_oracle_tie_breaking():
    agents = ["A", "B", "C"]
    value = lambda coalition: 0
    grand_coalition = [frozenset(agents)]

    assert dp_search(agents, value)[1] == grand_coalition
    assert idp_search(agents, value)[1] == grand_coalition
    assert brute_force_search(agents, value)[1] == grand_coalition


def test_oracle_enforces_its_agent_limit():
    with pytest.raises(ValueError, match="limited to 1 agents"):
        brute_force_search(["A", "B"], lambda coalition: 1, max_agents=1)


@pytest.mark.parametrize(
    "agents, structure, message",
    [
        (["A"], [frozenset()], "empty coalitions"),
        (["A"], [frozenset({"B"})], "unknown agents"),
        (["A", "B"], [frozenset({"A"})], "does not cover"),
        (["A", "B"], [frozenset({"A"}), frozenset({"A", "B"})], "more than once"),
    ],
)
def test_partition_validator_rejects_invalid_structures(agents, structure, message):
    with pytest.raises(ValueError, match=message):
        validate_partition(agents, structure)


def test_partition_validator_accepts_empty_partition_for_empty_agent_set():
    assert validate_partition([], []) is True


def test_partition_validator_currently_collapses_duplicate_agent_inputs():
    # Legacy quirk characterization, not a desired validation guarantee.
    assert validate_partition(["A", "A"], [frozenset({"A"})]) is True


def test_search_rejects_duplicate_and_unhashable_agent_ids():
    with pytest.raises(ValueError, match="unique"):
        dp_search(["A", "A"], lambda coalition: 1)
    with pytest.raises(TypeError, match="hashable"):
        dp_search([["A"]], lambda coalition: 1)


@pytest.mark.parametrize("invalid_value", [True, float("nan"), float("inf"), "1"])
def test_search_rejects_boolean_non_finite_or_non_numeric_coalition_values(invalid_value):
    with pytest.raises(ValueError, match="finite numbers"):
        dp_search(["A"], lambda coalition: invalid_value)


def test_search_accepts_hashable_non_comparable_ids_but_helpers_cannot_sort_them():
    class AgentId:
        def __init__(self, value):
            self.value = value

        def __hash__(self):
            return hash(self.value)

        def __eq__(self, other):
            return isinstance(other, AgentId) and self.value == other.value

    first, second = AgentId("A"), AgentId("B")
    value, structure, _ = dp_search([first, second], lambda coalition: len(coalition))

    assert value == 2
    assert_partition_shape([first, second], structure)
    with pytest.raises(TypeError):
        shapley_value(first, {first, second}, lambda coalition: len(coalition))
    with pytest.raises(TypeError):
        format_structure([{first, second}])


def test_shapley_value_is_marginal_contribution_average_for_additive_game():
    weights = {"A": 2, "B": 1, "C": 4}
    value = lambda coalition: sum(weights[agent] for agent in coalition)

    assert shapley_value("A", {"A", "B", "C"}, value) == pytest.approx(2)
    assert shapley_value("B", {"A", "B", "C"}, value) == pytest.approx(1)
    assert shapley_value("C", {"A", "B", "C"}, value) == pytest.approx(4)


def test_format_and_print_result_keep_observable_text_contract(capsys):
    structure = [frozenset({"b", "a"}), frozenset({"c"})]
    assert format_structure(structure) == "{ {a, b}  |  {c} }"

    print_result("DP", 2, structure, "nodes", 3, extra=("cuts", 1))
    output = capsys.readouterr().out
    assert "SC*           = { {a, b}  |  {c} }" in output
    assert "nodes          = 3" in output
    assert "cuts           = 1" in output


def test_print_shapley_transfers_returns_budget_bounded_payments(capsys):
    weights = {"A": 2, "B": 1}
    value = lambda coalition: sum(weights[agent] for agent in coalition)

    payments = print_shapley_transfers({"A", "B"}, value, 100, budgets={"A": 20, "B": 100})

    assert payments == pytest.approx({"A": 20, "B": 80})
    assert sum(payments.values()) == pytest.approx(100)
    output = capsys.readouterr().out
    assert "A" in output and "B" in output
    assert "Ajustement appliqué" in output
    assert "Σtoken=0" in output


def test_print_shapley_transfers_rejects_empty_coalition():
    with pytest.raises(ValueError, match="must not be empty"):
        print_shapley_transfers(set(), lambda coalition: 0, 10)


def test_importing_historical_modules_has_no_scenario_output():
    project_root = Path(__file__).resolve().parents[1]
    command = (
        "import sys; sys.path.insert(0, 'Multi-Agent'); "
        "import CoalitionStructureSearch; import Entry"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout == ""
