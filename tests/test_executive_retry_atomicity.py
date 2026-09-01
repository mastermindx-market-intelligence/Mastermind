"""Deterministic atomicity proofs for the COO retry transaction fence."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import (
    CooRetryMutationOutcome,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
)


def _intent(intent_id: str) -> dict[str, object]:
    return {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": intent_id,
        "actor": "ceo-sol",
        "objective": "Prove one atomic retry decision.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {
            "mastermind_sha": "a" * 40,
            "macro_sha": "b" * 40,
        },
        "execution_contract": {
            "requested_authorities": ["READ"],
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "material",
    }


def _register(runtime: Runtime) -> None:
    runtime.workers.register_worker(
        "worker-a",
        provider="codex",
        account_label="worker-a@company",
        worker_type="mock",
        capabilities=["read", "research"],
        quota_classes={
            "default": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
            }
        },
    )


def _safe_tx9_fixture(tmp_path, *, intent_id: str):
    runtime = Runtime.at(tmp_path)
    _register(runtime)
    submitted = submit_intent(runtime, _intent(intent_id))
    root = runtime.jobs.get_job(submitted["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
        ),
        worker_id="worker-a",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)
    attempt = dispatch.attempt
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE attempts SET execution_mode='OPERATOR_HARNESS',
              requested_execution_profile_json='{}',
              requested_execution_profile_digest=? WHERE attempt_id=?
            """,
            (hashlib.sha256(b"{}").hexdigest(), attempt.attempt_id),
        )
        connection.execute(
            """
            INSERT INTO harness_session_epochs(
              session_epoch_id,attempt_id,worker_id,epoch_number,
              provider_session_id,state,created_at_ms
            ) VALUES(?,?,?,1,?,'CURRENT',1)
            """,
            (
                f"EPOCH-{intent_id}",
                attempt.attempt_id,
                attempt.worker_id,
                f"SESSION-{intent_id}",
            ),
        )
        connection.execute(
            """
            INSERT INTO process_generations(
              process_generation_id,session_epoch_id,worker_id,
              provider_session_id,generation_number,started_at_ms,
              executive_writer_held,provider_writer_state,created_at_ms
            ) VALUES(?,?,?,?,1,1,1,'HELD',1)
            """,
            (
                f"GEN-{intent_id}",
                f"EPOCH-{intent_id}",
                attempt.worker_id,
                f"SESSION-{intent_id}",
            ),
        )
    assert runtime.operator_harness.invalidate_after_restore() == 1
    return runtime, root, planner, attempt


def _failed_orchestration_fixture(tmp_path, *, intent_id: str):
    runtime = Runtime.at(tmp_path)
    _register(runtime)
    submitted = submit_intent(runtime, _intent(intent_id))
    root = runtime.jobs.get_job(submitted["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)
    assert dispatch.lease_token is not None
    runtime.attempts.fail_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        payload={"summary": "fixture failure", "errors": ["failed"]},
    )
    return runtime, root, planner, dispatch.attempt


def _retry_events(runtime: Runtime, job_id: str):
    return [
        event
        for event in runtime.events.list_events(job_id=job_id)
        if event.event_type == "JOB_REQUEUED"
    ]


def _block_events(runtime: Runtime, root_job_id: str):
    return [
        event
        for event in runtime.events.list_events(job_id=root_job_id)
        if event.event_type == "COO_CYCLE_BLOCKED"
    ]


def test_two_runtime_instances_reconcile_one_identical_retry_without_stale_block(
    tmp_path,
):
    first, root, planner, attempt = _safe_tx9_fixture(
        tmp_path, intent_id="ATOMIC-SAME-CYCLE"
    )
    second = Runtime.at(tmp_path)
    first_projection = first.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=attempt.attempt_id
    )
    second_projection = second.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=attempt.attempt_id
    )
    barrier = threading.Barrier(2)

    def commit(runtime: Runtime, projection) -> CooRetryMutationOutcome:
        barrier.wait()
        return runtime.jobs.commit_coo_retry_decision(
            root.job_id,
            selected_job_id=planner.job_id,
            expectation=projection,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda item: commit(*item),
                ((first, first_projection), (second, second_projection)),
            )
        )

    assert [outcome.action for outcome in outcomes] == ["REQUEUED", "REQUEUED"]
    assert outcomes[0].receipt == outcomes[1].receipt
    assert len(_retry_events(first, planner.job_id)) == 1
    assert _block_events(first, root.job_id) == []
    assert len(first.attempts.list_attempts(planner.job_id)) == 1


