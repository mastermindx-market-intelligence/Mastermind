"""Actual native cycle claims at sealing/START; physical adapters are inert.

The ordinary child has no separately issued exact-target capability. All
Runtime claims, cancellations, heartbeats and replay Events
are genuine; no provider, host service or installed state is touched.
"""
import asyncio
import dataclasses
import os
import stat
from datetime import datetime
from pathlib import Path

import pytest

from control_plane import executive_supervisor as owner
from control_plane.executive_runtime import (
    AttemptStatus, JobStatus, OrchestrationDispatchOutcome, Runtime, StateConflict,
)
from control_plane.executive_supervisor import SupervisorError
from test_executive_os_sqlite import _hf1b_claim_fixture
from test_executive_supervisor import FakeInspector, Hf1bResultAdapter, _supervisor


def _ordinary_child(tmp_path):
    runtime, root, work, command, _, _ = _hf1b_claim_fixture(tmp_path)
    # The fixture's optional target definition is never issued or adopted.
    # This uses the incumbent ordinary native cycle-dispatch path directly.
    adapter = Hf1bResultAdapter(FakeInspector(), runtime, work)
    supervisor = _supervisor(runtime, tmp_path, adapter, worker_uid=os.geteuid())
    os.chown(adapter.provider_home, -1, os.getegid())
    return runtime, root, work, command, adapter, supervisor


def _capture_lease(monkeypatch, supervisor, retained, *, invalid_token=False):
    original = supervisor._start_claimed_job
    async def capture(job_id, lease, **kwargs):
        retained["lease"] = lease
        supplied = dataclasses.replace(lease, lease_token="unissued-test-token") if invalid_token else lease
        return await original(job_id, supplied, **kwargs)
    monkeypatch.setattr(supervisor, "_start_claimed_job", capture)


@pytest.mark.parametrize("change", ["cancel", "invalid-token", "expire"])
def test_native_child_validates_original_claim_at_sealed_start_boundary(tmp_path, monkeypatch, change):
    runtime, root, work, command, adapter, supervisor = _ordinary_child(tmp_path)
    retained = {}
    _capture_lease(monkeypatch, supervisor, retained, invalid_token=(change == "invalid-token"))
    write = owner._write_private_recovery_prompt
    def seal_then_change(path, prompt):
        write(path, prompt)
        lease = retained["lease"]
        retained.update(prompt_path=path, prompt=path.read_bytes(),
                        workspace_mode=stat.S_IMODE(Path(work.worktree).stat().st_mode))
        if change == "cancel":
            runtime.jobs.cancel_job(
                work.job_id, expected_attempt_id=lease.attempt.attempt_id,
                expected_fence_generation=lease.attempt.fence_generation)
        elif change == "expire":
            expires = int(datetime.fromisoformat(lease.attempt.lease_expires_at).timestamp() * 1000)
            runtime.store.clock = lambda: expires + 2000
    monkeypatch.setattr(owner, "_write_private_recovery_prompt", seal_then_change)
    with pytest.raises(SupervisorError):
        asyncio.run(supervisor.start_cycle_job(work.job_id, command_id=command))
    assert adapter.start_count == 0
    original = retained["lease"].attempt
    current = runtime.attempts.get_attempt(original.attempt_id)
    assert len(runtime.attempts.list_attempts(work.job_id)) == 1
    assert current.job_id == work.job_id and current.pid is None
    assert retained["prompt_path"].read_bytes() == retained["prompt"]
    # A stale/cancelled owner cannot seal the assignment of its successor.
    assert stat.S_IMODE(Path(work.worktree).stat().st_mode) == retained["workspace_mode"]
    assert current.status is (AttemptStatus.CANCEL_REQUESTED if change == "cancel"
                              else AttemptStatus.CLAIMED)
    assert current.fence_generation == original.fence_generation
    assert current.lease_owner == original.lease_owner
    with pytest.raises(StateConflict):
        runtime.validated_role_completion(work.job_id, expected_attempt_id=original.attempt_id)
    with pytest.raises(StateConflict, match="immutable handoff"):
        runtime.jobs.get_cycle_handoff(root.job_id)
    reopened = Runtime.at(runtime.store.root, create=False, existing_writable=True)
    assert reopened.attempts.get_attempt(original.attempt_id).status is current.status
    assert len(reopened.attempts.list_attempts(work.job_id)) == 1


def test_same_claim_heartbeat_during_sealing_still_starts_once(tmp_path, monkeypatch):
    runtime, root, work, command, adapter, supervisor = _ordinary_child(tmp_path)
    retained = {}
    _capture_lease(monkeypatch, supervisor, retained)
    write = owner._write_private_recovery_prompt
    def seal_then_heartbeat(path, prompt):
        write(path, prompt)
        lease = retained["lease"]
        runtime.attempts.heartbeat_attempt(
            lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, extend_seconds=120)
    monkeypatch.setattr(owner, "_write_private_recovery_prompt", seal_then_heartbeat)
    async def exercise():
        active = await supervisor.start_cycle_job(work.job_id, command_id=command)
        assert adapter.start_count == 1
        assert active.lease.attempt.attempt_id == retained["lease"].attempt.attempt_id
        adapter.inspector.live = False
        terminal = await supervisor.finish_job(active)
        assert terminal.job.status is JobStatus.COMPLETED
        assert terminal.attempt.status is AttemptStatus.COMPLETED
    asyncio.run(exercise())
    assert len(runtime.attempts.list_attempts(work.job_id)) == 1


@pytest.mark.parametrize("interruption", ["claimed-before-start", "start-response-lost"])
def test_ordinary_cycle_replay_never_reissues_original_start(tmp_path, monkeypatch, interruption):
    runtime, root, work, command, adapter, supervisor = _ordinary_child(tmp_path)
    if interruption == "claimed-before-start":
        original = runtime.attempts.dispatch_cycle_job(
            work.job_id, command_id=command, lease_owner=supervisor.instance_id)
        assert original.claimed_now
        expected_starts = 0
    else:
        adapter.ambiguous_start = True
        async def unresolved_absence(_run_id):
            raise ConnectionError("fixture original start disposition is unknown")
        monkeypatch.setattr(adapter, "cleanup_unbound_run", unresolved_absence)
        with pytest.raises(SupervisorError, match="ambiguous launch"):
            asyncio.run(supervisor.start_cycle_job(work.job_id, command_id=command))
        original = runtime.attempts.list_attempts(work.job_id)[0]
        expected_starts = 1
    attempt = runtime.attempts.list_attempts(work.job_id)[0]
    assert attempt.status is AttemptStatus.CLAIMED and adapter.start_count == expected_starts
    original_event = runtime.store.get_event_by_command_id(command)
    original_prompt = supervisor._run_dir(attempt.attempt_id) / "input" / "worker-prompt.txt"
    original_bytes = original_prompt.read_bytes() if original_prompt.exists() else None
    replay = asyncio.run(supervisor.start_cycle_job(work.job_id, command_id=command))
    assert type(replay) is OrchestrationDispatchOutcome and not replay.claimed_now
    assert replay.attempt.attempt_id == attempt.attempt_id
    assert adapter.start_count == expected_starts
    assert len(runtime.attempts.list_attempts(work.job_id)) == 1
    assert runtime.store.get_event_by_command_id(command) == original_event
    if original_bytes is not None:
        assert original_prompt.read_bytes() == original_bytes
    else:
        assert not original_prompt.exists()
    with pytest.raises(StateConflict, match="immutable handoff"):
        runtime.jobs.get_cycle_handoff(root.job_id)
