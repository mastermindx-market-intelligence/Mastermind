"""Selected-host identity seam; synthetic host facts, no live provider proof."""
from __future__ import annotations
import asyncio
from dataclasses import replace
from pathlib import Path
import pytest
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError,
)
from control_plane.executive_runtime import AttemptStatus, JobStatus
from control_plane.operator_harness_contract import WorkspaceIdentity
from test_executive_operator_supervisor import (
    _ActiveAdapter, _PromptSource, _seed_dispatchable_operator_planner,
)

def _remote_fixture(tmp_path):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    path = Path(planner.worktree)
    path.rename(path.with_name("fixture-host-workspace"))
    assert not path.exists()
    # Deliberate synthetic remote observation, never local inode relabelling.
    identity = WorkspaceIdentity(str(path), planner.constraints["base_sha"],
                                 901, 902, 903, 904)
    return runtime, root, planner, identity

def _run(runtime, root, planner, source):
    adapters = []
    def factory(attempt, requested, loader, *, recovery):
        assert requested.worker_id == attempt.worker_id == "worker-a"
        assert recovery is False
        adapter = _ActiveAdapter(runtime, loader, cancel_during_collect=False)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=factory, workspace_identity_source=source,
        prompt_source=_PromptSource())
    outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"))
    return outcome, adapters

def test_remote_only_workspace_completes_from_selected_host_facts(tmp_path):
    runtime, root, planner, identity = _remote_fixture(tmp_path)
    observations = []
    def source(attempt, job):
        observations.append((attempt.worker_id, job.assigned_worker_id,
                             job.current_attempt_id, attempt.attempt_id))
        assert attempt.status is AttemptStatus.CLAIMED
        return identity
    outcome, adapters = _run(runtime, root, planner, source)
    assert observations == [("worker-a", "worker-a",
                             outcome.attempt.attempt_id, outcome.attempt.attempt_id)]
    assert outcome.attempt.status is AttemptStatus.COMPLETED
    assert runtime.jobs.get_job(planner.job_id).status is JobStatus.COMPLETED
    assert len(adapters) == 1
    assert adapters[0].profile.workspace == identity
    assert adapters[0].begin_turn_calls == 1
    assert adapters[0].stop_calls == 1

@pytest.mark.parametrize("field,value", [
    ("workspace_path", "/another-host/worktree"), ("base_sha", "f" * 40),
    ("device", -1), ("device", True), ("inode", 0), ("inode", False),
    ("uid", -1), ("uid", True), ("gid", -1), ("gid", True),
])
def test_invalid_remote_facts_refuse_without_endpoint_or_local_fallback(
        tmp_path, monkeypatch, field, value):
    runtime, root, planner, identity = _remote_fixture(tmp_path)
    def forbidden_local(*args):
        raise AssertionError("selected-host source must not fall back to local Git")
    monkeypatch.setattr(ExecutiveOperatorSupervisor, "_git_head", forbidden_local)
    with pytest.raises(ExecutiveOperatorSupervisorError,
                       match="selected-host workspace identity"):
        _run(runtime, root, planner, lambda attempt, job: replace(identity, **{field: value}))
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 0

def test_failed_remote_source_refuses_without_local_fallback(tmp_path):
    runtime, root, planner, identity = _remote_fixture(tmp_path)
    def source(attempt, job):
        raise OSError("fixture host observation unavailable")
    with pytest.raises(ExecutiveOperatorSupervisorError,
                       match="selected-host workspace identity source refused"):
        _run(runtime, root, planner, source)

def test_claim_movement_during_remote_source_refuses_before_start(tmp_path):
    runtime, root, planner, identity = _remote_fixture(tmp_path)
    def source(attempt, job):
        runtime.jobs.cancel_job(job.job_id)
        return identity
    with pytest.raises(ExecutiveOperatorSupervisorError,
                       match="selected-host workspace binding moved"):
        _run(runtime, root, planner, source)
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 0

def test_remote_source_receives_detached_job_facts(tmp_path):
    runtime, root, planner, identity = _remote_fixture(tmp_path)
    def source(attempt, job):
        job.constraints["base_sha"] = "f" * 40
        return identity
    outcome, adapters = _run(runtime, root, planner, source)
    assert outcome.attempt.status is AttemptStatus.COMPLETED
    assert runtime.jobs.get_job(planner.job_id).constraints["base_sha"] == identity.base_sha

def test_remote_source_requires_claim_aware_factory(tmp_path):
    runtime, root, planner, identity = _remote_fixture(tmp_path)
    with pytest.raises(ExecutiveOperatorSupervisorError, match="claim-aware"):
        ExecutiveOperatorSupervisor(runtime, adapter_factory=lambda loader: None,
            workspace_identity_source=lambda attempt, job: identity,
            prompt_source=_PromptSource())


@pytest.mark.parametrize("field,value", [
    ("worktree", ""), ("worktree", None), ("worktree", "relative/path"),
    ("worktree", "/host/../alias"), ("worktree", "/host//alias"),
    ("base_sha", None), ("base_sha", ""),
])
def test_invalid_job_identity_refuses_before_host_lookup(tmp_path, field, value):
    import json
    runtime, root, planner, identity = _remote_fixture(tmp_path)
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        lease_owner="fixture")
    assert dispatch.attempt.status is AttemptStatus.CLAIMED
    with runtime.store.transaction() as connection:
        if field == "worktree":
            connection.execute("UPDATE jobs SET worktree=? WHERE job_id=?",
                               (value, planner.job_id))
        else:
            constraints = dict(planner.constraints, base_sha=value)
            connection.execute("UPDATE jobs SET constraints_json=? WHERE job_id=?",
                               (json.dumps(constraints), planner.job_id))
    job = runtime.jobs.get_job(planner.job_id)
    calls = []
    def source(attempt, claimed_job):
        calls.append("source")
        return replace(identity, workspace_path=job.worktree,
                       base_sha=job.constraints.get("base_sha"))
    def factory(*args, **kwargs):
        calls.append("factory")
        raise AssertionError("invalid identity reached construction")
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=factory, workspace_identity_source=source,
        prompt_source=_PromptSource())
    with pytest.raises(ExecutiveOperatorSupervisorError,
                       match="selected-host workspace identity"):
        supervisor._workspace_identity(job, dispatch.attempt)
    assert calls == []



@pytest.mark.parametrize("base", ["a" * 39, "A" * 40, "g" * 40])
def test_invalid_detached_base_refuses_before_host_lookup(tmp_path, base):
    # Runtime rejects malformed persisted SHAs and normalizes uppercase SHAs.
    # Exercise untrusted input at this boundary against a valid canonical Job.
    runtime, root, planner, identity = _remote_fixture(tmp_path)
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        lease_owner="fixture")
    job = runtime.jobs.get_job(planner.job_id)
    job = replace(job, constraints=dict(job.constraints, base_sha=base))
    calls = []
    def source(attempt, claimed_job):
        calls.append("source")
        return replace(identity, base_sha=base)
    def factory(*args, **kwargs):
        calls.append("factory")
        raise AssertionError("invalid identity reached construction")
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=factory, workspace_identity_source=source,
        prompt_source=_PromptSource())
    with pytest.raises(ExecutiveOperatorSupervisorError,
                       match="selected-host workspace identity"):
        supervisor._workspace_identity(job, dispatch.attempt)
    assert calls == []
