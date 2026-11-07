"""Ordinary Operator finite same-call completion on an empty placement set.

Real Runtime plan Job/Attempt and OHF fixture sealing; the physical worker
stays an inert fixture and nothing here claims paid provider execution.
"""
import asyncio
import dataclasses
from types import SimpleNamespace

import pytest

from control_plane import foreground_operation as scope
from control_plane.executive_coo_cycle import CooCycle, CooCycleOutcome
from control_plane.executive_runtime import (
    NATIVE_RETURN_TX5_EXECUTION_PROFILE,
    JobStatus,
    Runtime,
    StateConflict,
)
from control_plane.executive_service import ExecutiveControlService, _canonical_json, _ForegroundExecution
from tests.test_executive_service import _config, _FakeSupervisor
from tests.test_foreground_operation import frame, admit
from tests import test_executive_os_phase1fc as roles


def service_at(tmp_path):
    """Empty attended placements: only the ordinary Operator broker/OHF path."""
    service = ExecutiveControlService(_config(tmp_path),
        supervisor_factory=lambda runtime: _FakeSupervisor(runtime))
    service.runtime = Runtime.at(tmp_path / "runtime")
    # Host-config absence is the Operator-only shape under test here.
    assert service.config.coo_attended_work_placements == ()
    return service


def test_empty_placements_still_reserve_serial_scope_before_admission(tmp_path, monkeypatch):
    async def run():
        s = service_at(tmp_path)
        s.config = dataclasses.replace(s.config, coo_autonomy_armed=True)
        monkeypatch.setattr(s, "_require_current_autonomy", lambda: None)
        monkeypatch.setattr(s, "_require_coo_worker_composed", lambda: pytest.fail("foreign cycle entered"))
        async with scope._session_bridge_foreground_dispatch(s.runtime, frame(), lambda: None) as op:
            async with s._foreground_cycle_scope(op) as drive:
                assert not drive
                assert s._foreground_cycle_owner == (asyncio.current_task(), op)
                assert asyncio.current_task() in s._coo_action_tasks
                # The slot is held before any fresh admission can commit.
                with pytest.raises(scope.ForegroundOperationRefusal) as unbound:
                    await s._run_coo_cycle("not-yet-admitted")
                assert unbound.value.code == "root_unbound"
                # Even an inherited operation context cannot transfer ownership
                # to a competing asyncio task before admission.
                with pytest.raises(StateConflict, match="live original request owner"):
                    await asyncio.create_task(s._run_coo_cycle("not-yet-admitted"))
                assert not s.runtime.jobs.list_jobs()
                assert not s._coo_cycle_lock.locked()
            assert s._foreground_cycle_owner is None and not s._coo_action_tasks
        # A legacy absent operation stays un-driven and never takes the slot.
        async with s._foreground_cycle_scope(None) as drive:
            assert drive is False
        assert s._foreground_cycle_owner is None and not s._coo_action_tasks
    asyncio.run(run())


def test_scope_refuses_a_foreign_operation_source(tmp_path):
    async def run():
        s = service_at(tmp_path)
        async with scope._session_bridge_foreground_dispatch(s.runtime, frame(), lambda: None) as op:
            with pytest.raises(StateConflict, match="original request source"):
                async with s._foreground_cycle_scope("not-the-operation"):
                    pass  # pragma: no cover - the fence refuses before any yield
        assert s._foreground_cycle_owner is None and not s._coo_action_tasks
    asyncio.run(run())


