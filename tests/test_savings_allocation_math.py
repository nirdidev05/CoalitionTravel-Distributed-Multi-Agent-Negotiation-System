"""I2 (P5): exact mathematics, object by object (scope review I2, §4 and §5.1).

phi: Shapley axioms. y: projection properties. y': rounding properties. q: equal awards
under caps (R1 to R7c). The Shapley axioms are never required of y, y' or q.
"""

import ast
import itertools
import random
from fractions import Fraction
from pathlib import Path

import pytest
from coalition_travel.domain.coalition_game import build_game
from coalition_travel.domain.savings_allocation import (
    AllocationMathError,
    constrained_equal_awards,
    max_core_excess,
    project_onto_bounds,
    round_largest_remainder,
    shapley_exact,
    values_by_mask,
)
from CoalitionStructureSearch import shapley_value
from p4_support import TEST_CONFIGURATION, random_game

PACKAGE = Path(__file__).resolve().parents[1] / "Multi-Agent" / "coalition_travel"


def game_of(references, values):
    """CoalitionGame from references and the values v(C) of the feasible coalitions."""
    costs = {(unit,): reference for unit, reference in references.items()}
    for size in range(2, len(references) + 1):
        for coalition in itertools.combinations(sorted(references), size):
            value = values.get(coalition)
            costs[coalition] = (
                None if value is None else sum(references[u] for u in coalition) - value
            )
    return build_game("component-test", references, costs, TEST_CONFIGURATION)


def phi_of(game, block=None):
    members = game.players if block is None else tuple(sorted(block))
    masks = values_by_mask(members, game.cover_values(members))
    return members, masks, dict(shapley_exact(members, masks).phi)


def project(phi, value, references):
    lower = dict.fromkeys(phi, 0)
    return project_onto_bounds(phi, value, lower, dict(references))


# --- reference examples E1, E2, E4, E5 (domain level), E6 ------------------------------------


def test_e1_shapley_of_the_cover_game_is_4_4_1():
    game = game_of({"a": 10_000, "b": 10_000, "c": 10_000}, {("a", "b"): 6, ("a", "b", "c"): 9})
    _, _, phi = phi_of(game)
    assert phi == {"a": 4, "b": 4, "c": 1}
    projection = project(phi, 9, game.references)
    assert dict(projection.y) == phi and projection.lambda_star == 0
    assert not projection.active


def test_e2_projection_avoids_a_negative_payment():
    references = {"a": 100, "b": 1_000, "c": 1_000}
    game = game_of(references, {("a", "b", "c"): 900})
    _, _, phi = phi_of(game)
    assert phi == {"a": 300, "b": 300, "c": 300}
    projection = project(phi, 900, references)
    assert dict(projection.y) == {"a": 100, "b": 400, "c": 400}
    assert projection.lambda_star == -100
    assert projection.saturated_high == ("a",)
    payments = {u: references[u] - y for u, y in projection.y}
    assert payments == {"a": 0, "b": 600, "c": 600}


def test_e6_a_null_player_can_receive_savings_after_projection():
    references = {"a": 100, "b": 1_000, "c": 1_000}
    game = game_of(references, {("a", "b"): 900, ("a", "b", "c"): 900})
    _, _, phi = phi_of(game)
    assert phi == {"a": 450, "b": 450, "c": 0}  # c is a null player of v*
    projection = project(phi, 900, references)
    assert projection.lambda_star == -175
    assert dict(projection.y) == {"a": 100, "b": 625, "c": 175}  # c receives 175 > 0
    payments = {u: references[u] - y for u, y in projection.y}
    assert payments == {"a": 0, "b": 375, "c": 825}


def test_e4_individual_budgets_are_respected():
    result = constrained_equal_awards(5_000, {"a": 1_000, "b": 10_000})
    assert dict(result.amounts) == {"a": 1_000, "b": 4_000}
    assert result.tau == 4_000 and result.saturated == ("a",)


