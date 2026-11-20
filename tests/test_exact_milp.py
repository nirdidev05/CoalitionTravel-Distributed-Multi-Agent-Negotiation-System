"""P4.4-bis: optional MILP adapter, acceptance procedure and confidence labels."""

import random
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("scipy")

from coalition_travel.application.partition_solver import PartitionInvalid, solve_component
from coalition_travel.infrastructure.optimization import exact_milp
from coalition_travel.infrastructure.optimization.exact_milp import (
    CertificateFailure,
    IntegralityViolation,
    SolverAnomaly,
    SolverNotOptimal,
    solve_component_milp,
)
from p4_support import random_game


def test_milp_is_certified_by_exact_equality_with_idp():
    rng = random.Random(12)
    for _ in range(60):
        game = random_game(rng, rng.randint(2, 8))
        reference = solve_component(game, cross_checks=("dp",))
        certified = solve_component_milp(game, certify_with=reference)
        assert certified.label == "milp_certified_exact"
        assert certified.tie_break_score == reference.tie_break_score
        assert certified.value_cents == reference.value_cents
        alone = solve_component_milp(game)
        assert alone.label == "milp_solver_optimal"  # never "exact" without the certificate


def _fake_result(game, *, status=0, x=None, dual=None, message="fake"):
    columns = game.feasible_coalitions()
    if x is None:
        x = np.array([1.0 if len(c) == 1 else 0.0 for c in columns])
        dual = -float(sum(game.weight(c) for c in columns if len(c) == 1)) if dual is None else dual
    return SimpleNamespace(status=status, message=message, x=x, mip_dual_bound=dual)


def _game_with_gain():
    rng = random.Random(5)
    while True:
        game = random_game(rng, 4)
        reference = solve_component(game, cross_checks=())
        if reference.value_cents > 0:
            return game, reference


@pytest.mark.parametrize(
    "status,error", [(2, SolverAnomaly), (3, SolverAnomaly), (4, SolverNotOptimal)]
)
def test_bad_solver_statuses_raise(monkeypatch, status, error):
    game, _ = _game_with_gain()
    monkeypatch.setattr(exact_milp, "milp", lambda **kwargs: _fake_result(game, status=status))
    with pytest.raises(error):
        solve_component_milp(game)


def test_limit_reached_or_missing_dual_bound_is_never_optimal(monkeypatch):
    game, _ = _game_with_gain()
    monkeypatch.setattr(exact_milp, "milp", lambda **kwargs: _fake_result(game, status=1))
    assert solve_component_milp(game).label == "milp_feasible_unverified"
    monkeypatch.setattr(exact_milp, "milp", lambda **kwargs: _fake_result(game, dual=float("nan")))
    assert solve_component_milp(game).label == "milp_feasible_unverified"
    no_dual = _fake_result(game)
    no_dual.mip_dual_bound = None
    monkeypatch.setattr(exact_milp, "milp", lambda **kwargs: no_dual)
    assert solve_component_milp(game).label == "milp_feasible_unverified"


def test_a_suboptimal_claim_fails_the_certificate(monkeypatch):
    game, reference = _game_with_gain()
    # All singletons claimed optimal (status 0, consistent dual bound) while idp found a gain.
    monkeypatch.setattr(exact_milp, "milp", lambda **kwargs: _fake_result(game))
    with pytest.raises(CertificateFailure):
        solve_component_milp(game, certify_with=reference)


def test_fractional_or_non_partition_solutions_are_rejected(monkeypatch):
    game, _ = _game_with_gain()
    columns = game.feasible_coalitions()
    fractional = np.array([0.5] * len(columns))
    monkeypatch.setattr(
        exact_milp, "milp", lambda **kwargs: _fake_result(game, x=fractional, dual=0.0)
    )
    with pytest.raises(IntegralityViolation):
        solve_component_milp(game)
    everything = np.ones(len(columns))
    monkeypatch.setattr(
        exact_milp, "milp", lambda **kwargs: _fake_result(game, x=everything, dual=0.0)
    )
    with pytest.raises(PartitionInvalid):
        solve_component_milp(game)
