"""Baselines evaluated inside the P4 game (M6, specification section 7).

- B1 (new greedy): repeatedly take the disjoint feasible block with the largest v > 0,
  ties broken by fewer units then sorted identifiers; the remaining units are
  singletons. It uses the same feasible set F and the same v as the optimizer, so its
  gap to the optimum isolates the effect of the exact solver.
- Re-scoring: any structure (for instance the historical Broker B0) is scored in the P4
  game. A block of two units or more that is not in F, or that spans several components,
  is infeasible: it is counted and its members are scored as singletons (value 0).
  B0 is therefore never presented as equivalent to P4: it ignores admissibility,
  agreements and the common-offer requirement.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from coalition_travel.domain.coalition_game import (
    Coalition,
    CoalitionGame,
    canonical_coalition,
    canonical_structure,
)


class BaselineError(ValueError):
    """A baseline structure is not a valid partition of the players it covers."""


def greedy_b1(game: CoalitionGame) -> tuple[Coalition, ...]:
    if not isinstance(game, CoalitionGame):
        raise TypeError("game must be a CoalitionGame")
    ranked = sorted(
        (
            (coalition, value)
            for coalition, value in game.values
            if len(coalition) > 1 and value > 0
        ),
        key=lambda item: (-item[1], len(item[0]), item[0]),
    )
    taken: set[str] = set()
    chosen: list[Coalition] = []
    for coalition, _ in ranked:
        if taken.isdisjoint(coalition):
            chosen.append(coalition)
            taken.update(coalition)
    chosen.extend((unit,) for unit in game.players if unit not in taken)
    return game.check_structure(chosen)


@dataclass(frozen=True)
class RescoredStructure:
    structure: tuple[Coalition, ...]  # effective structure in the P4 game
    feasible_blocks: tuple[Coalition, ...]  # original multi-unit blocks that are in F
    infeasible_blocks: tuple[Coalition, ...]  # original multi-unit blocks that are not
    outside_game_units: tuple[str, ...]  # units without reference (not players)
    value_cents: int


def rescore_structure(
    structure: Iterable[Iterable[str]], games: Iterable[CoalitionGame]
) -> RescoredStructure:
    games = tuple(games)
    owner: dict[str, CoalitionGame] = {}
    for game in games:
        for unit in game.players:
            if unit in owner:
                raise BaselineError(f"unit {unit} belongs to two games")
            owner[unit] = game
    blocks = tuple(canonical_coalition(block) for block in structure)
    covered = [unit for block in blocks for unit in block]
    if len(covered) != len(set(covered)):
        raise BaselineError("the structure assigns a unit twice")
    missing = set(owner) - set(covered)
    if missing:
        raise BaselineError(f"the structure does not cover the players {sorted(missing)}")
    effective: list[Coalition] = []
    feasible: list[Coalition] = []
    infeasible: list[Coalition] = []
    outside: list[str] = []
    value = 0
    for block in blocks:
        players = tuple(unit for unit in block if unit in owner)
        outside.extend(unit for unit in block if unit not in owner)
        games_of_block = {id(owner[unit]) for unit in players}
        if len(block) > 1:
            in_game = len(players) == len(block) and len(games_of_block) == 1
            if in_game and owner[players[0]].is_feasible(block):
                feasible.append(block)
                effective.append(block)
                value += owner[players[0]].value(block)
                continue
            infeasible.append(block)
        effective.extend((unit,) for unit in players)
    return RescoredStructure(
        structure=canonical_structure(effective),
        feasible_blocks=tuple(sorted(feasible)),
        infeasible_blocks=tuple(sorted(infeasible)),
        outside_game_units=tuple(sorted(outside)),
        value_cents=value,
    )


@dataclass(frozen=True)
class OptimalityGap:
    absolute_cents: int  # V* - V, always defined
    relative: Fraction | None  # (V* - V) / V*, only when V* > 0


def optimality_gap(optimum_cents: int, value_cents: int) -> OptimalityGap:
    """Gap to a certified optimum (idp_search or milp_certified_exact only)."""
    if type(optimum_cents) is not int or type(value_cents) is not int:
        raise TypeError("values must be int cents")
    if value_cents > optimum_cents:
        raise BaselineError("a baseline cannot exceed the certified optimum")
    absolute = optimum_cents - value_cents
    return OptimalityGap(absolute, Fraction(absolute, optimum_cents) if optimum_cents > 0 else None)
