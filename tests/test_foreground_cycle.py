"""Finite same-call composition: real source/Runtime/cycle, inert worker finishes.

Nothing here admits a production realm or asserts paid provider execution.
"""
import asyncio
import dataclasses

import pytest

from control_plane import foreground_operation as scope
from control_plane.executive_coo_cycle import CooCycle, CooCycleOutcome
from control_plane.executive_runtime import Runtime, StateConflict, JobStatus
from control_plane.executive_service import ExecutiveControlService, _ForegroundExecution
from control_plane.fabric_attended_routing import AttendedWorkPlacement
from tests.test_executive_service import _config, _FakeSupervisor
from tests.test_foreground_operation import frame, admit
from tests import test_executive_os_phase1fc as roles


def service_at(tmp_path):
    service = ExecutiveControlService(_config(tmp_path),
        supervisor_factory=lambda runtime: _FakeSupervisor(runtime))
    service.runtime = Runtime.at(tmp_path / "runtime")
    # Host-config presence fixture only; production catalogue stays disabled.
    service.config = dataclasses.replace(service.config,
        coo_attended_work_placements=(AttendedWorkPlacement("fixture", "fixture", "fixture"),))
    # These cycle/finisher tests isolate host composition; real eligibility
    # and factory guards are covered in test_foreground_operator_eligibility.
    service._foreground_execution_state = lambda: _ForegroundExecution("ATTENDED_WORK", b"{}")
    return service


@pytest.mark.parametrize("action", ["NO_ACTION", "NO_NEW_WORK", "BLOCKED", "RECONCILIATION_REQUIRED", "UNKNOWN"])
def test_no_progress_returns_once_without_retry(tmp_path, monkeypatch, action):
    async def run():
        s = service_at(tmp_path)
        async with scope._session_bridge_foreground_dispatch(s.runtime, frame(), lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, frame())
                root = receipt["job_id"]
                monkeypatch.setattr(s, "_coo_binding_for_root", lambda _: {"operator_execution_profile_id": "ordinary"})
                calls = []
                async def once(value):
                    calls.append(value)
                    return CooCycleOutcome(root, action, None, None, {"reason": "test"})
                monkeypatch.setattr(s, "_run_coo_cycle", once)
                result = await s._drive_foreground_cycle(op, root)
                assert calls == [root] and result["state"] == action
                assert result["delivery"] == "INCOMPLETE"
        assert s._foreground_cycle_owner is None and not s._coo_action_tasks
    asyncio.run(run())


def test_pre_admission_owner_excludes_other_cycle_before_any_mutation(tmp_path, monkeypatch):
    async def run():
        s = service_at(tmp_path)
        s.config = dataclasses.replace(s.config, coo_autonomy_armed=True)
        monkeypatch.setattr(s, "_require_current_autonomy", lambda: None)
        monkeypatch.setattr(s, "_require_coo_worker_composed", lambda: pytest.fail("foreign cycle entered"))
        async with scope._session_bridge_foreground_dispatch(s.runtime, frame(), lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                assert op._root is None
                task = asyncio.current_task()
                with pytest.raises(StateConflict, match="original"):
                    await asyncio.create_task(s._run_coo_cycle("not-yet-admitted"))
                assert task in s._coo_action_tasks
                assert not s.runtime.jobs.list_jobs()
                assert not s._coo_cycle_lock.locked()
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["missing", "wrong_attempt", "quarantined", "early_finish"])
def test_unsettled_finisher_cannot_report_success(tmp_path, monkeypatch, failure):
    async def run():
        s = service_at(tmp_path)
        async with scope._session_bridge_foreground_dispatch(s.runtime, frame(), lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, frame())
                root = receipt["job_id"]
                planner = s.runtime.jobs.create_cycle_planner(root, command_id=f"coo-cycle:{root}:create-planner:0")
                dispatched = s.runtime.attempts.dispatch_cycle_job(planner.job_id,
                    command_id=f"coo-cycle:{root}:dispatch:{planner.job_id}:attempt:1", worker_id="worker-a")
                payload = dispatched.to_dict()
                if failure == "wrong_attempt": payload["attempt"]["attempt_id"] = "wrong"
                if failure in {"quarantined", "early_finish"}:
                    async def early():
                        if failure == "quarantined": s._service_state = "QUARANTINED"
                    s._dispatch_tasks[planner.job_id] = asyncio.create_task(early())
                result = CooCycleOutcome(root, "DISPATCHED", planner.job_id, "original", payload)
                with pytest.raises(StateConflict):
                    await s._await_foreground_dispatch(op, root, result)
                assert len(s.runtime.attempts.list_attempts()) == 1
    asyncio.run(run())


