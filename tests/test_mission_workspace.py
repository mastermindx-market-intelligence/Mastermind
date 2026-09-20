"""Contract tests for the pure held mission-workspace reducer."""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from control_plane.mission_workspace import SCHEMA, compose_mission_workspace


def _inputs(*, candidates=("JOB-1",), state="STARTED", historical=False, status="RUNNING", unjoined=0):
    return dict(control_room={"schema": "mastermind.chairman_control_room.v1", "generated_at": "2026-09-20T00:00:00Z", "work": [{"work_ref": "WS:ONE", "responsibility_ref": "responsibility:one", "agent_os": {"title": "One", "state": "active", "next_action": "Read"}}], "autonomy": {"cards": [{"responsibility_ref": "responsibility:one", "root_job_candidates": list(candidates), "runtime_root_state": "RESOLVED" if len(candidates) == 1 else "CONFLICT", "accountable_seat": "ceo", "dispatch": {"dispatch_state": state, "historical": historical, "actionable": state == "RETURNED" and not historical}}]}}, fabric_view={"schema": "mastermind.fabric_job_view.v1", "generated_at": "2026-09-20T00:00:00Z", "armed": {"source": "absent"}, "root": {"job_id": "JOB-1", "status": status, "depth": 0, "orchestration_role": "plan", "plan_step_id": None, "result": {"state": "IN_PROGRESS"}, "review": {"required": False, "reviews_job_id": None, "verdict": "NOT_YET"}}, "children": [], "unjoined_job_count": unjoined, "missingness": [], "degraded": [], "capability": {"state": "PARTIAL"}}, work_ref="WS:ONE", root_job_id="JOB-1", source_validity={"state": "CURRENT"}, cache_currentness={"state": "CURRENT"}, source_generation={})


def test_actual_owner_shape_is_reduced_without_authority_or_mutation():
    args = _inputs(); before = copy.deepcopy(args)
    doc = compose_mission_workspace(**args)
    assert args == before and doc["schema"] == SCHEMA
    assert doc["mission"]["root_job_id"] == "JOB-1"
    assert doc["posture"] == {"value": "RUNNING", "rule": "G1", "evidence": []}
    assert doc["acceptance"]["state"] == "NOT_PROJECTED"
    assert doc["execution"]["state"] == "IN_PROGRESS"


def test_ambiguous_roots_are_not_selected_and_incomplete_children_have_unknown_totals():
    args = _inputs(candidates=("JOB-1", "JOB-2"), unjoined=3)
    doc = compose_mission_workspace(**args)
    assert doc["mission"]["root_job_id"] is None
    assert doc["mission"]["runtime_root_state"] == "CONFLICT"
    assert doc["children"]["state"] == "INCOMPLETE"
    assert doc["children"]["total_count"] is None and doc["children"]["overflow_count"] is None
    assert doc["posture"]["value"] == "RECONCILIATION_REQUIRED"


def test_stale_start_never_announces_running_and_unknown_arm_is_not_false():
    args = _inputs(historical=True)
    doc = compose_mission_workspace(**args)
    assert doc["posture"]["value"] == "HISTORICAL_OBSERVATION"
    assert doc["mission"]["armed"]["ceo_submit_armed"] is None
    assert doc["mission"]["submission_availability"] == "UNKNOWN"


def test_late_or_unsafe_result_fields_do_not_escape_the_allowlist():
    args = _inputs(); args["fabric_view"]["root"]["result"].update({"summary": "/private/secret", "artifacts": ["https://private.example"], "next_actions": ["token"]})
    raw = json.dumps(compose_mission_workspace(**args), sort_keys=True)
    assert "/private/secret" not in raw and "private.example" not in raw


def test_same_inputs_have_byte_identical_output():
    args = _inputs()
    assert json.dumps(compose_mission_workspace(**args), sort_keys=True) == json.dumps(compose_mission_workspace(**copy.deepcopy(args)), sort_keys=True)


def test_module_has_no_acquisition_or_authority_imports():
    source = Path("control_plane/mission_workspace.py").read_text()
    tree = ast.parse(source)
    names = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    forbidden = {"os", "subprocess", "socket", "random", "time", "requests", "httpx", "executive_runtime", "executive_worker_broker"}
    assert not (names | modules) & forbidden
