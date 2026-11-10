"""Original TX-5 custody is readable, but it cannot authorize a G2 rerun.

Actual Runtime owners execute against disposable SQLite fixtures; native
provider calls remain inert. Corruption fixtures restore the original event
immutability triggers before exercising any recovery owner.
"""
from __future__ import annotations

import copy

import pytest

from control_plane.executive_orchestration_result import canonical_bytes
from control_plane.executive_runtime import AttemptStatus, StateConflict
from control_plane.operator_harness_contract import (
    OperationId, OperationReceiptKind, ProcessGenerationRef, ProcessLiveness,
    ProviderWriterState, ReconcileObservation, operation_receipt_command_id,
)
from test_codex_planner_turn_custody import _runtime_after_ack
from test_executive_operator_supervisor import _seed_expired_g1


BOUNDARY = "retained planner request custody cannot resume into G2; reconcile the original G1 turn"


def _mutate(runtime, command, transform=None):
    with runtime.store.transaction() as connection:
        event = connection.execute("SELECT * FROM events WHERE command_id=?", (command,)).fetchone()
        assert event is not None
        kind = "delete" if transform is None else "update"
        name = "events_are_immutable_" + kind
        trigger = connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()[0]
        connection.execute("DROP TRIGGER " + name)
        if transform is None:
            connection.execute("DELETE FROM events WHERE command_id=?", (command,))
        else:
            payload = copy.deepcopy(runtime.events.get_event_by_command_id(command).payload)
            transform(payload)
            connection.execute("UPDATE events SET payload_json=? WHERE command_id=?",
                (canonical_bytes(payload).decode(), command))
        connection.execute(trigger)


def _snapshot(runtime):
    with runtime.store.read() as connection:
        return {
            table: [dict(row) for row in connection.execute("SELECT * FROM " + table)]
            for table in ("events", "harness_session_epochs", "process_generations")
        }


def _dead(case):
    session, original_turn, original_operation = case.supervisor._recovery_session(case.lease)
    assert original_turn == case.turn and original_operation == case.operation
    case.runtime.operator_harness.record_reconcile_observation(
        generation=session.generation,
        observation=ReconcileObservation(ProcessLiveness.PROVEN_DEAD, case.adapter.process,
            False, ProviderWriterState.RELEASED, case.adapter.provider_session_id,
            session.launch.requested.expected_config_digest),
        fence_generation=case.lease.attempt.fence_generation,
        lease_token=case.lease.lease_token)
    return session


@pytest.mark.parametrize("nested", [False, True])
def test_canonical_g1_read_retains_original_native_request_and_cannot_allocate_g2(tmp_path, monkeypatch, nested):
    case = _runtime_after_ack(tmp_path, monkeypatch, nested=nested)
    harness = case.runtime.operator_harness
    before = _snapshot(case.runtime)
    applied_command = operation_receipt_command_id(case.operation, OperationReceiptKind.APPLIED)
    with case.runtime.store.read() as connection:
        row = connection.execute("SELECT * FROM attempts WHERE attempt_id=?", (case.turn.attempt_id,)).fetchone()
        intent = harness._require_turn_intent(connection, row=row, turn=case.turn,
            operation_id=case.operation, event=harness._event(connection, case.operation.command_id),
            provider_session_id=case.adapter.provider_session_id)
        applied = harness._require_turn_applied(connection, row=row, turn=case.turn,
            operation_id=case.operation, intent=intent, event=harness._event(connection, applied_command))
    assert intent["planner_producer"]["planner_producer_binding"]["root_job_id"] == case.root.job_id
    assert intent["planner_producer"]["planner_producer_binding"]["coordinator_job_id"] == case.coordinator.job_id
    assert applied["planner_custody"] == case.observation.planner_custody
    assert applied["planner_custody"]["evidence_kind"] == "NATIVE_REQUEST_ACK"
    assert _snapshot(case.runtime) == before
    session = _dead(case)
    before = _snapshot(case.runtime)
    with pytest.raises(StateConflict, match="^" + BOUNDARY + "$"):
        harness.reserve_same_epoch_resume(epoch=session.epoch, old_generation=session.generation,
            operation_id=OperationId("ohf-op:forbidden-bound-resume"),
            fence_generation=case.lease.attempt.fence_generation, lease_token=case.lease.lease_token)
    assert _snapshot(case.runtime) == before
    assert case.adapter.begin_turn_calls == 1 and case.adapter.resume_calls == 0
    assert case.runtime.attempts.get_attempt(case.turn.attempt_id).status is AttemptStatus.RUNNING
    assert case.runtime.events.get_event_by_command_id(f"orchestration-result-seal:{case.turn.attempt_id}") is None


