"""P4.3: solver adapter around the historical algorithms (M5)."""

import random

import pytest
from coalition_travel.application import partition_solver
from coalition_travel.application.coalition_candidates import FormationLimits
from coalition_travel.application.partition_solver import (
    PartitionInvalid,
    SolverDisagreement,
    solve_component,
)
from coalition_travel.domain import coalition_game
from coalition_travel.domain.coalition_game import build_game
from p4_support import TEST_CONFIGURATION, exclusion_optimum, random_game


def test_exact_solvers_match_an_independent_enumeration_on_500_games():
    """Correction stratum: 100 % equality required, idp = dp (value and structure) = brute force."""
    rng = random.Random(20261119)
    sizes = [rng.choice((2, 3, 4, 5, 6, 7, 8, 9)) for _ in range(500)]
    for size in sizes:
        game = random_game(rng, size)
        solution = solve_component(game)  # idp, cross-checked by dp and brute force
        assert solution.checks == ("dp", "brute_force")
        expected_value, expected_blocks = exclusion_optimum(game) if size <= 7 else (None, None)
        if expected_value is not None:
            assert (solution.value_cents, solution.block_count) == (expected_value, expected_blocks)
        assert game.decode(solution.tie_break_score) == solution.value_cents
        assert all(game.is_feasible(block) for block in solution.structure)
        for method in ("dp", "brute_force"):
            other = solve_component(game, method=method, cross_checks=())
            assert other.tie_break_score == solution.tie_break_score
        assert solve_component(game, method="dp", cross_checks=()).structure == solution.structure


@pytest.mark.parametrize("penalty", [1, 7, 10**6])
def test_the_penalty_value_changes_nothing(monkeypatch, penalty):
    rng = random.Random(55)
    games = [random_game(rng, rng.randint(2, 8)) for _ in range(40)]
    reference = [solve_component(game) for game in games]
    monkeypatch.setattr(coalition_game, "INFEASIBLE_PENALTY", penalty)
    for game, expected in zip(games, reference):
        solution = solve_component(game)
        assert (solution.structure, solution.tie_break_score) == (
            expected.structure,
            expected.tie_break_score,
        )


def test_statuses_and_singleton_component():
    single = build_game("k", {"a": 100}, {("a",): 100}, TEST_CONFIGURATION)
    solution = solve_component(single)
    assert (solution.status, solution.method, solution.checks) == (
        "singleton_component",
        "singleton",
        (),
    )
    zero = build_game(
        "k", {"a": 100, "b": 100}, {("a",): 100, ("b",): 100, ("a", "b"): 200}, TEST_CONFIGURATION
    )
    solution = solve_component(zero)
    assert solution.status == "no_beneficial_coalition"
    assert solution.structure == (("a",), ("b",))  # a zero-saving coalition is never formed
    gain = build_game(
        "k", {"a": 100, "b": 100}, {("a",): 100, ("b",): 100, ("a", "b"): 190}, TEST_CONFIGURATION
    )
    assert solve_component(gain).status == "optimized"


def test_limit_instance_of_proposition_2_keeps_the_cent():
    for n in range(2, 9):
        players = [f"u{i}" for i in range(n)]
        costs = {(unit,): 1_000 for unit in players}
        costs[tuple(players)] = n * 1_000 - 1
        game = build_game("k", {unit: 1_000 for unit in players}, costs, TEST_CONFIGURATION)
        solution = solve_component(game)
        assert (solution.value_cents, solution.structure) == (1, (tuple(players),))


def test_splittable_block_is_not_formed():
    """v(abcd) = v(ab) + v(cd): same savings, more blocks wins."""
    references = {u: 1_000 for u in "abcd"}
    costs = {(u,): 1_000 for u in "abcd"}
    costs.update({("a", "b"): 1_990, ("c", "d"): 1_990, ("a", "b", "c", "d"): 3_980})
    game = build_game("k", references, costs, TEST_CONFIGURATION)
    assert solve_component(game).structure == (("a", "b"), ("c", "d"))


