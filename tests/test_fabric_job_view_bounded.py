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


# ---------------------------------------------------------------------------
# root-ratified narrow COO-cycle planner join (immutable Runtime-row relation)
# ---------------------------------------------------------------------------


def _planner_fixture(tmp_path):
    runtime, root = _root(tmp_path)
    planner = runtime.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0")
    return runtime, root, planner


def _snapshot_with_jobs(monkeypatch, jobs, *, truncated=False):
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.read_job_root_bounded

    def mutated(read, root_id):
        snapshot = original(read, root_id)
        return dataclasses.replace(
            snapshot, jobs=tuple(jobs),
            jobs_truncated=bool(truncated) or snapshot.jobs_truncated)

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_job_root_bounded", mutated)


def test_canonical_planner_child_joins_the_validated_workstream_root(monkeypatch, tmp_path):
    runtime, root, planner = _planner_fixture(tmp_path)
    _use_runtime(monkeypatch, runtime)
    monkeypatch.setattr(runtime.events, "get_event_by_command_id", _trap)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, root.job_id, armed={}, runtime_identity=_identity())
    fabric = doc["fabric_view"]
    assert [child["job_id"] for child in fabric["children"]] == [planner.job_id]
    child = fabric["children"][0]
    assert child["orchestration_role"] == "plan"
    assert child["parent_job_id"] == root.job_id
    assert child["root_job_id"] == root.job_id
    assert child["depth"] == 1
    assert fabric["unjoined_job_ids"] == [] and fabric["unjoined_job_count"] == 0
    assert fabric["runtime"]["acquisition"]["provenance"] == {
        "state": "COMPLETE", "unjoined_job_ids": []}
    assert fabric["capability"]["state"] == "PROVEN"
    assert not any("provenance not projected" in note for note in fabric["degraded"])
    assert not any("planner join refused" in note for note in fabric["degraded"])


def test_planner_join_requires_event_backed_root_workstream(monkeypatch, tmp_path):
    runtime, root, planner = _planner_fixture(tmp_path)
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.get_creation_event_by_command_id

    def without_workstream(read, command):
        event = original(read, command)
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict) or "provenance" not in payload:
            return event
        stripped = dict(payload)
        stripped["provenance"] = {
            key: value for key, value in payload["provenance"].items()
            if key != "workstream"}
        return dataclasses.replace(event, payload=stripped)

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "get_creation_event_by_command_id", without_workstream)
    _use_runtime(monkeypatch, runtime)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, root.job_id, armed={}, runtime_identity=_identity())
    fabric = doc["fabric_view"]
    assert fabric["children"] == []
    assert fabric["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] == sorted(
        [root.job_id, planner.job_id])
    assert fabric["runtime"]["acquisition"]["provenance"]["state"] == "PARTIAL"


@pytest.mark.parametrize("fault", [
    "foreign_source_digest", "wrong_command", "wrong_creator", "work_role",
    "depth2", "foreign_parent", "nonnumeric_id",
])
def test_rehashed_or_foreign_plan_cycle_stays_unjoined(monkeypatch, tmp_path, fault):
    from control_plane.executive_runtime import orchestration_digest
    runtime, root, planner = _planner_fixture(tmp_path)
    cycle = dict(planner.orchestration_provenance)
    changes = {}
    if fault == "foreign_source_digest":
        cycle["source_digest"] = "f" * 64
    elif fault == "wrong_command":
        cycle["command_id"] = f"coo-cycle:{root.job_id}:create-planner:1"
    elif fault == "wrong_creator":
        cycle["creator"] = "ceo_intent"
    elif fault == "work_role":
        cycle["role"] = "work"
        changes["orchestration_role"] = "work"
    elif fault == "depth2":
        changes["depth"] = 2
    elif fault == "foreign_parent":
        cycle["parent_job_id"] = "JOB-999"
        changes["parent_job_id"] = "JOB-999"
    else:
        cycle["job_id"] = "JOB-XX"
        changes["job_id"] = "JOB-XX"
    changes["orchestration_provenance"] = cycle
    changes["orchestration_provenance_digest"] = orchestration_digest(cycle)
    hostile = dataclasses.replace(planner, **changes)
    _snapshot_with_jobs(monkeypatch, [root, hostile])
    _use_runtime(monkeypatch, runtime)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, root.job_id, armed={}, runtime_identity=_identity())
    fabric = doc["fabric_view"]
    assert fabric["children"] == []
    assert hostile.job_id in fabric["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"]
    assert root.job_id not in fabric["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"]
    assert any("provenance not projected" in note for note in fabric["degraded"])


def test_ordinary_child_without_cycle_stays_unjoined(monkeypatch, tmp_path):
    # The Runtime refuses role-null children in an orchestration subtree, so a
    # legacy row can only appear as a hostile observation member; the view must
    # still keep it unjoined rather than joining it as a planner.
    from control_plane.executive_runtime import Job
    runtime, root = _root(tmp_path)
    plain = Job(
        job_id="JOB-004", objective="plain child", department="executive-infrastructure",
        priority=5, status=None, assigned_worker_id=None, assigned_quota_class=None,
        authority_level="READ", branch=None, worktree=None, checkpoint=None, result=None,
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        parent_job_id=root.job_id, root_job_id=root.job_id, depth=1,
    )
    _snapshot_with_jobs(monkeypatch, [root, plain])
    _use_runtime(monkeypatch, runtime)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, root.job_id, armed={}, runtime_identity=_identity())
    fabric = doc["fabric_view"]
    assert fabric["children"] == []
    assert fabric["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] == [plain.job_id]


def test_foreign_root_member_invalidates_the_whole_bounded_observation(monkeypatch, tmp_path):
    # A row claiming another root never reaches the planner join: the bounded
    # membership invariant refuses the entire observation first.
    from control_plane.executive_runtime import orchestration_digest
    runtime, root, planner = _planner_fixture(tmp_path)
    cycle = dict(planner.orchestration_provenance)
    cycle["root_job_id"] = "JOB-999"
    hostile = dataclasses.replace(
        planner, root_job_id="JOB-999", orchestration_provenance=cycle,
        orchestration_provenance_digest=orchestration_digest(cycle))
    _snapshot_with_jobs(monkeypatch, [root, hostile])
    _use_runtime(monkeypatch, runtime)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, root.job_id, armed={}, runtime_identity=_identity())
    fabric = doc["fabric_view"]
    assert fabric["root"] is None
    assert fabric["children"] == []
    assert any("bounded acquisition unavailable" in note for note in fabric["degraded"])


