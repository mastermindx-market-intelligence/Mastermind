"""Checkpoint delivery through real Runtime, supervisor and adapter callback.

Only provider/process observations are simulated. No provider runs, no production
state is changed, and these tests do not assert paid-provider equivalence.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json

from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_retry_safety import classify_retry_safety, RetrySafetyDecision
from control_plane.executive_runtime import AttemptLease, Runtime
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.operator_harness_contract import CheckpointObservation, OperationId
from test_executive_operator_supervisor import _ActiveAdapter, _seed_dispatchable_operator_planner

FRONTIER = {
    "summary": "Source census complete; retain exact original-root responsibility.",
    "completed_steps": ["DO_NOT_REDO: inspected the accepted source revision"],
    "current_state": "No unfinished writes; next step is read-only verification.",
    "artifacts": ["github:commit:accepted-census", "agentos:pending-child-return"],
    "next_actions": ["Verify the saved candidate against the accepted source"],
    "errors": [],
}


def _prompt_source(runtime):
    return ExecutiveSupervisor(runtime, object(), inspector=object(), process_controller=object())


class _CheckpointAdapter(_ActiveAdapter):
    def checkpoint(self, *, operation_id, generation):
        return CheckpointObservation(FRONTIER, provider_mutated_state=False)


class _ConsumingAdapter(_ActiveAdapter):
    """Model substitute derives its result from the actual received checkpoint."""
    def begin_turn(self, *, turn, **kwargs):
        observation = super().begin_turn(turn=turn, **kwargs)
        prompt = self.prompts[-1]
        self.received_packet, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("{"):])
        assert self.received_packet["checkpoint"] == FRONTIER
        assert self.received_packet["authorities"] == ["READ"]
        assert self.received_packet["allowed_write_paths"] == []
        return observation

    def _canonical_result(self, turn):
        value = json.loads(super()._canonical_result(turn))
        value["role_result"]["steps"][0]["objective"] = self.received_packet["checkpoint"]["next_actions"][0]
        value["summary"] = "Continued from the retained checkpoint without repeating the source census."
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _checkpointed_predecessor(tmp_path, *, operation_stop):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a")
    lease = AttemptLease(dispatch.attempt, dispatch.lease_token)
    supervisor = ExecutiveOperatorSupervisor(runtime, adapter_factory=lambda loader: None,
                                             prompt_source=_prompt_source(runtime))
    adapter = _CheckpointAdapter(runtime, lambda turn: "not run", cancel_during_collect=False)
    orchestrator = supervisor._orchestrator(lease, adapter)
    requested = supervisor._requested_profile(planner, lease)
    session = orchestrator.start_attempt(attempt_id=lease.attempt.attempt_id,
        requested=requested, operation_id=OperationId("ohf-op:continuity-test-start"))
    observed = orchestrator.checkpoint(session, operation_id=OperationId("ohf-op:continuity-test-checkpoint"))
    assert observed.checkpoint_candidate == FRONTIER
    assert runtime.jobs.get_job(planner.job_id).checkpoint == FRONTIER
    if operation_stop:
        # The current production orchestrator path, not a synthetic legacy Event.
        orchestrator.graceful_stop(session, operation_id=OperationId("ohf-op:continuity-test-stop"))
    else:
        # Existing legacy typed Runtime release API. Provider observation is fake,
        # but generation identity, release/checkpoint Events and fences are real.
        stopped = dataclasses.replace(adapter.graceful_stop(session.generation),
                                      observed_config_digest=requested.expected_config_digest)
        runtime.operator_harness.record_graceful_stop(generation=session.generation,
            observation=stopped, fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token)
    runtime.operator_harness.abandon_epoch(epoch=session.epoch,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
    runtime.attempts.rate_limit_attempt(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
    return runtime, root, planner, lease.attempt


def test_generation_bound_checkpoint_is_persisted_before_the_provider_stop(tmp_path):
    runtime, root, planner, attempt = _checkpointed_predecessor(tmp_path, operation_stop=True)
    restored = Runtime.at(tmp_path / "runtime")
    assert restored.jobs.get_job(planner.job_id).checkpoint == FRONTIER
    assert restored.jobs.get_job(planner.job_id).current_attempt_id == attempt.attempt_id
    events = runtime.events.list_events(job_id=planner.job_id)
    assert any(event.event_type == "JOB_RATE_LIMITED" for event in events)
    assert any(event.event_type == "OPERATOR_OPERATION_APPLIED" for event in events)
    assert not any(event.event_type == "OHF_GRACEFUL_STOP" for event in events)


def test_current_operation_stop_stays_held_without_legacy_quota_release_proof(tmp_path):
    runtime, root, planner, attempt = _checkpointed_predecessor(tmp_path, operation_stop=True)
    expected = runtime.jobs.project_retry_safety(planner.job_id, expected_attempt_id=attempt.attempt_id)
    assert classify_retry_safety(expected.evidence) is not RetrySafetyDecision.SAFE_REQUEUE
    assert expected.evidence.effect_unknown is True  # positive quota proof is absent
    assert runtime.jobs.get_job(planner.job_id).status.value == "RATE_LIMITED"
    assert runtime.jobs.get_job(planner.job_id).checkpoint == FRONTIER


def test_same_model_other_pool_successor_consumes_checkpoint_after_runtime_reopen(tmp_path):
    runtime, root, planner, predecessor = _checkpointed_predecessor(tmp_path, operation_stop=False)
    expected = runtime.jobs.project_retry_safety(planner.job_id, expected_attempt_id=predecessor.attempt_id)
    assert classify_retry_safety(expected.evidence) is RetrySafetyDecision.SAFE_REQUEUE
    outcome = runtime.jobs.commit_coo_retry_decision(root.job_id, selected_job_id=planner.job_id,
                                                    expectation=expected)
    assert outcome.action == "REQUEUED"
    quota = runtime.workers.get_quota_class("worker-a", predecessor.quota_class)
    runtime.workers.register_worker("worker-b", provider=quota.provider, account_label="pool-b-fixture",
        worker_type="fixture", capabilities=quota.capabilities,
        quota_classes={quota.quota_class: {
            "provider": quota.provider, "model": quota.model, "effort": quota.effort,
            "cost_class": quota.cost_class, "capabilities": quota.capabilities, "metadata": quota.metadata}})
    # Recreate Runtime and prompt producer. No retained Python prompt/memory is reused.
    runtime = Runtime.at(tmp_path / "runtime")
    adapters = []
    def factory(loader):
        adapter = _ConsumingAdapter(runtime, loader, cancel_during_collect=False)
        adapter.provider_session_id = "SESSION-SUCCESSOR"
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime, adapter_factory=factory,
                                             prompt_source=_prompt_source(runtime))
    result = asyncio.run(supervisor.start_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:2"))
    assert result.outcome == "TERMINAL"
    job = runtime.jobs.get_job(planner.job_id)
    assert job.job_id == planner.job_id and job.root_job_id == root.job_id
    assert job.status.value == "COMPLETED"
    assert job.attempt_count == 2 and job.current_attempt_id != predecessor.attempt_id
    assert job.assigned_worker_id == "worker-b"
    assert len(adapters) == 1 and adapters[0].begin_turn_calls == 1
    assert adapters[0].received_packet["checkpoint"] == FRONTIER
    assert adapters[0].received_packet["run_id"] == job.current_attempt_id
    assert runtime.workers.get_quota_class("worker-a", predecessor.quota_class).status.value == "RATE_LIMITED"
    seals = [event for event in runtime.events.list_events(job_id=planner.job_id)
             if event.event_type == "ORCHESTRATION_ROLE_RESULT_SEALED"]
    assert len(seals) == 1
    assert FRONTIER["next_actions"][0] in json.dumps(seals[0].payload)
    assert not any(event.event_type == "OPERATOR_OPERATION_EFFECT_UNKNOWN"
                   for event in runtime.events.list_events(job_id=planner.job_id))
