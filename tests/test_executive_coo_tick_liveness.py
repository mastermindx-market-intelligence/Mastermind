"""Real-service, model-free proof of bounded pre-start queue liveness."""
from __future__ import annotations

import asyncio
import dataclasses
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from control_plane.executive_service import ExecutiveControlService
from control_plane.executive_runtime import JobPayload, StateConflict
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


def test_independent_ready_root_is_not_starved_by_unresolved_other_root(tmp_path, monkeypatch):
    """Persist A's real marker; admit B once, then return to A's exact barrier."""
    async def exercise():
        async with _prepared_pair(tmp_path) as (config, seed, ids, _):
            a, b = ids
            planner = seed.runtime.jobs.create_cycle_planner(
                a, command_id=f"coo-cycle:{a}:create-planner:0")
            exact_command = f"coo-cycle:{a}:dispatch:{planner.job_id}:attempt:1"
            claimed = seed.runtime.attempts.dispatch_cycle_job(
                planner.job_id, command_id=exact_command,
                lease_owner="retained-original-owner")
            assert claimed is not None and claimed.claimed_now
            seed.runtime.attempts.fail_attempt(
                claimed.attempt.attempt_id,
                fence_generation=claimed.attempt.fence_generation,
                lease_token=claimed.lease_token,
                payload=JobPayload(summary="Fixture provider refused before execution"))
            seed.runtime.jobs.record_cycle_dispatch_effect_unknown(
                a, selected_job_id=planner.job_id,
                dispatch_command_id=exact_command)
            marker = seed.runtime.jobs.pending_cycle_dispatch_effect_unknown(a)
            assert marker is not None and marker["dispatch_command_id"] == exact_command
            await seed.close()
            finish_gate = asyncio.Event()
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=1.0,
                shutdown_grace_seconds=3.0), finish_gate=finish_gate)
            await running.start()
            try:
                assert running.runtime.jobs.pending_cycle_dispatch_effect_unknown(a) == marker
                assert running._next_bound_coo_root(previous_root_id=a) == b
                # A remains the very next choice even if B keeps appearing
                # in the status scan and has not yet done useful work.
                assert running._next_bound_coo_root(previous_root_id=b) == a
                # A corrupt B-only marker is a local admission failure, not
                # a reason to erase A's original reconciliation fallback.
                reader = running.runtime.jobs.pending_cycle_dispatch_effect_unknown

                def bad_b(root_id):
                    if root_id == b:
                        raise StateConflict("B has multiple pending effects")
                    return reader(root_id)

                with monkeypatch.context() as patch:
                    patch.setattr(running.runtime.jobs,
                                  "pending_cycle_dispatch_effect_unknown", bad_b)
                    assert running._next_bound_coo_root(previous_root_id=a) == a
                observed = []
                actual_cycle = running._run_coo_cycle

                async def bounded_cycle(root_id):
                    observed.append(root_id)
                    if root_id == a:
                        # An unsettled same-run outcome cannot be retried here.
                        raise StateConflict("synthetic original effect still unresolved")
                    return await actual_cycle(root_id)

                running._run_coo_cycle = bounded_cycle
                assert await _until(lambda: len(observed) >= 3, timeout=8.0), {
                    "last_error": running._coo_last_error,
                    "last_tick": running._coo_last_tick_at,
                    "selected": observed,
                }
                assert observed[:3] == [b, a, b]
                assert _children(running, b)
                assert await _until(
                    lambda: any(child.attempt_count > 0 for child in _children(running, b)),
                    timeout=4.0,
                ), "B must progress beyond planner creation on its second tick"
                assert running.runtime.jobs.pending_cycle_dispatch_effect_unknown(a) == marker
                assert running.service_state == "READY"
            finally:
                finish_gate.set()
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
                # Quarantine is published before the original cycle thread returns.
                # Observe completion before the fixture's 100 ms shutdown drain.
                assert await _until(
                    lambda: not running._physical_workers and not running._coo_action_tasks
                ), running._coo_last_error
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


def _corrupt_real_pending_effect(service, root_id):
    """Damage a real persisted receipt while retaining its original claim."""
    planner = service.runtime.jobs.create_cycle_planner(
        root_id, command_id=f"coo-cycle:{root_id}:create-planner:0")
    command = f"coo-cycle:{root_id}:dispatch:{planner.job_id}:attempt:1"
    claim = service.runtime.attempts.dispatch_cycle_job(
        planner.job_id, command_id=command, lease_owner="retained-original-owner")
    assert claim is not None and claim.claimed_now
    service.runtime.attempts.fail_attempt(
        claim.attempt.attempt_id,
        fence_generation=claim.attempt.fence_generation,
        lease_token=claim.lease_token,
        payload=JobPayload(summary="Fixture provider refused before execution"))
    service.runtime.jobs.record_cycle_dispatch_effect_unknown(
        root_id, selected_job_id=planner.job_id, dispatch_command_id=command)
    marker = service.runtime.jobs.pending_cycle_dispatch_effect_unknown(root_id)
    assert marker is not None and marker["dispatch_command_id"] == command
    with service.runtime.store.transaction() as connection:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='events_are_immutable_update'").fetchone()
        assert trigger is not None
        connection.execute("DROP TRIGGER events_are_immutable_update")
        changed = connection.execute(
            "UPDATE events SET actor='fixture-untrusted-actor' "
            "WHERE event_type='COO_DISPATCH_EFFECT_UNKNOWN' AND job_id=?",
            (root_id,))
        assert changed.rowcount == 1
        connection.execute(trigger[0])
    with pytest.raises(StateConflict):
        service.runtime.jobs.pending_cycle_dispatch_effect_unknown(root_id)


