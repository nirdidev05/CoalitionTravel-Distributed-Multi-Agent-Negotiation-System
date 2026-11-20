"""3H, I1: the new standard-library-only modules import under a real Python 3.10.

Kept apart from tests/test_python310_compatibility.py so that I1 changes no existing test
other than the allow-list entry of the market (acceptance criterion of plan step I1).
The grammar of every new file is already checked by that module's whole-tree parse.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON310 = shutil.which("python3.10")
I1_STDLIB_ONLY_MODULES = (
    "coalition_travel.infrastructure.negotiation.journaling_oracle",
    "coalition_travel.infrastructure.negotiation.market",
)


@pytest.mark.skipif(PYTHON310 is None, reason="python3.10 is not installed")
def test_i1_standard_library_only_modules_import_under_python_3_10():
    code = (
        "import importlib, sys; "
        f"sys.path.insert(0, {str(REPOSITORY_ROOT / 'Multi-Agent')!r}); "
        f"[importlib.import_module(name) for name in {I1_STDLIB_ONLY_MODULES!r}]"
    )
    completed = subprocess.run(
        [PYTHON310, "-I", "-B", "-c", code],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
