"""Fixed economic reference scenarios run through the public command (final mission, §7.2).

Each scenario is a traveller request plus the other pending requests of its pool, on the
frozen catalogue named by the request (v1, or v2 for a route request). The scenario file
holds only public, fictional requests: the private seller terms stay in the frozen
catalogues, which are not modified.

The algorithm is the source of truth. A scenario carries an ``intent`` (the economic
situation it was written to exhibit); the runner records what the command actually
returns, checks the payment invariants on the public output, and reports an intent that
was not reached instead of hiding it.

    python Multi-Agent/evaluate_scenarios.py [--scenarios FILE] [--output FILE]
"""

import argparse
import hashlib
import io
import json
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import plan_trip
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.trip_planning import DemandPoolSnapshot, PlanningRequest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIOS = ROOT / "data" / "scenarios" / "economic_scenarios_v1.json"
SCHEMA = "economic-scenarios-v1"
RESULT_SCHEMA = "economic-scenario-results-v1"
SCENARIO_KEYS = frozenset(
    {"scenario_id", "intent", "description", "reference_date", "user", "pool"}
)
FILE_KEYS = frozenset({"schema", "synthetic", "catalog_versions", "purpose", "scenarios"})


class ScenarioError(ValueError):
    """The scenario file does not follow economic-scenarios-v1."""


def load_scenarios(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    document = json.loads(raw.decode("utf-8"), parse_float=Decimal)
    if not isinstance(document, dict) or set(document) != FILE_KEYS:
        raise ScenarioError(f"the file must have exactly the keys {sorted(FILE_KEYS)}")
    if document["schema"] != SCHEMA or document["synthetic"] is not True:
        raise ScenarioError(f"schema must be {SCHEMA!r} and synthetic must be true")
    seen = set()
    for scenario in document["scenarios"]:
        if not isinstance(scenario, dict) or set(scenario) != SCENARIO_KEYS:
            raise ScenarioError(f"a scenario must have exactly the keys {sorted(SCENARIO_KEYS)}")
        if scenario["scenario_id"] in seen:
            raise ScenarioError(f"duplicate scenario_id {scenario['scenario_id']!r}")
        seen.add(scenario["scenario_id"])
        TravelRequestDraft.model_validate(scenario["user"])
        for item in scenario["pool"]:
            if set(item) != {"request_id", "draft"} or not item["request_id"].startswith("pool-"):
                raise ScenarioError("a pool entry has exactly request_id (pool-…) and draft")
            TravelRequestDraft.model_validate(item["draft"])
    return document, hashlib.sha256(raw).hexdigest()


def _pool_loader(scenario: dict, catalog_version: str):
    entries = scenario["pool"]
    digest = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    snapshot = DemandPoolSnapshot(
        version=f"scenario-pool:{scenario['scenario_id']}",
        sha256=digest,
        catalog_version=catalog_version,
        requests=tuple(
            PlanningRequest(item["request_id"], TravelRequestDraft.model_validate(item["draft"]))
            for item in entries
        ),
    )
    return lambda _path: snapshot


def _is_route(draft: dict) -> bool:
    return any(
        draft.get(key) is not None
        for key in ("origin", "trip_type", "departure_before", "return_after", "return_before")
    )


def run_scenario(scenario: dict) -> dict:
    user = scenario["user"]
    catalog_version = "catalog-v2" if _is_route(user) else "catalog-v1"
    with tempfile.TemporaryDirectory() as directory:
        draft_path = Path(directory) / "draft.json"
        draft_path.write_text(json.dumps(user), encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        code = plan_trip.run(
            [
                "--draft-json",
                str(draft_path),
                "--reference-date",
                scenario["reference_date"],
                "--yes",
                "--json",
            ],
            stdin=io.StringIO(""),
            stdout=stdout,
            stderr=stderr,
            environ={},
            load_pool=_pool_loader(scenario, catalog_version),
            today=lambda: date.fromisoformat(scenario["reference_date"]),
        )
    output = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else None
    return {"exit_code": code, "output": output}


def summarise(scenario: dict, outcome: dict) -> dict:
    """Public facts of one run, plus invariant checks on the public payment."""
    output = outcome["output"] or {}
    status = output.get("status", {})
    allocation = output.get("allocation") or {}
    block = output.get("block") or {}
    user = scenario["user"]
    budget_cents = int(Decimal(str(user["budget_per_person"])) * 100) * user["travellers"]
    payment = allocation.get("payment_cents")
    reference = allocation.get("reference_cents")
    saving = allocation.get("saving_cents")
    checks = {}
    if payment is not None:
        checks["payment_within_budget"] = payment <= budget_cents
        checks["payment_plus_saving_is_reference"] = (
            reference is None or saving is None or payment + saving == reference
        )
        checks["saving_non_negative"] = saving is None or saving >= 0
    code = status.get("code") or output.get("reason") or output.get("status")
    return {
        "scenario_id": scenario["scenario_id"],
        "intent": scenario["intent"],
        "exit_code": outcome["exit_code"],
        "schema": output.get("schema"),
        "status": code if isinstance(code, str) else json.dumps(code, sort_keys=True),
        "modifiers": status.get("modifiers", []),
        "payment_cents": payment,
        "reference_cents": reference,
        "saving_cents": saving,
        "projection_active": allocation.get("projection_active"),
        "unit_saturated": allocation.get("unit_saturated"),
        "block_offer": block.get("offer_id"),
        "block_seats": block.get("seats"),
        "output_sha256": hashlib.sha256(
            json.dumps(outcome["output"], sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "checks": checks,
        "checks_pass": all(checks.values()),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    document, digest = load_scenarios(args.scenarios)
    rows = [summarise(s, run_scenario(s)) for s in document["scenarios"]]
    result = {
        "schema": RESULT_SCHEMA,
        "scenarios_schema": SCHEMA,
        "scenarios_sha256": digest,
        "results": rows,
        "all_checks_pass": all(row["checks_pass"] for row in rows),
    }
    rendered = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if result["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
