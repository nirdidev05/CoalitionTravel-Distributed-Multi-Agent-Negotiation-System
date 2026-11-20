"""Cooperative game of one connected component of the unit-offer graph (P4.1).

Notation of docs/PHASE_P4_SPECIFICATION.md (sections 3 and 4):

- players N: units that own an individual negotiated reference ``ref_u`` (cents);
- F: feasible coalitions, i.e. with a common admissible offer and at least one P3
  agreement on one of them; every singleton of N is in F;
- direct function ``v(C) = sum(ref_u for u in C) - c(C)`` on F only, in integer cents,
  possibly negative; infeasible coalitions have no value (exclusion);
- superadditive cover ``v*(S)``: best partition of S into blocks of F;
- solver weight ``w(C) = K * v(C) - (|C| - 1)`` on F and ``-P`` outside F, with
  ``K = n`` (number of players) and ``P = 1``. Maximizing the sum of w over partitions
  maximizes the savings in cents first, then the number of blocks (proposition 1), and
  ``V = ceil(W / K)`` decodes the savings (proposition 3).

All arithmetic is exact integer arithmetic. The module depends on the standard library
only: no NumPy, no solver, no agent, no LLM.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

Coalition = tuple[str, ...]

# P: technical penalty of an infeasible block inside the solver adapter (proposition 4).
INFEASIBLE_PENALTY = 1
# Integers of absolute value up to 2**53 and their sums in that range are exact floats.
FLOAT_EXACT_LIMIT = 2**53


class GameConsistencyError(ValueError):
    """The game violates an invariant (singleton value, references, coalitions)."""


class NumericDomainExceeded(ValueError):
    """Solver weights could leave the range where float sums are exact."""


def canonical_coalition(unit_ids: Iterable[str]) -> Coalition:
    """Sorted tuple of unique, non-blank unit identifiers."""
    if isinstance(unit_ids, str):
        raise TypeError("a coalition is a collection of unit identifiers, not a string")
    members = tuple(unit_ids)
    if not members:
        raise ValueError("a coalition must not be empty")
    if any(type(member) is not str or not member.strip() for member in members):
        raise TypeError("unit identifiers must be non-blank strings")
    if len(set(members)) != len(members):
        raise ValueError("a coalition must not repeat a unit")
    return tuple(sorted(members))


def canonical_structure(blocks: Iterable[Iterable[str]]) -> tuple[Coalition, ...]:
    """Blocks in canonical form, sorted; disjointness is checked by the game."""
    return tuple(sorted(canonical_coalition(block) for block in blocks))


def _require_int(value, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an int (cents), not {type(value).__name__}")
    return value


@dataclass(frozen=True)
class CoalitionGame:
    """Characteristic function of one component on its feasible coalitions.

    ``values`` holds exactly the feasible coalitions F, sorted by (size, identifiers);
    every singleton is present with value 0 (section 3.2 of the specification).
    """

    component_id: str
    players: tuple[str, ...]
    references: tuple[tuple[str, int], ...]
    values: tuple[tuple[Coalition, int], ...]
    oracle_configuration_id: str

    def __post_init__(self):
        if type(self.component_id) is not str or not self.component_id.strip():
            raise ValueError("component_id must be a non-blank string")
        if type(self.oracle_configuration_id) is not str or not self.oracle_configuration_id:
            raise ValueError("oracle_configuration_id must be a non-blank string")
        if type(self.players) is not tuple or not self.players:
            raise ValueError("a game needs a non-empty tuple of players")
        if canonical_coalition(self.players) != self.players:
            raise ValueError("players must be unique and sorted")
        if (
            type(self.references) is not tuple
            or tuple(unit for unit, _ in self.references) != self.players
        ):
            raise GameConsistencyError("references must list exactly the players, in order")
        for unit, reference in self.references:
            if _require_int(reference, f"reference of {unit}") <= 0:
                raise GameConsistencyError(f"reference of {unit} must be positive")
        if type(self.values) is not tuple:
            raise TypeError("values must be a tuple of (coalition, value) pairs")
        player_set = set(self.players)
        seen = set()
        for coalition, value in self.values:
            if canonical_coalition(coalition) != coalition:
                raise ValueError("coalitions must be canonical sorted tuples")
            if not set(coalition) <= player_set:
                raise GameConsistencyError(f"coalition {coalition} contains a non-player")
            if coalition in seen:
                raise ValueError(f"coalition {coalition} is listed twice")
            seen.add(coalition)
            _require_int(value, f"value of {coalition}")
        order = tuple(coalition for coalition, _ in self.values)
        if order != tuple(sorted(order, key=lambda coalition: (len(coalition), coalition))):
            raise ValueError("values must be sorted by (size, identifiers)")
        value_map = {frozenset(coalition): value for coalition, value in self.values}
        for unit in self.players:
            if value_map.get(frozenset((unit,))) != 0:
                raise GameConsistencyError(
                    f"singleton {unit} must be feasible with value 0 (v({{u}}) = 0)"
                )
        object.__setattr__(self, "_value_map", value_map)
        object.__setattr__(self, "_reference_map", dict(self.references))

    # --- basic accessors -----------------------------------------------------------

    @property
    def n(self) -> int:
        return len(self.players)

    @property
    def tie_break_factor(self) -> int:
        """K = n, the smallest factor for which proposition 1 holds (section 4)."""
        return self.n

    def reference(self, unit_id: str) -> int:
        return self._reference_map[unit_id]

    def is_feasible(self, coalition: Iterable[str]) -> bool:
        return frozenset(coalition) in self._value_map

    def value(self, coalition: Iterable[str]) -> int:
        """v(C) for C in F; KeyError for an infeasible coalition (it has no value)."""
        members = frozenset(coalition)
        if members not in self._value_map:
            raise KeyError(f"coalition {sorted(members)} is not feasible and has no value")
        return self._value_map[members]

    def feasible_coalitions(self) -> tuple[Coalition, ...]:
        return tuple(coalition for coalition, _ in self.values)

    # --- solver weight and decoding --------------------------------------------------

    def weight(self, coalition: Iterable[str]) -> int:
        """w(C) = K*v(C) - (|C| - 1) on F, -P outside F (sections 3.4 and 4)."""
        members = frozenset(coalition)
        if not members:
            raise ValueError("the empty coalition has no weight")
        value = self._value_map.get(members)
        if value is None:
            return -INFEASIBLE_PENALTY
        return self.tie_break_factor * value - (len(members) - 1)

    def decode(self, score: int) -> int:
        """V = ceil(W / K), valid for a partition into blocks of F (proposition 3)."""
        _require_int(score, "score")
        return -((-score) // self.tie_break_factor)

    def require_numeric_domain(self) -> None:
        """Every partial sum handled by a float solver must stay below 2**53.

        A partition has at most n blocks, so every partial sum is bounded by
        n * max |w(C)|, the maximum taken over F and the penalty.
        """
        largest = max(
            [INFEASIBLE_PENALTY] + [abs(self.weight(coalition)) for coalition, _ in self.values]
        )
        if self.n * largest >= FLOAT_EXACT_LIMIT:
            raise NumericDomainExceeded(
                f"n * max|w| = {self.n * largest} is not below 2**53; float sums would be inexact"
            )

    # --- partitions -------------------------------------------------------------------

    def check_structure(self, structure: Iterable[Iterable[str]]) -> tuple[Coalition, ...]:
        """Canonical structure that partitions the players exactly into blocks of F."""
        blocks = canonical_structure(structure)
        covered = [unit for block in blocks for unit in block]
        if sorted(covered) != list(self.players):
            raise GameConsistencyError("the structure does not partition the players exactly")
        for block in blocks:
            if not self.is_feasible(block):
                raise GameConsistencyError(f"block {block} is not a feasible coalition")
        return blocks

    def structure_value(self, structure: Iterable[Iterable[str]]) -> int:
        """V(pi) = sum of v over the blocks, in cents."""
        return sum(self.value(block) for block in self.check_structure(structure))

    def structure_score(self, structure: Iterable[Iterable[str]]) -> int:
        """W(pi) = K*V(pi) - (n - |pi|), recomputed exactly in integers."""
        blocks = self.check_structure(structure)
        return sum(self.weight(block) for block in blocks)

    # --- superadditive cover -------------------------------------------------------------

    def cover_values(self, subset: Iterable[str] | None = None) -> dict[Coalition, int]:
        """v*(S) for every non-empty S of ``subset`` (default: all players).

        Dynamic programming over subsets with the pivot rule (the block that contains the
        smallest member), exact in integers, Theta(3^m) for m members. Defined because
        every singleton is feasible (section 3.3).
        """
        members = self.players if subset is None else canonical_coalition(subset)
        if not set(members) <= set(self.players):
            raise GameConsistencyError("the subset contains a non-player")
        size = len(members)
        best = [0] * (1 << size)
        for mask in range(1, 1 << size):
            coalition = frozenset(members[i] for i in range(size) if mask >> i & 1)
            candidate = self._value_map.get(coalition)
            lowest = mask & -mask
            rest = mask ^ lowest
            sub = rest
            while True:
                first = lowest | sub
                if first != mask:
                    split = best[first] + best[mask ^ first]
                    if candidate is None or split > candidate:
                        candidate = split
                if sub == 0:
                    break
                sub = (sub - 1) & rest
            best[mask] = candidate
        return {
            tuple(members[i] for i in range(size) if mask >> i & 1): best[mask]
            for mask in range(1, 1 << size)
        }


def build_game(
    component_id: str,
    references: Mapping[str, int],
    coalition_costs: Mapping[Coalition, int | None],
    oracle_configuration_id: str,
) -> CoalitionGame:
    """Build the game from individual references and collective negotiated costs.

    ``coalition_costs`` maps every evaluated coalition to its cost c(C) in cents, or to
    None when no common offer produced an agreement (C not in F). Every singleton must be
    evaluated, and its cost must equal the reference: c({u}) = ref_u, so v({u}) = 0.
    """
    if not references:
        raise GameConsistencyError("a game needs at least one player")
    players = canonical_coalition(references)
    for unit in players:
        if _require_int(references[unit], f"reference of {unit}") <= 0:
            raise GameConsistencyError(f"reference of {unit} must be positive")
    costs: dict[Coalition, int | None] = {}
    for raw_coalition, cost in coalition_costs.items():
        coalition = canonical_coalition(raw_coalition)
        if coalition in costs:
            raise ValueError(f"coalition {coalition} is evaluated twice")
        if not set(coalition) <= set(players):
            raise GameConsistencyError(f"coalition {coalition} contains a non-player")
        if cost is not None and _require_int(cost, f"cost of {coalition}") <= 0:
            raise GameConsistencyError(f"cost of {coalition} must be positive")
        costs[coalition] = cost
    values = [
        (coalition, sum(references[unit] for unit in coalition) - cost)
        for coalition, cost in costs.items()
        if cost is not None
    ]
    for unit in players:
        if (unit,) not in costs:
            raise GameConsistencyError(f"singleton {unit} was not evaluated")
        cost = costs[(unit,)]
        if cost != references[unit]:
            raise GameConsistencyError(
                f"c({{{unit}}}) = {cost} differs from ref = {references[unit]}: "
                "same factory and oracle configuration required (section 3.2)"
            )
    values.sort(key=lambda item: (len(item[0]), item[0]))
    return CoalitionGame(
        component_id=component_id,
        players=players,
        references=tuple((unit, references[unit]) for unit in players),
        values=tuple(values),
        oracle_configuration_id=oracle_configuration_id,
    )
