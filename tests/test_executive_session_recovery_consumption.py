"""Checkpoint delivery through real Runtime, supervisor and adapter callback.

Only provider/process observations are simulated. No provider runs, no production
state is changed, and these tests do not assert paid-provider equivalence.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest

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
    # The original COO root must ingest the completed replacement planner
    # rather than leaving its logically returned plan inaccessible.
    from control_plane.executive_coo_cycle import CooCycle
    admission = CooCycle(runtime, dispatcher=lambda *_: None).run_once(root.job_id)
    assert admission.action == "PLAN_ADMITTED"
    work = [item for item in runtime.jobs.list_jobs()
            if item.root_job_id == root.job_id and item.orchestration_role == "work"]
    assert len(work) == 1
    assert work[0].objective == FRONTIER["next_actions"][0]
    assert work[0].parent_job_id == root.job_id
    # A repeated parent notification cannot materialize another work child:
    # the canonical deterministic plan-admission command must reconcile.
    admission_command = (
        f"coo-cycle:{root.job_id}:admit-plan:{job.current_attempt_id}"
    )
    replayed = runtime.jobs.admit_cycle_plan(root.job_id, command_id=admission_command)
    assert len(replayed) == 1 and replayed[0].job_id == work[0].job_id
    assert sum(e.event_type == "COO_PLAN_ADMITTED"
               for e in runtime.events.list_events(job_id=root.job_id)) == 1


def test_root_triage_identifies_modern_stop_receipt_gap_without_authorizing_requeue(tmp_path):
    from control_plane.executive_session_recovery import project_root_recovery
    runtime, root, planner, attempt = _checkpointed_predecessor(tmp_path, operation_stop=True)
    before = len(runtime.events.list_events())
    view = project_root_recovery(runtime, root.job_id)
    item = next(value for value in view["jobs"] if value["job_id"] == planner.job_id)
    assert "modern_stop_applied_but_quota_proof_not_recognized" in item["reason_codes"]
    assert item["quota_stop_receipt_gap"] == "MODERN_STOP_NOT_LEGACY_QUOTA_PROOF"
    assert item["next_action"] == "RECONCILE_ORIGINAL_ATTEMPT"
    assert item["retry_decision"] != "SAFE_REQUEUE"
    assert view["operation_performed"] is False
    assert len(runtime.events.list_events()) == before
    assert runtime.jobs.get_job(planner.job_id).status.value == "RATE_LIMITED"


def test_legacy_positive_graceful_stop_never_claims_modern_receipt_gap(tmp_path):
    from control_plane.executive_session_recovery import project_root_recovery
    runtime, root, planner, attempt = _checkpointed_predecessor(tmp_path, operation_stop=False)
    item = project_root_recovery(runtime, root.job_id)["jobs"][0]
    assert item["quota_stop_receipt_gap"] is None
    assert "modern_stop_applied_but_quota_proof_not_recognized" not in item["reason_codes"]
    assert item["next_action"] == "REQUEUE_WITH_EXISTING_COO"


def test_spoofed_modern_stop_for_unknown_generation_is_not_a_proven_gap(tmp_path):
    from control_plane.executive_runtime import OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION
    from control_plane.executive_session_recovery import _modern_stop_without_legacy_quota_proof
    runtime, root, planner, attempt = _checkpointed_predecessor(tmp_path, operation_stop=False)
    with runtime.store.transaction() as con:
        runtime.store.append_event(
            con, aggregate_type="operator_operation", aggregate_id="forged-stop",
            event_type="OPERATOR_OPERATION_APPLIED", command_id="forged-stop:applied",
            actor="supervisor", job_id=planner.job_id, attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id, quota_class=attempt.quota_class,
            payload={
                "schema_version": OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION,
                "operation_kind":"graceful_stop",
                "process_generation_id":"unbound-other-generation",
                "process_liveness":"PROVEN_DEAD",
                "provider_writer_state":"RELEASED",
                "executive_writer_released":True,
            },
        )
    with runtime.store.read() as con:
        assert not _modern_stop_without_legacy_quota_proof(
            con, job_id=planner.job_id, attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id, quota_class=attempt.quota_class,
        )


def test_nonrelease_modern_operation_is_not_labeled_as_stop_gap(tmp_path):
    from control_plane.executive_session_recovery import _modern_stop_without_legacy_quota_proof
    runtime, root, planner, attempt = _checkpointed_predecessor(tmp_path, operation_stop=False)
    with runtime.store.read() as con:
        assert not _modern_stop_without_legacy_quota_proof(
            con, job_id=planner.job_id, attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id, quota_class=attempt.quota_class,
        )


@pytest.mark.parametrize("replacement_provider", ["claude", "glm"])
def test_unqualified_cross_provider_registration_cannot_steal_original_checkpoint(
    tmp_path, replacement_provider,
):
    """A free different provider is not an admitted replacement for a Codex Job."""
    from control_plane.executive_session_recovery import project_root_recovery
    runtime, root, planner, predecessor = _checkpointed_predecessor(
        tmp_path, operation_stop=False,
    )
    expected = runtime.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=predecessor.attempt_id,
    )
    assert runtime.jobs.commit_coo_retry_decision(
        root.job_id, selected_job_id=planner.job_id,
        expectation=expected,
    ).action == "REQUEUED"
    quota = runtime.workers.get_quota_class(
        "worker-a", predecessor.quota_class,
    )
    runtime.workers.register_worker(
        "worker-b", provider=replacement_provider,
        account_label="alternate-provider-fixture", worker_type="fixture",
        capabilities=quota.capabilities,
        quota_classes={
            quota.quota_class: {
                "provider": replacement_provider,
                "model": quota.model, "effort": quota.effort,
                "cost_class": quota.cost_class,
                "capabilities": quota.capabilities,
                "metadata": quota.metadata,
            }
        },
    )
    runtime = Runtime.at(tmp_path / "runtime")
    before = len(runtime.events.list_events(job_id=planner.job_id))
    result = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:2",
        worker_id="worker-b",
    )
    assert result is None
    pending = runtime.jobs.get_job(planner.job_id)
    assert pending.current_attempt_id is None
    assert pending.status.value == "QUEUED"
    assert pending.checkpoint == FRONTIER
    assert pending.attempt_count == 1
    view = project_root_recovery(runtime, root.job_id)["jobs"][0]
    assert view["registered_supply"]["registered_free_count"] == 1
    assert view["registered_supply"]["provider_bound_free_count"] == 0
    assert view["registered_supply"]["route_qualified"] is False
    assert view["next_action"] == "WAIT_FOR_EXISTING_SCHEDULER"
    assert len(runtime.events.list_events(job_id=planner.job_id)) == before
