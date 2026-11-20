"""Tests for the extracted coalition optimization module boundaries."""

import subprocess
import sys
from pathlib import Path

import CoalitionStructureSearch as legacy_search
from coalition_travel.application import optimization
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.domain import partition_optimization
from coalition_travel.domain.request import TravelRequestDraft as LegacyTravelRequestDraft


def test_compatibility_facade_keeps_historical_star_exports():
    assert set(legacy_search.__all__) == {
        "Bounds",
        "LinearConstraint",
        "brute_force_search",
        "combinations",
        "dp_search",
        "format_structure",
        "idp_search",
        "ip_search",
        "milp",
        "np",
        "print_result",
        "print_shapley_transfers",
        "shapley_value",
        "validate_partition",
    }


def test_application_service_imports_optimization_from_domain():
    assert optimization.idp_search is partition_optimization.idp_search
    assert optimization.brute_force_search is partition_optimization.brute_force_search
    assert optimization.idp_search.__module__ == "coalition_travel.domain.partition_optimization"


def test_request_contract_lives_in_application_with_legacy_import_alias():
    assert LegacyTravelRequestDraft is TravelRequestDraft
    assert TravelRequestDraft.__module__ == "coalition_travel.application.request_contracts"


def test_domain_partition_algorithms_import_without_scipy():
    project_root = Path(__file__).resolve().parents[1]
    command = (
        "import sys; sys.path.insert(0, 'Multi-Agent'); "
        "sys.modules['scipy'] = None; sys.modules['scipy.optimize'] = None; "
        "from coalition_travel.domain.partition_optimization import dp_search, idp_search; "
        "assert dp_search(['A'], lambda coalition: 1)[0] == 1; "
        "assert idp_search(['A'], lambda coalition: 1)[0] == 1"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout == ""
