"""P4.1: the game model, its cover v* and the propositions of specification section 4."""

import ast
import itertools
import random
import sys
from pathlib import Path

import pytest
from coalition_travel.domain import coalition_game
from coalition_travel.domain.coalition_game import (
    FLOAT_EXACT_LIMIT,
    CoalitionGame,
    GameConsistencyError,
    NumericDomainExceeded,
    build_game,
    canonical_coalition,
)
from p4_support import TEST_CONFIGURATION, exclusion_optimum, random_game, set_partitions

SPEC_REFERENCES = {"a": 100, "b": 200, "c": 300}
# Specification example (§3.5): F = singletons, {a, b} with v = 6, {a, b, c} with v = 9.
SPEC_COSTS = {
    ("a",): 100,
    ("b",): 200,
    ("c",): 300,
    ("a", "b"): 294,
    ("a", "b", "c"): 591,
    ("a", "c"): None,
    ("b", "c"): None,
}


def spec_game():
    return build_game("k", SPEC_REFERENCES, SPEC_COSTS, TEST_CONFIGURATION)


# --- definition of v and exclusion -----------------------------------------------------


def test_build_game_computes_v_on_feasible_coalitions_only():
    game = spec_game()
    assert game.values == (
        (("a",), 0),
        (("b",), 0),
        (("c",), 0),
        (("a", "b"), 6),
        (("a", "b", "c"), 9),
    )
    assert game.value(("b", "a")) == 6
    assert not game.is_feasible(("a", "c"))
    with pytest.raises(KeyError, match="no value"):
        game.value(("a", "c"))


def test_singleton_cost_must_equal_the_reference():
    costs = dict(SPEC_COSTS)
    costs[("c",)] = 299
    with pytest.raises(GameConsistencyError, match="differs from ref"):
        build_game("k", SPEC_REFERENCES, costs, TEST_CONFIGURATION)
    del costs[("c",)]
    with pytest.raises(GameConsistencyError, match="not evaluated"):
        build_game("k", SPEC_REFERENCES, costs, TEST_CONFIGURATION)
    costs[("c",)] = None
    with pytest.raises(GameConsistencyError, match="differs from ref"):
        build_game("k", SPEC_REFERENCES, costs, TEST_CONFIGURATION)


@pytest.mark.parametrize(
    "references,costs,error",
    [
        ({"a": 100}, {("a",): 100, ("a", "z"): 50}, GameConsistencyError),
        ({"a": 100}, {("a",): 100.0}, TypeError),
        ({"a": 100}, {("a",): 0}, GameConsistencyError),
        ({"a": 0}, {("a",): 0}, GameConsistencyError),
        ({"a": 100}, {("a",): 100, ("a", "a"): 50}, ValueError),
    ],
)
def test_build_game_rejects_inconsistent_inputs(references, costs, error):
    with pytest.raises(error):
        build_game("k", references, costs, TEST_CONFIGURATION)


def test_direct_construction_enforces_singletons_and_canonical_order():
    with pytest.raises(GameConsistencyError, match="singleton"):
        CoalitionGame("k", ("a", "b"), (("a", 1), ("b", 1)), ((("a",), 0),), "cfg")
    with pytest.raises(ValueError, match="sorted"):
        CoalitionGame("k", ("a", "b"), (("a", 1), ("b", 1)), ((("b",), 0), (("a",), 0)), "cfg")
    with pytest.raises(ValueError, match="sorted"):
        CoalitionGame("k", ("b", "a"), (("b", 1), ("a", 1)), (), "cfg")


def test_canonical_coalition_rejects_strings_duplicates_and_blanks():
    assert canonical_coalition(["b", "a"]) == ("a", "b")
    for bad, error in (
        ("ab", TypeError),
        (["a", "a"], ValueError),
        ([""], TypeError),
        ([], ValueError),
    ):
        with pytest.raises(error):
            canonical_coalition(bad)


# --- weights and decoding (section 4) ---------------------------------------------------


def test_weight_uses_k_equal_n_and_penalty_one():
    game = spec_game()
    assert game.tie_break_factor == game.n == 3
    assert game.weight(("a",)) == 0
    assert game.weight(("a", "b")) == 3 * 6 - 1
    assert game.weight(("a", "b", "c")) == 3 * 9 - 2
    assert game.weight(("a", "c")) == -coalition_game.INFEASIBLE_PENALTY == -1
    assert game.structure_score([("a", "b", "c")]) == 25
    assert game.decode(25) == 9
    assert game.structure_score([("a", "b"), ("c",)]) == 17
    assert game.decode(17) == 6


def test_proposition_3_decoding_on_every_feasible_partition():
    rng = random.Random(31)
    for _ in range(80):
        game = random_game(rng, rng.randint(1, 6))
        for partition in set_partitions(game.players):
            blocks = [tuple(sorted(block)) for block in partition]
            if all(game.is_feasible(block) for block in blocks):
                score = game.structure_score(blocks)
                assert game.decode(score) == game.structure_value(blocks)