@pytest.mark.parametrize("fault", [
    "missing_producer", "wrong_producer", "missing_custody", "foreign_native_turn",
    "foreign_operation", "wrong_contract", "malformed_request_digest", "missing_dispatch",
    "unknown_effect", "downgrade",
])
def test_corrupted_original_g1_custody_refuses_before_bound_resume_boundary(tmp_path, monkeypatch, fault):
    case = _runtime_after_ack(tmp_path, monkeypatch)
    session = _dead(case)
    intent_id = case.operation.command_id
    applied_id = operation_receipt_command_id(case.operation, OperationReceiptKind.APPLIED)
    if fault == "missing_producer":
        _mutate(case.runtime, intent_id, lambda p: p.pop("planner_producer"))
    elif fault == "wrong_producer":
        _mutate(case.runtime, intent_id, lambda p: p["planner_producer"].update(job_id="JOB-OTHER"))
    elif fault == "missing_custody":
        _mutate(case.runtime, applied_id, lambda p: p.pop("planner_custody"))
    elif fault in {"foreign_native_turn", "foreign_operation", "wrong_contract", "malformed_request_digest"}:
        changes = {
            "foreign_native_turn": {"provider_native_turn_id": "NATIVE-OTHER"},
            "foreign_operation": {"operation_id": "ohf-op:foreign"},
            "wrong_contract": {"native_result_contract": {"name": "executive-plan-v1"}},
            "malformed_request_digest": {"native_request_digest": "not-a-digest"},
        }
        _mutate(case.runtime, applied_id, lambda p: p["planner_custody"].update(changes[fault]))
    elif fault == "missing_dispatch":
        _mutate(case.runtime, intent_id + ":dispatch")
    elif fault == "unknown_effect":
        # Model contradictory retained receipts; the normal receipt owner
        # cannot write this alongside APPLIED.
        with case.runtime.store.transaction() as connection:
            attempt = case.lease.attempt
            case.runtime.store.append_event(connection, aggregate_type="operator_operation",
                aggregate_id=intent_id, event_type=OperationReceiptKind.EFFECT_UNKNOWN.value,
                command_id=operation_receipt_command_id(case.operation, OperationReceiptKind.EFFECT_UNKNOWN),
                actor="fixture", job_id=attempt.job_id, attempt_id=attempt.attempt_id,
                worker_id=attempt.worker_id, quota_class=attempt.quota_class,
                payload={"schema_version": "mastermind.operator_harness_effect_unknown/v1",
                    "phase": "begin_turn_dispatch", "detail": "fixture contradictory receipt"})
    else:
        def downgrade(payload):
            payload["schema_version"] = "mastermind.operator_harness_turn_applied/v1"
            payload.pop("planner_custody")
        _mutate(case.runtime, applied_id, downgrade)
    before = _snapshot(case.runtime)
    with pytest.raises(StateConflict) as failure:
        case.runtime.operator_harness.reserve_same_epoch_resume(epoch=session.epoch,
            old_generation=session.generation, operation_id=OperationId("ohf-op:corrupt-bound-resume"),
            fence_generation=case.lease.attempt.fence_generation, lease_token=case.lease.lease_token)
    assert str(failure.value) != BOUNDARY
    assert _snapshot(case.runtime) == before
    assert case.adapter.begin_turn_calls == 1 and case.adapter.resume_calls == 0


@pytest.mark.parametrize("native_id", [None, "", "  "])
def test_legacy_g1_still_requires_nonempty_acknowledged_native_turn_id(tmp_path, native_id):
    _, runtime, _, _, dispatch, _, epoch = _seed_expired_g1(tmp_path, with_turn=True)
    original = OperationId("ohf-op:g2-recovery-turn")
    _mutate(runtime, operation_receipt_command_id(original, OperationReceiptKind.APPLIED),
        lambda p: p.update(provider_native_turn_id=native_id))
    with runtime.store.read() as connection:
        row = connection.execute("SELECT * FROM process_generations WHERE session_epoch_id=?", (epoch.session_epoch_id,)).fetchone()
    g1 = ProcessGenerationRef(row["process_generation_id"], epoch.session_epoch_id, 1, epoch.worker_id)
    before = _snapshot(runtime)
    with pytest.raises(StateConflict, match="G1 recovery TX-5 evidence is incomplete"):
        runtime.operator_harness.reserve_same_epoch_resume(epoch=epoch, old_generation=g1,
            operation_id=OperationId("ohf-op:invalid-legacy-resume"),
            fence_generation=dispatch.attempt.fence_generation, lease_token=dispatch.lease_token)
    assert _snapshot(runtime) == before
