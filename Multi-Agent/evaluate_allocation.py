"""P5 performance measurements M0, M1 and M2 in one session (scope review I2, §6).

M0  T_P4_total(14): full P4 pipeline (``run_formation_stages`` with a fresh cache) on the
    10 instances of 14 units of the P4 performance stratum (same cell, same seeds).
M1  T_P5 on dense blocks (every sub-coalition feasible, grand coalition optimal),
    k = 2 to 14, games built directly; durations split by sub-step.
M2  The exploratory stratum regenerated with the same cells and seeds; for each instance
    T_P4_total and T_P5 are measured in the same run; statistics over the instances that
    have at least one block.

Protocol: one warm-up, then ``--repetitions`` timed runs (default 5); medians per item.
Thresholds registered before measuring (scope review I2, §6):
    M1: median T_P5(dense k = 14) < median T_P4_total(14) of M0 in this session;
    M2: median over instances of T_P5 / T_P4_total <= 0.25.
Durations are volatile and machine dependent; the output directory also holds the
generated scenario catalogues, which contain private seller terms: never version it.
"""

import argparse
import hashlib
import json
import platform
import statistics
import sys
from decimal import Decimal
from itertools import combinations
from pathlib import Path
from time import perf_counter

from coalition_travel.application.coalition_formation import run_formation_stages
from coalition_travel.application.savings_allocation import (
    SUBSTEPS,
    CoverCache,
    SubstepClock,
    allocate_block,
    allocate_formation,
    split_unit_payment,
)
from coalition_travel.domain.coalition_game import build_game
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile
from coalition_travel.infrastructure.evaluation.formation_scenarios import (
    ScenarioParameters,
    build_scenario,
)
from evaluate_formation import FAMILY_CELLS, ofat_cells, random_cells

M1_THRESHOLD = "median T_P5(dense k=14) < median T_P4_total(14)"
M2_THRESHOLD_RATIO = 0.25
DENSE_REFERENCE_CENTS = 100_000


def _median(values):
    return statistics.median(values) if values else None


def _quantile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def _p4_run(scenario):
    started = perf_counter()
    stages = run_formation_stages(
        scenario.units, scenario.catalog, scenario.reference_date, scenario.oracle
    )
    return stages, perf_counter() - started


def _p5_run(formation, units):
    started = perf_counter()
    allocation = allocate_formation(formation, units)
    return allocation, perf_counter() - started


def measure_m0(output: Path, repetitions: int, instances: int = 10) -> dict:
    cell = ScenarioParameters(
        unit_count=14,
        profiles_per_unit=1,
        offer_count=1,
        density_percent=100,
        agreement_target_percent=100,
    )
    samples, per_instance = [], []
    for seed_index in range(instances):
        scenario = build_scenario(cell, seed_index, output / "scenarios")
        reference, _ = _p4_run(scenario)  # warm-up
        times = []
        for _ in range(repetitions):
            stages, elapsed = _p4_run(scenario)
            if stages.formation.result_sha256 != reference.formation.result_sha256:
                raise RuntimeError("a P4 repetition produced a different result")
            times.append(elapsed)
        samples.extend(times)
        per_instance.append({"seed_index": seed_index, "median_seconds": _median(times)})
    return {"samples": len(samples), "median_seconds": _median(samples), "instances": per_instance}


def dense_game(k: int):
    """All sub-coalitions feasible; v(S) = 1000 (|S|-1)^2 + (|S|-1) sum w_u, superadditive."""
    players = tuple(f"u{index:02d}" for index in range(k))
    weights = {unit: 10 * (index + 1) for index, unit in enumerate(players)}
    references = dict.fromkeys(players, DENSE_REFERENCE_CENTS)
    costs = {}
    for size in range(1, k + 1):
        for coalition in combinations(players, size):
            value = 1_000 * (size - 1) ** 2 + (size - 1) * sum(weights[u] for u in coalition)
            costs[coalition] = size * DENSE_REFERENCE_CENTS - value
    return build_game(f"dense-{k}", references, costs, "dense-measurement"), players


def _dense_units(players):
    budget = Decimal(DENSE_REFERENCE_CENTS) / 100
    return {
        unit: TravelUnit(
            unit,
            "dense",
            (TravelerProfile("all", 1, "Dense", budget),),
            hashlib.sha256(unit.encode()).hexdigest(),
        )
        for unit in players
    }


def _dense_allocation(game, players, units):
    clock = SubstepClock()
    started = perf_counter()
    block, _ = allocate_block(
        game,
        players,
        "dense",
        game.reference(players[0]) * len(players) - game.value(players),
        CoverCache(),
        clock,
    )
    for unit, payment in block.payments_cents:
        split_unit_payment(units[unit], payment, clock)
    return block, perf_counter() - started, clock.totals