def test_e5_renaming_moves_the_cent_but_not_the_amounts():
    def split(caps):
        awards = constrained_equal_awards(3_001, caps)
        return awards, round_largest_remainder(dict(awards.amounts), 3_001, caps)

    awards, rounded = split({("a", 1): 10_000, ("b", 1): 20_000})
    assert awards.tau == Fraction(3_001, 2) and awards.saturated == ()
    assert rounded == {("a", 1): 1_501, ("b", 1): 1_500}
    renamed, rounded_renamed = split({("a", 1): 20_000, ("b", 1): 10_000})
    assert renamed.tau == awards.tau  # R7a
    assert sorted(rounded_renamed.values()) == sorted(rounded.values())  # R7b
    assert rounded_renamed[("a", 1)] == 1_501  # R7c: the seat budgeted 20 000 now gets it


# --- phi: Shapley axioms, on cover games and on arbitrary games ---------------------------


def random_cover_games(count=300, seed=7):
    rng = random.Random(seed)
    for index in range(count):
        n = 2 + index % 5
        yield random_game(rng, n, feasible_probability=rng.choice((0.3, 0.6, 0.9)))


def test_phi_efficiency_and_non_negativity_on_300_cover_games():
    for game in random_cover_games():
        _, masks, phi = phi_of(game)
        assert sum(phi.values()) == masks[-1]  # efficiency on v*
        assert all(value >= 0 for value in phi.values())  # v* superadditive
        assert all(type(value) is Fraction for value in phi.values())


def arbitrary_games(count=300, seed=11):
    """Mask-indexed games: (members, symmetric, null for p0, first, second)."""
    rng = random.Random(seed)
    for _ in range(count):
        n = rng.randint(2, 6)
        members = tuple(f"p{i}" for i in range(n))
        # Values depending on |S| only make every pair symmetric; player 0 is made null.
        by_size = [0] + [rng.randint(-500, 900) for _ in range(n)]
        symmetric = [by_size[mask.bit_count()] for mask in range(1 << n)]
        null = [symmetric[mask & ~1] for mask in range(1 << n)]  # ignore player p0
        first = [0] + [rng.randint(-900, 900) for _ in range((1 << n) - 1)]
        second = [0] + [rng.randint(-900, 900) for _ in range((1 << n) - 1)]
        yield members, symmetric, null, first, second


def test_phi_symmetry_null_player_and_additivity_on_arbitrary_games():
    for members, symmetric, null, first, second in arbitrary_games():
        phi = dict(shapley_exact(members, symmetric).phi)
        assert len(set(phi.values())) == 1
        assert dict(shapley_exact(members, null).phi)["p0"] == 0
        total = [a + b for a, b in zip(first, second)]
        phi_first = dict(shapley_exact(members, first).phi)
        phi_second = dict(shapley_exact(members, second).phi)
        phi_total = dict(shapley_exact(members, total).phi)
        assert all(phi_total[u] == phi_first[u] + phi_second[u] for u in members)


def test_differential_oracle_uses_the_same_cover_game():
    """A4: the historical float shapley_value receives v*|C, never v.

    Games: the 300 cover games of A2 (same generator, same seed), 300 more, E1. E3 is
    checked on the block produced by plan_lot (test_savings_allocation.py).
    """
    games = list(random_cover_games()) + list(random_cover_games(count=300, seed=19))
    games.append(
        game_of({"a": 10_000, "b": 10_000, "c": 10_000}, {("a", "b"): 6, ("a", "b", "c"): 9})
    )
    for game in games:
        members, _, phi = phi_of(game)
        cover = game.cover_values(members)

        def v_star(coalition, cover=cover):
            return cover[tuple(sorted(coalition))] if coalition else 0

        tolerance = 1e-6 * max(1, abs(cover[members]))
        for unit in members:
            assert abs(shapley_value(unit, members, v_star) - phi[unit]) <= tolerance


def test_differential_oracle_on_the_arbitrary_games_of_a2():
    """A4 on the arbitrary games of A2 (there v is given by mask, v* = v by construction)."""
    for members, *games in arbitrary_games():
        for values in games:
            phi = dict(shapley_exact(members, values).phi)

            def v(coalition, values=values, members=members):
                return values[sum(1 << members.index(unit) for unit in coalition)]

            tolerance = 1e-6 * max(1, abs(values[-1]))
            for unit in members:
                assert abs(shapley_value(unit, members, v) - phi[unit]) <= tolerance


# --- y: projection properties --------------------------------------------------------------


