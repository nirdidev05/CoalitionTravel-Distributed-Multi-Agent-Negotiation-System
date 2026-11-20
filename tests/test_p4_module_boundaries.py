"""P4 dependency rules (specification §8.1) and the D8 guard, checked on the source AST."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "Multi-Agent" / "coalition_travel"
HISTORICAL_AGENTS = {
    "Agent",
    "BuyerAgent",
    "SellerAgent",
    "BrokerAgent",
    "Leader",
    "Negotiation",
    "Message",
    "Entry",
    "CoalitionStructureSearch",
}
FORBIDDEN_EVERYWHERE_IN_CORE = {"ollama", "sqlite3", "pydantic", "scipy"}
P4_APPLICATION = (
    "application/coalition_candidates.py",
    "application/coalition_feasibility.py",
    "application/negotiation_cache.py",
    "application/coalition_costs.py",
    "application/partition_solver.py",
    "application/coalition_formation.py",
    "application/formation_baselines.py",
    "application/formation_evaluation.py",
)


def imported_modules(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_game_model_depends_on_the_standard_library_only():
    modules = imported_modules(PACKAGE / "domain/coalition_game.py")
    assert not {name for name in modules if name.startswith("coalition_travel")}
    assert not modules & (HISTORICAL_AGENTS | FORBIDDEN_EVERYWHERE_IN_CORE | {"numpy"})


def test_p4_application_imports_no_infrastructure_agent_llm_or_storage():
    for relative in P4_APPLICATION:
        modules = imported_modules(PACKAGE / relative)
        roots = {name.split(".")[0] for name in modules}
        assert not roots & (HISTORICAL_AGENTS | FORBIDDEN_EVERYWHERE_IN_CORE), relative
        assert not any(name.startswith("coalition_travel.infrastructure") for name in modules), (
            relative
        )


def test_no_domain_or_application_module_imports_infrastructure():
    """D8: the scenario generator (and every infrastructure module) stays out of the core."""
    for layer in ("domain", "application"):
        for path in sorted((PACKAGE / layer).glob("*.py")):
            modules = imported_modules(path)
            assert not any(
                name.startswith("coalition_travel.infrastructure") for name in modules
            ), path


def test_historical_agents_and_scipy_are_confined_to_their_adapters():
    p4_infrastructure = (
        "infrastructure/baselines/legacy_broker.py",
        "infrastructure/optimization/exact_milp.py",
        "infrastructure/evaluation/formation_scenarios.py",
        "infrastructure/evaluation/formation_report.py",
    )
    for relative in p4_infrastructure:
        roots = {name.split(".")[0] for name in imported_modules(PACKAGE / relative)}
        if relative.endswith("legacy_broker.py"):
            assert {"BrokerAgent", "BuyerAgent", "Message"} <= roots
        else:
            assert not roots & HISTORICAL_AGENTS, relative
        if not relative.endswith("exact_milp.py"):
            assert "scipy" not in roots, relative
