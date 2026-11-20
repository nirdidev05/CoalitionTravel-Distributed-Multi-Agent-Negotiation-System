"""P4.4: baselines B1 (greedy) and B0 (historical Broker), re-scoring and gaps (M6)."""

import random
from fractions import Fraction

import pytest
from coalition_travel.application.formation_baselines import (
    BaselineError,
    greedy_b1,
    optimality_gap,
    rescore_structure,
)
from coalition_travel.application.partition_solver import solve_component
from coalition_travel.domain.coalition_game import build_game
from coalition_travel.infrastructure.baselines.legacy_broker import (
    B0_ARRIVAL_ORDERS,
    arrival_orders,
    run_b0,
)
from p4_support import REFERENCE, TEST_CONFIGURATION, make_unit, random_game


def game_from_values(values, players="abcd"):
    references = {unit: 10_000 for unit in players}
    costs = {(unit,): 10_000 for unit in players}
    for coalition, value in values.items():
        costs[coalition] = None if value is None else 10_000 * len(coalition) - value
    return build_game("k", references, costs, TEST_CONFIGURATION)


def test_b1_never_beats_the_optimum_on_random_games():
    rng = random.Random(8)
    for _ in range(200):
        game = random_game(rng, rng.randint(2, 8))
        optimum = solve_component(game, cross_checks=("dp",)).value_cents
        assert game.structure_value(greedy_b1(game)) <= optimum


def test_b1_is_optimal_when_positive_blocks_are_disjoint():
    game = game_from_values({("a", "b"): 30, ("c", "d"): 10, ("a", "c"): None, ("b", "d"): -5})
    assert greedy_b1(game) == (("a", "b"), ("c", "d"))
    assert game.structure_value(greedy_b1(game)) == solve_component(game).value_cents


def test_b1_can_be_suboptimal():
    """Greedy takes bc (15) and blocks ab + cd (10 + 10 = 20)."""
    game = game_from_values({("a", "b"): 10, ("c", "d"): 10, ("b", "c"): 15})
    assert greedy_b1(game) == (("a",), ("b", "c"), ("d",))
    assert game.structure_value(greedy_b1(game)) == 15
    assert solve_component(game).value_cents == 20


def test_rescoring_keeps_feasible_blocks_and_splits_the_others():
    first = game_from_values({("a", "b"): 12, ("c", "d"): None}, players="abcd")
    second = build_game("k2", {"x": 5_000}, {("x",): 5_000}, TEST_CONFIGURATION)
    rescored = rescore_structure(
        [("a", "b"), ("c", "d"), ("x", "outside"), ("lonely",)], [first, second]
    )
    assert rescored.feasible_blocks == (("a", "b"),)
    assert rescored.infeasible_blocks == (("c", "d"), ("outside", "x"))
    assert rescored.outside_game_units == ("lonely", "outside")
    assert rescored.structure == (("a", "b"), ("c",), ("d",), ("x",))
    assert rescored.value_cents == 12


def test_rescoring_refuses_invalid_structures():
    game = game_from_values({("a", "b"): 12}, players="ab")
    with pytest.raises(BaselineError, match="twice"):
        rescore_structure([("a", "b"), ("a",)], [game])
    with pytest.raises(BaselineError, match="does not cover"):
        rescore_structure([("a",)], [game])


def test_optimality_gap():
    assert optimality_gap(200, 150).absolute_cents == 50
    assert optimality_gap(200, 150).relative == Fraction(1, 4)
    assert optimality_gap(0, -30) == optimality_gap(0, -30)
    assert optimality_gap(0, -30).relative is None
    assert optimality_gap(0, -30).absolute_cents == 30
    with pytest.raises(BaselineError):
        optimality_gap(100, 101)


def test_b0_reproduces_the_historical_fifo_threshold_grouping(capsys):
    units = [make_unit(f"t{i}", budget=str(500 + i)) for i in range(7)]
    units += [make_unit(f"r{i}", budget="400", destination="Rome") for i in range(2)]
    order = ["t3", "t0", "r1", "t6", "t1", "t2", "t5", "r0", "t4"]
    structure = run_b0(units, order, REFERENCE)
    # Tokyo: groups of 3 in arrival order, the 7th unit waits; Rome: 2 units wait.
    assert structure == (
        ("r0",),
        ("r1",),
        ("t0", "t3", "t6"),
        ("t1", "t2", "t5"),
        ("t4",),
    )
    assert capsys.readouterr().out == ""


def test_b0_validation_and_arrival_orders():
    units = [make_unit("a"), make_unit("b")]
    with pytest.raises(ValueError, match="permutation"):
        run_b0(units, ["a"], REFERENCE)
    orders = arrival_orders(["b", "a", "c"], B0_ARRIVAL_ORDERS, "seed")
    assert len(orders) == 20
    assert all(sorted(order) == ["a", "b", "c"] for order in orders)
    assert orders == arrival_orders(["a", "b", "c"], B0_ARRIVAL_ORDERS, "seed")
    assert orders != arrival_orders(["a", "b", "c"], B0_ARRIVAL_ORDERS, "other seed")