def test_duplicate_eligible_planners_refuse_the_join(monkeypatch, tmp_path):
    from control_plane.executive_runtime import orchestration_digest
    runtime, root, planner = _planner_fixture(tmp_path)
    cycle = dict(planner.orchestration_provenance)
    cycle["job_id"] = "JOB-003"
    twin = dataclasses.replace(
        planner, job_id="JOB-003", orchestration_provenance=cycle,
        orchestration_provenance_digest=orchestration_digest(cycle))
    _snapshot_with_jobs(monkeypatch, [root, planner, twin])
    _use_runtime(monkeypatch, runtime)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, root.job_id, armed={}, runtime_identity=_identity())
    fabric = doc["fabric_view"]
    assert fabric["children"] == []
    assert fabric["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] == sorted(
        [planner.job_id, twin.job_id])
    assert any("ambiguous eligible plan children" in note for note in fabric["degraded"])


def test_truncated_job_scope_cannot_establish_planner_uniqueness(monkeypatch, tmp_path):
    runtime, root, planner = _planner_fixture(tmp_path)
    _snapshot_with_jobs(monkeypatch, [root, planner], truncated=True)
    _use_runtime(monkeypatch, runtime)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, root.job_id, armed={}, runtime_identity=_identity())
    fabric = doc["fabric_view"]
    assert fabric["children"] == []
    assert fabric["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] == [planner.job_id]
    assert any("planner uniqueness unavailable" in note for note in fabric["degraded"])


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


def _identity():
    return {"db_present": True}


def _trap_untrusted_root_paths(monkeypatch, runtime):
    monkeypatch.setattr(view, "_open_runtime", _trap)
    monkeypatch.setattr(view, "_read_armed", _trap)
    monkeypatch.setattr(Runtime, "discover_job_roots_bounded", _trap)
    monkeypatch.setattr(runtime.jobs, "list_jobs", _trap)
    monkeypatch.setattr(runtime.attempts, "list_attempts", _trap)
    monkeypatch.setattr(runtime.events, "list_events", _trap)
    monkeypatch.setattr(runtime.events, "get_event_by_command_id", _trap)
    monkeypatch.setattr(runtime.store, "get_event_by_command_id", _trap)
    from control_plane import executive_runtime as er
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "get_creation_event_by_command_id", _trap)
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_role_result_bounded", _trap)
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_job_root_bounded", _trap)


def _assert_cleared_root_list(doc):
    assert doc["schema"] == "mastermind.fabric_job_root_list.v2"
    assert doc["roots"] == []
    assert doc["count"] == 0
    assert doc["total"] is None
    assert doc["truncated"] is False
    assert doc["runtime"]["acquisition"]["snapshot_digest"] is None
    assert doc["runtime"]["acquisition"]["generation"]["state"] == "UNKNOWN"
    assert doc["runtime"]["acquisition"]["generation"]["source_identity"] is None
    assert any("bounded acquisition unavailable" in note for note in doc["degraded"])


def test_list_roots_v2_from_runtime_is_present():
    assert callable(getattr(view, "list_roots_v2_from_runtime"))


def test_trusted_root_discovery_closes_before_receipt_and_uses_one_connection(observation_fixture, monkeypatch):
    from control_plane import executive_runtime as er
    _, _, runtime, namespace, _, job_id, _ = observation_fixture
    _trap_untrusted_root_paths(monkeypatch, runtime)
    opened = []
    connect = er.sqlite3.connect

    def counted_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(er.sqlite3, "connect", counted_connect)
    encode = er.RuntimeReadObservationReceipt.to_dict

    def finalized(receipt):
        assert not namespace.active and namespace.exits == 1
        return encode(receipt)

    monkeypatch.setattr(er.RuntimeReadObservationReceipt, "to_dict", finalized)
    doc = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity())
    assert doc["schema"] == "mastermind.fabric_job_root_list.v2"
    assert set(doc) == view.ROOT_LIST_KEYS
    assert [row["job_id"] for row in doc["roots"]] == [job_id]
    assert set(doc["roots"][0]) == view.ROOT_ROW_KEYS
    assert doc["count"] == 1 and doc["total"] == 1 and doc["truncated"] is False
    assert len(opened) == namespace.entries == namespace.exits == 1
    generation = doc["runtime"]["acquisition"]["generation"]
    assert generation["schema"] == "mastermind.runtime_read_observation.v1"
    assert generation["state"] == "SAME"
    assert type(generation["before"]) is int and generation["before"] >= 0
    assert generation["before"] == generation["after"]
    assert type(generation["source_identity"]) is str and len(generation["source_identity"]) == 32
    assert "/" not in generation["source_identity"]
    assert len(doc["runtime"]["acquisition"]["snapshot_digest"]) == 64
    assert doc["runtime"]["root"] is None
    assert doc["runtime"]["acquisition"]["query"] == {"kind": "root_discovery", "root_job_id": None}
    provenance = doc["runtime"]["acquisition"]["provenance"]
    assert provenance["state"] == "PARTIAL"
    assert provenance["unjoined_job_ids"] == [job_id]
    assert any("exact-root" in note for note in doc["degraded"])


def test_trusted_root_discovery_never_opens_paths_or_events(observation_fixture, monkeypatch):
    _, _, runtime, _, _, job_id, _ = observation_fixture
    _trap_untrusted_root_paths(monkeypatch, runtime)
    doc = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity())
    assert doc["roots"][0]["job_id"] == job_id
    assert doc["runtime"]["acquisition"]["provenance"]["state"] == "PARTIAL"


