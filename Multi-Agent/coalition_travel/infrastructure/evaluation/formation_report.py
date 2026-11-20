"""Canonical result file and Markdown report of a P4 experiment stratum (M8).

Rules (specification §8.3 M8 and §11.3):

- ``results.json`` is canonical JSON (sorted keys, fixed separators); its SHA-256 is the
  report identity. The execution environment goes to ``environment.json``, outside the
  hashed part, together with any duration;
- every number comes from a recorded execution; nothing is typed by hand;
- each stratum is labelled; exploratory figures are descriptive only;
- any table that contains ``residual_collective_negotiation`` carries the mandatory
  note that it is an accounting residual, not causally identifiable;
- a MILP solution is called an exact optimum only when its label is
  ``milp_certified_exact``;
- no key may mention a seller floor.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

REPORT_SCHEMA = "p4-formation-report-v1"
STRATA = ("correctness", "performance", "exploratory", "confirmatory")
STRATUM_NOTES = {
    "correctness": "Strate correction : exigence de 100 %, non statistique.",
    "performance": "Strate performance : durées de la machine indiquée, médiane et "
    "écart interquartile de 5 répétitions après une chauffe ; jamais dans un identifiant.",
    "exploratory": "Strate exploratoire : statistiques descriptives uniquement, aucune "
    "p-valeur, aucune garantie de puissance statistique.",
    "confirmatory": "Strate confirmatoire : hypothèses préenregistrées, graines disjointes.",
}
RESIDUAL_NOTE = (
    "`residual_collective_negotiation` : résidu comptable, non identifiable causalement "
    "(plancher privé du palier collectif, avantage de négociation et artefact budgétaire "
    "de la stratégie historique mêlés)."
)
MILP_NOTE = (
    "Une solution MILP n'est un optimum exact que si son libellé est "
    "`milp_certified_exact` ; la structure officielle vient toujours d'`idp_search`."
)
SYNTHETIC_NOTE = "Données synthétiques ; aucune généralisation à un marché réel."


class ReportError(ValueError):
    """The report document violates a reporting rule."""


@dataclass(frozen=True)
class ReportManifest:
    results_path: Path
    environment_path: Path
    markdown_path: Path
    results_sha256: str


def _forbidden_keys(value, path="") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if "floor" in str(key).casefold():
                found.append(f"{path}/{key}")
            found.extend(_forbidden_keys(item, f"{path}/{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_keys(item, f"{path}[{index}]"))
    return found


def canonical_bytes(document: dict) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _markdown_table(table: dict) -> list[str]:
    columns = table["columns"]
    lines = [f"### {table['title']}", ""]
    if "residual_collective_negotiation" in columns:
        lines.extend([f"> {RESIDUAL_NOTE}", ""])
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "---|" * len(columns))
    for row in table["rows"]:
        lines.append("| " + " | ".join("—" if cell is None else str(cell) for cell in row) + " |")
    lines.append("")
    return lines


VOLATILE_NOTE = (
    "Tableau volatil : durées mesurées sur la machine décrite dans environment.json ; "
    "il n'entre pas dans results.json ni dans son empreinte."
)


def render_markdown(document: dict, volatile_tables: tuple[dict, ...] = ()) -> str:
    stratum = document["stratum"]
    lines = [
        f"# P4 — {document['title']}",
        "",
        f"- Schéma : `{document['schema']}`",
        f"- Strate : **{stratum}**",
        f"- {STRATUM_NOTES[stratum]}",
        f"- {SYNTHETIC_NOTE}",
        f"- {MILP_NOTE}",
        "",
    ]
    for table in document["tables"]:
        lines.extend(_markdown_table(table))
    for table in volatile_tables:
        lines.extend([f"> {VOLATILE_NOTE}", ""])
        lines.extend(_markdown_table(table))
    return "\n".join(lines)


def _check_table(table: dict) -> None:
    if set(table) != {"title", "columns", "rows"}:
        raise ReportError("a table needs exactly title, columns and rows")
    if any(len(row) != len(table["columns"]) for row in table["rows"]):
        raise ReportError(f"table {table['title']!r} has a row of the wrong width")


def write_report(
    document: dict,
    environment: dict,
    output_dir: Path,
    volatile_tables: tuple[dict, ...] = (),
) -> ReportManifest:
    """Validate and write results.json, environment.json and report.md.

    ``volatile_tables`` (durations) are rendered in report.md and stored in
    environment.json, never in results.json.
    """
    if document.get("schema") != REPORT_SCHEMA:
        raise ReportError(f"schema must be {REPORT_SCHEMA}")
    if document.get("stratum") not in STRATA:
        raise ReportError(f"stratum must be one of {STRATA}")
    for key in ("title", "tables", "records"):
        if key not in document:
            raise ReportError(f"missing section {key!r}")
    for table in (*document["tables"], *volatile_tables):
        _check_table(table)
    environment = {**environment, "volatile_tables": list(volatile_tables)}
    leaks = _forbidden_keys(document) + _forbidden_keys(environment)
    if leaks:
        raise ReportError(f"seller floor keys are not allowed in reports: {leaks}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_bytes = canonical_bytes(document)
    results_path = output_dir / "results.json"
    results_path.write_bytes(results_bytes)
    environment_path = output_dir / "environment.json"
    environment_path.write_text(
        json.dumps(environment, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path = output_dir / "report.md"
    markdown_path.write_text(render_markdown(document, tuple(volatile_tables)), encoding="utf-8")
    return ReportManifest(
        results_path=results_path,
        environment_path=environment_path,
        markdown_path=markdown_path,
        results_sha256=hashlib.sha256(results_bytes).hexdigest(),
    )
