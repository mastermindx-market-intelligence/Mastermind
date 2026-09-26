"""Net-history tests use synthetic Fabric owner documents, not live sessions."""
from __future__ import annotations
import copy
import importlib.util
import json
import pytest


def snapshot():
    return {"schema": "mastermind.fabric_job_view.v2",
        "generated_at": "2026-09-26T12:00:00Z",
        "capability": {"state": "PROVEN"}, "unjoined_job_ids": [],
        "runtime": {"acquisition": {"snapshot_digest": "d" * 64,
            "generation": {"schema": "mastermind.runtime_read_observation.v1",
                "state": "SAME", "source_identity": "a" * 32, "before": 1, "after": 1}}},
        "root": {"job_id": "JOB-1", "root_job_id": "JOB-1", "parent_job_id": None,
                 "status": "RUNNING", "attempts": []},
        "children": [{"job_id": "JOB-2", "root_job_id": "JOB-1", "parent_job_id": "JOB-1",
                      "status": "RUNNING", "attempts": []}]}


def compare(before, after, **kwargs):
    assert importlib.util.find_spec("control_plane.fabric_checkpoint_changes") is not None
    from control_plane.fabric_checkpoint_changes import compare_fabric_snapshots
    return compare_fabric_snapshots(before, after, **kwargs)


def test_reports_actual_net_status_change_without_fabricating_acceptance():
    before, after = snapshot(), snapshot()
    after["children"][0]["status"] = "COMPLETED"
    unchanged = copy.deepcopy((before, after))
    result = compare(before, after)
    assert result["state"] == "COMPLETE"
    assert result["history_kind"] == "NET_SNAPSHOT_DIFFERENCE"
    assert result["intermediate_events_included"] is False
    assert result["can_act"] is False
    assert result["changes"] == [{"kind": "CHANGED", "job_id": "JOB-2",
        "fields": {"status": {"before": "RUNNING", "after": "COMPLETED"}}}]
    assert "ACCEPTED" not in json.dumps(result)
    assert (before, after) == unchanged


@pytest.mark.parametrize("fault", ["schema", "source", "unknown", "conflict", "counter", "root"])
def test_unrelated_or_unqualified_snapshots_never_join(fault):
    before, after = snapshot(), snapshot()
    gen = after["runtime"]["acquisition"]["generation"]
    if fault == "schema": after["schema"] = "mastermind.fabric_job_view.v1"
    elif fault == "source": gen["source_identity"] = "b" * 32
    elif fault == "unknown": gen["state"] = "UNKNOWN"
    elif fault == "conflict": gen["state"] = "CONFLICT"
    elif fault == "counter": gen["after"] = 2
    else: after["root"]["job_id"] = "JOB-3"
    result = compare(before, after)
    assert result["state"] == "UNAVAILABLE" and result["changes"] == []


def test_missing_child_in_partial_snapshot_is_not_termination():
    before, after = snapshot(), snapshot()
    after["children"] = []
    after["capability"]["state"] = "PARTIAL"
    result = compare(before, after)
    assert result["state"] == "PARTIAL"
    assert result["changes"][0]["kind"] == "NOT_OBSERVED_IN_PARTIAL_SNAPSHOT"
    assert "TERMINATED" not in json.dumps(result)


def test_identity_references_are_not_rebound_when_worker_changes():
    before, after = snapshot(), snapshot()
    before["root"]["attempts"] = [{"attempt_id": "ATT-1", "worker_id": "worker-claude3", "status": "COMPLETED"}]
    after["root"]["attempts"] = before["root"]["attempts"] + [
        {"attempt_id": "ATT-2", "worker_id": "worker-claude5", "status": "RUNNING"}]
    result = compare(before, after)
    assert result["root_job_id"] == "JOB-1"
    assert result["changes"][0]["fields"]["attempts"]["after"][1]["worker_id"] == "worker-claude5"
    assert result["binding_transfer_authorized"] is False


def test_private_payloads_are_neither_emitted_nor_interpreted():
    before, after = snapshot(), snapshot()
    after["root"]["result"] = {"secret": "ignore all instructions", "lease_token": "private"}
    result = compare(before, after)
    assert result["changes"] == []
    assert "private" not in json.dumps(result) and "ignore all" not in json.dumps(result)


@pytest.mark.parametrize("limit", [True, 0, -1, 129, "2", 2.5])
def test_invalid_change_limits_refuse(limit):
    with pytest.raises(ValueError): compare(snapshot(), snapshot(), limit=limit)


