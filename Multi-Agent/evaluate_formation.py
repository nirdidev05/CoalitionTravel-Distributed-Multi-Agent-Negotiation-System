"""P4 experimental protocol runner: performance and exploratory strata (§11.3).

- correction stratum: the test suite (exhaustive comparisons, 100 % required);
- performance stratum: ``python Multi-Agent/evaluate_formation.py performance --output DIR``;
- exploratory stratum: ``python Multi-Agent/evaluate_formation.py exploratory --output DIR``;
- confirmatory stratum: not run here; it needs hypotheses pre-registered after the
  exploration and fresh seeds.

Every figure written by this script comes from an execution recorded in results.json.
Durations are measured only in the performance stratum and never enter a digest.
"""

import argparse
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from coalition_travel.application.coalition_candidates import (
    DEFAULT_LIMITS,
    ComponentTooLarge,
    enumerate_candidates,
)
from coalition_travel.application.coalition_costs import negotiate_candidate
from coalition_travel.application.coalition_feasibility import check_structural_feasibility
from coalition_travel.application.coalition_formation import form_coalitions
from coalition_travel.application.formation_baselines import (
    greedy_b1,
    optimality_gap,
    rescore_structure,
)
from coalition_travel.application.formation_evaluation import formation_metrics
from coalition_travel.application.lot_admissibility import lot_admissibility
from coalition_travel.application.negotiation_cache import CachingNegotiationOracle
from coalition_travel.application.partition_solver import solve_component
from coalition_travel.application.reference_costs import compute_reference_costs
from coalition_travel.domain.coalition_game import build_game
from coalition_travel.infrastructure.baselines.legacy_broker import (
    B0_ARRIVAL_ORDERS,
    arrival_orders,
    run_b0,
)
from coalition_travel.infrastructure.evaluation.formation_report import (
    REPORT_SCHEMA,
    write_report,
)
from coalition_travel.infrastructure.evaluation.formation_scenarios import (
    ScenarioParameters,
    build_scenario,
)

BASELINE_CELL = ScenarioParameters()
FACTOR_LEVELS = {
    "unit_count": (2, 4, 6, 8, 10, 12, 14),
    "profiles_per_unit": (1, 2, 3),
    "offer_count": (1, 2, 3, 5),
    "capacity_margin_percent": (0, 50),
    "tier_grid": ("flat", "moderate", "steep"),
    "budget_cv_percent": (0, 10, 30),
    "agreement_target_percent": (20, 50, 80, 100),
    "density_percent": (30, 60, 90),
}
FAMILY_CELLS = (
    ScenarioParameters(
        family="null",
        tier_grid="flat",
        offer_count=1,
        density_percent=100,
        agreement_target_percent=100,
        budget_cv_percent=0,
    ),
    ScenarioParameters(
        family="mutualisation",
        tier_grid="steep",
        offer_count=1,
        density_percent=100,
        agreement_target_percent=100,
        unit_count=10,
        profiles_per_unit=1,
    ),
    ScenarioParameters(family="isolated", density_percent=30, agreement_target_percent=50),
    ScenarioParameters(family="h2_violation", tier_grid="flat", density_percent=100),
    ScenarioParameters(family="large", unit_count=16, offer_count=1, density_percent=100),
)
RANDOM_CELLS_SEED = "p4-exploratory-random-cells-v1"
PERFORMANCE_SIZES = (6, 8, 10, 12, 14, 16)


def _rate(value: Fraction | None) -> str | None:
    return None if value is None else f"{float(value):.6f}"


def ofat_cells() -> tuple[ScenarioParameters, ...]:
    """Baseline cell, then one factor varied at a time (22 distinct cells)."""
    cells = {BASELINE_CELL.cell_id: BASELINE_CELL}
    base = BASELINE_CELL.as_dict()
    for factor, levels in FACTOR_LEVELS.items():
        for level in levels:
            cell = ScenarioParameters(**{**base, factor: level})
            cells.setdefault(cell.cell_id, cell)
    return tuple(cells.values())


