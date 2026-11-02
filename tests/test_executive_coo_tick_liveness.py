"""Real-service, model-free proof of bounded pre-start queue liveness."""
from __future__ import annotations

import asyncio
import dataclasses
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from control_plane.executive_runtime import JobPayload
from control_plane.executive_service import ExecutiveControlService
from control_plane.executive_supervisor import NoEligibleWorkerCapacity
from test_executive_service import (
    _FakeSupervisor, _config, _coo_intent, _request, _service,
)


@asynccontextmanager
async def _prepared_pair(tmp_path):
    # Seed via the existing admitted service before enabling a short tick.
    # This prevents setup speed from racing the liveness assertion.
    with tempfile.TemporaryDirectory(prefix="mmx-tick-") as socket_dir:
        config = _config(tmp_path, socket_root=Path(socket_dir),
                         coo_autonomy_armed=True, coo_tick_interval_seconds=3600.0)
        service, _ = _service(tmp_path, config=config, finish_gate=asyncio.Event())
        await service.start()
        try:
            assert (await _request(service, "register-worker"))["ok"] is True
            intents = [_coo_intent(config, "poison-first"),
                       _coo_intent(config, "healthy-second")]
            intents[1]["priority"] = 8
            ids = []
            for intent in intents:
                result = await _request(service, "submit-ceo-intent", {"intent": intent})
                assert result["ok"] is True, result
                ids.append(result["result"]["job_id"])
            paths = [Path(x["execution_contract"]["worktree"]) for x in intents]
            assert all(p.parent == config.proof_workspace_root for p in paths)
            yield config, service, ids, paths
        finally:
            if not service._closing:
                await service.close()


def _children(service, root_id):
    return [j for j in service.runtime.jobs.list_jobs() if j.parent_job_id == root_id]


async def _until(predicate, timeout=5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.05)
    return predicate()


def test_background_tick_drains_healthy_root_after_restart_with_missing_prestart_workspace(tmp_path):
    async def exercise():
        async with _prepared_pair(tmp_path) as (config, seed, ids, paths):
            await seed.close()
            unavailable = paths[0].with_name(paths[0].name + "-unavailable")
            paths[0].rename(unavailable)
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=1.0), finish_gate=asyncio.Event())
            await running.start()
            try:
                # No explicit cycle/dispatch/continue after this service starts.
                assert await _until(lambda: bool(_children(running, ids[1]))), {
                    "last_error": running._coo_last_error,
                    "last_tick": running._coo_last_tick_at,
                }
                assert running.service_state == "READY"
                assert _children(running, ids[0]) == []
                assert running.runtime.jobs.get_job(ids[0]).attempt_count == 0
                events = running.runtime.events.list_events(job_id=ids[0])
                assert sum(x.event_type == "COO_SERVICE_TICK_REFUSED" for x in events) == 1
                assert not any(x.event_type == "COO_CYCLE_BLOCKED" for x in events)
            finally:
                unavailable.rename(paths[0])
                await running.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("damage", ["missing", "dirty"])
def test_selector_defers_only_unstarted_unusable_root_and_recovers_from_current_input(tmp_path, damage):
    async def exercise():
        async with _prepared_pair(tmp_path) as (_, service, ids, paths):
            assert service._next_bound_coo_root() == ids[0]
            unavailable = paths[0].with_name(paths[0].name + "-unavailable")
            marker = paths[0] / "uncommitted-test-input"
            if damage == "missing":
                paths[0].rename(unavailable)
            else:
                marker.write_text("fixture only\n")
            try:
                assert service._next_bound_coo_root() == ids[1]
                assert all(service.runtime.jobs.get_job(i).attempt_count == 0 for i in ids)
                assert all(_children(service, i) == [] for i in ids)
            finally:
                if damage == "missing":
                    unavailable.rename(paths[0])
                else:
                    marker.unlink()
            # No requeue, unblocking command, cache reset or new admission.
            assert service._next_bound_coo_root() == ids[0]
    asyncio.run(exercise())


def test_existing_child_keeps_exact_root_reconciliation_priority_even_if_workspace_disappears(tmp_path):
    async def exercise():
        async with _prepared_pair(tmp_path) as (_, service, ids, paths):
            created = await _request(service, "run-coo-cycle", {"root_job_id": ids[0]})
            assert created["ok"] is True, created
            assert _children(service, ids[0])
            unavailable = paths[0].with_name(paths[0].name + "-unavailable")
            paths[0].rename(unavailable)
            try:
                assert service._next_bound_coo_root() == ids[0]
                assert _children(service, ids[1]) == []
            finally:
                unavailable.rename(paths[0])
    asyncio.run(exercise())


