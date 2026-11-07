"""Actual Runtime/Supervisor composition, with inert provider/process fixtures."""
import asyncio
import dataclasses

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_runtime import AttemptStatus, JobStatus, StateConflict
from control_plane.executive_supervisor import ActiveRun, ProcessPresence, ReconcileStatus, SupervisorError
from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
from tests.test_executive_supervisor import FakeAdapter, FakeInspector, _runtime_and_job, _supervisor


class Adapter(FakeAdapter):
    adapter_id = "codex-cli"


@pytest.fixture
def composition(tmp_path):
    runtime, first, workspace = _runtime_and_job(tmp_path)
    original = runtime.workers.get_worker("codex-01")
    quota = runtime.workers.get_quota_class("codex-01", "codex-native")
    runtime.workers.register_worker("codex-02", provider=original.provider,
        account_label="other-inert-account", worker_type=original.worker_type,
        capabilities=original.capabilities, quota_classes={"codex-native": {
            "capabilities": quota.capabilities, "model": quota.model,
            "effort": quota.effort, "cost_class": quota.cost_class}})
    a = _supervisor(runtime, tmp_path, Adapter(FakeInspector()))
    b = _supervisor(runtime, tmp_path, Adapter(FakeInspector()))
    mixed = MixedExecutionOwnerSupervisor(a, {"codex-01": a, "codex-02": b})
    second_workspace = workspace.parent / "second"
    second_workspace.mkdir(mode=0o700)
    job = runtime.jobs.get_job(first)
    second = runtime.jobs.create_job("Second independent artifact",
        worktree=str(second_workspace), requested_authorities=job.requested_authorities,
        allowed_write_paths=job.allowed_write_paths, validation_commands=job.validation_commands,
        constraints=job.constraints)
    return runtime, mixed, a, b, first, second.job_id


def test_interleaved_real_claims_finish_with_original_owner(composition):
    runtime, mixed, a, b, first, second = composition
    async def run():
        one = await mixed.start_job(first)
        two = await mixed.start_job(second)
        assert one.lease.attempt.worker_id == "codex-01"
        assert two.lease.attempt.worker_id == "codex-02"
        assert a.adapter.ref == one.process_ref and b.adapter.ref == two.process_ref
        r2 = await mixed.finish_job(two)
        r1 = await mixed.finish_job(one)
        assert r1.job.status is r2.job.status is JobStatus.COMPLETED
        with pytest.raises(SupervisorError, match="original owner"):
            await mixed.finish_job(one)
    asyncio.run(run())


def test_canonical_claimed_replay_without_exact_target_never_restarts(composition, monkeypatch):
    runtime, mixed, a, _b, _first, _second = composition
    runtime.workers.register_worker("cycle-worker", provider="codex",
        account_label="inert-cycle", worker_type="codex-cli", capabilities=["read"],
        quota_classes={"default": {"provider": "codex", "capabilities": ["read"],
                                   "cost_class": "small"}})
    mixed = MixedExecutionOwnerSupervisor(a, {**mixed.owners, "cycle-worker": a})
    root = submit_intent(runtime, {"schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-MIXED-REPLAY", "actor": "ceo-sol", "objective": "Review source",
        "department": "executive-infrastructure", "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {"requested_authorities": ["READ"], "attempt_limit": 2},
        "intent_kind": "executive_coo_cycle", "business_impact": "material"})["job_id"]
    job = runtime.jobs.create_cycle_planner(root, command_id=f"coo-cycle:{root}:create-planner:0")
    starts = []
    async def boundary(job_id, lease, **kwargs):
        starts.append(lease)
        return ActiveRun(lease, None, None)  # Deliberately stop before provider START.
    monkeypatch.setattr(a, "_start_claimed_job", boundary)
    command = f"coo-cycle:{root}:dispatch:{job.job_id}:attempt:1"
    async def run():
        first = await mixed.start_cycle_job(job.job_id, command_id=command)
        replay = await mixed.start_cycle_job(job.job_id, command_id=command)
        assert replay.claimed_now is False
        assert replay.attempt.attempt_id == first.lease.attempt.attempt_id
        assert len(starts) == 1
    asyncio.run(run())


