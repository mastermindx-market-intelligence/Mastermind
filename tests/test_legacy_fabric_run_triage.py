"""Read-only batch triage for existing account-local Fabric run IDs."""
from __future__ import annotations
import json
from pathlib import Path
import pytest


def _module():
    from control_plane import legacy_fabric_run_triage as m
    return m


def _status(run_id, state="ACTIVE_OR_WAITING", **overrides):
    return {"schema": "mastermind.fabric_task_status.v1", "run_id": run_id,
            "state": state, "rc": None, "signal": None,
            "result_available": False, "accepted": None, "acceptance_state": "UNVERIFIED",
            **overrides}


@pytest.mark.parametrize("state,expected", [
    ("ACTIVE_OR_WAITING", "OBSERVE_INCUMBENT_CONTROLLER"),
    ("SETTLING", "AWAIT_CANONICAL_SETTLEMENT"),
    ("EFFECT_UNKNOWN", "RECONCILE_ORIGINAL_EFFECT"),
    ("STATUS_UNREADABLE", "RECONCILE_ORIGINAL_STATUS"),
    ("NOT_FOUND", "VERIFY_ORIGINAL_RUN_ID"),
    ("RESULT_UNAVAILABLE", "RECONCILE_RESULT_AVAILABILITY"),
    ("TERMINAL_FAILURE", "CLASSIFY_ORIGINAL_TERMINAL_FAILURE"),
])
def test_never_infer_pool_exhaustion_from_opaque_native_stop(state, expected):
    result = _module().project_legacy_fabric_run(_status("run-a", state))
    assert result["next_action"] == expected
    assert result["retry_authorized"] is False
    assert result["model_switch_authorized"] is False
    assert result["queue_confirmed"] is False
    assert result["authority_effect"] == "NONE"
    assert result["run_id"] == "run-a"


def test_completed_unaccepted_child_requires_parent_review_not_fabric_retry():
    value = _status("run-a", "TERMINAL", rc=0, signal="ok", result_available=True)
    result = _module().project_legacy_fabric_run(value)
    assert result["next_action"] == "REVIEW_DELIVERED_RESULT"
    assert result["accepted"] is False
    assert result["model_switch_authorized"] is False


def test_accepted_terminal_return_is_not_a_running_worker():
    value = _status("run-a", "TERMINAL", rc=0, signal="ok", result_available=True,
                    accepted=True, acceptance_state="ACCEPTED")
    result = _module().project_legacy_fabric_run(value)
    assert result["next_action"] == "VERIFY_ORIGINAL_PARENT_BEFORE_CONSUMPTION"
    assert result["accepted"] is True
    assert result["lineage_confirmed_for_caller"] is False
    assert result["queue_confirmed"] is False


def test_terminal_success_without_result_is_not_accepted():
    value = _status("run-a", "TERMINAL", rc=0, signal="ok",
                    accepted=True, acceptance_state="ACCEPTED")
    result = _module().project_legacy_fabric_run(value)
    assert result["next_action"] == "RECONCILE_RESULT_AVAILABILITY"
    assert result["accepted"] is False


@pytest.mark.parametrize("value", [
    {"run_id": "run-a", "state": "TERMINAL"},
    _status("run-a", "mystery"),
    _status("run-a", "TERMINAL", rc=0, signal="effect_unknown", result_available=True),
    _status("run-a", "TERMINAL_FAILURE", signal="prelaunch_failure"),
])
def test_unsupported_states_do_not_grant_retry(value):
    result = _module().project_legacy_fabric_run(value)
    assert result["model_switch_authorized"] is False
    assert result["retry_authorized"] is False


def test_batch_thirty_runs_includes_unknown_causes_without_duplicate_execution():
    calls=[]
    def reader(run):
        calls.append(run)
        if run == "r-04":
            return _status(run, "EFFECT_UNKNOWN")
        if run == "r-11":
            return _status(run, "TERMINAL_FAILURE", rc=78, signal="prelaunch_failure")
        if run == "r-20":
            raise TimeoutError("existing status read timed out")
        return _status(run)
    runs=[f"r-{n:02d}" for n in range(30)]
    result=_module().project_legacy_fleet(runs, reader)
    assert len(calls) == 30 and calls == runs
    assert result["run_count"] == 30
    assert result["authority_effect"] == "NONE"
    assert result["operation_performed"] is False
    assert result["count_by_action"]["RECONCILE_ORIGINAL_EFFECT"] == 1
    assert result["count_by_action"]["CLASSIFY_ORIGINAL_TERMINAL_FAILURE"] == 1
    assert result["count_by_action"]["RECONCILE_ORIGINAL_STATUS"] == 1
    assert sum(result["count_by_action"].values()) == 30
    assert all(not item["retry_authorized"] for item in result["runs"])


