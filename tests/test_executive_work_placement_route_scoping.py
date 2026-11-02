"""Admitted cross-provider step placement is not same-Job failover.

Use the existing reviewed COO V3 plan producer, canonical Job/Attempt registry
and actual worker registrations. No provider/model run and no policy mutation.
"""
from __future__ import annotations

from control_plane.executive_runtime import Runtime
from test_executive_coo_ready_frontier import _admitted_pair


def test_admitted_provider_union_does_not_let_a_different_step_steal_this_job(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, codex_job, claude_job = _admitted_pair(runtime)
    # Both placements are source-authorized for the PLAN, not interchangeable
    # within a single sealed child Job created by that plan.
    assert codex_job.constraints["provider"] == "codex"
    assert codex_job.constraints["eligible_quota_classes"] == ["codex-hf1q-step"]
    assert claude_job.constraints["provider"] == "claude-compatible-subscription"
    assert claude_job.constraints["eligible_quota_classes"] == ["claude-hf1q-step"]
    assert len(runtime.jobs.list_jobs()) >= 3

    original_cmd = (
        f"coo-cycle:{root.job_id}:dispatch:{codex_job.job_id}:attempt:1"
    )
    before = len(runtime.events.list_events(job_id=codex_job.job_id))
    foreign = runtime.attempts.dispatch_cycle_job(
        codex_job.job_id, command_id=original_cmd,
        worker_id="worker-b", quota_class="claude-hf1q-step",
    )
    assert foreign is None
    parked = runtime.jobs.get_job(codex_job.job_id)
    assert parked.status.value == "QUEUED"
    assert parked.attempt_count == 0
    assert parked.current_attempt_id is None
    assert len(runtime.events.list_events(job_id=codex_job.job_id)) == before

    # The original authorized provider may still claim the same Job. No
    # rejection was written as a durable block or second carrier.
    original = runtime.attempts.dispatch_cycle_job(
        codex_job.job_id, command_id=original_cmd,
        worker_id="worker-a", quota_class="codex-hf1q-step",
    )
    assert original is not None and original.claimed_now
    assert original.attempt.worker_id == "worker-a"
    assert runtime.jobs.get_job(claude_job.job_id).status.value == "QUEUED"


def test_admitted_claude_step_does_not_fallback_into_codex_sibling(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, codex_job, claude_job = _admitted_pair(runtime)
    command = f"coo-cycle:{root.job_id}:dispatch:{claude_job.job_id}:attempt:1"
    denied = runtime.attempts.dispatch_cycle_job(
        claude_job.job_id, command_id=command,
        worker_id="worker-a", quota_class="codex-hf1q-step",
    )
    assert denied is None
    assert runtime.jobs.get_job(claude_job.job_id).attempt_count == 0
    claim = runtime.attempts.dispatch_cycle_job(
        claude_job.job_id, command_id=command,
        worker_id="worker-b", quota_class="claude-hf1q-step",
    )
    assert claim is not None and claim.attempt.worker_id == "worker-b"
