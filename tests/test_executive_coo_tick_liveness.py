"""Real-service, model-free proof of bounded pre-start queue liveness."""
from __future__ import annotations

import asyncio
import dataclasses
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from control_plane.executive_service import ExecutiveControlService
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
            running = ExecutiveControlService(dataclasses.replace(
                config, coo_tick_interval_seconds=1.0),
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