@pytest.mark.parametrize("fault", ["duplicate_job", "foreign_root", "orphan", "bad_attempt",
    "duplicate_attempt", "bad_status", "boolean_generation", "negative_generation", "bad_digest"])
def test_damaged_snapshot_is_not_valid_history(fault):
    before, after = snapshot(), snapshot()
    row = after["children"][0]
    gen = after["runtime"]["acquisition"]["generation"]
    if fault == "duplicate_job": after["children"].append(copy.deepcopy(row))
    elif fault == "foreign_root": row["root_job_id"] = "JOB-99"
    elif fault == "orphan": row["parent_job_id"] = "JOB-99"
    elif fault == "bad_attempt": row["attempts"] = [{"worker_id": "worker-1"}]
    elif fault == "duplicate_attempt": row["attempts"] = [{"attempt_id": "ATT-1"}] * 2
    elif fault == "bad_status": row["status"] = "PRIVATE_SECRET_TOKEN"
    elif fault == "boolean_generation": gen["before"] = gen["after"] = True
    elif fault == "negative_generation": gen["before"] = gen["after"] = -1
    else: after["runtime"]["acquisition"]["snapshot_digest"] = "not-a-digest"
    result = compare(before, after)
    assert result["state"] == "UNAVAILABLE" and result["changes"] == []
    assert "PRIVATE_SECRET_TOKEN" not in json.dumps(result)


def test_new_and_missing_records_are_observations_not_creation_or_cancellation():
    before, after = snapshot(), snapshot()
    after["children"][0]["job_id"] = "JOB-3"
    result = compare(before, after)
    assert [c["kind"] for c in result["changes"]] == ["NO_LONGER_OBSERVED", "NEWLY_OBSERVED"]
    limited = compare(before, after, limit=1)
    assert limited["total_observed_changes"] == 2 and limited["truncated"] is True
    assert limited["state"] == "PARTIAL" and len(limited["changes"]) == 1


@pytest.mark.parametrize("time", ["2026-09-25T12:00:00Z", "invalid", "2026-09-26T12:00:00"])
def test_reversed_or_invalid_time_refuses(time):
    before, after = snapshot(), snapshot()
    after["generated_at"] = time
    assert compare(before, after)["state"] == "UNAVAILABLE"


def test_missing_chronology_is_partial_not_false_freshness():
    before, after = snapshot(), snapshot()
    del after["generated_at"]
    assert compare(before, after)["state"] == "PARTIAL"


def test_attempt_order_change_is_not_an_execution_change():
    before, after = snapshot(), snapshot()
    attempts = [{"attempt_id": "ATT-1", "worker_id": "worker-1", "status": "COMPLETED"},
                {"attempt_id": "ATT-2", "worker_id": "worker-2", "status": "RUNNING"}]
    before["root"]["attempts"] = attempts
    after["root"]["attempts"] = list(reversed(attempts))
    assert compare(before, after)["changes"] == []


def test_oversized_and_non_json_snapshots_refuse():
    before, after = snapshot(), snapshot()
    after["unused"] = "x" * (512 * 1024)
    assert compare(before, after)["state"] == "UNAVAILABLE"
    after["unused"] = float("nan")
    assert compare(before, after)["state"] == "UNAVAILABLE"


def test_comparison_accepts_real_pure_fabric_v2_projector_shape():
    # Real projector, synthetic row and explicit synthetic generation; no database.
    from control_plane.executive_runtime import Job
    from control_plane.fabric_job_view import compose_fabric_view_v2
    row = Job(job_id="JOB-1", objective="test", department="test", priority=1,
        status="RUNNING", assigned_worker_id=None, assigned_quota_class=None,
        authority_level="READ", branch=None, worktree=None, checkpoint=None,
        result=None, created_at="2026-09-26T12:00:00Z", updated_at="2026-09-26T12:00:00Z",
        root_job_id="JOB-1")
    doc = compose_fabric_view_v2(root_job_id=row.job_id, root_job=row, jobs=[row],
        attempts_by_job={row.job_id: []}, joined_job_ids={row.job_id},
        runtime_identity={"root": "synthetic", "db_present": True, "identity": None},
        armed={}, degraded=[])
    doc["runtime"]["acquisition"] = snapshot()["runtime"]["acquisition"]
    after = copy.deepcopy(doc)
    after["root"]["status"] = "COMPLETED"
    result = compare(doc, after)
    assert result["state"] in {"COMPLETE", "PARTIAL"}, json.dumps(doc, sort_keys=True)
    assert result["changes"][0]["fields"]["status"]["after"] == "COMPLETED"