@pytest.mark.parametrize("edge", ["closed", "cancelled"])
def test_caller_end_requests_exact_cancel_without_cancelling_original_finisher(tmp_path, edge):
    async def run():
        s = service_at(tmp_path)
        f, gate = frame(), asyncio.Event()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                root = receipt["job_id"]
                planner = s.runtime.jobs.create_cycle_planner(root, command_id=f"coo-cycle:{root}:create-planner:0")
                dispatched = s.runtime.attempts.dispatch_cycle_job(planner.job_id,
                    command_id=f"coo-cycle:{root}:dispatch:{planner.job_id}:attempt:1", worker_id="worker-a")
                finisher = asyncio.create_task(gate.wait())
                s._dispatch_tasks[planner.job_id] = finisher
                outcome = CooCycleOutcome(root, "DISPATCHED", planner.job_id, "original", dispatched.to_dict())
                waiting = asyncio.create_task(s._await_foreground_dispatch(op, root, outcome))
                await asyncio.sleep(0)
                if edge == "closed": op._mark_source_closed()
                else: waiting.cancel()
                with pytest.raises((scope.ForegroundOperationClosed, asyncio.CancelledError)):
                    await waiting
                assert not finisher.done()
                assert s.runtime.jobs.get_job(planner.job_id).status is JobStatus.CANCEL_REQUESTED
                gate.set()
                await finisher
    asyncio.run(run())


def test_cancel_keeps_physical_transition_and_slot_until_original_return(tmp_path):
    async def run():
        s = service_at(tmp_path)
        entered, finish, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
        held = []
        async def request():
            async with scope._session_bridge_foreground_dispatch(s.runtime, frame(), lambda: None) as op:
                held.append(op)
                async with s._foreground_cycle_scope(op):
                    async def physical():
                        entered.set()
                        await finish.wait()
                    await s._run_owned_coroutine(physical())
        task = asyncio.create_task(request())
        await entered.wait()
        task.cancel()
        await held[0].wait_closed()
        assert not task.done() and s._foreground_cycle_owner[0] is task
        task.cancel()  # Repeated caller cancellation cannot discard that owner.
        await asyncio.sleep(0)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError): await task
        assert s._foreground_cycle_owner is None and not s._coo_action_tasks
    asyncio.run(run())