def test_disarmed_background_tick_does_not_advance_either_admitted_root(tmp_path):
    async def exercise():
        async with _prepared_pair(tmp_path) as (config, seed, ids, _):
            await seed.close()
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_autonomy_armed=False, coo_tick_interval_seconds=1.0))
            await running.start()
            try:
                await asyncio.sleep(1.2)
                assert all(_children(running, i) == [] for i in ids)
                assert running._coo_last_tick_at is None
            finally:
                await running.close()
    asyncio.run(exercise())


def test_ambiguous_claimed_start_quarantines_instead_of_draining_another_root(tmp_path):
    class LostStartReceipt(_FakeSupervisor):
        async def start_cycle_job(self, job_id, *, command_id):
            await super().start_cycle_job(job_id, command_id=command_id)
            raise RuntimeError("fixture lost response after durable claim")

    async def exercise():
        async with _prepared_pair(tmp_path) as (config, seed, ids, _):
            await seed.close()
            # The source fixture defaults to a 0.1s shutdown grace but this
            # test explicitly enables a 1.0s background tick. Linux CI may
            # legitimately retain that physical tick past 0.1s; the service
            # must not lie that its process/cycle custody drained. Give THIS
            # synthetic test enough grace for one wake/settlement, without
            # changing the production shutdown guard or retry policy.
            tick_interval = 1.0
            shutdown_grace = 3.0
            assert shutdown_grace > tick_interval
            running = ExecutiveControlService(dataclasses.replace(
                config, coo_tick_interval_seconds=tick_interval,
                shutdown_grace_seconds=shutdown_grace),
                supervisor_factory=LostStartReceipt, autonomy_guard=lambda: None)
            await running.start()
            try:
                assert await _until(lambda: running.service_state == "QUARANTINED")
                assert _children(running, ids[1]) == []
                attempted = _children(running, ids[0])
                assert len(attempted) == 1
                assert attempted[0].attempt_count == 1
            finally:
                await running.close()
    asyncio.run(exercise())


def test_background_tick_rechecks_restored_workspace_without_manual_continue(tmp_path):
    async def exercise():
        async with _prepared_pair(tmp_path) as (config, seed, ids, paths):
            await seed.close()
            hidden = [p.with_name(p.name + "-unavailable") for p in paths]
            for source, target in zip(paths, hidden):
                source.rename(target)
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=1.0), finish_gate=asyncio.Event())
            await running.start()
            try:
                assert await _until(lambda: running._coo_last_tick_at is not None)
                assert all(_children(running, i) == [] for i in ids)
                hidden[1].rename(paths[1])
                # Only an external input becomes available. No Runtime mutation,
                # command, cache clear or manual cycle is used to wake the work.
                assert await _until(lambda: bool(_children(running, ids[1]))), {
                    "last_error": running._coo_last_error,
                    "last_tick": running._coo_last_tick_at,
                }
                assert _children(running, ids[0]) == []
                assert running.service_state == "READY"
            finally:
                for source, target in zip(hidden, paths):
                    if source.exists():
                        source.rename(target)
                await running.close()
    asyncio.run(exercise())


class _LostStartReceipt(_FakeSupervisor):
    """Loses the dispatch response after the durable claim is committed."""

    async def start_cycle_job(self, job_id, *, command_id):
        await super().start_cycle_job(job_id, command_id=command_id)
        raise RuntimeError("fixture lost response after durable claim")


class _CapacityBlockedSupervisor(_FakeSupervisor):
    """Can never dispatch the named job, so that root can never act."""

    blocked_job_id: str | None = None

    async def start_cycle_job(self, job_id, *, command_id):
        if job_id == self.blocked_job_id:
            raise NoEligibleWorkerCapacity(job_id)
        return await super().start_cycle_job(job_id, command_id=command_id)


def _raw_events(service, root_id):
    """Read one root's persisted events byte for byte."""
    with service.runtime.store.read() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM events WHERE job_id=? ORDER BY event_id",
                (root_id,),
            ).fetchall()
        ]