@pytest.mark.parametrize("oversize", [False, True])
def test_operator_plan_completion_returns_finite_result_without_plan_admission(tmp_path, monkeypatch, oversize):
    async def run():
        s, f = service_at(tmp_path), frame()
        # Result-shaping fixture only; real eligibility/factory coverage is separate.
        monkeypatch.setattr(s, "_foreground_execution_state", lambda **kw: _ForegroundExecution("ORDINARY_OPERATOR", b"{}"))
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op) as drive:
                assert bool(drive) is True
                receipt = await admit(s.runtime, tmp_path, op, f)
                root = receipt["job_id"]
                monkeypatch.setattr(s, "_coo_binding_for_root", lambda _: {"operator_execution_profile_id": "ordinary", "operator_harness_armed": True})
                finishes = []
                async def finish(dispatched):
                    # The already-owned collector: real Runtime claim, profile,
                    # seal, receipt and result validators; inert physical worker.
                    await asyncio.sleep(0)
                    job = s.runtime.jobs.get_job(dispatched.job_id)
                    assert job.orchestration_role == "plan"
                    body = {"schema_version": "mastermind.execution_plan/v1", "root_job_id": root,
                        "plan_attempt_id": dispatched.attempt.attempt_id, "steps": [{
                        "ordinal": 0, "step_id": "step-1", "objective": "🧭" * 4096 if oversize else "Read one fact",
                        "business_impact": "routine", "review_required": True,
                        "requested_authorities": ["READ"], "allowed_write_paths": [],
                        "validation_ids": [], "attempt_limit": 1, "cost_class": "small"}]}
                    seal, _ = roles._complete_ohf_role(s.runtime, dispatched, body, identity_seed=7100)
                    finishes.append(job.orchestration_role)
                    s._dispatch_tasks.pop(job.job_id)
                    return seal
                def dispatch(job_id, command):
                    value = s.runtime.attempts.dispatch_cycle_job(job_id, command_id=command, worker_id="worker-a")
                    s._dispatch_tasks[job_id] = asyncio.create_task(finish(value))
                    return value
                cycle = CooCycle(s.runtime, dispatcher=dispatch)
                async def once(root_id):
                    return cycle.run_once(root_id)
                monkeypatch.setattr(s, "_run_coo_cycle", once)
                result = await s._drive_foreground_cycle(op, root)
                assert result["state"] == "OPERATOR_COMPLETED", result
                assert result["root_job_id"] == root
                current = s.runtime.jobs.get_job(root)
                assert result["root_status"] == current.status.value == JobStatus.QUEUED.value
                assert result["delivery"] == "INCOMPLETE"
                assert result["operator_delivery"] == ("RESULT_TOO_LARGE" if oversize else "COMPLETE")
                completion = result["operator_completion"]
                planner = [job for job in s.runtime.jobs.list_jobs() if job.job_id != root][0]
                assert completion["job_id"] == planner.job_id
                assert completion["attempt_id"] == planner.current_attempt_id
                assert completion["role"] == "plan"
                material = s.runtime.validated_role_completion(
                    planner.job_id, expected_attempt_id=planner.current_attempt_id)
                assert completion["result_digest"] == material.result_digest
                assert completion["role_result_digest"] == material.role_result_digest
                assert set(completion) == {"job_id", "attempt_id", "role",
                    "result_digest", "role_result_digest"} | (set() if oversize else {"result_envelope"})
                if oversize:
                    assert len(_canonical_json(material.result_envelope)) > 16384
                    assert "result_envelope" not in completion
                else:
                    assert completion["result_envelope"] == material.result_envelope
                assert len(_canonical_json(result)) <= 16384
                # The root stays open: no plan admission, work creation or
                # second dispatch may follow on this same call.
                assert len(s.runtime.attempts.list_attempts()) == 1
                assert finishes == ["plan"] and s._dispatch_tasks == {}
                assert not [event for event in s.runtime.events.list_events(job_id=root)
                            if event.event_type == "COO_PLAN_ADMITTED"]
                children = [job for job in s.runtime.jobs.list_jobs() if job.parent_job_id == root]
                assert [job.orchestration_role for job in children] == ["plan"]
                assert current.status is JobStatus.QUEUED and current.attempt_count == 0
                assert receipt["dispatched"] is False and receipt["duplicate"] is False
        assert s._foreground_cycle_owner is None and not s._coo_action_tasks
    asyncio.run(run())