def test_trusted_root_discovery_owner_truncation_never_invents_total(observation_fixture, monkeypatch):
    _, writer, runtime, _, _, _, _ = observation_fixture
    for index in range(64):
        writer.jobs.create_job(f"root-{index}")
    _trap_untrusted_root_paths(monkeypatch, runtime)
    doc = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity(), limit=1000)
    assert doc["count"] == 64 and doc["total"] is None and doc["truncated"] is True
    assert doc["runtime"]["acquisition"]["truncation"]["roots"] is True
    assert doc["runtime"]["acquisition"]["truncation"]["projection"] is False
    assert doc["runtime"]["acquisition"]["provenance"]["state"] == "PARTIAL"
    assert len(doc["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"]) == 64


def test_trusted_root_projection_limit_keeps_owner_digest_and_count(observation_fixture, monkeypatch):
    _, writer, runtime, _, _, job_id, _ = observation_fixture
    extra = [writer.jobs.create_job(f"root-{index}").job_id for index in range(2)]
    _trap_untrusted_root_paths(monkeypatch, runtime)
    full = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity(), limit=1000)
    page = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity(), limit=1)
    assert full["count"] == 3 and full["total"] == 3 and full["truncated"] is False
    assert page["count"] == 1 and page["total"] == 3 and page["truncated"] is True
    assert page["runtime"]["acquisition"]["truncation"]["roots"] is False
    assert page["runtime"]["acquisition"]["truncation"]["projection"] is True
    assert page["runtime"]["acquisition"]["snapshot_digest"] == full["runtime"]["acquisition"]["snapshot_digest"]
    assert page["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] == sorted([job_id, *extra])


@pytest.mark.parametrize("limit", [True, False, 0, -1])
def test_trusted_root_limit_is_validated_before_owner_enter(observation_fixture, monkeypatch, limit):
    _, _, runtime, namespace, _, _, _ = observation_fixture
    monkeypatch.setattr(Runtime, "observe_bounded_read", _trap)
    with pytest.raises(ValueError, match="positive integer"):
        view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity(), limit=limit)
    assert namespace.entries == 0


def test_trusted_root_unarmed_false_preserves_admitted_roots(observation_fixture, monkeypatch):
    _, _, runtime, _, _, job_id, _ = observation_fixture
    _trap_untrusted_root_paths(monkeypatch, runtime)
    doc = view.list_roots_v2_from_runtime(
        runtime, armed={"ceo_submit_armed": False}, runtime_identity=_identity(),
    )
    assert doc["roots"][0]["job_id"] == job_id
    assert any("new CEO submissions are unavailable" in note for note in doc["degraded"])


def test_trusted_root_empty_enumeration_is_explicitly_partial(tmp_path, monkeypatch):
    from control_plane import executive_runtime as er
    from tests.test_executive_runtime_bounded_read import ObservationNamespace
    root = tmp_path / "runtime"
    root.mkdir()
    writer = Runtime.at(root)
    keeper = er.sqlite3.connect(writer.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    namespace = ObservationNamespace(writer.store.path)
    binding = er.RuntimeReadBinding(namespace)
    runtime = Runtime.at(root, create=False, read_binding=binding)
    try:
        _trap_untrusted_root_paths(monkeypatch, runtime)
        doc = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity())
        assert doc["roots"] == [] and doc["count"] == 0 and doc["total"] == 0
        assert doc["truncated"] is False
        assert doc["runtime"]["acquisition"]["generation"]["state"] == "SAME"
        assert doc["runtime"]["acquisition"]["provenance"]["state"] == "PARTIAL"
        assert doc["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] == []
    finally:
        keeper.close()
        if binding._unclosed_connection is not None:
            er.sqlite3.Connection.close(binding._unclosed_connection)
        if binding._retained_namespace is not None:
            binding._retained_namespace.close()


def test_trusted_root_legacy_provenance_still_enumerated_without_events(observation_fixture, monkeypatch):
    from control_plane.ceo_intent import submit_intent
    _, writer, runtime, _, _, job_id, _ = observation_fixture
    writer.jobs.create_job("legacy", provenance={"schema": "mastermind.ceo_intent.v1", "workstream": "WS:LEGACY"})
    for index in range(16):
        submit_intent(writer, {
            "schema": "mastermind.ceo_intent.v2", "intent_kind": "executive_coo_cycle",
            "business_impact": "material", "intent_id": f"OBS-EXTRA-{index:02d}", "actor": "ceo-sol",
            "objective": "extra root", "department": "executive-infrastructure",
            "priority": 5, "workstream": "WS:FABRIC",
            "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
            "execution_contract": {"requested_authorities": ["READ"], "attempt_limit": 2},
        })
    _trap_untrusted_root_paths(monkeypatch, runtime)
    doc = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity())
    assert doc["count"] == 18 and doc["total"] == 18
    assert job_id in {row["job_id"] for row in doc["roots"]}
    assert doc["runtime"]["acquisition"]["provenance"]["state"] == "PARTIAL"
    assert len(doc["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"]) == 18


def test_trusted_root_discovery_commit_restore_is_conflict(observation_fixture, monkeypatch):
    _, writer, runtime, namespace, _, job_id, _ = observation_fixture
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.discover_job_roots_bounded

    def commit_and_restore(read):
        snapshot = original(read)
        objective = writer.jobs.get_job(job_id).objective
        with writer.store.transaction() as connection:
            connection.execute("UPDATE jobs SET objective=? WHERE job_id=?", ("changed", job_id))
        with writer.store.transaction() as connection:
            connection.execute("UPDATE jobs SET objective=? WHERE job_id=?", (objective, job_id))
        return snapshot

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "discover_job_roots_bounded", commit_and_restore)
    doc = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity())
    generation = doc["runtime"]["acquisition"]["generation"]
    assert generation["state"] == "CONFLICT"
    assert generation["before"] != generation["after"]
    assert doc["roots"][0]["job_id"] == job_id
    assert "CURRENT" not in str(doc)
    assert any("CONFLICT" in note for note in doc["degraded"])
    assert not namespace.active