def _original_effect_facts(service, root_id):
    """Observe original history, subtree and claims, excluding new diagnostics."""
    with service.runtime.store.read() as connection:
        history = [
            tuple(row) for row in connection.execute(
                "SELECT * FROM events WHERE job_id=? "
                "AND event_type!='COO_SERVICE_TICK_REFUSED' ORDER BY event_id",
                (root_id,)).fetchall()
        ]
        attempts = [
            tuple(row) for row in connection.execute(
                "SELECT * FROM attempts WHERE job_id IN "
                "(SELECT job_id FROM jobs WHERE root_job_id=?) ORDER BY attempt_id",
                (root_id,)).fetchall()
        ]
    subtree = sorted(
        (job.job_id, job.status.value, job.attempt_count, job.current_attempt_id)
        for job in service.runtime.jobs.list_jobs() if job.root_job_id == root_id
    )
    return history, attempts, subtree


def _tick_refusals(service, root_id):
    return [
        event for event in service.runtime.events.list_events(job_id=root_id)
        if event.event_type == "COO_SERVICE_TICK_REFUSED"
    ]


def test_corrupt_effect_selector_collects_refusal_without_writing_or_losing_fairness(tmp_path):
    async def exercise():
        async with _prepared_pair(tmp_path) as (_, service, ids, _):
            a, b = ids
            _corrupt_real_pending_effect(service, a)
            original = _original_effect_facts(service, a)
            refusals = {}
            assert service._next_bound_coo_root(prestart_refusals=refusals) == b
            assert set(refusals) == {a}
            assert isinstance(refusals[a], StateConflict)
            # Omitting the collector keeps the same read-only selector contract.
            assert service._next_bound_coo_root() == b
            assert service._next_bound_coo_root(previous_root_id=b) == a
            assert service._next_bound_coo_root(previous_root_id=a) == b
            assert _tick_refusals(service, a) == []
            assert _original_effect_facts(service, a) == original
            assert _children(service, b) == []
            assert service.runtime.jobs.get_job(b).attempt_count == 0
            with pytest.raises(StateConflict):
                service.runtime.jobs.pending_cycle_dispatch_effect_unknown(a)
    asyncio.run(exercise())


def test_corrupt_effect_tick_records_one_refusal_before_independent_progress(tmp_path):
    async def exercise():
        async with _prepared_pair(tmp_path) as (config, seed, ids, _):
            a, b = ids
            _corrupt_real_pending_effect(seed, a)
            original = _original_effect_facts(seed, a)
            await seed.close()
            finish_gate = asyncio.Event()
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_tick_interval_seconds=1.0,
                shutdown_grace_seconds=3.0), finish_gate=finish_gate)
            await running.start()
            try:
                observed = []
                receipts_before_action = []
                actual_cycle = running._run_coo_cycle

                async def observe_cycle(root_id):
                    observed.append(root_id)
                    receipts_before_action.append(_tick_refusals(running, a))
                    return await actual_cycle(root_id)

                running._run_coo_cycle = observe_cycle
                assert await _until(lambda: len(observed) >= 3, timeout=8.0), {
                    "last_error": running._coo_last_error, "selected": observed,
                }
                assert observed[:3] == [b, a, b]
                assert all(len(receipts) == 1 for receipts in receipts_before_action[:3])
                assert await _until(
                    lambda: any(child.attempt_count > 0 for child in _children(running, b)),
                    timeout=4.0,
                ), "B must progress again even while A's original receipt stays corrupt"
                refusals = _tick_refusals(running, a)
                assert len(refusals) == 1
                assert refusals[0].payload == {
                    "schema_version": "mastermind.executive_coo_tick_refusal/v1",
                    "root_job_id": a,
                    "error_type": "StateConflict",
                    "reason_code": "bounded_cycle_action_refused",
                    "routing_policy_version": running._coo_execution_binding[
                        "routing_policy_version"],
                    "capability_policy_digest": running._coo_execution_binding[
                        "capability_policy_digest"],
                }
                assert _original_effect_facts(running, a) == original
                with pytest.raises(StateConflict):
                    running.runtime.jobs.pending_cycle_dispatch_effect_unknown(a)
                assert running.service_state == "READY"
            finally:
                finish_gate.set()
                await running.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("gate", ["disarmed", "autonomy_revoked", "quarantined"])
def test_corrupt_effect_diagnostic_obeys_existing_tick_authority_gates(tmp_path, gate):
    async def exercise():
        async with _prepared_pair(tmp_path) as (config, seed, ids, _):
            a, b = ids
            _corrupt_real_pending_effect(seed, a)
            original = _original_effect_facts(seed, a)
            await seed.close()
            running, _ = _service(tmp_path, config=dataclasses.replace(
                config, coo_autonomy_armed=gate != "disarmed",
                coo_tick_interval_seconds=1.0, shutdown_grace_seconds=3.0),
                finish_gate=asyncio.Event())
            await running.start()
            try:
                if gate == "autonomy_revoked":
                    def refuse_autonomy():
                        raise StateConflict("fixture-private-authority-detail")
                    running._require_current_autonomy = refuse_autonomy
                elif gate == "quarantined":
                    running._service_state = "QUARANTINED"
                await asyncio.sleep(1.2)
                assert _tick_refusals(running, a) == []
                assert _original_effect_facts(running, a) == original
                assert _children(running, b) == []
                assert running.runtime.jobs.get_job(b).attempt_count == 0
            finally:
                await running.close()
    asyncio.run(exercise())