def random_projection(rng, total_equals_phi=True):
    n = rng.randint(1, 7)
    keys = [f"u{i}" for i in range(n)]
    phi = {k: Fraction(rng.randint(0, 5_000), rng.randint(1, 12)) for k in keys}
    upper = {k: rng.randint(0, 3_000) for k in keys}
    if total_equals_phi:
        total = sum(phi.values())
        while sum(upper.values()) < total:
            upper[rng.choice(keys)] += rng.randint(1, 3_000)
    else:
        total = Fraction(rng.randint(0, sum(upper.values()) * 7), 7)
    return phi, total, upper


def g(phi, upper, total, lam):
    return sum(min(max(phi[k] - lam, 0), upper[k]) for k in phi) - total


@pytest.mark.parametrize("total_equals_phi", [True, False])
def test_projection_properties_on_300_instances(total_equals_phi):
    rng = random.Random(23 if total_equals_phi else 29)
    for _ in range(300):
        phi, total, upper = random_projection(rng, total_equals_phi)
        result = project_onto_bounds(phi, total, dict.fromkeys(phi, 0), upper)
        y, lam = dict(result.y), result.lambda_star
        assert sum(y.values()) == total  # conserved sum
        assert all(0 <= y[k] <= upper[k] for k in y)  # bounds
        assert all(y[k] == min(max(phi[k] - lam, 0), upper[k]) for k in y)  # KKT form
        assert g(phi, upper, total, lam) == 0
        if lam != 0:  # convention: no root strictly between 0 and lambda*
            assert g(phi, upper, total, lam / 2) != 0
        if all(0 <= phi[k] <= upper[k] for k in phi) and sum(phi.values()) == total:
            assert y == phi and lam == 0  # no active bound
        if total_equals_phi:
            assert lam <= 0
            assert all(y[k] >= min(phi[k], upper[k]) for k in y)  # floor of y
        for a, b in itertools.combinations(phi, 2):  # conditional symmetry
            if phi[a] == phi[b] and upper[a] == upper[b]:
                assert y[a] == y[b]


def test_projection_lambda_star_is_the_root_closest_to_zero_on_plateaus():
    """Specification §9.5: when g is flat at zero, every lambda of the interval gives y;
    the convention keeps the point of the interval closest to 0."""
    # V = sum h: Lambda = (-inf, min(phi - h)] = (-inf, -2], so lambda* = -2.
    left = project_onto_bounds(
        {"a": Fraction(1), "b": Fraction(5)}, 7, {"a": 0, "b": 0}, {"a": 3, "b": 4}
    )
    assert left.lambda_star == -2 and dict(left.y) == {"a": 3, "b": 4}
    # V = sum l = 0: Lambda = [max(phi), +inf) = [3, +inf), so lambda* = 3.
    right = project_onto_bounds(
        {"a": Fraction(2), "b": Fraction(3)}, 0, {"a": 0, "b": 0}, {"a": 9, "b": 9}
    )
    assert right.lambda_star == 3 and dict(right.y) == {"a": 0, "b": 0}


def test_projection_refuses_an_infeasible_total():
    with pytest.raises(AllocationMathError, match="infeasible"):
        project_onto_bounds({"a": Fraction(5)}, 5, {"a": 0}, {"a": 4})


# --- y': rounding properties --------------------------------------------------------------


def test_rounding_properties_on_300_instances():
    rng = random.Random(31)
    for _ in range(300):
        n = rng.randint(1, 8)
        keys = [f"u{i}" for i in range(n)]
        values = {k: Fraction(rng.randint(0, 9_000), rng.choice((1, 2, 3, 7))) for k in keys}
        fractional = sum(values.values()) - int(sum(values.values()))
        values[keys[0]] += 1 - fractional if fractional else 0  # make the total an integer
        total = int(sum(values.values()))
        upper = {k: int(values[k]) + 1 for k in keys}
        rounded = round_largest_remainder(values, total, upper)
        assert sum(rounded.values()) == total
        for k in keys:
            floor_k = values[k].numerator // values[k].denominator
            assert rounded[k] in (floor_k, floor_k + 1) and rounded[k] <= upper[k]
            if values[k].denominator == 1:
                assert rounded[k] == values[k]  # no cent to an integral value