def test_trusted_root_unbound_runtime_is_unknown_not_same(tmp_path):
    runtime, job = _root(tmp_path)
    doc = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity())
    assert doc["roots"][0]["job_id"] == job.job_id
    assert doc["runtime"]["acquisition"]["generation"]["state"] == "UNKNOWN"
    assert doc["runtime"]["acquisition"]["generation"]["source_identity"] is None
    assert doc["runtime"]["acquisition"]["provenance"]["state"] == "PARTIAL"


def test_trusted_root_missing_runtime_has_no_fallback():
    doc = view.list_roots_v2_from_runtime(None, armed={}, runtime_identity=_identity())
    _assert_cleared_root_list(doc)


@pytest.mark.parametrize("fault", ["schema", "digest", "truncated", "duplicate", "foreign", "parent", "depth", "extra"])
def test_trusted_root_malformed_discovery_refuses_without_fallback(observation_fixture, monkeypatch, fault):
    _, _, runtime, namespace, _, _, _ = observation_fixture
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.discover_job_roots_bounded

    def mutated(read):
        snapshot = original(read)
        root = snapshot.roots[0]
        if fault == "schema":
            return dataclasses.replace(snapshot, schema_version="mastermind.not-discovery/v0")
        if fault == "digest":
            return dataclasses.replace(snapshot, snapshot_digest="0" * 63 + "G")
        if fault == "truncated":
            return dataclasses.replace(snapshot, truncated=1)
        if fault == "duplicate":
            return dataclasses.replace(snapshot, roots=(root, root))
        if fault == "foreign":
            return dataclasses.replace(snapshot, roots=(dataclasses.replace(root, root_job_id="foreign"),))
        if fault == "parent":
            return dataclasses.replace(snapshot, roots=(dataclasses.replace(root, parent_job_id="parent"),))
        if fault == "depth":
            return dataclasses.replace(snapshot, roots=(dataclasses.replace(root, depth=True),))
        extra = tuple(dataclasses.replace(root, job_id=f"JOB-X{index:02d}", root_job_id=f"JOB-X{index:02d}") for index in range(65))
        return dataclasses.replace(snapshot, roots=extra)

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "discover_job_roots_bounded", mutated)
    doc = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity())
    _assert_cleared_root_list(doc)
    assert not namespace.active


def test_trusted_root_close_failure_clears_rows_and_receipt(observation_fixture, monkeypatch):
    _, _, runtime, namespace, _, _, _ = observation_fixture
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.discover_job_roots_bounded

    def invalidate(read):
        snapshot = original(read)
        namespace.invalid = True
        return snapshot

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "discover_job_roots_bounded", invalidate)
    doc = view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity())
    _assert_cleared_root_list(doc)
    assert "private path" not in str(doc)
    assert not namespace.active


def test_trusted_root_cancellation_closes_and_propagates(observation_fixture, monkeypatch):
    _, _, runtime, namespace, _, _, _ = observation_fixture
    from control_plane import executive_runtime as er

    def interrupt(_read):
        raise KeyboardInterrupt("sample interrupted")

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "discover_job_roots_bounded", interrupt)
    with pytest.raises(KeyboardInterrupt, match="sample interrupted"):
        view.list_roots_v2_from_runtime(runtime, armed={}, runtime_identity=_identity())
    assert not namespace.active
    assert namespace.entries == namespace.exits == 1


from tests.test_fabric_result_projection import bound_max_chain, bound_sealed_worker_planner  # noqa: E402
from tests.test_fabric_result_projection import _select_bound  # noqa: E402
from control_plane import fabric_result_projection as frp
from control_plane.executive_runtime import JobStatus


_INDEX_KEYS = {
    "schema", "root_job_id", "snapshot_digest", "generation", "availability",
    "refs", "absent_job_ids", "omitted_job_ids", "truncated",
}
_REF_KEYS = {
    "root_job_id", "job_id", "attempt_id", "result_envelope_digest",
    "orchestration_role", "validation",
}
_V3_KEYS = {"schema", "fabric_view", "result_refs"}


