"""Contract tests for the pure held mission-workspace reducer."""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from control_plane.chairman_control_room import compose_control_room
from control_plane.fabric_job_view import compose_fabric_view
from control_plane.mission_workspace import SCHEMA, _posture, compose_mission_workspace


def _inputs(*, candidates=("JOB-1",), state="STARTED", historical=False, status="RUNNING", unjoined=0):
    validity = {"schema": "mastermind.control_room_source_validity.v1", "profile": "b5.darwin-chrome-paired-v1", "publication_seq": 1, "qualification_generation": 1, "cards": [{"responsibility_ref": "WS:ONE", "root_job_id": "JOB-1", "components": {name: {"remaining_ms": 1, "state": "current", "proof_ref": "a" * 64} for name in ("card", "dispatch", "owed_open_age")}}]}
    return dict(control_room={"schema": "mastermind.chairman_control_room.v1", "generated_at": "2026-09-20T00:00:00Z", "work": [{"work_ref": "WS:ONE", "agent_os": {"title": "One", "state": "active", "next_action": "Read"}}], "autonomy": {"responsibilities": [{"responsibility_ref": "WS:ONE", "root_job_id": "JOB-1", "root_job_candidates": list(candidates), "runtime_root_state": "RESOLVED" if len(candidates) == 1 else "CONFLICT", "accountable_seat": "ceo", "dispatch": {"dispatch_state": state, "historical": historical, "actionable": state == "RETURNED" and not historical}}]}}, fabric_view={"schema": "mastermind.fabric_job_view.v1", "generated_at": "2026-09-20T00:00:00Z", "armed": {"source": "absent"}, "root": {"job_id": "JOB-1", "status": status, "depth": 0, "orchestration_role": "plan", "plan_step_id": None, "result": {"state": "IN_PROGRESS"}, "review": {"required": False, "reviews_job_id": None, "verdict": "NOT_YET"}}, "children": [], "unjoined_job_count": unjoined, "missingness": [], "degraded": [], "capability": {"state": "PARTIAL"}}, work_ref="WS:ONE", root_job_id="JOB-1", source_validity=validity, cache_currentness={"state": "fresh", "publication_seq": 1, "qualification_generation": 1}, source_generation={})


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


def test_expired_validity_never_promotes_current_cache_to_running():
    args = _inputs()
    args["source_validity"] = {"schema": "mastermind.control_room_source_validity.v1", "profile": "b5.darwin-chrome-paired-v1", "publication_seq": 1, "qualification_generation": 1, "cards": [
        {"responsibility_ref": "WS:ONE", "root_job_id": "JOB-1", "components": {
            "card": {"remaining_ms": 0, "state": "expired", "proof_ref": "a" * 64}, "owed_open_age": {"remaining_ms": 0, "state": "expired", "proof_ref": "a" * 64},
            "dispatch": {"remaining_ms": 0, "state": "expired", "proof_ref": "a" * 64},
        }}]}
    doc = compose_mission_workspace(**args)
    assert doc["read_state"]["state"] != "CURRENT"
    assert doc["posture"]["value"] != "RUNNING"


def test_absent_or_unjoined_fabric_never_claims_complete_zero_children():
    args = _inputs(); args["fabric_view"] = None
    assert compose_mission_workspace(**args)["children"]["total_count"] is None
    args = _inputs(); args["fabric_view"]["unjoined_job_count"] = None
    doc = compose_mission_workspace(**args)
    assert doc["children"]["state"] == "INCOMPLETE"
    assert doc["children"]["total_count"] is None


def test_child_attempt_is_bounded_and_worker_identity_is_explicitly_missing():
    args = _inputs()
    args["fabric_view"]["children"] = [{"job_id": "CHILD", "root_job_id": "JOB-1", "status": "RUNNING", "latest_attempt": {"attempt_id": "A", "attempt_number": 1, "status": "RUNNING", "error": {"raw": "token"}, "provider_session_id": "secret"}}]
    doc = compose_mission_workspace(**args)
    attempt = doc["children"]["items"][0]["latest_attempt"]
    assert attempt == {"attempt_id": "A", "attempt_number": 1, "status": "RUNNING", "started_at": None, "finished_at": None, "exit_code": None, "has_result": False, "error_present": True}
    assert doc["children"]["items"][0]["worker_id"] is None