def measure_m1(repetitions: int, sizes=range(2, 15)) -> list[dict]:
    rows = []
    for k in sizes:
        game, players = dense_game(k)
        units = _dense_units(players)
        reference, _, _ = _dense_allocation(game, players, units)  # warm-up
        totals, steps = [], {name: [] for name in SUBSTEPS}
        for _ in range(repetitions):
            block, elapsed, substeps = _dense_allocation(game, players, units)
            if block != reference:
                raise RuntimeError("a P5 repetition produced a different allocation")
            totals.append(elapsed)
            for name in SUBSTEPS:
                steps[name].append(substeps[name])
        rows.append(
            {
                "k": k,
                "median_seconds": _median(totals),
                "q1_seconds": _quantile(totals, 0.25),
                "q3_seconds": _quantile(totals, 0.75),
                "substep_median_seconds": {name: _median(v) for name, v in steps.items()},
            }
        )
    return rows


def measure_m2(output: Path, repetitions: int, seeds: int, random_count: int) -> dict:
    cells = ofat_cells() + random_cells(random_count) + FAMILY_CELLS
    records = []
    for cell in cells:
        for seed_index in range(seeds):
            scenario = build_scenario(cell, seed_index, output / "scenarios")
            stages, _ = _p4_run(scenario)  # warm-up
            reference, _ = _p5_run(stages.formation, scenario.units)
            p4_times, p5_times = [], []
            for _ in range(repetitions):
                stages, p4_elapsed = _p4_run(scenario)
                allocation, p5_elapsed = _p5_run(stages.formation, scenario.units)
                if allocation.allocation_sha256 != reference.allocation_sha256:
                    raise RuntimeError("a P5 repetition produced a different allocation")
                p4_times.append(p4_elapsed)
                p5_times.append(p5_elapsed)
            block_sizes = [len(block.unit_ids) for block in stages.formation.blocks]
            records.append(
                {
                    "cell": cell.cell_id,
                    "seed_index": seed_index,
                    "formation_status": stages.formation.status,
                    "blocks": len(block_sizes),
                    "largest_block": max(block_sizes, default=0),
                    "projection_active_blocks": sum(b.projection_active for b in reference.blocks),
                    "t_p4_total_seconds": _median(p4_times),
                    "t_p5_seconds": _median(p5_times),
                    "allocation_sha256": reference.allocation_sha256,
                }
            )
    with_blocks = [r for r in records if r["blocks"] > 0]
    ratios = [r["t_p5_seconds"] / r["t_p4_total_seconds"] for r in with_blocks]
    p5 = [r["t_p5_seconds"] for r in with_blocks]
    sizes = [r["largest_block"] for r in with_blocks]
    return {
        "instances": len(records),
        "instances_with_blocks": len(with_blocks),
        "t_p5_seconds": {
            "median": _median(p5),
            "p95": _quantile(p5, 0.95),
            "max": max(p5, default=None),
        },
        "ratio_t_p5_over_t_p4_total": {
            "median": _median(ratios),
            "p95": _quantile(ratios, 0.95),
            "max": max(ratios, default=None),
        },
        "largest_block_size": {
            "median": _median(sizes),
            "p95": _quantile(sizes, 0.95),
            "max": max(sizes, default=None),
        },
        "projection_active_blocks": sum(r["projection_active_blocks"] for r in with_blocks),
        "records": records,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--random-cells", type=int, default=60)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    m0 = measure_m0(args.output, args.repetitions)
    print(f"M0 median T_P4_total(14) = {m0['median_seconds']:.4f} s", flush=True)
    m1 = measure_m1(args.repetitions)
    k14 = next(row for row in m1 if row["k"] == 14)
    print(f"M1 median T_P5(dense k=14) = {k14['median_seconds']:.4f} s", flush=True)
    m2 = measure_m2(args.output, args.repetitions, args.seeds, args.random_cells)
    ratio = m2["ratio_t_p5_over_t_p4_total"]["median"]
    verdict = {
        "M1": {
            "rule": M1_THRESHOLD,
            "t_p5_dense_k14_median_seconds": k14["median_seconds"],
            "t_p4_total_14_median_seconds": m0["median_seconds"],
            "met": k14["median_seconds"] < m0["median_seconds"],
        },
        "M2": {
            "rule": f"median T_P5 / T_P4_total <= {M2_THRESHOLD_RATIO}",
            "median_ratio": ratio,
            "met": ratio is not None and ratio <= M2_THRESHOLD_RATIO,
        },
    }
    document = {
        "schema": "p5-allocation-measurements-v1",
        "protocol": {"warm_up": 1, "repetitions": args.repetitions, "seeds": args.seeds},
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "elapsed_seconds": perf_counter() - started,
        "M0": m0,
        "M1": m1,
        "M2": m2,
        "verdict": verdict,
    }
    (args.output / "allocation_measurements.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"M2 {m2['instances_with_blocks']}/{m2['instances']} instances with blocks", flush=True)
    print(f"M2 median T_P5/T_P4_total = {ratio:.6f}", flush=True)
    print(json.dumps(verdict, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