def _subtree_facts(service, root_id):
    """Read one root's whole subtree as comparable facts."""
    return sorted(
        (
            job.job_id,
            job.status.value,
            job.attempt_count,
            job.current_attempt_id,
            job.parent_job_id,
        )
        for job in service.runtime.jobs.list_jobs()
        if job.root_job_id == root_id
    )


async def _seal_failed_planner(service, root_id):
    """Give one root a planner child whose claim is already settled.

    The claim is terminal, so the runtime holds no unowned active Attempt and
    the root keeps its lawful reconciliation path.
    """
    created = await _request(service, "run-coo-cycle", {"root_job_id": root_id})
    assert created["ok"] is True, created
    planner = _children(service, root_id)[0]
    runtime = service.runtime
    command = f"coo-cycle:{root_id}:dispatch:{planner.job_id}:attempt:1"
    outcome = runtime.attempts.dispatch_cycle_job(
        planner.job_id, command_id=command, lease_owner="fixture-marker")
    assert outcome is not None and outcome.lease_token is not None
    payload = JobPayload(
        summary="fixture work complete",
        completed_steps=["fixture"],
        current_state="complete",
    )
    runtime.attempts.checkpoint_attempt(
        outcome.attempt.attempt_id,
        fence_generation=outcome.attempt.fence_generation,
        lease_token=outcome.lease_token,
        payload=payload,
    )
    runtime.attempts.fail_attempt(
        outcome.attempt.attempt_id,
        fence_generation=outcome.attempt.fence_generation,
        lease_token=outcome.lease_token,
        payload=payload,
    )
    return planner, command


async def _persist_pending_effect(service, root_id):
    """Persist one real unresolved dispatch effect for one bound root.

    The effect is written by the incumbent Runtime through its canonical
    EventStore and read back through its canonical reader, so no marker
    lookup is faked anywhere in this regression.
    """
    planner, command = await _seal_failed_planner(service, root_id)
    service.runtime.jobs.record_cycle_dispatch_effect_unknown(
        root_id,
        selected_job_id=planner.job_id,
        dispatch_command_id=command,
    )
    assert service.runtime.jobs.pending_cycle_dispatch_effect_unknown(root_id) is not None


@asynccontextmanager
async def _pair_with_real_pending_effect(tmp_path, marked_index=0):
    """Seed two roots and persist a real unresolved dispatch effect on one."""
    async with _prepared_pair(tmp_path) as (config, seed, ids, paths):
        await seed.close()
        seeding, _ = _service(tmp_path, config=dataclasses.replace(
            config, coo_tick_interval_seconds=3600.0), finish_gate=asyncio.Event())
        await seeding.start()
        try:
            await _persist_pending_effect(seeding, ids[marked_index])
        finally:
            await seeding.close()
        yield config, ids, paths


def test_real_pending_effect_root_defers_to_an_independent_ready_root(tmp_path):
    async def exercise():
        async with _pair_with_real_pending_effect(tmp_path) as (config, ids, paths):
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=1.0), finish_gate=asyncio.Event())
            await running.start()
            try:
                marker_before = running.runtime.jobs.pending_cycle_dispatch_effect_unknown(ids[0])
                assert marker_before is not None
                events_before = _raw_events(running, ids[0])
                facts_before = _subtree_facts(running, ids[0])
                workers_before = [w.worker_id for w in running.runtime.workers.list_workers()]
                # The unresolved effect of one root does not fence a different
                # root that is ready and independent of it.
                assert running._next_bound_coo_root() == ids[1]
                assert await _until(lambda: bool(_children(running, ids[1]))), {
                    "last_error": running._coo_last_error,
                    "last_tick": running._coo_last_tick_at,
                }
                # The deferred root is neither advanced nor acknowledged, and
                # the deferral admits no new worker and no second effect.
                assert running.runtime.jobs.pending_cycle_dispatch_effect_unknown(ids[0]) == marker_before
                assert _raw_events(running, ids[0]) == events_before
                assert _subtree_facts(running, ids[0]) == facts_before
                assert [w.worker_id for w in running.runtime.workers.list_workers()] == workers_before
                assert running.service_state == "READY"
            finally:
                await running.close()
    asyncio.run(exercise())