@pytest.mark.parametrize("closes_at_terminal", [False, True])
def test_actual_cycle_plan_work_review_aggregation_is_delivered_on_same_call(tmp_path, monkeypatch, closes_at_terminal):
    async def run():
        s, f = service_at(tmp_path), frame()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                root = receipt["job_id"]
                monkeypatch.setattr(s, "_coo_binding_for_root", lambda _: {"operator_execution_profile_id": "ordinary"})
                quota = s.runtime.workers.get_quota_class("worker-a", "codex-hf1q-step")
                s.runtime.workers.register_worker("worker-review", provider="codex",
                    account_label="independent-review", worker_type="mock", capabilities=["read", "research"],
                    quota_classes={"codex-hf1q-step": {"provider": "codex", "capabilities": quota.capabilities,
                        "cost_class": quota.cost_class, "model": quota.model, "effort": quota.effort,
                        "metadata": quota.metadata}})
                data, finishes = {}, []
                async def finish(dispatched):
                    # Simulate the already-owned collector while retaining real
                    # Runtime claim, profile, seal, receipt and result validators.
                    await asyncio.sleep(0)
                    job = s.runtime.jobs.get_job(dispatched.job_id)
                    if job.orchestration_role == "plan":
                        body = {"schema_version": "mastermind.execution_plan/v1", "root_job_id": root,
                            "plan_attempt_id": dispatched.attempt.attempt_id, "steps": [{
                            "ordinal": 0, "step_id": "step-1", "objective": "Read one fact",
                            "business_impact": "routine", "review_required": True,
                            "requested_authorities": ["READ"], "allowed_write_paths": [],
                            "validation_ids": [], "attempt_limit": 1, "cost_class": "small"}]}
                        data["plan"] = body
                    elif job.orchestration_role == "work":
                        body = {"schema_version": "mastermind.work_result/v1", "root_job_id": root,
                            "plan_attempt_id": data["plan"]["plan_attempt_id"],
                            "plan_digest": roles.result_digest(data["plan"]), "plan_step_id": "step-1",
                            "repair_round": 0, "artifacts": [], "evidence_digests": []}
                        data["work"] = dispatched
                    elif job.orchestration_role == "review":
                        body = {"schema_version": "mastermind.review_result/v1", "root_job_id": root,
                            "plan_attempt_id": data["plan"]["plan_attempt_id"],
                            "plan_digest": roles.result_digest(data["plan"]), "plan_step_id": "step-1",
                            "reviewed_job_id": data["work"].job_id,
                            "reviewed_attempt_id": data["work"].attempt.attempt_id,
                            "reviewed_result_digest": data["work_seal"]["role_result_digest"],
                            "repair_round": 0, "verdict": "approve", "evidence_digests": [], "findings": []}
                    else:
                        handoff = s.runtime.jobs.get_cycle_handoff(root)
                        keys = {"ordinal", "plan_step_id", "current_job_id", "current_attempt_id",
                            "current_result_digest", "repair_round", "review_required", "qualifying_review_job_id",
                            "qualifying_review_attempt_id", "qualifying_review_result_digest"}
                        body = {"schema_version": "mastermind.aggregation_result/v1", "root_job_id": root,
                            "handoff_digest": handoff["handoff_digest"], "policy_sha": handoff["policy_sha"],
                            "plan_attempt_id": handoff["plan_attempt_id"], "plan_digest": handoff["plan_digest"],
                            "revisions": [{k: item[k] for k in keys} for item in handoff["revisions"]],
                            "aggregate_summary": "The requested bounded result", "evidence_digests": []}
                    seal, _ = roles._complete_ohf_role(s.runtime, dispatched, body, identity_seed=9100+len(finishes))
                    if job.orchestration_role == "work": data["work_seal"] = seal
                    finishes.append(job.orchestration_role)
                    s._dispatch_tasks.pop(job.job_id)
                    if closes_at_terminal and job.job_id == root:
                        op._mark_source_closed()
                def dispatch(job_id, command):
                    job = s.runtime.jobs.get_job(job_id)
                    worker = "worker-review" if job.orchestration_role == "review" else "worker-a"
                    value = s.runtime.attempts.dispatch_cycle_job(job_id, command_id=command, worker_id=worker)
                    s._dispatch_tasks[job_id] = asyncio.create_task(finish(value))
                    return value
                cycle = CooCycle(s.runtime, dispatcher=dispatch)
                async def once(root_id): return cycle.run_once(root_id)
                monkeypatch.setattr(s, "_run_coo_cycle", once)
                if closes_at_terminal:
                    # Both the original finisher and origin-end are ready. The
                    # dead caller cannot receive more work, but exact terminal
                    # material is retained and no false quarantine/cancel occurs.
                    with pytest.raises(scope.ForegroundOperationClosed):
                        await s._drive_foreground_cycle(op, root)
                    job = s.runtime.jobs.get_job(root)
                    final = s.runtime.validated_role_completion(root, expected_attempt_id=job.current_attempt_id)
                    assert final.result_envelope["role_result"]["aggregate_summary"] == "The requested bounded result"
                    assert s.service_state == "READY" and not s._dispatch_errors
                    assert not [e for e in s.runtime.events.list_events(job_id=root) if e.event_type == "JOB_CANCEL_REQUESTED"]
                else:
                    result = await s._drive_foreground_cycle(op, root)
                    assert result["state"] == "ROOT_COMPLETED", result
                    assert result["delivery"] == "COMPLETE"
                    assert result["results"][-1]["result_envelope"]["role_result"]["aggregate_summary"] == "The requested bounded result"
                assert finishes == ["plan", "work", "review", "aggregation"]
                assert receipt["dispatched"] is False and receipt["duplicate"] is False
                assert len(s.runtime.attempts.list_attempts()) == 4
    asyncio.run(run())


@pytest.mark.parametrize("edge", ["foreign_root", "native_no_child", "repeated_transition"])
def test_invalid_binding_or_nonprogress_never_extends_cycle(tmp_path, monkeypatch, edge):
    from control_plane.executive_runtime import NATIVE_RETURN_TX5_EXECUTION_PROFILE
    async def run():
        s, f = service_at(tmp_path), frame()
        async with scope._session_bridge_foreground_dispatch(s.runtime, f, lambda: None) as op:
            async with s._foreground_cycle_scope(op):
                receipt = await admit(s.runtime, tmp_path, op, f)
                root = receipt["job_id"]
                profile = NATIVE_RETURN_TX5_EXECUTION_PROFILE if edge == "native_no_child" else "ordinary"
                monkeypatch.setattr(s, "_coo_binding_for_root", lambda _: {"operator_execution_profile_id": profile})
                calls = []
                async def once(root_id):
                    calls.append(root_id)
                    return CooCycleOutcome(root, "PLANNER_CREATED", "same", "same", {})
                monkeypatch.setattr(s, "_run_coo_cycle", once)
                with pytest.raises((StateConflict, scope.ForegroundOperationRefusal)):
                    await s._drive_foreground_cycle(op, "foreign" if edge == "foreign_root" else root)
                assert len(calls) == (2 if edge == "repeated_transition" else 0)
                assert not s.runtime.attempts.list_attempts()
    asyncio.run(run())