def test_proposition_1_score_order_is_lexicographic_savings_then_blocks():
    rng = random.Random(7)
    for _ in range(60):
        game = random_game(rng, rng.randint(2, 6))
        feasible = []
        for partition in set_partitions(game.players):
            blocks = [tuple(sorted(block)) for block in partition]
            if all(game.is_feasible(block) for block in blocks):
                feasible.append(blocks)
        for left, right in itertools.combinations(feasible, 2):
            score_order = (game.structure_score(left) > game.structure_score(right)) - (
                game.structure_score(left) < game.structure_score(right)
            )
            key_left = (game.structure_value(left), len(left))
            key_right = (game.structure_value(right), len(right))
            lexicographic = (key_left > key_right) - (key_left < key_right)
            assert score_order == lexicographic


@pytest.mark.parametrize("n", range(2, 9))
def test_proposition_2_k_below_n_breaks_the_order_on_the_limit_instance(n):
    """Grand coalition saving 1 cent against singletons: tie for K = n-1, strict for K = n."""
    players = [f"u{i}" for i in range(n)]
    references = {unit: 1_000 for unit in players}
    costs = {(unit,): 1_000 for unit in players}
    costs[tuple(players)] = n * 1_000 - 1
    game = build_game("k", references, costs, TEST_CONFIGURATION)

    def score(k, blocks):
        return sum(k * game.value(block) - (len(block) - 1) for block in blocks)

    grand, singletons = [tuple(players)], [(unit,) for unit in players]
    assert score(n - 1, grand) == score(n - 1, singletons)  # K = n - 1: tie
    if n > 2:
        assert score(n - 2, grand) < score(n - 2, singletons)  # K < n - 1: 1 cent lost
    assert score(n, grand) > score(n, singletons)  # K = n: strict
    assert game.structure_score(grand) > game.structure_score(singletons)


@pytest.mark.parametrize("penalty", [1, 7, 10**6])
def test_proposition_4_no_maximizer_contains_a_penalized_block(penalty):
    rng = random.Random(penalty)
    for _ in range(50):
        game = random_game(rng, rng.randint(2, 6))
        best_score, best_blocks = None, None
        for partition in set_partitions(game.players):
            blocks = [tuple(sorted(block)) for block in partition]
            score = sum(
                game.weight(block) if game.is_feasible(block) else -penalty for block in blocks
            )
            if best_score is None or score > best_score:
                best_score, best_blocks = score, blocks
        assert all(game.is_feasible(block) for block in best_blocks)
        assert (game.decode(best_score), len(best_blocks)) == exclusion_optimum(game)


# --- superadditive cover v* (section 3.3) ------------------------------------------------


def test_cover_on_the_specification_example():
    cover = spec_game().cover_values()
    assert cover == {
        ("a",): 0,
        ("b",): 0,
        ("c",): 0,
        ("a", "b"): 6,
        ("a", "c"): 0,
        ("b", "c"): 0,
        ("a", "b", "c"): 9,
    }


def test_cover_properties_on_random_games():
    rng = random.Random(2026)
    for _ in range(80):
        game = random_game(rng, rng.randint(1, 6))
        cover = game.cover_values()
        subsets = list(cover)
        for subset, value in cover.items():
            sub_game_best = max(
                sum(game.value(tuple(sorted(block))) for block in partition)
                for partition in set_partitions(subset)
                if all(game.is_feasible(block) for block in partition)
            )
            assert value == sub_game_best  # definition
            assert value >= 0  # property 2
            if len(subset) == 1:
                assert value == 0  # property 1
            if game.is_feasible(subset):
                assert value >= game.value(subset)  # property 5
        for left, right in itertools.product(subsets, repeat=2):
            if not set(left) & set(right):
                union = tuple(sorted(set(left) | set(right)))
                assert cover[union] >= cover[left] + cover[right]  # property 3
            if set(left) <= set(right):
                assert cover[right] >= cover[left]  # property 4


def test_blocks_of_an_optimal_partition_have_cover_equal_to_value():
    rng = random.Random(77)
    for _ in range(40):
        game = random_game(rng, rng.randint(2, 6))
        cover = game.cover_values()
        best = None
        for partition in set_partitions(game.players):
            blocks = [tuple(sorted(block)) for block in partition]
            if all(game.is_feasible(block) for block in blocks):
                value = sum(game.value(block) for block in blocks)
                if best is None or value > best[0]:
                    best = (value, blocks)
        for block in best[1]:
            assert cover[block] == game.value(block)  # property 6


def test_cover_of_a_subset_and_rejection_of_non_players():
    game = spec_game()
    assert game.cover_values(("b", "a")) == {("a",): 0, ("b",): 0, ("a", "b"): 6}
    with pytest.raises(GameConsistencyError):
        game.cover_values(("a", "z"))


# --- structures and numeric domain -------------------------------------------------------


def test_structure_checks_reject_non_partitions_and_infeasible_blocks():
    game = spec_game()
    with pytest.raises(GameConsistencyError, match="partition"):
        game.check_structure([("a", "b")])
    with pytest.raises(GameConsistencyError, match="not a feasible"):
        game.check_structure([("a", "c"), ("b",)])
    assert game.check_structure([("c",), ("b", "a")]) == (("a", "b"), ("c",))


def test_numeric_domain_guard():
    huge = FLOAT_EXACT_LIMIT // 2
    references = {"a": huge, "b": huge}
    costs = {("a",): huge, ("b",): huge, ("a", "b"): 1}
    game = build_game("k", references, costs, TEST_CONFIGURATION)
    with pytest.raises(NumericDomainExceeded):
        game.require_numeric_domain()
    spec_game().require_numeric_domain()


def test_game_module_imports_the_standard_library_only():
    source = Path(coalition_game.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names)