def test_deferred_root_regains_its_own_reconciliation_path(tmp_path):
    async def exercise():
        async with _pair_with_real_pending_effect(tmp_path) as (config, ids, paths):
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=3600.0), finish_gate=asyncio.Event())
            await running.start()
            try:
                assert running.runtime.jobs.pending_cycle_dispatch_effect_unknown(ids[0]) is not None
                # The independent root is selected while it still owns
                # actionable work of its own.
                assert running._next_bound_coo_root() == ids[1]
                # Give that root its own unresolved effect as well, so no root
                # has independently actionable work left.
                await _persist_pending_effect(running, ids[1])
                # The deferred root is then selected for its own lawful
                # reconciliation instead of being starved by the scan.
                assert running._next_bound_coo_root() == ids[0]
                attempts_before = len(running.runtime.attempts.list_attempts())
                await running._run_coo_cycle(ids[0])
                # The reconciliation is finite and exact: the very same claim
                # is resolved, and no second effect is created.
                assert running.runtime.jobs.pending_cycle_dispatch_effect_unknown(ids[0]) is None
                assert len(running.runtime.attempts.list_attempts()) == attempts_before
            finally:
                await running.close()
    asyncio.run(exercise())


def test_unreadable_effect_state_fails_closed_for_its_own_root_only(tmp_path):
    async def exercise():
        async with _pair_with_real_pending_effect(tmp_path) as (config, ids, paths):
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=3600.0), finish_gate=asyncio.Event())
            await running.start()
            try:
                # Corrupt the persisted effect receipt the way history can rot.
                with running.runtime.store.transaction() as connection:
                    connection.execute("DROP TRIGGER events_are_immutable_update")
                    connection.execute(
                        "UPDATE events SET actor='foreign' "
                        "WHERE event_type='COO_DISPATCH_EFFECT_UNKNOWN' AND job_id=?",
                        (ids[0],),
                    )
                # An unreadable effect state is never treated as "no effect",
                # never dispatches that root and never aborts another root's
                # selection.
                assert running._next_bound_coo_root() == ids[1]
                # The refusal is recorded, so the condition is not silent.
                refusals = [
                    event
                    for event in running.runtime.events.list_events(job_id=ids[0])
                    if event.event_type == "COO_SERVICE_TICK_REFUSED"
                ]
                assert len(refusals) == 1
            finally:
                await running.close()
    asyncio.run(exercise())


def test_live_dispatch_keeps_the_serialized_worker_on_its_own_root(tmp_path):
    async def exercise():
        async with _pair_with_real_pending_effect(tmp_path) as (config, ids, paths):
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=1.0), finish_gate=asyncio.Event())
            await running.start()
            try:
                facts_before = _subtree_facts(running, ids[0])
                # Drive the independent root onto the serialized worker.
                await running._run_coo_cycle(ids[1])
                await running._run_coo_cycle(ids[1])
                live = [
                    job_id
                    for job_id, task in running._dispatch_tasks.items()
                    if not task.done()
                ]
                assert live, "the independent root must own the serialized worker"
                await asyncio.sleep(1.5)
                # The live dispatch keeps the tick on its own root, so the
                # deferred root is not reconciled behind the running worker.
                assert running.runtime.jobs.pending_cycle_dispatch_effect_unknown(ids[0]) is not None
                assert _subtree_facts(running, ids[0]) == facts_before
                # The deferred root is not even attempted while that worker
                # owns the serialized dispatch.
                assert not [
                    event
                    for event in running.runtime.events.list_events(job_id=ids[0])
                    if event.event_type == "COO_SERVICE_TICK_REFUSED"
                ]
            finally:
                await running.close()
    asyncio.run(exercise())