def _bound_pair(tmp_path):
    from control_plane import executive_runtime as er
    from tests.test_executive_runtime_bounded_read import ObservationNamespace
    root = tmp_path / "runtime"
    root.mkdir()
    writer = Runtime.at(root)
    keeper = er.sqlite3.connect(writer.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    namespace = ObservationNamespace(writer.store.path)
    binding = er.RuntimeReadBinding(namespace)
    reader = Runtime.at(root, create=False, read_binding=binding)
    return writer, reader, namespace, keeper, binding


def _release_bound(keeper, binding):
    from control_plane import executive_runtime as er
    keeper.close()
    if binding._unclosed_connection is not None:
        er.sqlite3.Connection.close(binding._unclosed_connection)
    if binding._retained_namespace is not None:
        binding._retained_namespace.close()


def _trap_v3_fanout(monkeypatch, runtime):
    monkeypatch.setattr(view, "_open_runtime", _trap)
    monkeypatch.setattr(view, "_read_armed", _trap)
    monkeypatch.setattr(view, "read_fabric_view_v2_from_runtime", _trap)
    monkeypatch.setattr(Runtime, "discover_job_roots_bounded", _trap)
    monkeypatch.setattr(runtime.jobs, "list_jobs", _trap)
    monkeypatch.setattr(runtime.attempts, "list_attempts", _trap)
    monkeypatch.setattr(runtime.events, "list_events", _trap)


def _assert_closed_index(index, *, root_job_id):
    assert set(index) == _INDEX_KEYS
    assert index["schema"] == "mastermind.fabric_result_reference_index.v1"
    assert index["root_job_id"] == root_job_id
    assert index["refs"] == sorted(index["refs"], key=lambda row: row["job_id"])
    assert index["absent_job_ids"] == sorted(index["absent_job_ids"])
    assert index["omitted_job_ids"] == sorted(index["omitted_job_ids"])
    ids = [row["job_id"] for row in index["refs"]] + index["absent_job_ids"] + index["omitted_job_ids"]
    assert len(ids) == len(set(ids))
    for row in index["refs"]:
        assert set(row) == _REF_KEYS
        assert row["root_job_id"] == root_job_id
        assert row["validation"] == "UNVALIDATED"


def test_v3_apis_are_present():
    assert callable(getattr(view, "read_fabric_view_v3_from_runtime"))
    assert callable(getattr(view, "compose_fabric_result_reference_index"))


def test_v3_operator_harness_same_observation_and_selected_detail(bound_max_chain, monkeypatch):
    runtime, root, nodes, expected, reader = bound_max_chain
    from control_plane import executive_runtime as er
    original_result_read = er.BoundedRuntimeReadObservation.read_role_result_bounded
    result_reads = []

    def trap_result(self, *args, **kwargs):
        result_reads.append(True)
        raise AssertionError("full result read during index creation")

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_role_result_bounded", trap_result)
    _trap_v3_fanout(monkeypatch, reader)
    encode = er.RuntimeReadObservationReceipt.to_dict
    closed = []

    def finalized(receipt):
        closed.append(True)
        return encode(receipt)

    monkeypatch.setattr(er.RuntimeReadObservationReceipt, "to_dict", finalized)
    doc = view.read_fabric_view_v3_from_runtime(
        reader, root.job_id, armed={}, runtime_identity=_identity(),
    )
    assert closed == [True]
    assert result_reads == []
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_role_result_bounded", original_result_read)
    assert set(doc) == _V3_KEYS
    assert doc["schema"] == "mastermind.fabric_job_view.v3"
    fabric = doc["fabric_view"]
    index = doc["result_refs"]
    assert fabric["schema"] == "mastermind.fabric_job_view.v2"
    assert set(fabric) == view.OUTPUT_KEYS
    assert fabric["root"]["acceptance"]["state"] == "NOT_PROJECTED"
    _assert_closed_index(index, root_job_id=root.job_id)
    assert index["snapshot_digest"] == fabric["runtime"]["acquisition"]["snapshot_digest"]
    assert index["generation"] == fabric["runtime"]["acquisition"]["generation"]
    assert index["generation"]["state"] == "SAME"
    assert fabric["runtime"]["acquisition"]["query"] == {"kind": "root_detail", "root_job_id": root.job_id}
    refs = {row["job_id"]: row for row in index["refs"]}
    for completion in expected:
        row = refs[completion.job.job_id]
        raw = runtime.jobs.get_job(completion.job.job_id)
        assert raw.result["schema_version"] == "mastermind.orchestration_terminal_receipt/v1"
        assert row["attempt_id"] == completion.attempt.attempt_id == raw.current_attempt_id
        assert row["result_envelope_digest"] == completion.result_digest == raw.result["result_envelope_digest"]
        assert row["orchestration_role"] == raw.orchestration_role
    completion = expected[0]
    snapshot, receipt = _select_bound(reader, root.job_id, completion)
    projection = frp.project_fabric_role_result(snapshot, receipt)
    assert refs[completion.job.job_id]["result_envelope_digest"] == (
        projection.complete["selection"]["result_envelope_digest"]
    )
    assert "INDEX_MUST_NOT_SERIALIZE" not in str(index)


def test_v3_sealed_worker_same_observation_and_selected_detail(bound_sealed_worker_planner, monkeypatch):
    runtime, root, expected, reader = bound_sealed_worker_planner
    from control_plane import executive_runtime as er
    original_result_read = er.BoundedRuntimeReadObservation.read_role_result_bounded
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_role_result_bounded", _trap)
    _trap_v3_fanout(monkeypatch, reader)
    doc = view.read_fabric_view_v3_from_runtime(
        reader, root.job_id, armed={}, runtime_identity=_identity(),
    )
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_role_result_bounded", original_result_read)
    index = doc["result_refs"]
    _assert_closed_index(index, root_job_id=root.job_id)
    assert expected.execution_mode == "SEALED_WORKER"
    refs = {row["job_id"]: row for row in index["refs"]}
    row = refs[expected.job.job_id]
    raw = runtime.jobs.get_job(expected.job.job_id)
    assert raw.result["schema_version"] == "mastermind.orchestration_terminal_receipt/v1"
    assert raw.result["execution_mode"] == "SEALED_WORKER"
    assert row["result_envelope_digest"] == expected.result_digest == raw.result["result_envelope_digest"]
    snapshot, receipt = _select_bound(reader, root.job_id, expected)
    projection = frp.project_fabric_role_result(snapshot, receipt)
    assert row["result_envelope_digest"] == projection.complete["selection"]["result_envelope_digest"]
    assert index["snapshot_digest"] == doc["fabric_view"]["runtime"]["acquisition"]["snapshot_digest"]
    assert index["generation"] == doc["fabric_view"]["runtime"]["acquisition"]["generation"]


def test_v3_index_never_serializes_nested_envelope_sentinel(bound_max_chain, monkeypatch):
    runtime, root, nodes, expected, reader = bound_max_chain
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.read_job_root_bounded

    def inject(read, root_id):
        snapshot = original(read, root_id)
        jobs = []
        for job in snapshot.jobs:
            result = job.result
            if isinstance(result, dict) and isinstance(result.get("result_envelope"), dict):
                envelope = dict(result["result_envelope"])
                envelope["__index_sentinel__"] = "INDEX_MUST_NOT_SERIALIZE"
                result = dict(result)
                result["result_envelope"] = envelope
                job = dataclasses.replace(job, result=result)
            jobs.append(job)
        return dataclasses.replace(snapshot, jobs=tuple(jobs))

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_job_root_bounded", inject)
    _trap_v3_fanout(monkeypatch, reader)
    doc = view.read_fabric_view_v3_from_runtime(
        reader, root.job_id, armed={}, runtime_identity=_identity(),
    )
    encoded = __import__("json").dumps(doc["result_refs"], sort_keys=True)
    assert "INDEX_MUST_NOT_SERIALIZE" not in encoded
    assert "__index_sentinel__" not in encoded
    assert expected[0].job.job_id in {row["job_id"] for row in doc["result_refs"]["refs"]}


def test_v3_seventeen_noncompleted_missing_are_available_absent(tmp_path, monkeypatch):
    writer, reader, namespace, keeper, binding = _bound_pair(tmp_path)
    try:
        root = writer.jobs.create_job("root-absent")
        children = [writer.jobs.create_job(f"child-{index:02d}", parent_job_id=root.job_id) for index in range(16)]
        _trap_v3_fanout(monkeypatch, reader)
        doc = view.read_fabric_view_v3_from_runtime(
            reader, root.job_id, armed={}, runtime_identity=_identity(),
        )
        index = doc["result_refs"]
        expected_ids = sorted([root.job_id, *[child.job_id for child in children]])
        _assert_closed_index(index, root_job_id=root.job_id)
        assert index["availability"] == "AVAILABLE"
        assert index["refs"] == []
        assert index["absent_job_ids"] == expected_ids
        assert index["omitted_job_ids"] == []
        assert index["truncated"] is False
        assert index["generation"]["state"] == "SAME"
        assert not namespace.active
    finally:
        _release_bound(keeper, binding)


def test_v3_seventeen_completed_missing_are_partial_omitted(tmp_path, monkeypatch):
    writer, reader, namespace, keeper, binding = _bound_pair(tmp_path)
    try:
        root = writer.jobs.create_job("root-missing")
        for index in range(16):
            writer.jobs.create_job(f"child-{index:02d}", parent_job_id=root.job_id)
        from control_plane import executive_runtime as er
        original = er.BoundedRuntimeReadObservation.read_job_root_bounded

        def missing_results(read, root_id):
            snapshot = original(read, root_id)
            jobs = tuple(
                dataclasses.replace(job, status=JobStatus.COMPLETED, result=None, current_attempt_id=None)
                for job in snapshot.jobs
            )
            return dataclasses.replace(snapshot, jobs=jobs)

        monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_job_root_bounded", missing_results)
        _trap_v3_fanout(monkeypatch, reader)
        doc = view.read_fabric_view_v3_from_runtime(
            reader, root.job_id, armed={}, runtime_identity=_identity(),
        )
        index = doc["result_refs"]
        _assert_closed_index(index, root_job_id=root.job_id)
        assert index["availability"] == "PARTIAL"
        assert index["refs"] == []
        assert index["absent_job_ids"] == []
        assert len(index["omitted_job_ids"]) == 17
        assert index["truncated"] is False
        assert not namespace.active
    finally:
        _release_bound(keeper, binding)


@pytest.mark.parametrize("fault", [
    "missing_current", "wrong_job", "wrong_mode", "wrong_role",
    "wrong_digest", "wrong_schema", "extra_keys", "legacy", "attempts_truncation",
])
def test_v3_malformed_or_mismatched_receipt_never_fabricates_refs(bound_max_chain, monkeypatch, fault):
    runtime, root, nodes, expected, reader = bound_max_chain
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.read_job_root_bounded
    target_id = expected[0].job.job_id

    def mutated(read, root_id):
        snapshot = original(read, root_id)
        jobs = []
        attempts = list(snapshot.attempts)
        for job in snapshot.jobs:
            if job.job_id != target_id:
                jobs.append(job)
                continue
            result = dict(job.result) if isinstance(job.result, dict) else {}
            if fault == "missing_current":
                jobs.append(dataclasses.replace(job, current_attempt_id="ATT-missing"))
            elif fault == "wrong_job":
                result["job_id"] = "JOB-foreign"
                jobs.append(dataclasses.replace(job, result=result))
            elif fault == "wrong_mode":
                result["execution_mode"] = "OPERATOR_HARNESS" if result.get("execution_mode") == "SEALED_WORKER" else "SEALED_WORKER"
                jobs.append(dataclasses.replace(job, result=result))
            elif fault == "wrong_role":
                result["orchestration_role"] = "plan" if job.orchestration_role != "plan" else "work"
                jobs.append(dataclasses.replace(job, result=result))
            elif fault == "wrong_digest":
                result["result_envelope_digest"] = "a" * 64
                jobs.append(dataclasses.replace(job, result=result))
            elif fault == "wrong_schema":
                result["schema_version"] = "mastermind.legacy_result/v0"
                jobs.append(dataclasses.replace(job, result=result))
            elif fault == "extra_keys":
                result["extra"] = "nope"
                jobs.append(dataclasses.replace(job, result=result))
            elif fault == "legacy":
                jobs.append(dataclasses.replace(job, result={"summary": "legacy"}))
            else:
                jobs.append(job)
        if fault == "attempts_truncation":
            remaining = tuple(item for item in attempts if item.job_id != target_id)
            return dataclasses.replace(
                snapshot, jobs=tuple(jobs), attempts=remaining,
                attempts_truncated_job_ids=(target_id,),
            )
        return dataclasses.replace(snapshot, jobs=tuple(jobs), attempts=tuple(attempts))

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_job_root_bounded", mutated)
    _trap_v3_fanout(monkeypatch, reader)
    doc = view.read_fabric_view_v3_from_runtime(
        reader, root.job_id, armed={}, runtime_identity=_identity(),
    )
    index = doc["result_refs"]
    _assert_closed_index(index, root_job_id=root.job_id)
    assert target_id not in {row["job_id"] for row in index["refs"]}
    assert target_id in index["omitted_job_ids"]
    assert index["availability"] == "PARTIAL"
    if fault == "attempts_truncation":
        assert index["truncated"] is True


def test_v3_current_attempt_is_not_latest_time_heuristic():
    from types import SimpleNamespace
    generation = {
        "schema": "mastermind.runtime_read_observation.v1",
        "state": "SAME", "source_identity": "a" * 32, "before": 1, "after": 1,
    }
    receipt = {
        "schema_version": "mastermind.orchestration_terminal_receipt/v1",
        "status": "COMPLETED", "job_id": "JOB-1", "attempt_id": "ATT-old",
        "orchestration_role": "work", "execution_mode": "OPERATOR_HARNESS",
        "result_seal_command_id": "orchestration-result-seal:ATT-old",
        "result_evidence": None, "result_envelope": {"nested": True},
        "result_envelope_digest": "b" * 64, "artifact_receipt_digest": "c" * 64,
        "validation_receipt_digest": "d" * 64, "effective_grant_digest": "e" * 64,
        "terminal_evidence_digest": "f" * 64,
    }
    newer = dict(receipt, attempt_id="ATT-new", result_envelope_digest="1" * 64)
    job = SimpleNamespace(
        job_id="JOB-1", root_job_id="JOB-root", status=JobStatus.COMPLETED,
        orchestration_role="work", current_attempt_id="ATT-old", result=receipt, parent_job_id="JOB-root",
    )
    root = SimpleNamespace(
        job_id="JOB-root", root_job_id="JOB-root", status=JobStatus.QUEUED,
        orchestration_role="aggregation", current_attempt_id=None, result=None, parent_job_id=None,
    )
    old = SimpleNamespace(attempt_id="ATT-old", job_id="JOB-1", status=JobStatus.COMPLETED,
                          execution_mode="OPERATOR_HARNESS", result=receipt, started_at="2020-01-01T00:00:00Z")
    new = SimpleNamespace(attempt_id="ATT-new", job_id="JOB-1", status=JobStatus.COMPLETED,
                          execution_mode="OPERATOR_HARNESS", result=newer, started_at="2026-01-01T00:00:00Z")
    snapshot = SimpleNamespace(
        root_job_id="JOB-root", jobs=(root, job), attempts=(new, old),
        jobs_truncated=False, attempts_truncated_job_ids=(), snapshot_digest="a" * 64,
    )
    index = view.compose_fabric_result_reference_index(snapshot, generation)
    assert [row["attempt_id"] for row in index["refs"]] == ["ATT-old"]
    assert index["refs"][0]["result_envelope_digest"] == "b" * 64
    assert index["availability"] == "AVAILABLE"


def test_v3_foreign_root_job_is_omitted_not_a_ref():
    from types import SimpleNamespace
    generation = {
        "schema": "mastermind.runtime_read_observation.v1",
        "state": "SAME", "source_identity": "a" * 32, "before": 1, "after": 1,
    }
    receipt = {
        "schema_version": "mastermind.orchestration_terminal_receipt/v1",
        "status": "COMPLETED", "job_id": "JOB-1", "attempt_id": "ATT-1",
        "orchestration_role": "work", "execution_mode": "OPERATOR_HARNESS",
        "result_seal_command_id": "orchestration-result-seal:ATT-1",
        "result_evidence": None, "result_envelope": {"nested": True},
        "result_envelope_digest": "b" * 64, "artifact_receipt_digest": "c" * 64,
        "validation_receipt_digest": "d" * 64, "effective_grant_digest": "e" * 64,
        "terminal_evidence_digest": "f" * 64,
    }
    root = SimpleNamespace(
        job_id="JOB-root", root_job_id="JOB-root", status=JobStatus.QUEUED,
        orchestration_role="aggregation", current_attempt_id=None, result=None, parent_job_id=None,
    )
    job = SimpleNamespace(
        job_id="JOB-1", root_job_id="JOB-foreign", status=JobStatus.COMPLETED,
        orchestration_role="work", current_attempt_id="ATT-1", result=receipt, parent_job_id="JOB-root",
    )
    attempt = SimpleNamespace(
        attempt_id="ATT-1", job_id="JOB-1", status=JobStatus.COMPLETED,
        execution_mode="OPERATOR_HARNESS", result=receipt,
    )
    snapshot = SimpleNamespace(
        root_job_id="JOB-root", jobs=(root, job), attempts=(attempt,),
        jobs_truncated=False, attempts_truncated_job_ids=(), snapshot_digest="a" * 64,
    )
    index = view.compose_fabric_result_reference_index(snapshot, generation)
    assert index["refs"] == []
    assert index["omitted_job_ids"] == ["JOB-1"]
    assert index["absent_job_ids"] == ["JOB-root"]
    assert index["availability"] == "PARTIAL"


def test_v3_conflict_and_unknown_are_unavailable(observation_fixture, monkeypatch):
    _, writer, runtime, namespace, _, job_id, _ = observation_fixture
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.get_creation_event_by_command_id

    def commit_and_restore(read, command):
        event = original(read, command)
        objective = writer.jobs.get_job(job_id).objective
        with writer.store.transaction() as connection:
            connection.execute("UPDATE jobs SET objective=? WHERE job_id=?", ("changed", job_id))
        with writer.store.transaction() as connection:
            connection.execute("UPDATE jobs SET objective=? WHERE job_id=?", (objective, job_id))
        return event

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "get_creation_event_by_command_id", commit_and_restore)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, job_id, armed={}, runtime_identity=_identity(),
    )
    index = doc["result_refs"]
    assert index["availability"] == "UNAVAILABLE"
    assert index["refs"] == []
    assert index["absent_job_ids"] == []
    assert index["generation"]["state"] == "CONFLICT"
    assert index["snapshot_digest"] == doc["fabric_view"]["runtime"]["acquisition"]["snapshot_digest"]
    assert index["generation"] == doc["fabric_view"]["runtime"]["acquisition"]["generation"]
    assert doc["fabric_view"]["root"]["job_id"] == job_id
    assert not namespace.active


