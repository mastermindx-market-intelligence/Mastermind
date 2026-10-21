"""Recover the original remote attempt after an actual no-handoff process exit.

Only the disposable control process exits. The test-owned broker stays alive;
its provider adapter is a fixture, so no model, service or account is invoked.
"""
from __future__ import annotations

import asyncio
import multiprocessing
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import AttemptStatus, JobStatus, Runtime
from control_plane.executive_supervisor import ReconcileStatus
from control_plane.executive_worker_broker import WorkerBrokerClient
from test_executive_remote_restart_survivability import (
    _close_fixture,
    _runtime_and_job,
    _serve_fixture,
    _supervisor_for,
)


_CRASH_EXIT_CODE = 86
_LEASE_SECONDS = 120
_CHILD_DEADLINE_SECONDS = 30


def _exit_control_without_handoff(
    runtime_root: Path,
    test_root: Path,
    socket_path: Path,
    policy_fields: dict,
    job_id: str,
    crash_stage: str,
) -> None:
    """Spawn entrypoint: no parent supervisor or broker objects are inherited."""

    async def run() -> None:
        runtime = Runtime.at(runtime_root, lease_seconds=_LEASE_SECONDS)
        broker_view = SimpleNamespace(policy=SimpleNamespace(**policy_fields))
        client = WorkerBrokerClient(socket_path, timeout_seconds=10.0)
        supervisor = _supervisor_for(
            runtime, broker_view, client, test_root,
            instance_id="control-that-exits-without-handoff",
        )
        active = await supervisor.start_job(job_id)
        if crash_stage in {"after_collection", "after_validation"}:
            await supervisor.adapter.collect_result(active.process_ref)
        if crash_stage == "after_validation":
            await supervisor.adapter.run_validation_argv(
                active.launch_spec, ["/usr/bin/true"]
            )
        # Deliberately skip finally/atexit, final result publication and closeout.
        # The new supervisor must recover solely from existing durable owners.
        os._exit(_CRASH_EXIT_CODE)

    asyncio.run(run())


@pytest.mark.parametrize(
    ("crash_stage", "expected_recovery", "collected_before", "validated_before"),
    [
        ("after_start", ReconcileStatus.LIVE_RECOVERED, 0, 0),
        ("after_collection", ReconcileStatus.TERMINAL_RECOVERED, 1, 0),
        ("after_validation", ReconcileStatus.TERMINAL_RECOVERED, 1, 1),
    ],
)
def test_remote_attempt_survives_control_process_exit_without_handoff(
    tmp_path: Path,
    crash_stage: str,
    expected_recovery: ReconcileStatus,
    collected_before: int,
    validated_before: int,
) -> None:
    async def scenario() -> None:
        broker, adapter, server, socket_path, client = await _serve_fixture(tmp_path)
        runtime_root, runtime, job = _runtime_and_job(
            tmp_path, broker, lease_seconds=_LEASE_SECONDS
        )
        # spawn, rather than fork, excludes inherited Runtime connections and
        # in-memory supervisor state from the process-level proof.
        policy_fields = {
            name: getattr(broker.policy, name)
            for name in (
                "workspace_root", "run_root", "worker_user", "worker_uid", "worker_gid"
            )
        }
        controller = multiprocessing.get_context("spawn").Process(
            target=_exit_control_without_handoff,
            args=(runtime_root, tmp_path, socket_path, policy_fields, job.job_id, crash_stage),
            name="disposable-executive-control-crash-test",
        )
        try:
            if crash_stage != "after_start":
                adapter.finished.set()
            controller.start()
            assert controller.pid != os.getpid()
            await asyncio.to_thread(controller.join, _CHILD_DEADLINE_SECONDS)
            assert not controller.is_alive(), "test control process failed to reach its crash boundary"
            assert controller.exitcode == _CRASH_EXIT_CODE

            attempts_before = runtime.attempts.list_attempts(job.job_id)
            assert len(attempts_before) == 1
            original = attempts_before[0]
            assert original.status in {AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED}
            assert original.exit_code is None
            assert runtime.jobs.get_job(job.job_id).status is not JobStatus.COMPLETED
            assert adapter.start_calls == 1
            assert adapter.collect_calls == collected_before
            assert len(adapter.validation_calls) == validated_before

            reopened = Runtime.at(runtime_root, lease_seconds=_LEASE_SECONDS)
            restarted = _supervisor_for(
                reopened, broker, client, tmp_path,
                instance_id="control-after-actual-process-exit",
            )
            outcomes = await asyncio.to_thread(
                restarted.reconcile_restart, requeue_lost=False
            )
            assert [item.status for item in outcomes] == [expected_recovery]
            repeated = await asyncio.to_thread(
                restarted.reconcile_restart, requeue_lost=False
            )
            assert [item.status for item in repeated] == [ReconcileStatus.ALREADY_RECOVERED]
            recovered = restarted.take_recovered_runs()
            assert len(recovered) == 1
            assert recovered[0].lease.attempt.attempt_id == original.attempt_id
            assert restarted.take_recovered_runs() == ()
            assert adapter.start_calls == 1
            assert adapter.collect_calls == collected_before
            assert len(adapter.validation_calls) == validated_before

            adapter.finished.set()
            terminal = await restarted.finish_job(recovered[0])
            assert terminal.job.status is JobStatus.COMPLETED
            assert terminal.attempt.status is AttemptStatus.COMPLETED
            assert terminal.attempt.attempt_id == original.attempt_id
            assert terminal.attempt.fence_generation == original.fence_generation + 1
            assert terminal.attempt.exit_code == 0
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 1
            assert adapter.validation_calls == [("/usr/bin/true",)]
            assert [
                item.attempt_id for item in reopened.attempts.list_attempts(job.job_id)
            ] == [original.attempt_id]
            assert broker._active_run_id is None
            assert Path(terminal.collection_receipt_path).is_file()
            assert Path(terminal.validation_receipt_path or "").is_file()
            assert Path(terminal.assignment_seal_receipt_path or "").is_file()
        finally:
            try:
                # Cleanup addresses only this test's exact child handle.
                if controller.pid is not None and controller.is_alive():
                    controller.terminate()
                    await asyncio.to_thread(controller.join, 5.0)
                    if controller.is_alive():
                        controller.kill()
                        await asyncio.to_thread(controller.join, 5.0)
                    assert not controller.is_alive(), "test-owned child did not terminate"
                controller.close()
            finally:
                await _close_fixture(broker, adapter, server, socket_path)

    asyncio.run(scenario())