def test_unknown_owner_preserves_original_claim_without_fallback(composition):
    runtime, _mixed, a, b, first, _ = composition
    mixed = MixedExecutionOwnerSupervisor(b, {"codex-02": b})
    with pytest.raises(SupervisorError, match="no exact execution owner"):
        asyncio.run(mixed.start_job(first))
    attempt = runtime.attempts.list_attempts(first)[0]
    assert attempt.status is AttemptStatus.CLAIMED
    assert a.adapter.spec is b.adapter.spec is None


@pytest.mark.parametrize("damage", ["provider", "profile"])
def test_selection_refuses_current_quota_drift(composition, monkeypatch, damage):
    runtime, mixed, _a, _b, first, _ = composition
    lease = runtime.broker.claim(first)
    quota = runtime.workers.get_quota_class(lease.attempt.worker_id, lease.attempt.quota_class)
    if damage == "provider":
        quota = dataclasses.replace(quota, provider="foreign")
    else:
        quota = dataclasses.replace(quota, metadata={"execution_profile_id": "foreign"})
    monkeypatch.setattr(runtime.workers, "get_quota_class", lambda *args: quota)
    with pytest.raises(SupervisorError):
        mixed._select(lease.attempt)


def test_restart_partitions_real_supervisor_before_any_process_probe(composition, monkeypatch):
    runtime, mixed, a, b, first, second = composition
    one = runtime.broker.claim(first)
    two = runtime.broker.claim(second)
    seen = {a: [], b: []}
    for owner in (a, b):
        def presence(attempt, owner=owner):
            seen[owner].append(attempt.attempt_id)
            return ProcessPresence.UNKNOWN
        monkeypatch.setattr(owner.process_controller, "presence", presence)
    before = runtime.attempts.list_attempts()
    receipts = mixed.reconcile_restart()
    assert seen[a] == [one.attempt.attempt_id]
    assert seen[b] == [two.attempt.attempt_id]
    assert all(r.status is ReconcileStatus.IDENTITY_AMBIGUOUS for r in receipts)
    assert runtime.attempts.list_attempts() == before


def test_unknown_restart_owner_never_probes_or_changes_rows(composition, monkeypatch):
    runtime, _mixed, a, b, first, _ = composition
    lease = runtime.broker.claim(first)
    mixed = MixedExecutionOwnerSupervisor(b, {"codex-02": b})
    def forbidden(*args):
        raise AssertionError("foreign owner probe")
    for owner in (a, b):
        monkeypatch.setattr(owner.process_controller, "presence", forbidden)
    receipt, = mixed.reconcile_restart()
    assert receipt.status is ReconcileStatus.IDENTITY_AMBIGUOUS
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id) == lease.attempt


def test_recovered_runs_keep_exact_owner_and_drain_once(composition):
    _runtime, mixed, a, b, first, second = composition
    one, two = asyncio.run(_start_pair(mixed, first, second))
    # A restart composes a fresh facade; each existing owner supplies its own
    # canonical recovered ActiveRun. No new claim or START occurs here.
    recovered = MixedExecutionOwnerSupervisor(a, {"codex-01": a, "codex-02": b})
    a._recovered_runs[one.lease.attempt.attempt_id] = one
    b._recovered_runs[two.lease.attempt.attempt_id] = two
    assert recovered.take_recovered_runs() == (one, two)
    assert recovered.take_recovered_runs() == ()


async def _start_pair(mixed, first, second):
    return await mixed.start_job(first), await mixed.start_job(second)


def test_empty_restart_scope_does_not_probe_anything(composition, monkeypatch):
    runtime, _mixed, a, _b, first, _ = composition
    runtime.broker.claim(first)
    monkeypatch.setattr(a.process_controller, "presence", lambda _: pytest.fail("unexpected probe"))
    assert a.reconcile_restart(attempt_ids=frozenset()) == []
    with pytest.raises(SupervisorError, match="exact Attempt"):
        a.reconcile_restart(attempt_ids=["caller-list"])