def test_v3_unbound_runtime_index_is_unavailable(tmp_path):
    runtime, job = _root(tmp_path)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, job.job_id, armed={}, runtime_identity=_identity(),
    )
    index = doc["result_refs"]
    assert index["availability"] == "UNAVAILABLE"
    assert index["refs"] == []
    assert index["absent_job_ids"] == []
    assert index["generation"]["state"] == "UNKNOWN"
    assert index["generation"] == doc["fabric_view"]["runtime"]["acquisition"]["generation"]
    assert doc["fabric_view"]["root"]["job_id"] == job.job_id


def test_v3_finalization_failure_clears_both_parts(observation_fixture, monkeypatch):
    _, _, runtime, namespace, _, job_id, _ = observation_fixture
    from control_plane import executive_runtime as er
    original = er.BoundedRuntimeReadObservation.get_creation_event_by_command_id

    def invalidate(read, command):
        event = original(read, command)
        namespace.invalid = True
        return event

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "get_creation_event_by_command_id", invalidate)
    doc = view.read_fabric_view_v3_from_runtime(
        runtime, job_id, armed={}, runtime_identity=_identity(),
    )
    assert doc["fabric_view"]["root"] is None
    assert doc["fabric_view"]["runtime"]["acquisition"]["snapshot_digest"] is None
    index = doc["result_refs"]
    assert index["availability"] == "UNAVAILABLE"
    assert index["refs"] == []
    assert index["absent_job_ids"] == []
    assert index["snapshot_digest"] is None
    assert index["generation"]["state"] == "UNKNOWN"
    assert index["root_job_id"] == job_id
    assert not namespace.active