def test_root_without_independently_ready_work_does_not_starve_the_deferred_root(tmp_path):
    """A root that cannot act must not starve the deferred root's turn.

    The independent root can never dispatch its work, so it proves that it
    cannot act. The deferred root must then receive its own reconciliation
    turn instead of waiting behind a root that made no progress.
    """
    async def exercise():
        async with _pair_with_real_pending_effect(tmp_path) as (config, ids, paths):
            holder = {}

            def factory(runtime):
                supervisor = _CapacityBlockedSupervisor(runtime)
                holder["supervisor"] = supervisor
                return supervisor

            running = ExecutiveControlService(
                dataclasses.replace(config, coo_tick_interval_seconds=1.0),
                supervisor_factory=factory,
                autonomy_guard=lambda: None,
            )
            await running.start()
            try:
                # The independent root creates its planner and can never
                # dispatch it, so its cycle can make no progress at all.
                await running._run_coo_cycle(ids[1])
                planner = _children(running, ids[1])[0]
                holder["supervisor"].blocked_job_id = planner.job_id
                # The deferred root's own reconciliation still happens, and it
                # resolves the very same claim without a second effect.
                assert await _until(
                    lambda: running.runtime.jobs.pending_cycle_dispatch_effect_unknown(ids[0]) is None,
                    timeout=10.0,
                ), {
                    "last_error": running._coo_last_error,
                    "last_tick": running._coo_last_tick_at,
                }
                assert running.runtime.jobs.get_job(ids[0]).attempt_count == 0
            finally:
                await running.close()
    asyncio.run(exercise())


def test_deferred_turn_needs_a_no_progress_outcome_and_a_free_worker(tmp_path):
    """The deferred root's turn is bounded by both of its own conditions."""
    async def exercise():
        async with _pair_with_real_pending_effect(tmp_path) as (config, ids, paths):
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=3600.0), finish_gate=asyncio.Event())
            await running.start()
            try:
                # A root that acted keeps the tick to itself.
                assert running._deferred_effect_turn_allowed("DISPATCHED") is False
                assert running._deferred_effect_turn_allowed("PLAN_ADMITTED") is False
                # A root that proved it cannot act frees the tick, but only
                # while the serialized worker is free.
                assert running._deferred_effect_turn_allowed("NO_ACTION") is True
                release = asyncio.Event()
                running._dispatch_tasks["live-fixture"] = asyncio.create_task(release.wait())
                try:
                    assert running._deferred_effect_turn_allowed("NO_ACTION") is False
                finally:
                    release.set()
                    for task in tuple(running._dispatch_tasks.values()):
                        task.cancel()
                    await asyncio.gather(
                        *tuple(running._dispatch_tasks.values()),
                        return_exceptions=True,
                    )
                assert running._deferred_effect_turn_allowed("NO_ACTION") is True
            finally:
                await running.close()
    asyncio.run(exercise())


def test_root_that_owns_queued_work_is_still_selected_over_the_deferred_root(tmp_path):
    """Ready work of its own is never withheld from an independent root."""
    async def exercise():
        async with _pair_with_real_pending_effect(tmp_path) as (config, ids, paths):
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=3600.0), finish_gate=asyncio.Event())
            await running.start()
            try:
                # The independent root now owns work it can dispatch on its own.
                await running._run_coo_cycle(ids[1])
                queued = [
                    job for job in _children(running, ids[1])
                    if job.status.value == "QUEUED"
                ]
                assert queued
                assert running._next_bound_coo_root() == ids[1]
            finally:
                await running.close()
    asyncio.run(exercise())


def test_quarantined_service_never_advances_another_root(tmp_path):
    async def exercise():
        async with _prepared_pair(tmp_path) as (config, seed, ids, paths):
            await seed.close()
            lossy = ExecutiveControlService(
                dataclasses.replace(config, coo_tick_interval_seconds=1.0),
                supervisor_factory=_LostStartReceipt,
                autonomy_guard=lambda: None,
            )
            await lossy.start()
            try:
                await _request(lossy, "run-coo-cycle", {"root_job_id": ids[0]})
                await _request(lossy, "run-coo-cycle", {"root_job_id": ids[0]})
                assert lossy.service_state == "QUARANTINED"
                await asyncio.sleep(1.5)
                # A globally quarantined service stops every root, including
                # the independent ready one.
                assert _children(lossy, ids[1]) == []
            finally:
                await lossy.close()
    asyncio.run(exercise())


def test_unbound_independent_root_is_not_selected_over_the_deferred_root(tmp_path):
    async def exercise():
        async with _pair_with_real_pending_effect(tmp_path) as (config, ids, paths):
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=3600.0), finish_gate=asyncio.Event())
            await running.start()
            try:
                bound = running._is_bound_coo_root
                running._is_bound_coo_root = lambda root: (
                    root.job_id != ids[1] and bound(root)
                )
                # An unbound root is never selected. The deferred root keeps
                # its own reconciliation path.
                assert running._next_bound_coo_root() == ids[0]
            finally:
                await running.close()
    asyncio.run(exercise())