def test_different_service_instance_is_not_an_execution_owner(composition):
    _runtime, _mixed, a, b, _first, _second = composition
    b.instance_id = "foreign-service"
    with pytest.raises(SupervisorError, match="service instance"):
        MixedExecutionOwnerSupervisor(a, {"codex-01": a, "codex-02": b})


def test_exact_cancel_is_atomic_and_idempotent(composition):
    runtime, _mixed, _a, _b, first, _ = composition
    lease = runtime.broker.claim(first)
    kwargs = dict(expected_attempt_id=lease.attempt.attempt_id,
                  expected_fence_generation=lease.attempt.fence_generation)
    result = runtime.jobs.cancel_job(first, **kwargs)
    assert result.status is JobStatus.CANCEL_REQUESTED
    events = runtime.events.list_events(job_id=first)
    assert runtime.jobs.cancel_job(first, **kwargs) == result
    assert runtime.events.list_events(job_id=first) == events


@pytest.mark.parametrize("damage", ["fence", "attempt", "missing-fence", "bool-fence"])
def test_exact_cancel_refuses_wrong_or_incomplete_identity(composition, damage):
    runtime, _mixed, _a, _b, first, _ = composition
    lease = runtime.broker.claim(first)
    kwargs = dict(expected_attempt_id=lease.attempt.attempt_id,
                  expected_fence_generation=lease.attempt.fence_generation)
    if damage == "fence": kwargs["expected_fence_generation"] += 1
    if damage == "attempt": kwargs["expected_attempt_id"] = "foreign-attempt"
    if damage == "missing-fence": kwargs.pop("expected_fence_generation")
    if damage == "bool-fence": kwargs["expected_fence_generation"] = True
    before = runtime.jobs.get_job(first), runtime.events.list_events(job_id=first)
    with pytest.raises(StateConflict):
        runtime.jobs.cancel_job(first, **kwargs)
    assert (runtime.jobs.get_job(first), runtime.events.list_events(job_id=first)) == before


def test_exact_cancel_terminal_wins_and_never_cancels_successor(composition):
    runtime, mixed, a, _b, first, _ = composition
    a.adapter.output_status = "FAILED"
    async def run():
        original = await mixed.start_job(first)
        terminal = await mixed.finish_job(original)
        return original, terminal
    original, terminal = asyncio.run(run())
    assert terminal.job.status is JobStatus.FAILED
    kwargs = dict(expected_attempt_id=original.lease.attempt.attempt_id,
                  expected_fence_generation=original.lease.attempt.fence_generation)
    events = runtime.events.list_events(job_id=first)
    assert runtime.jobs.cancel_job(first, **kwargs) == terminal.job
    assert runtime.events.list_events(job_id=first) == events
    runtime.jobs.requeue_job(first)
    successor = runtime.broker.claim(first)
    with pytest.raises(StateConflict, match="Attempt or fence changed"):
        runtime.jobs.cancel_job(first, **kwargs)
    assert runtime.attempts.get_attempt(successor.attempt.attempt_id) == successor.attempt


class InertOriginSignal:
    """Consumer-only fixture; never evidence of authenticated origin/START."""
    def __init__(self, *, fail=False):
        self.closed = asyncio.Event()
        self.fail = fail

    def require_root(self, root):
        assert not self.closed.is_set()

    async def wait_closed(self):
        await self.closed.wait()
        if self.fail:
            raise RuntimeError("origin transport observation failed")