def test_v3_cancellation_closes_and_propagates(observation_fixture, monkeypatch):
    _, _, runtime, namespace, _, job_id, _ = observation_fixture
    from control_plane import executive_runtime as er

    def interrupt(_read, _root):
        raise KeyboardInterrupt("sample interrupted")

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_job_root_bounded", interrupt)
    with pytest.raises(KeyboardInterrupt, match="sample interrupted"):
        view.read_fabric_view_v3_from_runtime(
            runtime, job_id, armed={}, runtime_identity=_identity(),
        )
    assert not namespace.active
    assert namespace.entries == namespace.exits == 1


def test_v3_nested_v2_preserves_closed_shape_with_frozen_time(observation_fixture, monkeypatch):
    _, _, runtime, _, _, job_id, _ = observation_fixture
    monkeypatch.setattr(view, "_utc_now", lambda: "2020-01-01T00:00:00Z")
    v2 = view.read_fabric_view_v2_from_runtime(runtime, job_id, armed={}, runtime_identity=_identity())
    v3 = view.read_fabric_view_v3_from_runtime(runtime, job_id, armed={}, runtime_identity=_identity())
    nested = v3["fabric_view"]
    assert nested["generated_at"] == v2["generated_at"] == "2020-01-01T00:00:00Z"
    assert nested["schema"] == v2["schema"] == "mastermind.fabric_job_view.v2"
    assert set(nested) == set(v2) == view.OUTPUT_KEYS
    assert "result_refs" not in nested
    assert nested["root"]["job_id"] == v2["root"]["job_id"] == job_id
    assert nested["root"]["acceptance"] == v2["root"]["acceptance"]