@pytest.mark.parametrize("ids", [
    [], ["run-a", "run-a"], ["bad space"], ["../bad"], ["run-a", ""],
    ["x"*130], [42], [f"r-{i}" for i in range(101)],
])
def test_bad_run_selection_never_calls_original_status(ids):
    calls=[]
    with pytest.raises((ValueError, TypeError)):
        _module().project_legacy_fleet(ids, lambda x: calls.append(x))
    assert calls==[]


def test_foreign_or_unbound_status_is_never_adopted():
    view = _module().project_legacy_fleet(
        ["run-a","run-b"],
        lambda rid: _status("run-other", "TERMINAL", rc=0,
                            signal="ok", result_available=True, accepted=True, acceptance_state="ACCEPTED"))
    assert all(item["next_action"]=="RECONCILE_ORIGINAL_STATUS" for item in view["runs"])
    assert all(not item["accepted"] for item in view["runs"])


def test_raw_output_and_account_or_session_secrets_do_not_reach_triage():
    value=_status("run-a", "TERMINAL", rc=0, signal="ok", result_available=True,
                  account_label="private@example.com", provider_session_id="secret",
                  controller_observation={"secrets":"hidden"}, result_path="/home/user/private")
    projected=json.dumps(_module().project_legacy_fabric_run(value))
    assert "private@example.com" not in projected
    assert "secret" not in projected and "/home/user/private" not in projected


def test_cli_rejects_script_not_exact_name_or_wrong_digest(tmp_path):
    from scripts.fabric_legacy_triage import safe_fabric_entry
    script=tmp_path/"unrelated.py"
    script.write_text("print('not a status API')\n")
    with pytest.raises(ValueError):
        safe_fabric_entry(script, "0"*64)
    actual=tmp_path/"fabric_task.py"
    actual.write_text("print('not a status API')\n")
    with pytest.raises(ValueError):
        safe_fabric_entry(actual, "0"*64)


def test_cli_only_uses_status_verb_with_exact_run_id(tmp_path):
    from scripts.fabric_legacy_triage import safe_fabric_entry, read_legacy_status
    import hashlib
    script=tmp_path/"fabric_task.py"
    script.write_text('''import json,sys
assert sys.argv[1] == "status" and sys.argv[2]=="run-a" and len(sys.argv)==3
print(json.dumps({"schema":"mastermind.fabric_task_status.v1","run_id":"run-a",
"state":"ACTIVE_OR_WAITING","rc":None,"signal":None,"result_available":False}))
''')
    sha=hashlib.sha256(script.read_bytes()).hexdigest()
    safe_fabric_entry(script,sha)
    result=read_legacy_status(script,"run-a",sha,timeout_seconds=5)
    assert result["run_id"] == "run-a"
    assert result["state"] == "ACTIVE_OR_WAITING"

def test_actual_entrypoint_runs_from_unrelated_working_directory(tmp_path):
    import subprocess, sys, hashlib
    repository = Path(__file__).resolve().parents[1]
    entrypoint = repository / "scripts" / "fabric_legacy_triage.py"
    original=tmp_path/"fabric_task.py"
    original.write_text('''import json,sys
assert sys.argv[1:]==["status","r-1"]
print(json.dumps({"schema":"mastermind.fabric_task_status.v1","run_id":"r-1",
"state":"EFFECT_UNKNOWN","rc":None,"signal":"effect_unknown","result_available":False}))
''')
    digest=hashlib.sha256(original.read_bytes()).hexdigest()
    result=subprocess.run([sys.executable,str(entrypoint),
                           "--fabric-task",str(original),
                           "--expected-sha256",digest,"--run-id","r-1"],
                          cwd=tmp_path,capture_output=True,text=True,timeout=10)
    assert result.returncode==0, result.stderr
    status=json.loads(result.stdout)
    assert status["count_by_action"]=={"RECONCILE_ORIGINAL_EFFECT":1}
    assert status["operation_performed"] is False

def test_native_timeout_exception_is_isolated_to_original_run():
    import subprocess
    calls=[]
    def reader(rid):
        calls.append(rid)
        if rid=="r-1":
            raise subprocess.TimeoutExpired(["fabric_task.py","status",rid], 1)
        return _status(rid)
    result=_module().project_legacy_fleet(["r-1","r-2"],reader)
    assert calls==["r-1","r-2"]
    assert result["count_by_action"] == {
        "OBSERVE_INCUMBENT_CONTROLLER":1,"RECONCILE_ORIGINAL_STATUS":1}