@pytest.mark.parametrize("phase", ["between-start-finish", "during-collection", "caller-cancel", "observer-failure"])
def test_origin_loss_retains_exact_real_finisher(composition, monkeypatch, phase):
    runtime, mixed, a, _b, first, _ = composition
    async def run():
        signal = InertOriginSignal(fail=phase == "observer-failure")
        monkeypatch.setattr(mixed, "_foreground", lambda _: signal)
        gate, collecting = asyncio.Event(), asyncio.Event()
        collect, cancel = a.adapter.collect_result, a.adapter.cancel
        calls = []
        async def held_collect(ref):
            calls.append("collect")
            collecting.set()
            await gate.wait()
            return await collect(ref)
        async def observed_cancel(ref, reason):
            calls.append("cancel")
            await cancel(ref, reason)
            gate.set()
        monkeypatch.setattr(a.adapter, "collect_result", held_collect)
        monkeypatch.setattr(a.adapter, "cancel", observed_cancel)
        active = await mixed.start_job(first)
        if phase == "between-start-finish":
            signal.closed.set()
            await asyncio.sleep(0)
            assert runtime.jobs.get_job(first).status is JobStatus.CANCEL_REQUESTED
        finishing = asyncio.create_task(mixed.finish_job(active))
        await collecting.wait()
        if phase in {"during-collection", "observer-failure"}: signal.closed.set()
        if phase == "caller-cancel": finishing.cancel()
        if phase == "caller-cancel":
            with pytest.raises(asyncio.CancelledError): await finishing
        elif phase == "observer-failure":
            with pytest.raises(SupervisorError, match="cancellation remains unresolved"):
                await finishing
        else:
            receipt = await finishing
            assert receipt.job.status is JobStatus.CANCELLED
        assert runtime.jobs.get_job(first).status is JobStatus.CANCELLED
        assert calls == ["collect", "cancel"]
        assert not mixed._active
    asyncio.run(asyncio.wait_for(run(), timeout=5))


def test_caller_cancel_during_start_keeps_original_launch_owner(composition, monkeypatch):
    runtime, mixed, a, _b, first, _ = composition
    async def run():
        signal = InertOriginSignal()
        monkeypatch.setattr(mixed, "_foreground", lambda _: signal)
        entered, gate = asyncio.Event(), asyncio.Event()
        start = a.adapter.start
        calls = []
        async def held_start(spec):
            calls.append("start")
            entered.set()
            await gate.wait()
            return await start(spec)
        monkeypatch.setattr(a.adapter, "start", held_start)
        starting = asyncio.create_task(mixed.start_job(first))
        await entered.wait()
        starting.cancel()
        await asyncio.sleep(0)
        assert runtime.jobs.get_job(first).status is JobStatus.CANCEL_REQUESTED
        gate.set()
        # The real Supervisor retains launch/persistence cleanup. Depending on
        # where cancel wins, it may report that exact launch failure to caller.
        with pytest.raises((asyncio.CancelledError, SupervisorError)):
            await starting
        assert calls == ["start"]
        assert not a.adapter.inspector.live
        assert not mixed._active
    asyncio.run(asyncio.wait_for(run(), timeout=5))


def test_database_cancel_failure_cannot_be_swallowed_by_monitor(composition, monkeypatch):
    import sqlite3
    runtime, mixed, _a, _b, first, _ = composition
    async def run():
        signal = InertOriginSignal()
        monkeypatch.setattr(mixed, "_foreground", lambda _: signal)
        active = await mixed.start_job(first)
        def refused(*args, **kwargs):
            raise sqlite3.OperationalError("inert storage failure")
        monkeypatch.setattr(runtime.jobs, "cancel_job", refused)
        custody = mixed._active[active.lease.attempt.attempt_id][2]
        signal.closed.set()
        await custody.monitor
        with pytest.raises(SupervisorError, match="cancellation remains unresolved"):
            await mixed.finish_job(active)
    asyncio.run(run())


def test_recovered_batch_drift_retains_every_original_handle(composition, monkeypatch):
    runtime, mixed, a, b, first, second = composition
    one, two = asyncio.run(_start_pair(mixed, first, second))
    recovered = MixedExecutionOwnerSupervisor(a, {"codex-01": a, "codex-02": b})
    a._recovered_runs[one.lease.attempt.attempt_id] = one
    b._recovered_runs[two.lease.attempt.attempt_id] = two
    original = runtime.workers.get_quota_class
    def drift(worker, quota):
        value = original(worker, quota)
        return dataclasses.replace(value, metadata={"execution_profile_id": "changed"}) if worker == "codex-02" else value
    with monkeypatch.context() as patch:
        patch.setattr(runtime.workers, "get_quota_class", drift)
        with pytest.raises(SupervisorError, match="profile drifted"):
            recovered.take_recovered_runs()
    assert len(recovered._pending_recovery) == 2 and recovered._active == {}
    assert recovered.take_recovered_runs() == (one, two)
    assert recovered.take_recovered_runs() == ()


