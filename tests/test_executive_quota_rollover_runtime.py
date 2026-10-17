"""Real Executive lifecycle, synthetic provider-release evidence; no provider launch."""
from __future__ import annotations

import json
import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_retry_safety import RetrySafetyDecision, classify_retry_safety
from control_plane.executive_runtime import Runtime


def _worker(runtime, name, provider="codex"):
    runtime.workers.register_worker(name, provider=provider, account_label=name,
        worker_type="mock", capabilities=["read", "research"],
        quota_classes={"default": {"provider": provider, "capabilities": ["read", "research"],
                                    "cost_class": "small"}})


def _fixture(tmp_path):
    runtime = Runtime.at(tmp_path)
    _worker(runtime, "pool-a")
    submitted = submit_intent(runtime, {
        "schema": INTENT_SCHEMA_V2, "intent_id": "QUOTA-CONTINUITY",
        "actor": "ceo-sol", "objective": "Preserve source census through quota rollover.",
        "department": "executive-infrastructure", "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {"requested_authorities": ["READ"], "attempt_limit": 2},
        "intent_kind": "executive_coo_cycle", "business_impact": "material",
    })
    root = runtime.jobs.get_job(submitted["job_id"])
    job = runtime.jobs.create_cycle_planner(root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0")
    dispatch = runtime.attempts.dispatch_cycle_job(job.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:1", worker_id="pool-a")
    attempt = dispatch.attempt
    now = runtime.store.now_ms()
    # Transport proof is explicitly fixture data, not real host acceptance.
    with runtime.store.transaction() as con:
        con.execute("UPDATE attempts SET execution_mode='OPERATOR_HARNESS', requested_execution_profile_json='{}', requested_execution_profile_digest=? WHERE attempt_id=?", (hashlib.sha256(b"{}").hexdigest(), attempt.attempt_id))
        con.execute("INSERT INTO harness_session_epochs(session_epoch_id,attempt_id,worker_id,"
                    "epoch_number,provider_session_id,state,created_at_ms) VALUES(?,?,?,1,?,'ABANDONED',?)",
                    ("quota-epoch", attempt.attempt_id, "pool-a", "quota-session", now - 3))
        con.execute("INSERT INTO process_generations(process_generation_id,session_epoch_id,worker_id,"
                    "provider_session_id,generation_number,started_at_ms,ended_at_ms,"
                    "executive_writer_held,provider_writer_state,created_at_ms) "
                    "VALUES(?,?,?,?,1,?,?,0,'RELEASED',?)",
                    ("quota-generation", "quota-epoch", "pool-a", "quota-session", now - 2, now - 1, now - 2))
        runtime.store.append_event(con, aggregate_type="process_generation", aggregate_id="quota-generation",
            event_type="OHF_GRACEFUL_STOP", actor="supervisor", job_id=job.job_id,
            attempt_id=attempt.attempt_id, worker_id="pool-a", quota_class="default",
            payload={"writer_released": True}, timestamp_ms=now - 1)
    runtime.attempts.rate_limit_attempt(attempt.attempt_id,
        fence_generation=attempt.fence_generation, lease_token=dispatch.lease_token,
        payload={"summary": "Census is done", "completed_steps": ["census"],
                 "artifacts": ["github:commit:accepted-census"], "next_actions": ["Review exact candidate"]})
    return runtime, root, job, attempt


def _project(runtime, job, attempt):
    return runtime.jobs.project_retry_safety(job.job_id, expected_attempt_id=attempt.attempt_id)


def _commit(runtime, root, job, attempt):
    return runtime.jobs.commit_coo_retry_decision(root.job_id, selected_job_id=job.job_id,
                                                expectation=_project(runtime, job, attempt))


def test_positive_release_reaches_existing_safe_classifier(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    projection = _project(runtime, job, attempt)
    assert classify_retry_safety(projection.evidence) is RetrySafetyDecision.SAFE_REQUEUE
    assert projection.requeue_kind == "NON_MODIFYING_QUOTA"


def test_same_job_checkpoint_and_exhausted_pool_survive_requeue(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    before = runtime.jobs.get_job(job.job_id).checkpoint
    outcome = _commit(runtime, root, job, attempt)
    assert outcome.action == "REQUEUED"
    observed = runtime.jobs.get_job(job.job_id)
    assert observed.status.value == "QUEUED"
    assert observed.current_attempt_id is None
    assert observed.checkpoint == before
    assert observed.attempt_count == 1
    with runtime.store.read() as con:
        quota = con.execute("SELECT * FROM worker_quota_classes WHERE worker_id='pool-a'").fetchone()
        assert quota["status"] == "RATE_LIMITED"
        assert quota["held_attempt_id"] is None
    # Restart does not require a second queue or session store.
    reopened = Runtime.at(tmp_path)
    assert reopened.jobs.get_job(job.job_id).checkpoint == before
    assert reopened.jobs.get_job(job.job_id).status.value == "QUEUED"


def test_duplicate_callbacks_have_one_durable_requeue(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    expectation = _project(runtime, job, attempt)

    def apply(_):
        owner = Runtime.at(tmp_path)
        return owner.jobs.commit_coo_retry_decision(root.job_id, selected_job_id=job.job_id,
                                                     expectation=expectation)

    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(executor.map(apply, range(30)))
    assert all(item.action == "REQUEUED" for item in outcomes)
    events = [event for event in runtime.events.list_events(job_id=job.job_id)
              if event.event_type == "JOB_REQUEUED"]
    assert len(events) == 1
    assert runtime.jobs.get_job(job.job_id).attempt_count == 1


@pytest.mark.parametrize("provider", ["codex", "claude", "glm"])
def test_no_slot_waits_then_other_pool_claims_same_job(tmp_path, provider):
    runtime, root, job, attempt = _fixture(tmp_path)
    assert _commit(runtime, root, job, attempt).action == "REQUEUED"
    old_receipt = next(event for event in runtime.events.list_events(job_id=job.job_id)
                       if event.event_type == "JOB_REQUEUED")
    cycle = CooCycle(runtime, dispatcher=lambda job_id, command_id:
        runtime.attempts.dispatch_cycle_job(job_id, command_id=command_id))
    waiting = cycle.run_once(root.job_id)
    assert waiting.action == "NO_ACTION"
    assert runtime.jobs.get_job(job.job_id).status.value == "QUEUED"
    assert runtime.jobs.get_job(job.job_id).attempt_count == 1
    _worker(runtime, "pool-b", provider=provider)
    ready = cycle.run_once(root.job_id)
    successor = runtime.jobs.get_job(job.job_id)
    assert successor.current_attempt_id != attempt.attempt_id
    assert successor.assigned_worker_id == "pool-b", (waiting, ready)
    assert successor.attempt_count == 2
    assert successor.checkpoint["completed_steps"] == ["census"]
    # Receipt read remains valid after successor work changes the logical Job.
    from control_plane.executive_runtime import _requeue_outcome_from_event
    with runtime.store.read() as con:
        event_row = con.execute("SELECT * FROM events WHERE event_id=?", (old_receipt.event_id,)).fetchone()
        assert _requeue_outcome_from_event(con, event_row, expected_job_id=job.job_id).requeue_kind == "NON_MODIFYING_QUOTA"
    assert runtime.jobs.get_job(job.job_id).current_attempt_id == successor.current_attempt_id


@pytest.mark.parametrize("mutation", [
    "UPDATE process_generations SET executive_writer_held=1",
])
def test_release_drift_between_projection_and_commit_cannot_requeue(tmp_path, mutation):
    runtime, root, job, attempt = _fixture(tmp_path)
    expectation = _project(runtime, job, attempt)
    with runtime.store.transaction() as con:
        con.execute(mutation)
    outcome = runtime.jobs.commit_coo_retry_decision(root.job_id, selected_job_id=job.job_id,
                                                    expectation=expectation)
    assert outcome.action != "REQUEUED"
    assert runtime.jobs.get_job(job.job_id).current_attempt_id == attempt.attempt_id


def test_original_coo_cycle_automatically_requeues_safe_quota_stop(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    outcome = CooCycle(runtime).run_once(root.job_id)
    assert outcome.action == "REQUEUED"
    assert runtime.jobs.get_job(job.job_id).status.value == "QUEUED"


def test_root_triage_explains_recovery_without_performing_it(tmp_path):
    from control_plane.executive_session_recovery import project_root_recovery
    runtime, root, job, attempt = _fixture(tmp_path)
    before = len(runtime.events.list_events())
    view = project_root_recovery(runtime, root.job_id)
    assert view["count_by_action"] == {"REQUEUE_WITH_EXISTING_COO": 1}
    assert view["jobs"][0]["attempt_id"] == attempt.attempt_id
    assert view["jobs"][0]["checkpoint_available"] is True
    assert view["jobs"][0]["queue_position"] is None
    assert len(runtime.events.list_events()) == before
    assert runtime.jobs.get_job(job.job_id).status.value == "RATE_LIMITED"
    assert _commit(runtime, root, job, attempt).action == "REQUEUED"
    assert project_root_recovery(runtime, root.job_id)["count_by_action"] == {"WAIT_FOR_EXISTING_SCHEDULER": 1}


def test_append_only_event_protection_remains_in_force(tmp_path):
    from control_plane.executive_runtime import StateConflict
    runtime, root, job, attempt = _fixture(tmp_path)
    with pytest.raises(StateConflict, match="immutable"):
        with runtime.store.transaction() as con:
            con.execute("DELETE FROM events WHERE event_type='OHF_GRACEFUL_STOP'")


def test_late_unknown_effect_blocks_an_already_projected_quota_retry(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    expected = _project(runtime, job, attempt)
    with runtime.store.transaction() as con:
        runtime.store.append_event(con, aggregate_type="job", aggregate_id=job.job_id,
            event_type="OPERATOR_OPERATION_EFFECT_UNKNOWN", actor="supervisor",
            job_id=job.job_id, attempt_id=attempt.attempt_id, worker_id="pool-a",
            quota_class="default", payload={"reason": "late source observation"})
    outcome = runtime.jobs.commit_coo_retry_decision(root.job_id, selected_job_id=job.job_id,
                                                    expectation=expected)
    assert outcome.action != "REQUEUED"


def test_queued_triage_retains_why_the_original_worker_stopped(tmp_path):
    from control_plane.executive_session_recovery import project_root_recovery
    runtime, root, job, attempt = _fixture(tmp_path)
    assert _commit(runtime, root, job, attempt).action == "REQUEUED"
    before = len(runtime.events.list_events())
    view = project_root_recovery(runtime, root.job_id)["jobs"][0]
    assert view["next_action"] == "WAIT_FOR_EXISTING_SCHEDULER"
    assert view["attempt_id"] is None
    assert view["previous_attempt_id"] == attempt.attempt_id
    assert view["previous_worker_id"] == "pool-a"
    assert view["stop_reason"] == "QUOTA_OR_RATE_LIMIT"
    assert view["stop_reason_scope"] == "previous_attempt"
    assert view["queue_position"] is None
    assert "requeued_after_quota_limit" in view["reason_codes"]
    assert len(runtime.events.list_events()) == before
