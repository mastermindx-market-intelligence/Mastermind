from __future__ import annotations

import ast
import io
import json
from pathlib import Path

import pytest
import yaml

from control_plane.chairman_cognition import (
    ENVELOPE_SCHEMA,
    INPUT_SCHEMA,
    evaluate_document,
)
from scripts import chairman_cognition as cli

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


def _valid_document() -> dict:
    return {
        "schema": INPUT_SCHEMA,
        "as_of": "2026-08-30T16:00:00Z",
        "source_receipts": [
            {
                "source_ref": "SRC-CHAIRMAN",
                "owner": "CHAIRMAN_DIRECTIVE",
                "revision": "conversation:2026-08-30",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T16:00:00Z",
            }
        ],
        "strategic_constraints": {
            "autonomous_production_deploy": "prohibited",
            "autonomous_live_capital_execution": "prohibited",
            "duplicate_control_planes": "prohibited",
            "unbounded_autonomous_strategic_modification": "prohibited",
        },
        "delegation_envelope": None,
        "options": [
            {
                "option_id": "OPT-DUPLICATE",
                "title": "Hold while validating input integrity",
                "action": "PORTFOLIO_HOLD",
                "reversibility": "READ_ONLY",
                "source_refs": ["SRC-CHAIRMAN"],
                "scope_refs": [],
                "effect_state": "NONE",
                "operation_key": None,
                "carrier_state": "NOT_APPLICABLE",
                "carrier_ref": None,
                "expected_head_sha": None,
                "repositories": [],
                "paths": [],
                "budget_units": 0,
                "active_children_after": 0,
                "creates_duplicate_control_plane": False,
                "stop_condition": None,
                "rollback_plan": None,
                "falsifier": None,
                "benefits": {
                    "strategic_leverage": 50,
                    "dependency_unlock": 50,
                    "learning_value": 50,
                    "chairman_load_reduction": 50,
                    "user_or_machine_value": 50,
                },
                "costs": {
                    "time_to_evidence": 20,
                    "execution_cost": 20,
                    "coordination_risk": 20,
                    "irreversibility_risk": 20,
                    "scarce_cognition_cost": 20,
                },
            }
        ],
    }


def _duplicate_payload(secret: str, *, nested: bool) -> str:
    valid = json.dumps(_valid_document(), separators=(",", ":"))
    if nested:
        target = '"option_id":"OPT-DUPLICATE"'
        replacement = f'"option_id":"{secret}","option_id":"OPT-DUPLICATE"'
        assert target in valid
        return valid.replace(target, replacement, 1)
    return f'{{"schema":"{secret}",' + valid[1:]


def test_source_law_freezes_one_office_two_modes_and_no_duplicate_owner():
    law = _text(_LAW)
    for marker in (
        "SOL:META-CEO:MASTERMIND",
        "CHAIRMAN_COGNITION",
        "CEO_EXECUTION",
        "does **not** create a second `META_CHAIRMAN`",
        "execution_authority_granted=false",
        "SUPERVISED_LIVE_CANARY",
        "PORTFOLIO_HOLD",
        "PROGRAM_START",
        "PROGRAM_RETIRE",
        "EFFECT_UNKNOWN_RECONCILE_FIRST",
        "EFFECT_ALREADY_APPLIED",
        "NEW_CHILD_CARRIER_REQUIRED",
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
        "canonical affected-scope references",
        "allowed exact-carrier prefixes",
        "known-applied effect",
        "explicit `NEW_CHILD` carrier state",
        "No `chairman_brain.db`",
    ):
        assert marker in spec


def test_program_has_real_vertical_and_completion_not_docs():
    plan = _text(_PLAN)
    for marker in (
        "control_plane/chairman_cognition.py",
        "scripts/chairman_cognition.py",
        "tests/test_chairman_cognition.py",
        "tests/test_chairman_cognition_hardening.py",
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
    assert (
        state["constraints"]["unbounded_autonomous_strategic_modification"]
        == "prohibited"
    )
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


@pytest.mark.parametrize(
    "use_stdin,nested",
    [(False, False), (True, True)],
)
def test_cli_rejects_duplicate_keys_that_would_otherwise_form_valid_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_stdin: bool,
    nested: bool,
) -> None:
    secret = "duplicate-secret-must-not-leak"
    payload = _duplicate_payload(secret, nested=nested)

    permissive_document = json.loads(payload)
    assert evaluate_document(permissive_document)["recommended_option_id"] == "OPT-DUPLICATE"

    if use_stdin:
        monkeypatch.setattr(cli.sys, "stdin", io.StringIO(payload))
        path = "-"
    else:
        input_path = tmp_path / "duplicate-valid.json"
        input_path.write_text(payload, encoding="utf-8")
        path = str(input_path)

    assert cli.main([path]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error == {
        "error": "INVALID_INPUT",
        "schema": "mastermind.chairman_cognition_error.v1",
    }
    assert secret not in captured.err