def test_bad_schema_cross_root_and_malformed_facts_fail_closed_without_escape():
    args = _inputs()
    args["fabric_view"]["root"]["job_id"] = "OTHER"
    args["fabric_view"]["children"] = [{"job_id": "OTHER-CHILD", "root_job_id": "OTHER", "latest_attempt": {"token": "secret"}}]
    args["fabric_view"]["missingness"] = [{"missingness_class": [], "target_field": {}, "reason": []}]
    args["source_generation"] = {"version": "v1", "token": "secret", "nested": {"url": "https://private.example"}}
    doc = compose_mission_workspace(**args)
    assert doc["mission"]["root_job_id"] is None
    assert doc["children"]["total_count"] is None
    raw = json.dumps(doc, sort_keys=True)
    assert "private.example" not in raw and "secret" not in raw


def test_missing_currentness_is_historical_not_current():
    args = _inputs(); args["cache_currentness"] = None
    doc = compose_mission_workspace(**args)
    assert doc["read_state"]["state"] != "CURRENT"
    assert doc["posture"]["value"] != "RUNNING"


def test_late_or_unsafe_result_fields_do_not_escape_the_allowlist():
    args = _inputs(); args["fabric_view"]["root"]["result"].update({"summary": "/private/secret", "artifacts": ["https://private.example"], "next_actions": ["token"]})
    raw = json.dumps(compose_mission_workspace(**args), sort_keys=True)
    assert "/private/secret" not in raw and "private.example" not in raw


def test_safe_owner_artifacts_survive_and_unsafe_values_are_named_excluded():
    args = _inputs()
    args["fabric_view"]["root"]["result"].update({"artifacts": ["review receipt"], "next_actions": ["https://private.example"]})
    doc = compose_mission_workspace(**args)
    assert doc["execution"]["artifacts"] == ["review receipt"]
    assert doc["execution"]["next_actions"] == []
    assert any(row["target_field"] == "execution.next_actions" for row in doc["missingness"])


def test_fabric_diagnostic_paths_and_fact_reasons_are_withheld():
    args = _inputs()
    args["fabric_view"]["degraded"] = ["control.json missing at /private/secret/control.json", "executive_runtime: failed at /Users/example/private.sqlite3"]
    args["fabric_view"]["missingness"] = [{"missingness_class": "DEGRADED", "target_field": "runtime", "producer_owner": "executive_os", "reason": "token at /private/secret"}]
    raw = json.dumps(compose_mission_workspace(**args), sort_keys=True)
    assert "/private/secret" not in raw and "private.sqlite3" not in raw
    assert "source detail withheld" in raw


def test_producer_composers_supply_the_real_envelope_shapes():
    job = SimpleNamespace(job_id="JOB-1", status="RUNNING", parent_job_id=None, root_job_id="JOB-1", depth=0, orchestration_role="plan", plan_step_id=None, attempt_count=1, attempt_limit=2, current_attempt_id="A-1", result={"artifacts": ["receipt"]}, review_required=False, reviews_job_id=None, repair_round=None, supersedes_job_id=None)
    fabric = compose_fabric_view(root_job_id="JOB-1", root_job=job, jobs=[job], attempts_by_job={}, joined_job_ids={"JOB-1"}, runtime_identity={"db_present": True}, armed={}, degraded=[], generated_at="2026-09-20T00:00:00Z")
    control = compose_control_room(inbox=None, boot_packet=None, active_builds=None, agent_os_state=None, runtime_jobs=None, bindings=None, generated_at="2026-09-20T00:00:00Z")
    assert fabric["schema"] == "mastermind.fabric_job_view.v1"
    assert control["schema"] == "mastermind.chairman_control_room.v1"