def test_oversize_operator_completion_keeps_identities_and_omits_envelope(tmp_path):
    async def run():
        s, f = service_at(tmp_path), frame()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                root = receipt["job_id"]
                material = SimpleNamespace(
                    job=SimpleNamespace(job_id="planner-job", orchestration_role="plan"),
                    attempt=SimpleNamespace(attempt_id="planner-attempt"),
                    result_digest="a" * 64, role_result_digest="b" * 64,
                    result_envelope={"schema_version": "mastermind.role_result/v1",
                                     "role_result": {"objective": "x" * 40000}})
                value = s._operator_plan_completion(root, material)
                assert value["state"] == "OPERATOR_COMPLETED"
                assert value["root_job_id"] == root
                assert value["root_status"] == JobStatus.QUEUED.value
                assert value["delivery"] == "INCOMPLETE"
                assert value["operator_delivery"] == "RESULT_TOO_LARGE"
                assert value["operator_completion"] == {
                    "job_id": "planner-job", "attempt_id": "planner-attempt",
                    "role": "plan", "result_digest": "a" * 64,
                    "role_result_digest": "b" * 64}
                assert len(_canonical_json(value)) <= 16384
                # A bounded exact envelope is still delivered complete.
                material.result_envelope = {"schema_version": "mastermind.role_result/v1"}
                exact = s._operator_plan_completion(root, material)
                assert exact["operator_delivery"] == "COMPLETE"
                assert exact["operator_completion"]["result_envelope"] == material.result_envelope
                assert len(_canonical_json(exact)) <= 16384
        assert s._foreground_cycle_owner is None and not s._coo_action_tasks
    asyncio.run(run())


def test_duplicate_replay_never_drives_or_extends_operator_cycle(tmp_path):
    async def run():
        s, f = service_at(tmp_path), frame()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                assert receipt["duplicate"] is False and receipt["dispatched"] is False
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as replay_op:
            async with s._foreground_cycle_scope(replay_op):
                replay = await admit(s.runtime, tmp_path, replay_op, f)
                assert replay["duplicate"] is True and replay_op._root is None
                with pytest.raises(scope.ForegroundOperationRefusal) as refused:
                    replay_op.require_root(receipt["job_id"])
                assert refused.value.code == "root_unbound"
        assert len(s.runtime.jobs.list_jobs()) == 1
        assert s.runtime.attempts.list_attempts() == []
        assert s._foreground_cycle_owner is None and not s._coo_action_tasks
    asyncio.run(run())


def test_drive_refuses_without_original_request_ownership(tmp_path):
    async def run():
        s, f = service_at(tmp_path), frame()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                root = receipt["job_id"]
        with pytest.raises(StateConflict, match="not owned by this request"):
            await s._drive_foreground_cycle(op, root)
        assert len(s.runtime.jobs.list_jobs()) == 1
    asyncio.run(run())


@pytest.mark.parametrize("edge", ["native_no_child", "foreign_root"])
def test_native_profile_and_foreign_root_never_extend_operator_cycle(tmp_path, monkeypatch, edge):
    async def run():
        s, f = service_at(tmp_path), frame()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                root = receipt["job_id"]
                if edge == "native_no_child":
                    profile = NATIVE_RETURN_TX5_EXECUTION_PROFILE
                    monkeypatch.setattr(s, "_coo_binding_for_root",
                        lambda _: {"operator_execution_profile_id": profile})
                    with pytest.raises(StateConflict, match="native no-child return profile"):
                        await s._drive_foreground_cycle(op, root)
                else:
                    monkeypatch.setattr(s, "_coo_binding_for_root", lambda _: {"operator_execution_profile_id": "ordinary", "operator_harness_armed": True})
                    calls = []
                    async def once(root_id):
                        calls.append(root_id)
                        return CooCycleOutcome("foreign-root", "NO_ACTION", None, None, {})
                    monkeypatch.setattr(s, "_run_coo_cycle", once)
                    with pytest.raises(StateConflict, match="foreign root"):
                        await s._drive_foreground_cycle(op, root)
                    assert calls == [root]
                assert not s.runtime.attempts.list_attempts()
                assert len(s.runtime.jobs.list_jobs()) == 1
        assert s._foreground_cycle_owner is None and not s._coo_action_tasks
    asyncio.run(run())


def test_expired_source_deadline_refuses_before_any_cycle(tmp_path, monkeypatch):
    async def run():
        s, f = service_at(tmp_path), frame()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                real_time = scope.time.time
                monkeypatch.setattr(scope.time, "time", lambda: real_time() + 10000)
                calls = []
                async def once(root_id):
                    calls.append(root_id)
                    return CooCycleOutcome(root_id, "NO_ACTION", None, None, {})
                monkeypatch.setattr(s, "_run_coo_cycle", once)
                with pytest.raises(scope.ForegroundOperationRefusal) as refused:
                    await s._drive_foreground_cycle(op, receipt["job_id"])
                assert refused.value.code == "principal_not_live"
                assert calls == []
        assert len(s.runtime.jobs.list_jobs()) == 1
    asyncio.run(run())


