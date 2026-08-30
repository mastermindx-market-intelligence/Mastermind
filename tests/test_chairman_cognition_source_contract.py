from __future__ import annotations

import ast
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_LAW = _ROOT / "docs" / "EXECUTIVE_CHAIRMAN_COGNITION_LAW.md"
_SPEC = (
    _ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-chairman-cognition-loop-design.md"
)
_PLAN = (
    _ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-30-chairman-cognition-loop-accelerated-program.md"
)
_MODULE = _ROOT / "control_plane" / "chairman_cognition.py"
_CLI = _ROOT / "scripts" / "chairman_cognition.py"
_STATE = _ROOT / "config" / "strategic_state.yml"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing Chairman Cognition source: {path}"
    return path.read_text(encoding="utf-8")


def test_source_law_freezes_one_office_two_modes_and_no_duplicate_owner():
    law = _text(_LAW)
    for marker in (
        "SOL:META-CEO:MASTERMIND",
        "CHAIRMAN_COGNITION",
        "CEO_EXECUTION",
        "does **not** create a second `META_CHAIRMAN`",
        "execution_authority_granted=false",
        "SUPERVISED_LIVE_CANARY",
        "EFFECT_UNKNOWN_RECONCILE_FIRST",
        "DUPLICATE_CONTROL_PLANE_REFUSED",
    ):
        assert marker in law


def test_architecture_preserves_canonical_owners_and_accelerated_live_canary():
    spec = _text(_SPEC)
    for marker in (
        "Executive OS",
        "Agent OS",
        "GitHub",
        "Linear",
        "RuntimeBinding",
        "Wake",
        "Capacity",
        "Executive Steward",
        "Executive Attention Frontier",
        "Runtime Observability",
        "Operation Assurance",
        "no mandatory multi-week shadow",
        "one supervised live reversible canary",
        "No `chairman_brain.db`",
    ):
        assert marker in spec


def test_program_has_real_vertical_and_completion_not_docs():
    plan = _text(_PLAN)
    for marker in (
        "control_plane/chairman_cognition.py",
        "scripts/chairman_cognition.py",
        "tests/test_chairman_cognition.py",
        "CCL-A2",
        "CCL-A3",
        "CCL-A4",
        "CCL-A5",
        "CCL-A6",
        "One closed canary",
        "zero routine",
    ):
        assert marker in plan


def test_strategic_state_records_current_chairman_cognition_objective():
    state = yaml.safe_load(_text(_STATE))
    assert str(state["meta"]["as_of"]) == "2026-08-30"
    objectives = {item["id"]: item for item in state["p0"]}
    objective = objectives["CHAIRMAN_COGNITION_AUTONOMY"]
    assert objective["department"] == "executive"
    assert objective["status"] == "active"
    assert "Chairman-engineering" in objective["objective"]
    assert "first_chairman_cognition_supervised_live_cycle" in state["review_triggers"]
    assert state["constraints"]["autonomous_production_deploy"] == "prohibited"
    assert state["constraints"]["autonomous_live_capital_execution"] == "prohibited"
    assert state["constraints"]["duplicate_control_planes"] == "prohibited"
    assert sum(float(v) for v in state["resource_policy"].values()) == 1.0


def test_pure_core_imports_no_runtime_io_network_or_connector_owner():
    tree = ast.parse(_text(_MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    forbidden_fragments = (
        "sqlite",
        "subprocess",
        "socket",
        "urllib",
        "httpx",
        "requests",
        "worker_runtime",
        "executive_runtime",
        "executive_service",
        "capacity",
        "runtime_binding",
        "session_targets",
        "slack",
        "linear",
        "github",
        "agentos",
        "mcp",
    )
    offenders = sorted(
        module
        for module in imported
        if any(fragment in module.lower() for fragment in forbidden_fragments)
    )
    assert not offenders, offenders


def test_cli_is_a_bounded_json_projection_not_an_actuator():
    tree = ast.parse(_text(_CLI))
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "write_text" not in calls
    assert "unlink" not in calls
    assert "replace" not in calls
    assert "system" not in calls