def test_brute_force_method_respects_its_limit():
    rng = random.Random(1)
    game = random_game(rng, 6)
    with pytest.raises(ValueError, match="brute_force"):
        solve_component(
            game,
            method="brute_force",
            cross_checks=("dp",),
            limits=FormationLimits(brute_force_max_units=5),
        )
    solution = solve_component(game, limits=FormationLimits(brute_force_max_units=5))
    assert solution.checks == ("dp",)


def test_disagreements_and_invalid_partitions_are_detected(monkeypatch):
    references = {u: 1_000 for u in ("u0", "u1", "u2", "u3")}
    costs = {(u,): 1_000 for u in references}
    costs.update({("u0", "u1"): None, ("u1", "u2"): 1_900, ("u2", "u3"): 1_950})
    game = build_game("k", references, costs, TEST_CONFIGURATION)
    honest = solve_component(game)
    assert honest.structure == (("u0",), ("u1", "u2"), ("u3",))
    infeasible = ("u0", "u1")

    def lying_dp(agents, v):
        rest = [unit for unit in agents if unit not in infeasible]
        return 10.0**9, [frozenset(infeasible), *(frozenset([unit]) for unit in rest)], 1

    monkeypatch.setattr(partition_solver, "dp_search", lying_dp)
    with pytest.raises(PartitionInvalid):
        solve_component(game)

    def other_structure_dp(agents, v):
        return float(honest.tie_break_score), [frozenset([u]) for u in agents], 1

    monkeypatch.setattr(partition_solver, "dp_search", other_structure_dp)
    with pytest.raises(SolverDisagreement):
        solve_component(game)


def test_invalid_arguments():
    rng = random.Random(2)
    game = random_game(rng, 3)
    with pytest.raises(ValueError):
        solve_component(game, method="simplex")
    with pytest.raises(ValueError):
        solve_component(game, method="idp", cross_checks=("idp",))
    with pytest.raises(TypeError):
        solve_component("not a game")


def test_float_exactness_close_to_two_to_the_53(monkeypatch):
    """Weights just below the bound: every partial sum stays exact; just above: refused."""
    base = 2**51
    players = ("a", "b", "c", "d")
    references = dict.fromkeys(players, base)

    def game_with_pair_value(value):
        costs = {(u,): base for u in players}
        costs.update({("a", "b"): 2 * base - value, ("c", "d"): 2 * base - value})
        return build_game("k", references, costs, TEST_CONFIGURATION)

    value = 2**49 - 3  # w = 4*value - 1 = 2**51 - 13, n * max|w| = 2**53 - 52
    game = game_with_pair_value(value)
    game.require_numeric_domain()
    largest = max(abs(game.weight(c)) for c in game.feasible_coalitions())
    assert game.n * largest < 2**53
    solution = solve_component(game)  # idp, dp and brute force, exact recomputation
    assert solution.value_cents == 2 * value
    assert solution.tie_break_score == 2 * (4 * value - 1)
    assert float(solution.tie_break_score) == solution.tie_break_score

    too_large = game_with_pair_value(2**49 + 1)

    def must_not_run(*args, **kwargs):
        raise AssertionError("the solver must not be called outside the exact domain")

    monkeypatch.setattr(partition_solver, "idp_search", must_not_run)
    with pytest.raises(coalition_game.NumericDomainExceeded):
        solve_component(too_large)


def test_dp_returning_another_structure_with_the_same_score_is_refused(monkeypatch):
    """Two optimal partitions with equal W: idp_search and dp_search must agree on one."""
    references = dict.fromkeys("abcd", 1_000)
    costs = {(u,): 1_000 for u in "abcd"}
    costs.update({("a", "b"): 1_990, ("c", "d"): 1_990, ("a", "c"): 1_990, ("b", "d"): 1_990})
    game = build_game("k", references, costs, TEST_CONFIGURATION)
    honest = solve_component(game)
    alternatives = {(("a", "b"), ("c", "d")), (("a", "c"), ("b", "d"))}
    assert honest.structure in alternatives
    (other,) = alternatives - {honest.structure}
    assert game.structure_score(other) == honest.tie_break_score

    def same_score_other_structure(agents, v):
        return float(honest.tie_break_score), [frozenset(block) for block in other], 1

    monkeypatch.setattr(partition_solver, "dp_search", same_score_other_structure)
    with pytest.raises(SolverDisagreement, match="same structure"):
        solve_component(game, cross_checks=("dp",))