def test_malformed_plan_seal_never_reports_operator_completion(tmp_path, monkeypatch):
    async def run():
        s, f = service_at(tmp_path), frame()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                root = receipt["job_id"]
                monkeypatch.setattr(s, "_coo_binding_for_root", lambda _: {"operator_execution_profile_id": "ordinary", "operator_harness_armed": True})
                async def finish(dispatched):
                    await asyncio.sleep(0)
                    job = s.runtime.jobs.get_job(dispatched.job_id)
                    body = {"schema_version": "mastermind.execution_plan/v9", "root_job_id": root,
                        "plan_attempt_id": dispatched.attempt.attempt_id, "steps": []}
                    seal, _ = roles._complete_ohf_role(s.runtime, dispatched, body, identity_seed=7200)
                    s._dispatch_tasks.pop(job.job_id)
                    return seal
                def dispatch(job_id, command):
                    value = s.runtime.attempts.dispatch_cycle_job(job_id, command_id=command, worker_id="worker-a")
                    s._dispatch_tasks[job_id] = asyncio.create_task(finish(value))
                    return value
                cycle = CooCycle(s.runtime, dispatcher=dispatch)
                async def once(root_id):
                    return cycle.run_once(root_id)
                monkeypatch.setattr(s, "_run_coo_cycle", once)
                with pytest.raises(Exception):
                    await s._drive_foreground_cycle(op, root)
                planner = [job for job in s.runtime.jobs.list_jobs() if job.parent_job_id == root][0]
                with pytest.raises(StateConflict):
                    s.runtime.validated_role_completion(
                        planner.job_id, expected_attempt_id=planner.current_attempt_id)
                assert not [event for event in s.runtime.events.list_events(job_id=root)
                            if event.event_type == "COO_PLAN_ADMITTED"]
                assert len(s.runtime.attempts.list_attempts()) == 1
                assert s.runtime.jobs.get_job(root).status is JobStatus.QUEUED
                assert s.service_state == "READY" and not s._dispatch_errors
    asyncio.run(run())


def test_quarantined_service_never_reports_operator_completion(tmp_path, monkeypatch):
    async def run():
        s, f = service_at(tmp_path), frame()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                root = receipt["job_id"]
                monkeypatch.setattr(s, "_coo_binding_for_root", lambda _: {"operator_execution_profile_id": "ordinary", "operator_harness_armed": True})
                async def finish(dispatched):
                    await asyncio.sleep(0)
                    job = s.runtime.jobs.get_job(dispatched.job_id)
                    body = {"schema_version": "mastermind.execution_plan/v1", "root_job_id": root,
                        "plan_attempt_id": dispatched.attempt.attempt_id, "steps": [{
                        "ordinal": 0, "step_id": "step-1", "objective": "Read one fact",
                        "business_impact": "routine", "review_required": True,
                        "requested_authorities": ["READ"], "allowed_write_paths": [],
                        "validation_ids": [], "attempt_limit": 1, "cost_class": "small"}]}
                    seal, _ = roles._complete_ohf_role(s.runtime, dispatched, body, identity_seed=7300)
                    s._dispatch_tasks.pop(job.job_id)
                    return seal
                def dispatch(job_id, command):
                    value = s.runtime.attempts.dispatch_cycle_job(job_id, command_id=command, worker_id="worker-a")
                    s._dispatch_tasks[job_id] = asyncio.create_task(finish(value))
                    return value
                cycle = CooCycle(s.runtime, dispatcher=dispatch)
                async def once(root_id):
                    return cycle.run_once(root_id)
                monkeypatch.setattr(s, "_run_coo_cycle", once)
                s._service_state = "QUARANTINED"
                with pytest.raises(StateConflict, match="did not settle"):
                    await s._drive_foreground_cycle(op, root)
                planner = [job for job in s.runtime.jobs.list_jobs() if job.parent_job_id == root][0]
                material = s.runtime.validated_role_completion(
                    planner.job_id, expected_attempt_id=planner.current_attempt_id)
                assert material.result_envelope["role"] == "plan"
                assert not [event for event in s.runtime.events.list_events(job_id=root)
                            if event.event_type == "COO_PLAN_ADMITTED"]
                assert len(s.runtime.attempts.list_attempts()) == 1
                assert s.runtime.jobs.get_job(root).status is JobStatus.QUEUED
    asyncio.run(run())
