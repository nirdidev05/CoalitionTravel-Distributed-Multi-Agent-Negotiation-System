"""Application service around the existing deterministic partition solvers."""

from dataclasses import dataclass
from time import perf_counter

from coalition_travel.domain.partition import validate_partition
from coalition_travel.domain.partition_optimization import brute_force_search, idp_search


@dataclass(frozen=True)
class OptimizationResult:
    value: float
    structure: tuple[frozenset, ...]
    algorithm: str
    evaluated_coalitions: int
    pruned_pairs: int
    elapsed_ms: float
    oracle_value: float | None = None
    oracle_structure: tuple[frozenset, ...] | None = None
    oracle_partitions: int | None = None


class CoalitionOptimizationService:
    """Run IDP; optionally cross-check a small instance with an exact oracle."""

    def __init__(self, oracle_max_agents: int = 8):
        if oracle_max_agents < 0:
            raise ValueError("oracle_max_agents must be non-negative")
        self.oracle_max_agents = oracle_max_agents

    def optimize(self, agents, coalition_value, verify: bool = False) -> OptimizationResult:
        agents = list(agents)
        started = perf_counter()
        value, structure, evaluated, pruned = idp_search(agents, coalition_value)
        elapsed_ms = (perf_counter() - started) * 1000
        validate_partition(agents, structure)

        oracle_partitions = None
        oracle_value = None
        oracle_structure = None
        if verify and len(agents) <= self.oracle_max_agents:
            oracle_value, oracle_result, oracle_partitions = brute_force_search(
                agents, coalition_value, max_agents=self.oracle_max_agents
            )
            oracle_structure = tuple(oracle_result)
            if abs(value - oracle_value) > 1e-9:
                raise RuntimeError(
                    f"IDP value {value} differs from exhaustive oracle {oracle_value}"
                )

        return OptimizationResult(
            value=value,
            structure=tuple(structure),
            algorithm="IDP",
            evaluated_coalitions=evaluated,
            pruned_pairs=pruned,
            elapsed_ms=elapsed_ms,
            oracle_value=oracle_value,
            oracle_structure=oracle_structure,
            oracle_partitions=oracle_partitions,
        )
