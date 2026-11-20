"""Economic reference scenarios (final mission, step 3): regression on the pinned results.

The pinned file was produced by ``Multi-Agent/evaluate_scenarios.py`` (the algorithm is
the source of truth) and is compared byte for byte; the payment invariants are checked
again on every run.
"""

import json
from pathlib import Path

import evaluate_scenarios

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / "docs" / "final_results" / "economic_scenarios_v1.results.json"


def _rerun():
    document, digest = evaluate_scenarios.load_scenarios(evaluate_scenarios.DEFAULT_SCENARIOS)
    rows = [
        evaluate_scenarios.summarise(scenario, evaluate_scenarios.run_scenario(scenario))
        for scenario in document["scenarios"]
    ]
    return document, digest, rows


def test_the_scenarios_reproduce_the_pinned_results():
    _, digest, rows = _rerun()
    pinned = json.loads(PINNED.read_text(encoding="utf-8"))
    assert pinned["scenarios_sha256"] == digest
    assert rows == pinned["results"]


def test_every_scenario_reaches_its_intent_and_keeps_the_payment_invariants():
    _, _, rows = _rerun()
    statuses = {row["scenario_id"]: (row["status"], row["modifiers"]) for row in rows}
    for row in rows:
        assert row["checks_pass"], row["scenario_id"]
        assert row["exit_code"] == 0, row["scenario_id"]
        if row["intent"] in {
            "served_in_coalition",
            "alone_no_beneficial_coalition",
            "alone_social_optimum",
            "no_admissible_offer",
            "no_solo_reference",
            "capacity_model_violated",
            "component_too_large",
        }:
            assert row["status"] == row["intent"], row["scenario_id"]
    assert statuses["s13-budget-cap"] == ("served_in_coalition", ["budget_cap_active"])


def test_the_arrival_order_of_the_pool_does_not_change_the_economics():
    _, _, rows = _rerun()
    by_id = {row["scenario_id"]: row for row in rows}
    keys = ("status", "modifiers", "payment_cents", "reference_cents", "saving_cents")
    first, reversed_order = by_id["s01-coalition-e3"], by_id["s09-arrival-order-reversed"]
    assert {k: first[k] for k in keys} == {k: reversed_order[k] for k in keys}


def test_the_scenario_file_is_strict(tmp_path):
    document = json.loads(evaluate_scenarios.DEFAULT_SCENARIOS.read_text(encoding="utf-8"))
    document["scenarios"].append(dict(document["scenarios"][0]))
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    try:
        evaluate_scenarios.load_scenarios(path)
    except evaluate_scenarios.ScenarioError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("a duplicate scenario_id must be refused")