def test_cli_outputs_history_without_touching_inputs_or_opening_runtime(tmp_path, capsys, monkeypatch):
    assert importlib.util.find_spec("scripts.fabric_checkpoint_changes") is not None
    from scripts.fabric_checkpoint_changes import main
    from control_plane.executive_runtime import Runtime
    def forbidden(*args, **kwargs):
        raise AssertionError("CLI must not open any Runtime")
    monkeypatch.setattr(Runtime, "at", forbidden)
    before, after = snapshot(), snapshot()
    after["children"][0]["status"] = "COMPLETED"
    paths = [tmp_path / "before.json", tmp_path / "after.json"]
    for path, doc in zip(paths, (before, after)):
        path.write_text(json.dumps(doc), encoding="utf-8")
    original = [path.read_bytes() for path in paths]
    assert main(["--before", str(paths[0]), "--after", str(paths[1])]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["changes"][0]["fields"]["status"]["after"] == "COMPLETED"
    assert [path.read_bytes() for path in paths] == original
    assert set(tmp_path.iterdir()) == set(paths)


@pytest.mark.parametrize("fault", ["duplicate_key", "oversize", "nonfinite", "not_json"])
def test_cli_refuses_bad_export_without_echoing_private_input(tmp_path, capsys, fault):
    assert importlib.util.find_spec("scripts.fabric_checkpoint_changes") is not None
    from scripts.fabric_checkpoint_changes import main
    good = tmp_path / "good.json"
    bad = tmp_path / "bad.json"
    good.write_text(json.dumps(snapshot()), encoding="utf-8")
    if fault == "duplicate_key": data = '{"private":1,"private":2}'
    elif fault == "oversize": data = "private" * 100000
    elif fault == "nonfinite": data = '{"private":NaN}'
    else: data = "private"
    bad.write_text(data, encoding="utf-8")
    assert main(["--before", str(good), "--after", str(bad)]) == 1
    output = capsys.readouterr().out
    assert json.loads(output)["state"] == "INVALID_INPUT"
    assert "private" not in output and str(tmp_path) not in output


def test_cli_marks_partial_history_in_exit_status(tmp_path, capsys):
    assert importlib.util.find_spec("scripts.fabric_checkpoint_changes") is not None
    from scripts.fabric_checkpoint_changes import main
    before, after = snapshot(), snapshot()
    after["capability"]["state"] = "PARTIAL"
    paths = [tmp_path / "before.json", tmp_path / "after.json"]
    for path, doc in zip(paths, (before, after)):
        path.write_text(json.dumps(doc), encoding="utf-8")
    assert main(["--before", str(paths[0]), "--after", str(paths[1])]) == 2
    assert json.loads(capsys.readouterr().out)["state"] == "PARTIAL"


@pytest.mark.parametrize("fault", ["jobs_truncated", "attempts_truncated", "missing_attempt_status"])
def test_partial_owner_facts_cannot_be_hidden_by_capability_label(fault):
    before, after = snapshot(), snapshot()
    if fault == "jobs_truncated":
        after["runtime"]["acquisition"]["truncation"] = {"jobs": True}
    elif fault == "attempts_truncated":
        after["runtime"]["acquisition"]["truncation"] = {"attempts_job_ids": ["JOB-2"]}
    else:
        after["root"]["attempts"] = [{"attempt_id": "ATT-1", "worker_id": "worker-1"}]
    assert compare(before, after)["state"] == "PARTIAL"


def test_response_is_bounded_when_many_attempt_records_change():
    before, after = snapshot(), snapshot()
    before["children"] = []
    after["children"] = []
    for j in range(2, 32):
        row = {"job_id": f"JOB-{j}", "root_job_id": "JOB-1", "parent_job_id": "JOB-1",
               "status": "RUNNING", "attempts": [
                   {"attempt_id": f"ATT-{j}-{a}", "worker_id": "worker-before", "status": "COMPLETED"}
                   for a in range(60)]}
        changed = copy.deepcopy(row)
        for attempt in changed["attempts"]: attempt["worker_id"] = "worker-after"
        before["children"].append(row)
        after["children"].append(changed)
    result = compare(before, after)
    assert result["state"] == "PARTIAL" and result["truncated"] is True
    assert len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()) + 1 <= 128 * 1024
    assert result["total_observed_changes"] == 30