def random_cells(count: int) -> tuple[ScenarioParameters, ...]:
    generator = random.Random(RANDOM_CELLS_SEED)
    cells: dict[str, ScenarioParameters] = {}
    while len(cells) < count:
        choice = {factor: generator.choice(levels) for factor, levels in FACTOR_LEVELS.items()}
        cell = ScenarioParameters(**choice)
        cells.setdefault(cell.cell_id, cell)
    return tuple(cells.values())


def evaluate_scenario(scenario) -> dict:
    """One instance: formation, metrics, decomposition, B1 and B0 re-scored."""
    lot = lot_admissibility(scenario.units, scenario.catalog, scenario.reference_date)
    caching = CachingNegotiationOracle(scenario.oracle)
    record = {
        "scenario_id": scenario.scenario_id,
        "cell_id": scenario.parameters.cell_id,
        "family": scenario.parameters.family,
        "seed_index": scenario.seed_index,
        "manifest": scenario.manifest,
    }
    if lot.status == "capacity_model_violated":
        record.update(status="capacity_model_violated", oracle_requests=0)
        return record
    references = compute_reference_costs(lot, caching)
    result = form_coalitions(lot, references, caching)
    metrics = formation_metrics(result, len(scenario.units), references)
    record.update(
        status=result.status,
        result_sha256=result.result_sha256,
        formation_run_id=result.formation_run_id,
        players=metrics.eligible_units,
        unserved=metrics.unserved_units,
        unresolved=metrics.unresolved_units,
        social_value_cents=metrics.social_value_cents,
        total_reference_cents=metrics.total_reference_cents,
        total_cost_cents=metrics.total_cost_cents,
        savings_rate=_rate(metrics.savings_rate),
        coalitions=metrics.coalition_count,
        units_in_coalitions=metrics.units_in_coalitions,
        coalition_sizes=[list(item) for item in metrics.coalition_sizes],
        candidates=metrics.candidates,
        feasible_candidates=metrics.feasible_candidates,
        feasibility_rate=_rate(metrics.feasibility_rate),
        negotiations=metrics.negotiations,
        agreements=metrics.agreements,
        agreement_rate=_rate(metrics.agreement_rate),
        oracle_requests=caching.statistics.requests,
        oracle_calls=caching.statistics.oracle_calls,
        cache_hits=caching.statistics.hits,
    )
    if metrics.decomposition is not None:
        d = metrics.decomposition
        record["decomposition"] = {
            "savings_individual_negotiation": d.savings_individual_negotiation,
            "savings_offer_switch": d.savings_offer_switch,
            "savings_public_tier_pooling": d.savings_public_tier_pooling,
            "residual_collective_negotiation": d.residual_collective_negotiation,
            "individual_list_cents": d.individual_list_cents,
            "reference_cents": d.reference_cents,
            "cost_cents": d.cost_cents,
        }
    games = [item.game for item in result.components if item.game is not None]
    if games:
        optimum = result.total_value_cents
        b1_value = sum(game.structure_value(greedy_b1(game)) for game in games)
        b1_gap = optimality_gap(optimum, b1_value)
        b0_values, b0_infeasible = [], []
        unit_ids = [unit.unit_id for unit in scenario.units]
        for order in arrival_orders(unit_ids, B0_ARRIVAL_ORDERS, scenario.scenario_id):
            rescored = rescore_structure(
                run_b0(scenario.units, order, scenario.reference_date), games
            )
            optimality_gap(optimum, rescored.value_cents)  # B0 cannot exceed the optimum
            b0_values.append(rescored.value_cents)
            b0_infeasible.append(len(rescored.infeasible_blocks))
        record["baselines"] = {
            "optimum_cents": optimum,
            "b1_value_cents": b1_value,
            "b1_gap_cents": b1_gap.absolute_cents,
            "b1_relative_gap": _rate(b1_gap.relative),
            "b0_value_mean_cents": statistics.fmean(b0_values),
            "b0_value_min_cents": min(b0_values),
            "b0_value_max_cents": max(b0_values),
            "b0_infeasible_blocks_mean": statistics.fmean(b0_infeasible),
            "b0_orders": B0_ARRIVAL_ORDERS,
        }
    return record


def _quartiles(values: list[float]) -> tuple[float, float, float] | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0], values[0], values[0]
    q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return q1, median, q3


def _fmt(value, digits=4):
    return None if value is None else round(value, digits)