def test_legacy_public_requeue_refuses_fresh_failed_orchestration_mutation(tmp_path):
    runtime, _, planner, _ = _failed_orchestration_fixture(
        tmp_path, intent_id="ATOMIC-BYPASS-FAILED"
    )
    job_before = runtime.jobs.get_job(planner.job_id)
    events_before = runtime.events.list_events()

    with pytest.raises(StateConflict, match="atomic COO retry decision"):
        runtime.jobs.requeue_job(planner.job_id)

    assert runtime.jobs.get_job(planner.job_id) == job_before
    assert runtime.events.list_events() == events_before


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "decision",
        "evidence",
        "digest",
        "outer_digest",
        "correlated_evidence",
    ],
)
def test_durable_blocked_retry_receipt_mutation_is_rejected_everywhere(
    tmp_path, mutation
):
    runtime, root, planner, attempt = _failed_orchestration_fixture(
        tmp_path, intent_id=f"ATOMIC-BLOCK-RECEIPT-{mutation.upper()}"
    )
    projection = runtime.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=attempt.attempt_id
    )
    blocked = runtime.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=projection,
    )
    assert blocked.action == "BLOCKED"
    command = blocked.command_id
    with runtime.store.transaction() as connection:
        row = connection.execute(
            "SELECT payload_json FROM events WHERE command_id=?", (command,)
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row["payload_json"]))
        retry_safety = payload["evidence"]["retry_safety"]
        if mutation == "schema":
            retry_safety["schema_version"] = "mastermind.executive_retry_safety_receipt/v2"
        elif mutation == "decision":
            retry_safety["decision"] = "SAFE_REQUEUE"
        elif mutation == "evidence":
            retry_safety["evidence"]["effect_unknown"] = True
        elif mutation == "digest":
            retry_safety["evidence_digest"] = "0" * 64
        elif mutation == "correlated_evidence":
            retry_safety["evidence"]["result_present"] = False
            retry_safety["decision"] = "NEEDS_SOL"
            retry_safety["evidence_digest"] = hashlib.sha256(
                json.dumps(
                    retry_safety["evidence"],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
        else:
            payload["evidence_digest"] = "0" * 64
        if mutation != "outer_digest":
            payload["evidence_digest"] = hashlib.sha256(
                json.dumps(
                    payload["evidence"],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
        connection.execute("DROP TRIGGER events_are_immutable_update")
        connection.execute(
            "UPDATE events SET payload_json=? WHERE command_id=?",
            (
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                command,
            ),
        )
        connection.execute(
            """
            CREATE TRIGGER events_are_immutable_update
            BEFORE UPDATE ON events BEGIN
              SELECT RAISE(ABORT, 'events are immutable');
            END
            """
        )
    job_before = runtime.jobs.get_job(planner.job_id)
    attempts_before = runtime.attempts.list_attempts(planner.job_id)
    events_before = runtime.events.list_events()

    with pytest.raises(StateConflict, match="COO|retry-safety"):
        runtime.jobs.commit_coo_retry_decision(
            root.job_id,
            selected_job_id=planner.job_id,
            expectation=projection,
        )
    with pytest.raises(StateConflict, match="COO|retry-safety"):
        CooCycle(runtime).run_once(root.job_id)

    assert runtime.jobs.get_job(planner.job_id) == job_before
    assert runtime.attempts.list_attempts(planner.job_id) == attempts_before
    assert runtime.events.list_events() == events_before


def test_block_cycle_refuses_fresh_self_consistent_but_unobserved_retry_receipt(
    tmp_path,
):
    runtime, root, planner, attempt = _failed_orchestration_fixture(
        tmp_path, intent_id="ATOMIC-BLOCK-FRESH-INVALID"
    )
    projection = runtime.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=attempt.attempt_id
    )
    evidence = projection.evidence.to_dict()
    evidence["result_present"] = False
    receipt = {
        "schema_version": "mastermind.executive_retry_safety_receipt/v1",
        "decision": "NEEDS_SOL",
        "evidence": evidence,
        "evidence_digest": hashlib.sha256(
            json.dumps(
                evidence,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest(),
    }
    events_before = runtime.events.list_events()
    job_before = runtime.jobs.get_job(planner.job_id)

    with pytest.raises(StateConflict, match="Runtime evidence"):
        runtime.jobs.block_cycle(
            root.job_id,
            selected_job_id=planner.job_id,
            reason="state_conflict",
            command_id=(
                f"coo-cycle:{root.job_id}:block:state_conflict:{planner.job_id}"
            ),
            evidence={"retry_safety": receipt},
        )

    assert runtime.events.list_events() == events_before
    assert runtime.jobs.get_job(planner.job_id) == job_before


def test_legacy_public_requeue_refuses_fresh_tx9_orchestration_mutation(tmp_path):
    runtime, root, planner, attempt = _safe_tx9_fixture(
        tmp_path, intent_id="ATOMIC-BYPASS-TX9"
    )
    job_before = runtime.jobs.get_job(planner.job_id)
    events_before = runtime.events.list_events()
    command = f"coo-cycle:{root.job_id}:requeue:{planner.job_id}:{attempt.attempt_id}"

    with pytest.raises(StateConflict, match="atomic COO retry decision"):
        runtime.jobs.requeue_job(planner.job_id, command_id=command)

    assert runtime.jobs.get_job(planner.job_id) == job_before
    assert runtime.events.list_events() == events_before


def test_different_prior_cycle_block_prevents_later_safe_retry_commit(tmp_path):
    first, root, planner, attempt = _safe_tx9_fixture(
        tmp_path, intent_id="ATOMIC-PRIOR-BLOCK"
    )
    second = Runtime.at(tmp_path)
    projection = first.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=attempt.attempt_id
    )
    job_before = first.jobs.get_job(planner.job_id)
    attempt_before = first.attempts.list_attempts(planner.job_id)
    second.jobs.block_cycle(
        root.job_id,
        selected_job_id=planner.job_id,
        reason="invalid_policy",
        command_id=f"coo-cycle:{root.job_id}:block:invalid_policy:{planner.job_id}",
    )

    outcome = first.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=projection,
    )

    assert outcome.action == "RECONCILIATION_REQUIRED"
    assert outcome.receipt["effect_state"] == "NONE"
    assert outcome.receipt["reason"] == "prior_block_drift"
    assert first.jobs.get_job(planner.job_id) == job_before
    assert first.attempts.list_attempts(planner.job_id) == attempt_before
    assert _retry_events(first, planner.job_id) == []
    assert len(_block_events(first, root.job_id)) == 1


@pytest.mark.parametrize(
    "mutation",
    ["schema", "decision", "evidence", "digest"],
)
def test_durable_retry_safety_receipt_mutation_is_rejected_on_replay(
    tmp_path, mutation
):
    runtime, root, planner, attempt = _safe_tx9_fixture(
        tmp_path, intent_id=f"ATOMIC-RECEIPT-{mutation.upper()}"
    )
    projection = runtime.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=attempt.attempt_id
    )
    applied = runtime.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=projection,
    )
    assert applied.action == "REQUEUED"
    command = applied.command_id
    with runtime.store.transaction() as connection:
        row = connection.execute(
            "SELECT payload_json FROM events WHERE command_id=?", (command,)
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row["payload_json"]))
        retry_safety = payload["retry_safety"]
        if mutation == "schema":
            retry_safety["schema_version"] = "mastermind.executive_retry_safety_receipt/v2"
        elif mutation == "decision":
            retry_safety["decision"] = "NEEDS_SOL"
        elif mutation == "evidence":
            retry_safety["evidence"]["effect_unknown"] = True
        else:
            retry_safety["evidence_digest"] = "0" * 64
        # Simulate below-Runtime durable corruption while restoring the schema's
        # immutable-Event guard in the same transaction.  The replay path must
        # independently reject malformed historical bytes.
        connection.execute("DROP TRIGGER events_are_immutable_update")
        connection.execute(
            "UPDATE events SET payload_json=? WHERE command_id=?",
            (
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                command,
            ),
        )
        connection.execute(
            """
            CREATE TRIGGER events_are_immutable_update
            BEFORE UPDATE ON events BEGIN
              SELECT RAISE(ABORT, 'events are immutable');
            END
            """
        )
    job_before = runtime.jobs.get_job(planner.job_id)
    attempts_before = runtime.attempts.list_attempts(planner.job_id)
    events_before = runtime.events.list_events()

    with pytest.raises(StateConflict, match="retry-safety"):
        runtime.jobs.commit_coo_retry_decision(
            root.job_id,
            selected_job_id=planner.job_id,
            expectation=projection,
        )

    assert runtime.jobs.get_job(planner.job_id) == job_before
    assert runtime.attempts.list_attempts(planner.job_id) == attempts_before
    assert runtime.events.list_events() == events_before


