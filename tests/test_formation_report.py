"""P4.5: report writer rules (M8)."""

import json

import pytest
from coalition_travel.infrastructure.evaluation.formation_report import (
    REPORT_SCHEMA,
    RESIDUAL_NOTE,
    VOLATILE_NOTE,
    ReportError,
    write_report,
)


def document(**changes):
    base = {
        "schema": REPORT_SCHEMA,
        "stratum": "exploratory",
        "title": "test",
        "records": [{"value": 1}],
        "tables": [
            {
                "title": "decomposition",
                "columns": ["cell", "residual_collective_negotiation"],
                "rows": [["c1", -12]],
            }
        ],
    }
    base.update(changes)
    return base


def test_results_are_canonical_and_deterministic(tmp_path):
    first = write_report(document(), {"python": "x"}, tmp_path / "a")
    second = write_report(document(), {"python": "y"}, tmp_path / "b")
    assert first.results_sha256 == second.results_sha256  # environment is outside the digest
    assert first.results_path.read_bytes() == second.results_path.read_bytes()
    assert json.loads(first.results_path.read_text()) == document()


def test_mandatory_notes_are_rendered(tmp_path):
    manifest = write_report(document(), {}, tmp_path)
    text = manifest.markdown_path.read_text(encoding="utf-8")
    assert RESIDUAL_NOTE in text
    assert "milp_certified_exact" in text
    assert "aucune garantie de puissance statistique" in text


def test_volatile_tables_stay_out_of_results(tmp_path):
    timing = {"title": "durations", "columns": ["n", "median"], "rows": [[8, 0.12]]}
    manifest = write_report(document(stratum="performance"), {}, tmp_path, (timing,))
    assert "durations" not in manifest.results_path.read_text(encoding="utf-8")
    environment = json.loads(manifest.environment_path.read_text(encoding="utf-8"))
    assert environment["volatile_tables"] == [timing]
    assert VOLATILE_NOTE in manifest.markdown_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "changes",
    [
        {"schema": "other"},
        {"stratum": "anecdotal"},
        {"records": [{"seller_floor_total": 1}]},
        {"tables": [{"title": "t", "columns": ["a", "b"], "rows": [[1]]}]},
        {"tables": [{"title": "t", "columns": ["a"]}]},
    ],
)
def test_reporting_rules_are_enforced(tmp_path, changes):
    with pytest.raises(ReportError):
        write_report(document(**changes), {}, tmp_path)