def summarize_cells(records: list[dict]) -> list[list]:
    rows = []
    cells: dict[str, list[dict]] = {}
    for record in records:
        cells.setdefault(record["cell_id"], []).append(record)
    for items in cells.values():
        done = [r for r in items if "savings_rate" in r]
        rates = sorted(float(r["savings_rate"]) for r in done if r["savings_rate"] is not None)
        quart = _quartiles(rates)
        with_opt = [r for r in done if "baselines" in r]
        b1_suboptimal = sum(1 for r in with_opt if r["baselines"]["b1_gap_cents"] > 0)
        b1_gaps = [
            float(r["baselines"]["b1_relative_gap"])
            for r in with_opt
            if r["baselines"]["b1_relative_gap"] is not None
        ]
        b0_shares = [
            r["baselines"]["b0_value_mean_cents"] / r["baselines"]["optimum_cents"]
            for r in with_opt
            if r["baselines"]["optimum_cents"] > 0
        ]
        statuses = sorted({r["status"] for r in items})
        rows.append(
            [
                items[0]["manifest"]["parameters"]["family"],
                _describe(items[0]["manifest"]["parameters"]),
                len(items),
                "/".join(statuses),
                None if quart is None else _fmt(quart[1]),
                None if quart is None else f"[{_fmt(quart[0])}, {_fmt(quart[2])}]",
                _fmt(statistics.median([r["coalitions"] for r in done])) if done else None,
                f"{b1_suboptimal}/{len(with_opt)}" if with_opt else None,
                _fmt(max(b1_gaps)) if b1_gaps else None,
                _fmt(statistics.median(b0_shares)) if b0_shares else None,
                _fmt(
                    statistics.fmean(r["baselines"]["b0_infeasible_blocks_mean"] for r in with_opt)
                )
                if with_opt
                else None,
                _fmt(
                    statistics.median(
                        float(r["agreement_rate"]) for r in done if r["agreement_rate"]
                    )
                )
                if any(r["agreement_rate"] for r in done)
                else None,
            ]
        )
    return rows


def decomposition_rows(records: list[dict]) -> list[list]:
    cells: dict[str, list[dict]] = {}
    for record in records:
        if "decomposition" in record:
            cells.setdefault(record["cell_id"], []).append(record)
    rows = []
    for items in cells.values():
        totals = {
            key: sum(r["decomposition"][key] for r in items)
            for key in (
                "savings_individual_negotiation",
                "savings_offer_switch",
                "savings_public_tier_pooling",
                "residual_collective_negotiation",
                "reference_cents",
                "cost_cents",
            )
        }
        value = totals["reference_cents"] - totals["cost_cents"]
        identity = (
            totals["savings_offer_switch"]
            + totals["savings_public_tier_pooling"]
            + totals["residual_collective_negotiation"]
            == value
        )
        rows.append(
            [
                _describe(items[0]["manifest"]["parameters"]),
                len(items),
                value,
                totals["savings_offer_switch"],
                totals["savings_public_tier_pooling"],
                totals["residual_collective_negotiation"],
                totals["savings_individual_negotiation"],
                "oui" if identity else "NON",
            ]
        )
    return rows


def _describe(parameters: dict) -> str:
    return (
        f"{parameters['family']} n={parameters['unit_count']} p={parameters['profiles_per_unit']} "
        f"o={parameters['offer_count']} m={parameters['capacity_margin_percent']} "
        f"g={parameters['tier_grid']} cv={parameters['budget_cv_percent']} "
        f"a={parameters['agreement_target_percent']} d={parameters['density_percent']}"
    )


