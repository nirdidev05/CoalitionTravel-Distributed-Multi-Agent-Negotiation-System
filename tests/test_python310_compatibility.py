"""The project declares requires-python >= 3.10; check it with a real 3.10 interpreter.

Only modules that depend on the standard library alone can be imported here: the 3.10
interpreter has no project dependencies installed. The whole code base is also parsed
with the 3.10 grammar. Both checks run in isolated mode (-I) and write no bytecode (-B).
The test is skipped when no python3.10 executable is available.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON310 = shutil.which("python3.10")

STDLIB_ONLY_MODULES = (
    "coalition_travel.domain.money",
    "coalition_travel.domain.destination",
    "coalition_travel.domain.traveler_profile",
    "coalition_travel.domain.travel_unit",
    "coalition_travel.domain.offer",
    "coalition_travel.infrastructure.catalog.json_catalog",
    "coalition_travel.infrastructure.evaluation.provenance",
)

pytestmark = pytest.mark.skipif(PYTHON310 is None, reason="python3.10 is not installed")


def _run_python310(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON310, "-I", "-B", "-c", code],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_interpreter_is_really_python_3_10():
    completed = _run_python310("import sys; print(sys.version_info[:2])")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "(3, 10)"


def test_standard_library_only_modules_import_under_python_3_10():
    code = (
        "import importlib, sys; "
        f"sys.path.insert(0, {str(REPOSITORY_ROOT / 'Multi-Agent')!r}); "
        f"[importlib.import_module(name) for name in {STDLIB_ONLY_MODULES!r}]"
    )
    completed = _run_python310(code)
    assert completed.returncode == 0, completed.stderr


def test_project_sources_parse_with_python_3_10_grammar():
    code = (
        "import ast, pathlib, sys; "
        f"root = pathlib.Path({str(REPOSITORY_ROOT)!r}); "
        "files = [p for d in ('Multi-Agent', 'tests') for p in (root / d).rglob('*.py') "
        "if '__pycache__' not in p.parts and not any(part.endswith('.egg-info') for part in p.parts)]; "
        "errors = []\n"
        "for path in files:\n"
        "    try:\n"
        "        ast.parse(path.read_text(encoding='utf-8'), str(path))\n"
        "    except SyntaxError as exc:\n"
        "        errors.append(f'{path}:{exc.lineno}: {exc.msg}')\n"
        "print(len(files)); sys.exit('\\n'.join(errors) if errors else 0)"
    )
    completed = _run_python310(code)
    assert completed.returncode == 0, completed.stderr
    assert int(completed.stdout.strip()) > 50
