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
    assert result["next_action"] == "CONSUME_ACCEPTED_RETURN"
    assert result["accepted"] is True
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