def environment() -> dict:
    import numpy
    import scipy

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def run_exploratory(output: Path, seeds: int, random_count: int) -> None:
    cells = ofat_cells() + random_cells(random_count) + FAMILY_CELLS
    records = []
    for cell in cells:
        for seed_index in range(seeds):
            scenario = build_scenario(cell, seed_index, output / "scenarios")
            records.append(evaluate_scenario(scenario))
    document = {
        "schema": REPORT_SCHEMA,
        "stratum": "exploratory",
        "title": "exploration descriptive",
        "design": {
            "ofat_cells": len(ofat_cells()),
            "random_cells": random_count,
            "family_cells": len(FAMILY_CELLS),
            "seeds_per_cell": seeds,
            "seed_range": [0, seeds],
            "b0_arrival_orders": B0_ARRIVAL_ORDERS,
        },
        "records": records,
        "tables": [
            {
                "title": "Cellules (médianes et quartiles sur les graines)",
                "columns": [
                    "famille",
                    "cellule",
                    "instances",
                    "statuts",
                    "taux d'économie médian",
                    "quartiles [Q1, Q3]",
                    "coalitions (médiane)",
                    "B1 sous-optimal",
                    "écart relatif B1 max",
                    "B0 / optimum (médiane)",
                    "blocs B0 non réalisables (moyenne)",
                    "taux d'accord (C, o) médian",
                ],
                "rows": summarize_cells(records),
            },
            {
                "title": "Décomposition des économies (sommes sur les instances, centimes)",
                "columns": [
                    "cellule",
                    "instances",
                    "v total",
                    "savings_offer_switch",
                    "savings_public_tier_pooling",
                    "residual_collective_negotiation",
                    "savings_individual_negotiation",
                    "identité exacte",
                ],
                "rows": decomposition_rows(records),
            },
        ],
    }
    manifest = write_report(document, environment(), output)
    print(f"exploratory: {len(records)} instances -> {manifest.markdown_path}")
    print(f"results.json sha256 {manifest.results_sha256}")


PHASES = (
    "admissibility",
    "references",
    "enumeration",
    "feasibility",
    "negotiation",
    "game",
    "solver_idp",
    "check_dp",
    "check_brute_force",
)


class _TimedOracle:
    """Proxy that measures the time spent inside the oracle itself (cache misses only)."""

    def __init__(self, oracle):
        self._oracle = oracle
        self.oracle_configuration_id = oracle.oracle_configuration_id
        self.seconds = 0.0

    def negotiate(self, request):
        started = time.perf_counter()
        try:
            return self._oracle.negotiate(request)
        finally:
            self.seconds += time.perf_counter() - started


def _instrumented_run(scenario) -> tuple[dict, dict]:
    """One timed execution with a stopwatch per phase.

    It replays the orchestration of ``form_coalitions`` step by step with the same public
    functions, so that the duration can be attributed to enumeration, negotiation or
    optimization. The caller checks once, outside any timing, that the result equals
    the one of ``form_coalitions``.
    """
    clock = time.perf_counter
    phases = dict.fromkeys(PHASES, 0.0)
    started = clock()
    lot = lot_admissibility(scenario.units, scenario.catalog, scenario.reference_date)
    phases["admissibility"] = clock() - started
    timed_oracle = _TimedOracle(scenario.oracle)
    caching = CachingNegotiationOracle(timed_oracle)
    record = {"scenario_id": scenario.scenario_id, "unit_count": len(scenario.units)}
    if lot.status == "capacity_model_violated":
        record.update(status="capacity_model_violated", component_sizes=[], candidates=0)
        record.update(oracle_requests=0, oracle_calls=0, cache_hits=0, value_cents=0, blocks=[])
        phases["oracle_inside"] = 0.0
        return record, phases
    mark = clock()
    references = compute_reference_costs(lot, caching)
    phases["references"] = clock() - mark
    relation = references.effective_relation
    sizes, blocks, value, candidate_count, too_large = [], [], 0, 0, False
    for component in references.effective_components:
        sizes.append(len(component.units))
        mark = clock()
        try:
            candidates = enumerate_candidates(relation, component, DEFAULT_LIMITS)
        except ComponentTooLarge:
            phases["enumeration"] += clock() - mark
            too_large = True
            continue
        phases["enumeration"] += clock() - mark
        candidate_count += len(candidates)
        mark = clock()
        for candidate in candidates:
            check_structural_feasibility(candidate, lot, references)
        phases["feasibility"] += clock() - mark
        mark = clock()
        costs = {c.unit_ids: negotiate_candidate(c, relation, caching) for c in candidates}
        phases["negotiation"] += clock() - mark
        mark = clock()
        game = build_game(
            component.component_id,
            {unit.unit_id: references.reference(unit.unit_id) for unit in component.units},
            {coalition: cost.cost_cents for coalition, cost in costs.items()},
            caching.oracle_configuration_id,
        )
        phases["game"] += clock() - mark
        mark = clock()
        solution = solve_component(game, cross_checks=())
        phases["solver_idp"] += clock() - mark
        mark = clock()
        if solve_component(game, method="dp", cross_checks=()).structure != solution.structure:
            raise RuntimeError("dp_search and idp_search disagree")
        phases["check_dp"] += clock() - mark
        if 1 < game.n <= DEFAULT_LIMITS.brute_force_max_units:
            mark = clock()
            check = solve_component(game, method="brute_force", cross_checks=())
            if check.tie_break_score != solution.tie_break_score:
                raise RuntimeError("brute force and idp_search disagree")
            phases["check_brute_force"] += clock() - mark
        blocks.extend(list(block) for block in solution.structure)
        value += solution.value_cents
    phases["oracle_inside"] = timed_oracle.seconds  # included in references + negotiation
    statistics_ = caching.statistics
    record.update(
        status="incomplete" if too_large else "optimized",
        component_sizes=sorted(sizes),
        candidates=candidate_count,
        oracle_requests=statistics_.requests,
        oracle_calls=statistics_.oracle_calls,
        cache_hits=statistics_.hits,
        value_cents=value,
        blocks=sorted(blocks),
    )
    return record, phases