@pytest.mark.parametrize(
    "event_type",
    [
        "OPERATOR_OPERATION_EFFECT_UNKNOWN",
        "OHF_CANDIDATE_RESULT_RECORDED",
        "ORCHESTRATION_ROLE_RESULT_SEALED",
    ],
)
def test_late_effect_evidence_returns_typed_no_effect_reconciliation(
    tmp_path, event_type
):
    first, root, planner, attempt = _safe_tx9_fixture(
        tmp_path, intent_id="ATOMIC-EVIDENCE-DRIFT"
    )
    second = Runtime.at(tmp_path)
    projection = first.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=attempt.attempt_id
    )
    with second.store.transaction() as connection:
        second.store.append_event(
            connection,
            aggregate_type="operator_operation",
            aggregate_id="late-effect",
            event_type=event_type,
            command_id=f"late-{event_type.lower()}",
            actor="supervisor",
            job_id=planner.job_id,
            attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id,
            quota_class=attempt.quota_class,
            payload={"phase": "provider_response_missing"},
        )

    outcome = first.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=projection,
    )

    assert outcome.action == "RECONCILIATION_REQUIRED"
    assert outcome.receipt["effect_state"] == "NONE"
    assert outcome.receipt["reason"] == "retry_expectation_drift"
    assert _retry_events(first, planner.job_id) == []
    assert _block_events(first, root.job_id) == []
    assert len(first.attempts.list_attempts(planner.job_id)) == 1