@pytest.mark.parametrize("digest", [None, "", "a" * 63, "g" * 64, 7, False, "a" * 64])
def test_v3_reference_coverage_requires_snapshot_digest(digest):
    root = SimpleNamespace(
        job_id="JOB-root", root_job_id="JOB-root", status=JobStatus.QUEUED,
        result=None,
    )
    snapshot = SimpleNamespace(
        root_job_id="JOB-root", jobs=(root,), attempts=(),
        jobs_truncated=False, attempts_truncated_job_ids=(), snapshot_digest=digest,
    )
    generation = {
        "schema": "mastermind.runtime_read_observation.v1", "state": "SAME",
        "source_identity": "a" * 32, "before": 1, "after": 1,
    }
    index = view.compose_fabric_result_reference_index(snapshot, generation)
    if digest == "a" * 64:
        assert index["availability"] == "AVAILABLE"
        assert index["snapshot_digest"] == digest
        assert index["absent_job_ids"] == ["JOB-root"]
        assert index["generation"] == generation
    else:
        assert index["availability"] == "UNAVAILABLE"
        assert index["snapshot_digest"] is None
        assert index["absent_job_ids"] == []
    assert index["refs"] == []


def test_v3_failed_acquisition_retains_unknown_null_digest():
    snapshot = SimpleNamespace(root_job_id="JOB-root", jobs=(), attempts=(), snapshot_digest=None)
    generation = {
        "schema": "mastermind.runtime_read_observation.v1", "state": "UNKNOWN",
        "source_identity": None, "before": None, "after": None,
    }
    assert view.compose_fabric_result_reference_index(snapshot, generation) == {
        "schema": "mastermind.fabric_result_reference_index.v1", "root_job_id": "JOB-root",
        "snapshot_digest": None, "generation": generation, "availability": "UNAVAILABLE",
        "refs": [], "absent_job_ids": [], "omitted_job_ids": [], "truncated": False,
    }


def test_v3_acquired_null_digest_never_produces_refs(bound_max_chain, monkeypatch):
    from control_plane import executive_runtime as er
    _, root, _, _, reader = bound_max_chain
    original = er.BoundedRuntimeReadObservation.read_job_root_bounded

    def omit_digest(read, root_job_id):
        return dataclasses.replace(original(read, root_job_id), snapshot_digest=None)

    monkeypatch.setattr(er.BoundedRuntimeReadObservation, "read_job_root_bounded", omit_digest)
    doc = view.read_fabric_view_v3_from_runtime(reader, root.job_id, armed={}, runtime_identity=_identity())
    index = doc["result_refs"]
    assert index["availability"] == "UNAVAILABLE"
    assert index["snapshot_digest"] is None
    assert index["refs"] == []
    assert index["absent_job_ids"] == []