def _official_record(scenario) -> tuple[int, list]:
    """Value and structure computed by form_coalitions (untimed equivalence check)."""
    lot = lot_admissibility(scenario.units, scenario.catalog, scenario.reference_date)
    if lot.status == "capacity_model_violated":
        return 0, []
    caching = CachingNegotiationOracle(scenario.oracle)
    result = form_coalitions(lot, compute_reference_costs(lot, caching), caching)
    return result.total_value_cents, sorted(list(block) for block in result.structure)


def run_performance(
    output: Path, instances: int, repetitions: int, sizes: tuple[int, ...] = PERFORMANCE_SIZES
) -> None:
    records, volatile_instances = [], []
    for size in sizes:
        cell = ScenarioParameters(
            unit_count=size,
            profiles_per_unit=1,
            offer_count=1,
            density_percent=100,
            agreement_target_percent=100,
        )
        for seed_index in range(instances):
            scenario = build_scenario(cell, seed_index, output / "scenarios")
            warm_record, warm_phases = _instrumented_run(scenario)  # warm-up, kept apart
            if _official_record(scenario) != (warm_record["value_cents"], warm_record["blocks"]):
                raise RuntimeError("instrumented run differs from form_coalitions")
            totals = []
            phase_samples = {phase: [] for phase in (*PHASES, "oracle_inside")}
            for _ in range(repetitions):
                record, phases = _instrumented_run(scenario)
                if record != warm_record:
                    raise RuntimeError("a repetition produced a different result")
                totals.append(sum(phases[phase] for phase in PHASES))
                for phase in (*PHASES, "oracle_inside"):
                    phase_samples[phase].append(phases[phase])
            records.append({**warm_record, "seed_index": seed_index})
            q1, median, q3 = _quartiles(sorted(totals))
            volatile_instances.append(
                {
                    "unit_count": size,
                    "seed_index": seed_index,
                    "largest_component": max(warm_record["component_sizes"], default=0),
                    "candidates": warm_record["candidates"],
                    "oracle_calls": warm_record["oracle_calls"],
                    "cache_hits": warm_record["cache_hits"],
                    "warm_up_seconds": sum(warm_phases[phase] for phase in PHASES),
                    "timed_seconds": totals,
                    "median_seconds": median,
                    "q1_seconds": q1,
                    "q3_seconds": q3,
                    "phase_median_seconds": {
                        phase: statistics.median(samples)
                        for phase, samples in phase_samples.items()
                    },
                }
            )
    deterministic_rows, timing_rows, phase_rows, instance_rows = [], [], [], []
    for size in sizes:
        items = [r for r in records if r["unit_count"] == size]
        times = [i for i in volatile_instances if i["unit_count"] == size]
        deterministic_rows.append(
            [
                size,
                len(items),
                "/".join(sorted({r["status"] for r in items})),
                round(statistics.fmean(max(r["component_sizes"], default=0) for r in items), 2),
                round(statistics.fmean(r["candidates"] for r in items), 1),
                round(statistics.fmean(r["oracle_requests"] for r in items), 1),
                round(statistics.fmean(r["oracle_calls"] for r in items), 1),
                round(statistics.fmean(r["cache_hits"] for r in items), 1),
            ]
        )
        all_totals = sorted(value for i in times for value in i["timed_seconds"])
        q1, median, q3 = _quartiles(all_totals)
        timing_rows.append(
            [
                size,
                len(all_totals),
                round(statistics.median(i["warm_up_seconds"] for i in times), 4),
                round(median, 4),
                f"[{round(q1, 4)}, {round(q3, 4)}]",
                round(max(all_totals), 4),
            ]
        )
        phase_rows.append(
            [size]
            + [
                round(statistics.median(i["phase_median_seconds"][phase] for i in times), 4)
                for phase in (*PHASES, "oracle_inside")
            ]
        )
        for item in times:
            instance_rows.append(
                [
                    size,
                    item["seed_index"],
                    item["largest_component"],
                    item["candidates"],
                    item["oracle_calls"],
                    item["cache_hits"],
                    round(item["warm_up_seconds"], 4),
                    round(item["median_seconds"], 4),
                    f"[{round(item['q1_seconds'], 4)}, {round(item['q3_seconds'], 4)}]",
                ]
            )
    document = {
        "schema": REPORT_SCHEMA,
        "stratum": "performance",
        "title": "banc d'essai de performance",
        "design": {
            "sizes": list(sizes),
            "instances_per_size": instances,
            "warm_up_runs": 1,
            "timed_repetitions": repetitions,
            "phases": list(PHASES),
            "cell": "factorial, 1 profile per unit, 1 offer, density 100, agreement 100, "
            "moderate grid",
        },
        "records": records,
        "tables": [
            {
                "title": "Charge déterministe par taille (moyennes sur les instances)",
                "columns": [
                    "unités",
                    "instances",
                    "statuts",
                    "plus grande composante",
                    "candidats",
                    "requêtes au cache",
                    "appels réels à l'oracle",
                    "succès du cache",
                ],
                "rows": deterministic_rows,
            }
        ],
    }
    volatile_tables = (
        {
            "title": "Durée totale par taille, secondes (toutes les mesures chronométrées)",
            "columns": ["unités", "mesures", "chauffe (médiane)", "médiane", "[Q1, Q3]", "maximum"],
            "rows": timing_rows,
        },
        {
            "title": "Médiane par phase, secondes (médiane des médianes par instance) ; "
            "oracle_inside est déjà inclus dans references et negotiation",
            "columns": ["unités", *PHASES, "oracle_inside"],
            "rows": phase_rows,
        },
        {
            "title": "Détail par instance",
            "columns": [
                "unités",
                "graine",
                "plus grande composante",
                "candidats",
                "appels oracle",
                "succès cache",
                "chauffe (s)",
                "médiane (s)",
                "[Q1, Q3] (s)",
            ],
            "rows": instance_rows,
        },
    )
    timing_environment = environment()
    timing_environment["instances"] = volatile_instances
    manifest = write_report(document, timing_environment, output, volatile_tables)
    print(f"performance: {len(records)} instances -> {manifest.markdown_path}")
    print(f"results.json sha256 {manifest.results_sha256}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="stratum", required=True)
    exploratory = sub.add_parser("exploratory")
    exploratory.add_argument("--output", type=Path, required=True)
    exploratory.add_argument("--seeds", type=int, default=20)
    exploratory.add_argument("--random-cells", type=int, default=60)
    performance = sub.add_parser("performance")
    performance.add_argument("--output", type=Path, required=True)
    performance.add_argument("--instances", type=int, default=10)
    performance.add_argument("--repetitions", type=int, default=5)
    performance.add_argument("--sizes", type=int, nargs="+", default=list(PERFORMANCE_SIZES))
    args = parser.parse_args(argv)
    if args.stratum == "exploratory":
        run_exploratory(args.output, args.seeds, args.random_cells)
    else:
        run_performance(args.output, args.instances, args.repetitions, tuple(args.sizes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
