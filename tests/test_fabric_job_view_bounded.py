"""Bounded Fabric v2 integration against the accepted Runtime acquisition owner."""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from control_plane import fabric_job_view as view
from control_plane.ceo_intent import submit_intent
from control_plane.executive_runtime import Runtime


def _root(tmp_path):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, {
        "schema": "mastermind.ceo_intent.v2", "intent_kind": "executive_coo_cycle",
        "business_impact": "material", "intent_id": "CEO-BOUNDED-001", "actor": "ceo-sol",
        "objective": "Verify bounded Fabric reads", "department": "executive-infrastructure",
        "priority": 5, "workstream": "WS:FABRIC",
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {"requested_authorities": ["READ"], "attempt_limit": 2},
    }, workspace_root=tmp_path)
    return runtime, runtime.jobs.get_job(receipt["job_id"])


def _trap(*args, **kwargs):
    raise AssertionError("population-unbounded registry read reached")


def _use_runtime(monkeypatch, runtime):
    monkeypatch.setattr(view, "_open_runtime", lambda *_args: (runtime, True, []))
    monkeypatch.setattr(runtime.jobs, "list_jobs", _trap)
    monkeypatch.setattr(runtime.attempts, "list_attempts", _trap)
    monkeypatch.setattr(runtime.events, "list_events", _trap)


def test_real_bounded_root_and_unique_creation_event(monkeypatch, tmp_path):
    runtime, job = _root(tmp_path)
    calls = []
    point = runtime.store.get_event_by_command_id
    def observed_point(command, *, connection):
        assert connection is not None
        calls.append(command)
        return point(command, connection=connection)
    monkeypatch.setattr(runtime.store, "get_event_by_command_id", observed_point)
    monkeypatch.setattr(runtime.events, "get_event_by_command_id", _trap)
    _use_runtime(monkeypatch, runtime)
    doc = view.read_fabric_view_v2(tmp_path, job.job_id)
    assert doc["root"]["job_id"] == job.job_id
    assert calls == ["ceo-intent:CEO-BOUNDED-001"]
    assert doc["runtime"]["acquisition"]["provenance"]["state"] == "COMPLETE"
    assert doc["runtime"]["acquisition"]["generation"]["state"] == "UNKNOWN"
    assert doc["root"]["acceptance"]["state"] == "NOT_PROJECTED"
    assert len(doc["runtime"]["acquisition"]["snapshot_digest"]) == 64
    roots = view.list_roots_v2(tmp_path)
    assert roots["total"] == 1 and roots["roots"][0]["job_id"] == job.job_id


@pytest.mark.parametrize("change", [
    {"orchestration_provenance": None},
    {"orchestration_provenance_digest": "0" * 64},
    {"parent_job_id": "foreign"},
    {"root_job_id": "foreign"},
])
def test_bad_or_legacy_cycle_never_reads_event(tmp_path, change):
    runtime, job = _root(tmp_path)
    runtime.events.get_event_by_command_id = _trap
    provenance, warning = view._bounded_provenance(runtime, dataclasses.replace(job, **change))
    assert provenance is None and warning


@pytest.mark.parametrize("field,value", [
    ("job_id", "foreign"), ("aggregate_id", "foreign"),
    ("aggregate_type", "attempt"), ("command_id", "ceo-intent:foreign"),
    ("event_type", "JOB_COMPLETED"),
])
def test_event_identity_mismatch_cannot_join(tmp_path, field, value):
    runtime, job = _root(tmp_path)
    event = runtime.events.get_event_by_command_id("ceo-intent:CEO-BOUNDED-001")
    runtime.events.get_event_by_command_id = lambda _command: dataclasses.replace(event, **{field: value})
    provenance, _ = view._bounded_provenance(runtime, job)
    assert provenance is None


