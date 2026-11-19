"""Byte-for-byte historical baseline and mutation check for working-tree Entry.py."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from BuyerAgent import BuyerAgent
from Message import Message
from Negotiation import run_alternating_negotiation
from SellerAgent import SellerAgent

# Documentary provenance only; tests execute the working tree and never this commit.
BASELINE_COMMIT = "53649ef3c5788edcf0dfd9dd01da14f1b0ae777d"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = Path(__file__).parent / "golden/entry_run_scenarios_2026-11-19.txt"
GOLDEN_SHA256 = "a5977fde152d329b53c2651ff89534a5fdd605b38b1419efacc6e1d533bd08b7"
# Modules whose resolved source file proves which project directory is executed.
ORIGIN_MODULES = ("Entry", "SellerAgent", "Leader", "coalition_travel")


def _subprocess_environment(project_directory: Path) -> dict[str, str]:
    """Drop every inherited PYTHON* variable, then pin the interpreter settings.

    The comparison is byte-for-byte, so a developer setting such as
    PYTHONIOENCODING=latin-1 must not be able to change the captured output.
    """
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("PYTHON")
    }
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": str(project_directory),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
        }
    )
    return environment


def _module_origins(project_directory: Path) -> dict[str, Path]:
    """Return the source file each origin module resolves to in the subprocess."""
    invocation = (
        "import importlib, json; "
        f"names = {ORIGIN_MODULES!r}; "
        "print(json.dumps({name: importlib.import_module(name).__file__ for name in names}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", invocation],
        cwd=project_directory,
        env=_subprocess_environment(project_directory),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    return {name: Path(path).resolve() for name, path in json.loads(completed.stdout).items()}


def _assert_modules_resolve_inside(project_directory: Path) -> None:
    root = project_directory.resolve()
    for name, origin in _module_origins(project_directory).items():
        assert origin.is_relative_to(root), f"{name} resolved outside {root}: {origin}"


def _run_entry(project_directory: Path) -> subprocess.CompletedProcess:
    environment = _subprocess_environment(project_directory)
    entry_path = project_directory / "Entry.py"
    invocation = (
        "from datetime import date; import runpy; "
        f"entry = runpy.run_path({str(entry_path)!r}, run_name='EntryGoldenMaster'); "
        "entry['run_scenarios'](reference_date=date(2026, 11, 19))"
    )
    return subprocess.run(
        [sys.executable, "-c", invocation],
        cwd=project_directory,
        env=environment,
        capture_output=True,
        timeout=90,
        check=False,
    )


def _scenario(text: str, beginning: str, ending: str) -> str:
    start = text.index(beginning)
    return text[start : text.index(ending, start)]


def test_entry_run_scenarios_working_tree_matches_pinned_historical_golden_master():
    """Run Entry.py from the current working tree against the pinned reference."""
    expected = GOLDEN_PATH.read_bytes()
    assert hashlib.sha256(expected).hexdigest() == GOLDEN_SHA256
    # Prove the executed modules are the repository working tree, not an archive or copy.
    _assert_modules_resolve_inside(REPOSITORY_ROOT / "Multi-Agent")
    completed = _run_entry(REPOSITORY_ROOT / "Multi-Agent")

    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stderr == b""
    assert completed.stdout == expected

    output = completed.stdout.decode("utf-8")
    bilateral = _scenario(output, "SCÉNARIO 1", "SCÉNARIO 2")
    broker = _scenario(output, "SCÉNARIO 2", "SCÉNARIO 3")
    deadline = _scenario(output, "SCÉNARIO 4", "SCÉNARIO 5")
    optimization_and_negotiation = _scenario(output, "SCÉNARIO 5", "FIN DES SCÉNARIOS")
    assert "Accord : 453.60€ en 6 tours." in bilateral
    assert "ACCORD OBTENU à 1512.00€" in broker
    assert "ACCORD OBTENU à 1792.00€" in broker
    assert deadline.count("Accord : 408.24€ en 8 tours.") == 2
    assert "V(SC*)        = 250.60" in optimization_and_negotiation
    assert "valeur 198.00€" in optimization_and_negotiation
    assert "valeur 181.20€" in optimization_and_negotiation
    assert "ACCORD OBTENU à 957.60€" in optimization_and_negotiation
    assert "ACCORD OBTENU à 1478.40€" in optimization_and_negotiation
    assert "Bob           68.20      491.80€" in optimization_and_negotiation
    assert "Carol         66.95      493.05€" in optimization_and_negotiation
    assert "Eve           66.45      493.55€" in optimization_and_negotiation
    assert "ACCORD OBTENU à 1960.00€" in optimization_and_negotiation


def test_entry_golden_master_detects_seller_mutation_only_in_temporary_copy(tmp_path):
    """Prove a real working-tree execution detects a controlled source mutation."""
    expected = GOLDEN_PATH.read_bytes()
    assert hashlib.sha256(expected).hexdigest() == GOLDEN_SHA256

    copied_project = tmp_path / "Multi-Agent"
    shutil.copytree(
        REPOSITORY_ROOT / "Multi-Agent",
        copied_project,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    seller_path = copied_project / "SellerAgent.py"
    assert seller_path.is_relative_to(tmp_path)
    original_seller = seller_path.read_bytes()
    # The editable install appends the repository to sys.path after PYTHONPATH; prove the
    # copy still shadows it, so the witness and the mutation really execute the copy.
    _assert_modules_resolve_inside(copied_project)

    witness = _run_entry(copied_project)
    assert witness.returncode == 0, witness.stderr.decode("utf-8", errors="replace")
    assert witness.stderr == b""
    assert witness.stdout == expected

    source = seller_path.read_text(encoding="utf-8")
    old_expression = "self.current_offer * 0.90"
    new_expression = "self.current_offer * 0.91"
    occurrences = source.count(old_expression)
    if occurrences != 1:
        pytest.fail(
            f"expected exactly one seller mutation target, found {occurrences} in temporary copy"
        )
    mutated_source = source.replace(old_expression, new_expression, 1)
    if mutated_source == source or new_expression not in mutated_source:
        pytest.fail("seller mutation did not change the temporary source copy")
    seller_path.write_text(mutated_source, encoding="utf-8")
    assert old_expression not in seller_path.read_text(encoding="utf-8")
    assert new_expression in seller_path.read_text(encoding="utf-8")

    mutated = _run_entry(copied_project)
    assert mutated.returncode == 0, mutated.stderr.decode("utf-8", errors="replace")
    assert mutated.stdout != expected
    assert (REPOSITORY_ROOT / "Multi-Agent/SellerAgent.py").read_bytes() == original_seller


def test_golden_master_ignores_inherited_python_environment(monkeypatch):
    """Developer PYTHON* settings must not alter the byte-for-byte comparison."""
    expected = GOLDEN_PATH.read_bytes()
    for name, value in {
        "PYTHONIOENCODING": "latin-1",
        "PYTHONUTF8": "0",
        "PYTHONWARNINGS": "error",
        "PYTHONOPTIMIZE": "2",
        "PYTHONHASHSEED": "123",
    }.items():
        monkeypatch.setenv(name, value)

    completed = _run_entry(REPOSITORY_ROOT / "Multi-Agent")

    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stderr == b""
    assert completed.stdout == expected


def test_historical_characterization_known_per_ticket_vs_group_total_quantity_defect():
    """Legacy buyer accepts a single-ticket quote as a four-traveler total price.

    This locks a known historical defect for diagnosis only. It is not a desired
    contract for the new group-negotiation workflow.
    """
    reference_date = date(2026, 11, 19)
    buyer = BuyerAgent(
        "FourTravelerProfile",
        budget=2_000,
        deadline=reference_date + timedelta(days=30),
        reference_date=reference_date,
        traveller_count=4,
        budget_per_person=500,
    )
    seller = SellerAgent("PerTicketSeller", min_price=400, release_date="01-Dec")

    accepted, turns = run_alternating_negotiation(
        Message(buyer, seller, "CFP", {"destination": "Tokyo"}), seller
    )

    assert buyer.traveller_count == 4
    assert buyer.budget_per_person == 500
    assert buyer.budget == 2_000
    assert seller.min_price == 400
    assert seller.current_offer == 560
    assert accepted.type == "ACCEPT"
    assert accepted.content["price"] == 560
    assert turns == 2
    assert accepted.content["price"] / buyer.traveller_count == 140
    assert accepted.content["price"] / buyer.traveller_count < buyer.budget_per_person