def test_batch_deadline_does_not_hang_all_thirty_workers():
    from scripts.fabric_legacy_triage import bounded_reader
    now=[0.0]
    seen=[]
    def clock():
        return now[0]
    def read(path,run,digest,*,timeout_seconds):
        seen.append((run,timeout_seconds))
        now[0]+=10
        return _status(run)
    reader=bounded_reader(Path("/any/fabric_task.py"),"a"*64,
        per_run_seconds=5,total_seconds=18,clock=clock,read=read)
    result=_module().project_legacy_fleet([f"r-{i}" for i in range(30)],reader)
    assert seen == [("r-0",5),("r-1",5)]
    assert result["run_count"]==30
    assert result["count_by_action"]=={
        "OBSERVE_INCUMBENT_CONTROLLER":2,"RECONCILE_ORIGINAL_STATUS":28}


def test_accepted_native_run_cannot_be_assigned_to_unknown_original_parent():
    value = _status("run-a", "TERMINAL", rc=0, signal="ok",
                    result_available=True, accepted=True, acceptance_state="ACCEPTED",
                    root_id="root-a", parent_run_id="orchestrator-a")
    result = _module().project_legacy_fabric_run(value)
    assert result["next_action"] == "VERIFY_ORIGINAL_PARENT_BEFORE_CONSUMPTION"
    assert result["accepted"] is True
    assert result["return_consumed_by_parent"] is False
    assert result["lineage_confirmed_for_caller"] is False


@pytest.mark.parametrize("actual_root,actual_parent", [
    ("other-root", "orchestrator-a"), (None, "orchestrator-a"),
    ("root-a", "other-parent"), ("root-a", None)
])
def test_foreign_or_unproven_native_lineage_cannot_be_consumed(actual_root, actual_parent):
    value = _status("run-a", "TERMINAL", rc=0, signal="ok",
                    result_available=True, accepted=True, acceptance_state="ACCEPTED",
                    root_id=actual_root, parent_run_id=actual_parent)
    projection = _module().project_legacy_fleet(
        ["run-a"], lambda _run: value,
        expected_root_id="root-a", expected_parent_run_id="orchestrator-a")
    record = projection["runs"][0]
    assert record["next_action"] == "RECONCILE_ORIGINAL_IDENTITY"
    assert record["accepted"] is False
    assert record["lineage_confirmed_for_caller"] is False
    assert record["model_switch_authorized"] is False


def test_exact_retained_root_parent_identity_can_be_returned_without_relaunch():
    value = _status("run-a", "TERMINAL", rc=0, signal="ok",
                    result_available=True, accepted=True, acceptance_state="ACCEPTED",
                    root_id="root-a", parent_run_id="orchestrator-a")
    projection = _module().project_legacy_fleet(
        ["run-a"], lambda _run: value,
        expected_root_id="root-a", expected_parent_run_id="orchestrator-a")
    record = projection["runs"][0]
    assert record["next_action"] == "CONSUME_ACCEPTED_RETURN"
    assert record["accepted"] is True
    assert record["lineage_confirmed_for_caller"] is True
    assert record["return_consumed_by_parent"] is False
    assert record["retry_authorized"] is False
    assert "root-a" not in json.dumps(record)
    assert "orchestrator-a" not in json.dumps(record)


@pytest.mark.parametrize("bad", ["", "../other", "with whitespace", [], True, 42, "a"*130])
def test_invalid_expected_root_is_rejected_before_any_native_reader(bad):
    calls = []
    with pytest.raises((ValueError, TypeError)):
        _module().project_legacy_fleet(["run-a"], lambda run: calls.append(run),
                                        expected_root_id=bad)
    assert calls == []


def test_active_worker_without_native_acceptance_cannot_claim_lineage():
    value = _status("run-a", "ACTIVE_OR_WAITING")
    result = _module().project_legacy_fleet(
        ["run-a"], lambda _run: value,
        expected_root_id="root-a", expected_parent_run_id="orchestrator-a")["runs"][0]
    assert result["next_action"] == "OBSERVE_INCUMBENT_CONTROLLER"
    assert result["lineage_confirmed_for_caller"] is False
    assert result["queue_confirmed"] is False


@pytest.mark.parametrize("missing_or_foreign", [None, "other-root"])
def test_scoped_unaccepted_terminal_artifact_cannot_be_reviewed_under_wrong_root(missing_or_foreign):
    value = _status("run-a", "TERMINAL", rc=0, signal="ok", result_available=True,
                    accepted=False, acceptance_state="NOT_ACCEPTED", root_id=missing_or_foreign,
                    parent_run_id="parent-a")
    item = _module().project_legacy_fleet(
        ["run-a"], lambda _run: value, expected_root_id="root-a",
        expected_parent_run_id="parent-a")["runs"][0]
    assert item["next_action"] == "RECONCILE_ORIGINAL_IDENTITY"
    assert item["accepted"] is False