def test_same_lease_cannot_cross_start_twice(composition, monkeypatch):
    _runtime, mixed, a, _b, first, _ = composition
    async def run():
        active = await mixed.start_job(first)
        async def forbidden(*args, **kwargs): pytest.fail("duplicate START")
        monkeypatch.setattr(a, "_start_claimed_job", forbidden)
        with pytest.raises(SupervisorError, match="already has a launch"):
            await mixed._start(a, first, active.lease, None)
    asyncio.run(run())


def test_failed_finisher_retains_handle_without_authorizing_collection_replay(composition, monkeypatch):
    _runtime, mixed, a, _b, first, _ = composition
    async def run():
        active = await mixed.start_job(first)
        async def refused(*args): raise RuntimeError("original collection is uncertain")
        monkeypatch.setattr(a, "finish_job", refused)
        with pytest.raises(RuntimeError, match="collection is uncertain"):
            await mixed.finish_job(active)
        assert mixed._unsettled[active.lease.attempt.attempt_id] == (a, active)
        with pytest.raises(SupervisorError, match="original owner"):
            await mixed.finish_job(active)
    asyncio.run(run())


@pytest.mark.parametrize("order", ["service-first", "custody-first", "terminal-first"])
def test_foreground_review_cancel_race_uses_one_idempotent_runtime_transition(composition, tmp_path, monkeypatch, order):
    """Falsify review D1 against the actual cancel, Supervisor and service finisher."""
    from control_plane.executive_service import ExecutiveControlService
    from tests.test_executive_service import _config
    runtime, mixed, a, _b, first, _ = composition
    async def run():
        service = ExecutiveControlService(_config(tmp_path / "service"),
            supervisor_factory=lambda _: mixed)
        service.runtime, service.supervisor = runtime, mixed
        signal = InertOriginSignal()
        monkeypatch.setattr(mixed, "_foreground", lambda _: signal)
        gate, collecting = asyncio.Event(), asyncio.Event()
        collect, cancel = a.adapter.collect_result, a.adapter.cancel
        async def held_collect(ref):
            collecting.set()
            await gate.wait()
            return await collect(ref)
        async def observed_cancel(ref, reason):
            await cancel(ref, reason)
            gate.set()
        monkeypatch.setattr(a.adapter, "collect_result", held_collect)
        monkeypatch.setattr(a.adapter, "cancel", observed_cancel)
        active = await mixed.start_job(first)
        attempt = active.lease.attempt
        custody = mixed._active[attempt.attempt_id][2]
        exact = dict(expected_attempt_id=attempt.attempt_id,
                     expected_fence_generation=attempt.fence_generation)
        finishing = asyncio.create_task(service._finish_dispatched(first, active))
        service._dispatch_tasks[first] = finishing
        await collecting.wait()
        if order == "terminal-first":
            gate.set()
            await finishing
            before = runtime.events.list_events(job_id=first)
            signal.closed.set()
            runtime.jobs.cancel_job(first, **exact)
            custody.request_cancel()
            assert runtime.events.list_events(job_id=first) == before
        else:
            if order == "service-first": runtime.jobs.cancel_job(first, **exact)
            signal.closed.set()
            await custody.monitor
            if order == "custody-first": runtime.jobs.cancel_job(first, **exact)
            await finishing
        assert custody.error is None
        assert runtime.attempts.get_attempt(attempt.attempt_id).fence_generation == attempt.fence_generation
        assert service.service_state == "READY" and not service._dispatch_errors
        assert not mixed._active and first not in service._dispatch_tasks
        events = [e for e in runtime.events.list_events(job_id=first) if e.event_type == "JOB_CANCEL_REQUESTED"]
        assert len(events) == (0 if order == "terminal-first" else 1)
        assert runtime.jobs.get_job(first).status is (JobStatus.COMPLETED if order == "terminal-first" else JobStatus.CANCELLED)
    asyncio.run(asyncio.wait_for(run(), 5))
