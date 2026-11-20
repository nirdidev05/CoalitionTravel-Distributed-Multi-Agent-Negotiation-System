"""I2: the new standard-library-only P5 module imports under a real Python 3.10 (A10).

Kept apart from the existing compatibility tests so that I2 changes no existing test.
The application module needs the project dependencies and is covered by the grammar
check of tests/test_python310_compatibility.py.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON310 = shutil.which("python3.10")


@pytest.mark.skipif(PYTHON310 is None, reason="python3.10 is not installed")
def test_p5_domain_module_imports_and_computes_under_python_3_10():
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(REPOSITORY_ROOT / 'Multi-Agent')!r}); "
        "from coalition_travel.domain.savings_allocation import shapley_exact; "
        "from fractions import Fraction; "
        "phi = dict(shapley_exact(('a', 'b', 'c'), [0, 0, 0, 6, 0, 0, 0, 9]).phi); "
        "assert phi == {'a': 4, 'b': 4, 'c': 1}, phi"
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
