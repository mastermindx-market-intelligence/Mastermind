"""Bounded ready-frontier behavior for the existing Executive COO cycle."""
from __future__ import annotations

import dataclasses

from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import OrchestrationDispatchOutcome, Runtime
from test_executive_os_phase1fc import _admit_v2_plan, _register_placement_union

_CODEX = {"provider_realm": "codex", "quota_class": "codex-hf1q-step"}
_CLAUDE = {
    "provider_realm": "claude-compatible-subscription",
    "quota_class": "claude-hf1q-step",
}


def _admitted_pair(runtime: Runtime):
    _register_placement_union(runtime)
    runtime, root, _plan, admitted = _admit_v2_plan(
        runtime,
        placements=[_CODEX, _CLAUDE],
    )
    by_step = {job.plan_step_id: job for job in admitted}
    return root, by_step["step-0"], by_step["step-1"]


def _start_first(runtime: Runtime, root_id: str, job_id: str):
    outcome = runtime.attempts.dispatch_cycle_job(
        job_id,
        command_id=f"coo-cycle:{root_id}:dispatch:{job_id}:attempt:1",
        worker_id="worker-a",
        quota_class="codex-hf1q-step",
    )
    assert isinstance(outcome, OrchestrationDispatchOutcome)
    return outcome


def test_live_read_only_work_does_not_starve_ready_sibling(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    first_dispatch = _start_first(runtime, root.job_id, first.job_id)
    calls: list[str] = []

    def dispatch(job_id: str, command_id: str):
        calls.append(job_id)
        job = runtime.jobs.get_job(job_id)
        assert job is not None
        worker = "worker-a" if job.plan_step_id == "step-0" else "worker-b"
        quota = "codex-hf1q-step" if worker == "worker-a" else "claude-hf1q-step"
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id=worker,
            quota_class=quota,
        )
        assert outcome is not None
        return outcome

    outcome = CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)

    assert outcome.action == "DISPATCHED"
    assert outcome.selected_job_id == second.job_id
    assert calls == [second.job_id]
    assert runtime.jobs.get_job(first.job_id).current_attempt_id == (
        first_dispatch.attempt.attempt_id
    )
    assert runtime.jobs.get_job(first.job_id).attempt_count == 1
    assert runtime.jobs.get_job(second.job_id).attempt_count == 1


def test_expired_active_attempt_keeps_reconciliation_priority(tmp_path):
    now_ms = [1_800_000_000_000]
    runtime = Runtime.at(
        tmp_path,
        clock=lambda: now_ms[0],
        lease_seconds=30,
    )
    root, first, second = _admitted_pair(runtime)
    first_dispatch = _start_first(runtime, root.job_id, first.job_id)
    now_ms[0] += 31_000
    calls: list[str] = []

    def reconcile(job_id: str, command_id: str):
        calls.append(job_id)
        return first_dispatch

    outcome = CooCycle(runtime, dispatcher=reconcile).run_once(root.job_id)

    assert outcome.action == "DISPATCHED"
    assert outcome.selected_job_id == first.job_id
    assert calls == [first.job_id]
    assert runtime.jobs.get_job(second.job_id).attempt_count == 0


def _register_codex_peer(runtime: Runtime, worker_id: str) -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}@company",
        worker_type="mock",
        capabilities=["read", "research"],
        quota_classes={
            "codex-hf1q-step": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "metadata": {
                    "routing_policy_version": "fph0-routing",
                    "execution_profile_id": "fph0-execution",
                    "execution_profile_digest": "b" * 64,
                    "capability_policy_version": "fph0-capability",
                    "capability_policy_digest": "c" * 64,
                },
            }
        },
    )


def test_two_live_read_only_children_do_not_starve_third_ready_sibling(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register_placement_union(runtime)
    _register_codex_peer(runtime, "worker-c")
    runtime, root, _plan, admitted = _admit_v2_plan(
        runtime,
        placements=[_CODEX, _CLAUDE, _CODEX],
    )
    by_step = {job.plan_step_id: job for job in admitted}
    first = by_step["step-0"]
    _start_first(runtime, root.job_id, first.job_id)

    workers = {
        "step-0": ("worker-a", "codex-hf1q-step"),
        "step-1": ("worker-b", "claude-hf1q-step"),
        "step-2": ("worker-c", "codex-hf1q-step"),
    }
    calls: list[str] = []

    def dispatch(job_id: str, command_id: str):
        job = runtime.jobs.get_job(job_id)
        assert job is not None
        calls.append(str(job.plan_step_id))
        worker, quota = workers[str(job.plan_step_id)]
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id=worker,
            quota_class=quota,
        )
        assert outcome is not None
        return outcome

    cycle = CooCycle(runtime, dispatcher=dispatch)
    second = cycle.run_once(root.job_id)
    third = cycle.run_once(root.job_id)

    assert second.selected_job_id == by_step["step-1"].job_id
    assert third.selected_job_id == by_step["step-2"].job_id
    assert calls == ["step-1", "step-2"]
    assert all(runtime.jobs.get_job(job.job_id).attempt_count == 1 for job in admitted)


def test_ready_frontier_refuses_write_capable_sibling(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    _start_first(runtime, root.job_id, first.job_id)
    active = runtime.jobs.get_job(first.job_id)
    candidate = runtime.jobs.get_job(second.job_id)
    assert active is not None and candidate is not None

    write_candidate = dataclasses.replace(
        candidate,
        requested_authorities=["READ", "WRITE_BRANCH"],
        allowed_write_paths=["control_plane/example.py"],
    )
    cycle = CooCycle(runtime, dispatcher=lambda _job, _command: None)

    assert cycle._is_read_only_frontier_work(candidate)
    assert not cycle._is_read_only_frontier_work(write_candidate)
    assert not cycle._ready_frontier_candidate(write_candidate, [active])
