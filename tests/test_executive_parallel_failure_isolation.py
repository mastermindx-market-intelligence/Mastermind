"""Hermetic failure isolation for concurrent, independently placed COO work.

These fixtures exercise Runtime and COO semantics, not live provider readiness.
"""
from __future__ import annotations

from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import OrchestrationDispatchOutcome, Runtime
from test_executive_os_phase1fc import (
    _admit_v2_plan,
    _complete_ohf_role,
    _register_placement_union,
)


def test_failed_parallel_sibling_preserves_accepted_result_across_restart(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register_placement_union(runtime)
    runtime, root, plan, admitted = _admit_v2_plan(
        runtime,
        plan_schema_version="mastermind.execution_plan/v3",
        placements=[
            {"provider_realm": "codex", "quota_class": "codex-hf1q-step"},
            {
                "provider_realm": "claude-compatible-subscription",
                "quota_class": "claude-hf1q-step",
            },
        ],
    )
    by_step = {job.plan_step_id: job for job in admitted}
    accepted_job = by_step["step-0"]
    failed_job = by_step["step-1"]
    first = runtime.attempts.dispatch_cycle_job(
        accepted_job.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{accepted_job.job_id}:attempt:1",
        worker_id="worker-a",
        quota_class="codex-hf1q-step",
    )
    assert isinstance(first, OrchestrationDispatchOutcome)

    dispatched = []

    def dispatch_sibling(job_id, command_id):
        assert job_id == failed_job.job_id
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id="worker-b",
            quota_class="claude-hf1q-step",
        )
        assert isinstance(outcome, OrchestrationDispatchOutcome)
        dispatched.append(outcome)
        return outcome

    # The cycle must actually dispatch the independent sibling while first is live.
    outcome = CooCycle(runtime, dispatcher=dispatch_sibling).run_once(root.job_id)
    assert outcome.action == "DISPATCHED"
    assert len(dispatched) == 1
    second = dispatched[0]
    assert runtime.jobs.get_job(accepted_job.job_id).current_attempt_id == first.attempt.attempt_id

    _complete_ohf_role(
        runtime,
        first,
        {
            "schema_version": "mastermind.work_result/v1",
            "root_job_id": root.job_id,
            "plan_attempt_id": plan["plan_attempt_id"],
            "plan_digest": canonical_digest(plan),
            "plan_step_id": "step-0",
            "repair_round": 0,
            "artifacts": [],
            "evidence_digests": [],
        },
        identity_seed=114401,
    )
    accepted_before = runtime.jobs.get_job(accepted_job.job_id)
    attempts_before = runtime.attempts.list_attempts(accepted_job.job_id)
    events_before = runtime.events.list_events(job_id=accepted_job.job_id)
    assert second.lease_token is not None
    runtime.attempts.fail_attempt(
        second.attempt.attempt_id,
        fence_generation=second.attempt.fence_generation,
        lease_token=second.lease_token,
        payload={"summary": "Injected sibling failure", "errors": ["failed"]},
    )
    failed_before = runtime.jobs.get_job(failed_job.job_id)

    def no_dispatch(job_id, command_id):
        raise AssertionError(f"Unexpected replay of {job_id}: {command_id}")

    blocked = CooCycle(runtime, dispatcher=no_dispatch).run_once(root.job_id)
    assert blocked.action == "BLOCKED"
    assert blocked.selected_job_id == failed_job.job_id
    assert blocked.receipt["reason"] == "child_terminal_adverse"

    # Repeated ticks and reopening canonical storage cannot reset either sibling.
    for observed in (runtime, Runtime.at(tmp_path)):
        replay = CooCycle(observed, dispatcher=no_dispatch).run_once(root.job_id)
        assert replay.to_dict() == blocked.to_dict()
        assert observed.jobs.get_job(accepted_job.job_id) == accepted_before
        assert observed.attempts.list_attempts(accepted_job.job_id) == attempts_before
        assert observed.events.list_events(job_id=accepted_job.job_id) == events_before
        assert observed.jobs.get_job(failed_job.job_id) == failed_before
        assert not any(
            event.event_type == "JOB_REQUEUED"
            for event in observed.events.list_events(job_id=failed_job.job_id)
        )