def test_real_control_room_relationship_and_fabric_join_reduce_b5_root():
    control = compose_control_room(inbox={"schema": "mastermind.executive_inbox.v1", "generated_at": "2026-09-05T00:00:00Z", "attention": [{"attention_id": "A", "kind": "decision", "target": "ceo", "reason": "fixture", "workstream": "WS:B5"}]}, boot_packet=None, active_builds=None, agent_os_state={"schema": "agent_os_state.v1", "generated_at": "2026-09-03T00:00:01Z", "workstreams": [{"key": "B5", "title": "B5", "owner": "ceo-sol", "status": "active"}]}, runtime_jobs=[{"job_id": "JOB-B5", "root_job_id": "JOB-B5", "workstream": "WS:B5"}], bindings=None, generated_at="2026-09-05T00:00:00Z")
    card = control["autonomy"]["responsibilities"][0]
    card["dispatch"] = {"dispatch_state": "RETURNED", "historical": False, "actionable": True}
    job = SimpleNamespace(job_id="JOB-B5", status="RUNNING", parent_job_id=None, root_job_id="JOB-B5", depth=0, orchestration_role="plan", plan_step_id=None, attempt_count=1, attempt_limit=2, current_attempt_id="A", result={}, review_required=False, reviews_job_id=None, repair_round=None, supersedes_job_id=None)
    fabric = compose_fabric_view(root_job_id="JOB-B5", root_job=job, jobs=[job], attempts_by_job={}, joined_job_ids={"JOB-B5"}, runtime_identity={"db_present": True}, armed={}, degraded=[], generated_at="2026-09-05T00:00:00Z")
    validity = {"schema": "mastermind.control_room_source_validity.v1", "profile": "b5.darwin-chrome-paired-v1", "publication_seq": 7, "qualification_generation": 1, "cards": [{"responsibility_ref": "WS:B5", "root_job_id": "JOB-B5", "components": {x: {"remaining_ms": 1, "state": "current", "proof_ref": "a" * 64} for x in ("card", "dispatch", "owed_open_age")}}]}
    doc = compose_mission_workspace(control_room=control, fabric_view=fabric, work_ref="WS:B5", root_job_id="JOB-B5", source_validity=validity, cache_currentness={"state": "fresh", "publication_seq": 7, "qualification_generation": 1}, source_generation={})
    assert doc["mission"]["root_job_id"] == "JOB-B5"
    assert doc["principal"]["accountable_seat"] == "ceo"
    assert doc["transport"]["dispatch_state"] == "RETURNED"


def test_posture_terminal_domain_and_synthetic_acceptance_product_path():
    for state, expected in (("FAILED", "C1"), ("CANCELLED", "C2"), ("LOST", "C3"), ("RATE_LIMITED", "C4")):
        assert _posture(execution=state, dispatch="UNKNOWN", current=False, conflict=False, blocker=False, acceptance={}, review="NOT_YET")[1] == expected
    assert _posture(execution="ACCEPTED", dispatch="RETURNED", current=True, conflict=False, blocker=False, acceptance={"state": "ACCEPTED", "artifact_revision": "r1", "ruling": "accept"}, review="approve") == ("ACCEPTED_PRODUCT", "F2")


def test_same_inputs_have_byte_identical_output():
    args = _inputs()
    assert json.dumps(compose_mission_workspace(**args), sort_keys=True) == json.dumps(compose_mission_workspace(**copy.deepcopy(args)), sort_keys=True)


def test_module_has_no_acquisition_or_authority_imports():
    source = Path("control_plane/mission_workspace.py").read_text()
    tree = ast.parse(source)
    names = {name.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names}
    modules = {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    forbidden = {"os", "subprocess", "socket", "random", "time", "requests", "httpx", "executive_runtime", "executive_worker_broker"}
    assert not (names | modules) & forbidden
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    attributes = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls & {"open", "exec", "eval", "__import__"}
    assert not attributes & {"read_text", "write_text", "run", "Popen", "request", "post", "connect"}