def test_original_root_match_without_parent_match_never_recommends_consumption():
    value = _status("run-a", "TERMINAL", rc=0, signal="ok", result_available=True,
                    accepted=True, acceptance_state="ACCEPTED", root_id="root-a",
                    parent_run_id="unrelated-parent")
    item = _module().project_legacy_fleet(["run-a"], lambda _run: value,
        expected_root_id="root-a", expected_parent_run_id="parent-a")["runs"][0]
    assert item["next_action"] == "RECONCILE_ORIGINAL_IDENTITY"


def test_partial_scoped_root_without_parent_only_requests_original_parent_verification():
    value = _status("run-a", "TERMINAL", rc=0, signal="ok", result_available=True,
                    accepted=True, acceptance_state="ACCEPTED", root_id="root-a",
                    parent_run_id="parent-a")
    item = _module().project_legacy_fleet(["run-a"], lambda _run: value,
        expected_root_id="root-a")["runs"][0]
    assert item["next_action"] == "VERIFY_ORIGINAL_PARENT_BEFORE_CONSUMPTION"
    assert item["lineage_confirmed_for_caller"] is False


def test_incumbent_stale_controller_poll_is_not_proof_worker_died_or_quota_exhausted():
    native = _status("run-a", "ACTIVE_OR_WAITING",
        controller_observation={
            "source": "local_retained_controller_log",
            "state": "STALE_NO_TERMINAL_EVIDENCE",
            "worker_state": "UNKNOWN",
            "retry_authorized": False,
            "silence_lower_bound_seconds": 1480,
            "last_poll_at": "2026-10-12T19:00Z",
            "log_excerpt": "private content",
        })
    item = _module().project_legacy_fabric_run(native)
    assert item["next_action"] == "RECONCILE_INCUMBENT_CONTROLLER"
    assert item["controller_observation_state"] == "STALE_NO_TERMINAL_EVIDENCE"
    assert item["silence_lower_bound_seconds"] == 1480
    assert item["retry_authorized"] is False
    assert item["model_switch_authorized"] is False
    assert item["provider_quota_known"] is False
    assert item["queue_confirmed"] is False
    assert "private content" not in json.dumps(item)
    assert "2026-10-12" not in json.dumps(item)


def test_recent_controller_poll_does_not_infer_provider_liveness_or_all_slots_busy():
    native = _status("run-a", "ACTIVE_OR_WAITING",
        controller_observation={
            "source": "local_retained_controller_log",
            "state": "LOCAL_POLL_EVIDENCE_ONLY",
            "worker_state": "UNKNOWN",
            "retry_authorized": False,
            "silence_lower_bound_seconds": 0})
    item = _module().project_legacy_fabric_run(native)
    assert item["next_action"] == "OBSERVE_INCUMBENT_CONTROLLER"
    assert item["controller_observation_state"] == "LOCAL_POLL_EVIDENCE_ONLY"
    assert item["provider_quota_known"] is False


@pytest.mark.parametrize("observation", [
    {"source":"malicious","state":"STALE_NO_TERMINAL_EVIDENCE","worker_state":"UNKNOWN","retry_authorized":False,"silence_lower_bound_seconds":500},
    {"source":"local_retained_controller_log","state":"STALE_NO_TERMINAL_EVIDENCE","worker_state":"DEAD","retry_authorized":False,"silence_lower_bound_seconds":500},
    {"source":"local_retained_controller_log","state":"STALE_NO_TERMINAL_EVIDENCE","worker_state":"UNKNOWN","retry_authorized":True,"silence_lower_bound_seconds":500},
    {"source":"local_retained_controller_log","state":"STALE_NO_TERMINAL_EVIDENCE","worker_state":"UNKNOWN","retry_authorized":False,"silence_lower_bound_seconds":True},
    {"source":"local_retained_controller_log","state":"STALE_NO_TERMINAL_EVIDENCE","worker_state":"UNKNOWN","retry_authorized":False,"silence_lower_bound_seconds":-1},
    {"state":"STALE_NO_TERMINAL_EVIDENCE"},
    "STALLED",
])
def test_unverified_staleness_evidence_cannot_promote_a_dead_worker_claim(observation):
    native=_status("run-a", "ACTIVE_OR_WAITING",controller_observation=observation)
    item=_module().project_legacy_fabric_run(native)
    assert item["next_action"] == "OBSERVE_INCUMBENT_CONTROLLER"
    assert item["controller_observation_state"] is None
    assert item["retry_authorized"] is False


def test_native_result_ownership_and_staleness_are_not_same_plane():
    native=_status("run-a", "EFFECT_UNKNOWN",controller_observation={
        "source":"local_retained_controller_log","state":"STALE_NO_TERMINAL_EVIDENCE",
        "worker_state":"UNKNOWN","retry_authorized":False,
        "silence_lower_bound_seconds":2000})
    item=_module().project_legacy_fabric_run(native)
    assert item["next_action"] == "RECONCILE_ORIGINAL_EFFECT"
    assert item["controller_observation_state"] is None