def test_legacy_job_visible_but_provenance_partial(monkeypatch, tmp_path):
    runtime = Runtime.at(tmp_path)
    job = runtime.jobs.create_job("legacy", provenance={"schema": "mastermind.ceo_intent.v1", "workstream": "WS:LEGACY"})
    _use_runtime(monkeypatch, runtime)
    runtime.events.get_event_by_command_id = _trap
    doc = view.read_fabric_view_v2(tmp_path, job.job_id)
    assert doc["root"]["job_id"] == job.job_id
    assert doc["capability"]["state"] == "PARTIAL"
    assert doc["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] == [job.job_id]
    assert any(f["target_field"] == "runtime.acquisition.provenance" for f in doc["missingness"])


def test_missing_owner_api_is_no_unbounded_fallback(monkeypatch, tmp_path):
    old = SimpleNamespace(jobs=SimpleNamespace(list_jobs=_trap), events=SimpleNamespace(list_events=_trap))
    monkeypatch.setattr(view, "_open_runtime", lambda *_args: (old, True, []))
    detail = view.read_fabric_view_v2(tmp_path, "JOB-001")
    assert detail["root"] is None
    assert any("bounded acquisition unavailable" in e for e in detail["degraded"])
    roots = view.list_roots_v2(tmp_path)
    assert roots["total"] is None and roots["roots"] == []


def test_detail_truncation_has_missingness_and_partial(monkeypatch, tmp_path):
    runtime, job = _root(tmp_path)
    from control_plane.executive_runtime import BoundedRuntimeReadObservation
    original = BoundedRuntimeReadObservation.read_job_root_bounded
    def truncated(read, root_id):
        return dataclasses.replace(original(read, root_id), jobs_truncated=True, attempts_truncated_job_ids=(job.job_id,))
    monkeypatch.setattr(BoundedRuntimeReadObservation, "read_job_root_bounded", truncated)
    _use_runtime(monkeypatch, runtime)
    doc = view.read_fabric_view_v2(tmp_path, job.job_id)
    assert doc["capability"]["state"] == "PARTIAL"
    assert doc["runtime"]["acquisition"]["truncation"]["jobs"] is True
    assert any(f["missingness_class"] == "OMITTED" for f in doc["missingness"])


def test_real_discovery_owner_truncation_never_invents_total(monkeypatch, tmp_path):
    runtime = Runtime.at(tmp_path)
    for index in range(66):
        runtime.jobs.create_job(f"root-{index}")
    _use_runtime(monkeypatch, runtime)
    doc = view.list_roots_v2(tmp_path, limit=1000)
    assert doc["count"] == 64 and doc["total"] is None and doc["truncated"] is True
    assert doc["runtime"]["acquisition"]["truncation"]["roots"] is True


def test_projection_limit_does_not_change_owner_budget(monkeypatch, tmp_path):
    runtime = Runtime.at(tmp_path)
    for index in range(3):
        runtime.jobs.create_job(f"root-{index}")
    _use_runtime(monkeypatch, runtime)
    doc = view.list_roots_v2(tmp_path, limit=1)
    assert doc["count"] == 1 and doc["total"] == 3 and doc["truncated"] is True
    assert doc["runtime"]["acquisition"]["truncation"]["roots"] is False
    assert doc["runtime"]["acquisition"]["truncation"]["projection"] is True



@pytest.fixture
def observation_fixture(tmp_path):
    """Reuse the Runtime owner's closed test namespace; never a service adapter."""
    import importlib.util
    from pathlib import Path
    from control_plane import executive_runtime as er
    path = Path(er.__file__).resolve().parents[1] / "tests/test_executive_runtime_bounded_read.py"
    spec = importlib.util.spec_from_file_location("fabric_runtime_owner_test_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield from module.observation_fixture.__wrapped__(tmp_path)


def test_trusted_owner_observation_closes_before_receipt_and_uses_one_connection(observation_fixture, monkeypatch):
    from control_plane import executive_runtime as er
    _, _, runtime, namespace, _, job_id, _ = observation_fixture
    monkeypatch.setattr(runtime.events, "get_event_by_command_id", _trap)
    monkeypatch.setattr(runtime.jobs, "list_jobs", _trap)
    monkeypatch.setattr(runtime.attempts, "list_attempts", _trap)
    monkeypatch.setattr(runtime.events, "list_events", _trap)
    opened, events = [], []
    connect = er.sqlite3.connect
    def counted_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        opened.append(connection)
        return connection
    monkeypatch.setattr(er.sqlite3, "connect", counted_connect)
    point = runtime.store.get_event_by_command_id
    def bounded_point(command_id, *, connection):
        assert namespace.active and connection is not None
        events.append(command_id)
        return point(command_id, connection=connection)
    monkeypatch.setattr(runtime.store, "get_event_by_command_id", bounded_point)
    encode = er.RuntimeReadObservationReceipt.to_dict
    def finalized(receipt):
        assert not namespace.active and namespace.exits == 1
        return encode(receipt)
    monkeypatch.setattr(er.RuntimeReadObservationReceipt, "to_dict", finalized)
    doc = view.read_fabric_view_v2_from_runtime(runtime, job_id, armed={}, runtime_identity={"db_present": True})
    assert doc["root"]["job_id"] == job_id
    assert len(opened) == namespace.entries == namespace.exits == 1
    assert events == ["ceo-intent:OBS-ROOT-001"]
    generation = doc["runtime"]["acquisition"]["generation"]
    assert generation["schema"] == "mastermind.runtime_read_observation.v1"
    assert generation["state"] == "SAME"
    assert generation["before"] == generation["after"]
    assert doc["runtime"]["root"] is None


def test_trusted_owner_observation_concurrent_commit_is_conflict(observation_fixture, monkeypatch):
    _, writer, runtime, namespace, _, job_id, _ = observation_fixture
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.get_creation_event_by_command_id
    def commit_after_event(read, command):
        event = original(read, command)
        writer.jobs.create_job("concurrent unrelated commit")
        return event
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "get_creation_event_by_command_id", commit_after_event)
    doc = view.read_fabric_view_v2_from_runtime(runtime, job_id, armed={}, runtime_identity={"db_present": True})
    generation = doc["runtime"]["acquisition"]["generation"]
    assert generation["state"] == "CONFLICT"
    assert generation["before"] != generation["after"]
    assert doc["root"]["job_id"] == job_id and not namespace.active


@pytest.mark.parametrize("fault", ["namespace", "event"])
def test_trusted_owner_failed_observation_discards_rows_and_receipt(observation_fixture, monkeypatch, fault):
    _, _, runtime, namespace, _, job_id, _ = observation_fixture
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.get_creation_event_by_command_id
    def fail(read, command):
        if fault == "event":
            raise er.RuntimeReadUnavailable("private path must not be emitted")
        event = original(read, command)
        namespace.invalid = True
        return event
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "get_creation_event_by_command_id", fail)
    doc = view.read_fabric_view_v2_from_runtime(runtime, job_id, armed={}, runtime_identity={"db_present": True})
    assert doc["root"] is None
    assert doc["runtime"]["acquisition"]["snapshot_digest"] is None
    assert doc["runtime"]["acquisition"]["generation"]["state"] == "UNKNOWN"
    assert "private path" not in str(doc)
    assert not namespace.active


def test_trusted_runtime_without_namespace_never_attests_same(tmp_path):
    runtime, job = _root(tmp_path)
    doc = view.read_fabric_view_v2_from_runtime(runtime, job.job_id, armed={}, runtime_identity={"db_present": True})
    assert doc["root"]["job_id"] == job.job_id
    assert doc["runtime"]["acquisition"]["generation"]["state"] == "UNKNOWN"
    assert doc["runtime"]["acquisition"]["generation"]["source_identity"] is None