def test_late_writer_and_moved_attempt_each_fail_closed_without_block(tmp_path):
    runtime, root, planner, attempt = _safe_tx9_fixture(
        tmp_path, intent_id="ATOMIC-WRITER-DRIFT"
    )
    projection = runtime.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=attempt.attempt_id
    )
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE process_generations SET executive_writer_held=1,
              provider_writer_state='HELD'
            WHERE session_epoch_id IN (
              SELECT session_epoch_id FROM harness_session_epochs WHERE attempt_id=?
            )
            """,
            (attempt.attempt_id,),
        )
    writer_drift = runtime.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=projection,
    )
    assert writer_drift.action == "RECONCILIATION_REQUIRED"
    assert writer_drift.receipt["effect_state"] == "NONE"
    assert _retry_events(runtime, planner.job_id) == []
    assert _block_events(runtime, root.job_id) == []

    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE process_generations SET executive_writer_held=0, provider_writer_state='RELEASED'"
        )
        connection.execute(
            """
            UPDATE jobs SET status='QUEUED',current_attempt_id=NULL,
              assigned_worker_id=NULL,assigned_quota_class=NULL WHERE job_id=?
            """,
            (planner.job_id,),
        )
    moved = runtime.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=projection,
    )
    assert moved.action == "RECONCILIATION_REQUIRED"
    assert moved.receipt["effect_state"] == "NONE"
    assert _retry_events(runtime, planner.job_id) == []
    assert _block_events(runtime, root.job_id) == []


def test_command_replay_precedes_moved_state_but_changed_expectation_is_refused(
    tmp_path,
):
    runtime, root, planner, attempt = _safe_tx9_fixture(
        tmp_path, intent_id="ATOMIC-REPLAY"
    )
    projection = runtime.jobs.project_retry_safety(
        planner.job_id, expected_attempt_id=attempt.attempt_id
    )
    applied = runtime.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=projection,
    )
    assert applied.action == "REQUEUED"

    restarted = Runtime.at(tmp_path)
    replay = restarted.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=projection,
    )
    changed = restarted.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=dataclasses.replace(
            projection, retry_evidence_digest="0" * 64
        ),
    )
    changed_kind = restarted.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=dataclasses.replace(projection, requeue_kind="ORDINARY"),
    )
    changed_tx9_digest = restarted.jobs.commit_coo_retry_decision(
        root.job_id,
        selected_job_id=planner.job_id,
        expectation=dataclasses.replace(
            projection, tx9_evidence_digest="1" * 64
        ),
    )

    assert replay.action == "REQUEUED"
    assert replay.receipt == applied.receipt
    assert changed.action == "RECONCILIATION_REQUIRED"
    assert changed.receipt["effect_state"] == "NONE"
    assert changed.receipt["reason"] == "command_expectation_conflict"
    assert changed_kind.action == "RECONCILIATION_REQUIRED"
    assert changed_kind.receipt["effect_state"] == "NONE"
    assert changed_tx9_digest.action == "RECONCILIATION_REQUIRED"
    assert changed_tx9_digest.receipt["effect_state"] == "NONE"
    assert len(_retry_events(restarted, planner.job_id)) == 1
    assert _block_events(restarted, root.job_id) == []


def test_coo_cycle_race_reconciles_committed_retry_and_never_calls_provider(
    tmp_path,
):
    first, root, planner, attempt = _safe_tx9_fixture(
        tmp_path, intent_id="ATOMIC-COO-RACE"
    )
    second = Runtime.at(tmp_path)
    barrier = threading.Barrier(2)
    provider_calls: list[str] = []

    def cycle(runtime: Runtime):
        original = runtime.jobs.project_retry_safety

        def gated(job_id: str, *, expected_attempt_id: str):
            projection = original(
                job_id, expected_attempt_id=expected_attempt_id
            )
            barrier.wait()
            return projection

        runtime.jobs.project_retry_safety = gated  # type: ignore[method-assign]
        return CooCycle(
            runtime,
            dispatcher=lambda job_id, command_id: provider_calls.append(job_id),
        ).run_once(root.job_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(cycle, (first, second)))

    assert [outcome.action for outcome in outcomes] == ["REQUEUED", "REQUEUED"]
    assert outcomes[0].receipt == outcomes[1].receipt
    assert len(_retry_events(first, planner.job_id)) == 1
    assert _block_events(first, root.job_id) == []
    assert len(first.attempts.list_attempts(planner.job_id)) == 1
    assert provider_calls == []