def test_rounding_breaks_ties_by_ascending_key():
    values = {"b": Fraction(1, 2), "a": Fraction(1, 2)}
    assert round_largest_remainder(values, 1, {"a": 1, "b": 1}) == {"a": 1, "b": 0}


# --- q: equal awards under caps (plan §6.1, R1 to R7c) -------------------------------------


def test_equal_awards_properties_and_certificate_on_1000_units():
    rng = random.Random(37)
    for _ in range(1_000):
        m = rng.randint(1, 20)
        caps = {(f"p{rng.randint(0, 3)}", seat): rng.randint(1, 60_000) for seat in range(m)}
        total = rng.randint(0, sum(caps.values()))
        result = constrained_equal_awards(total, caps)
        q, tau = dict(result.amounts), result.tau
        assert sum(q.values()) == total  # R1
        assert all(0 <= q[k] <= caps[k] for k in caps)  # R2
        for s, t in itertools.combinations(caps, 2):
            if caps[s] == caps[t]:
                assert q[s] == q[t]  # R3
            if caps[s] <= caps[t]:
                assert q[s] <= q[t]  # R4
            if q[s] < q[t]:
                assert q[s] == caps[s]  # certificate of optimality
            if q[t] < q[s]:
                assert q[t] == caps[t]
        if Fraction(total, m) <= min(caps.values()):
            assert all(value == Fraction(total, m) for value in q.values())  # R5
        assert all(q[k] == min(caps[k], tau) for k in caps)  # R6: b_s if b_s <= tau else tau
        assert set(result.saturated) == {k for k in caps if caps[k] < tau}
        # R7a and R7b under a random renaming of the keys.
        keys = list(caps)
        names = keys[:]
        rng.shuffle(names)
        renamed_caps = {names[i]: caps[keys[i]] for i in range(m)}
        renamed = constrained_equal_awards(total, renamed_caps)
        assert renamed.tau == tau
        assert sorted(caps[k] for k in result.saturated) == sorted(
            renamed_caps[k] for k in renamed.saturated
        )
        original_cents = round_largest_remainder(q, total, caps)
        renamed_cents = round_largest_remainder(dict(renamed.amounts), total, renamed_caps)
        assert sorted(original_cents.values()) == sorted(renamed_cents.values())


def test_equal_awards_edge_cases():
    assert dict(constrained_equal_awards(0, {"a": 5, "b": 9}).amounts) == {"a": 0, "b": 0}
    full = constrained_equal_awards(14, {"a": 5, "b": 9})
    assert dict(full.amounts) == {"a": 5, "b": 9} and full.tau == 9  # convention tau = max
    one = constrained_equal_awards(7, {"a": 9})
    assert dict(one.amounts) == {"a": 7} and one.tau == 7
    with pytest.raises(AllocationMathError):
        constrained_equal_awards(15, {"a": 5, "b": 9})


# --- diagnostics and guards ---------------------------------------------------------------


def test_max_core_excess_is_the_best_secession_gain():
    members = ("a", "b", "c")
    values = [0, 0, 0, 6, 0, 0, 0, 9]  # v*({a,b}) = 6, v*(C) = 9
    y = {"a": Fraction(4), "b": Fraction(4), "c": Fraction(1)}
    assert max_core_excess(members, values, y) == -1  # {a,b}: 6 - 8
    assert max_core_excess(("a",), [0, 0], {"a": Fraction(0)}) is None


def test_values_by_mask_requires_a_complete_cover():
    with pytest.raises(AllocationMathError, match="every non-empty subset"):
        values_by_mask(("a", "b"), {("a",): 0, ("b",): 0})


def _module_tree(relative):
    return ast.parse((PACKAGE / relative).read_text(encoding="utf-8"))


def test_official_modules_never_use_the_historical_shapley_value():
    for relative in ("domain/savings_allocation.py", "application/savings_allocation.py"):
        tree = _module_tree(relative)
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert not {
            m for m in modules if "CoalitionStructureSearch" in m or "cooperative_game" in m
        }
        assert "shapley_value" not in names, relative


def test_the_domain_module_produces_no_float():
    tree = _module_tree("domain/savings_allocation.py")
    floats = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and type(node.value) is float
    ]
    assert not floats
    assert "float" not in {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
