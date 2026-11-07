"""Original idle-close receipt, TX5 fence, and same-Attempt cold recovery.

Provider process effects are explicitly inert; Runtime transactions are real.
The production native profile remains disabled and no installed grant is claimed.
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from control_plane import executive_runtime as rt
from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.operator_harness_contract import (
    OperationId, OperationReceiptKind, ProcessIdentityObservation, ProcessLiveness,
    ProviderWriterState, ReconcileObservation, SessionStartObservation,
    operation_receipt_command_id,
)
from control_plane.operator_harness_orchestrator import (
    OperatorEffectUnknown, OperatorHarnessOrchestrator, OperatorStartHandle,
)
from test_dsh_native_runtime_result import _started_native, _turn, _corrupt_fixture
from test_dsh_native_runtime_resume import _resume


def _dead(f):
    return ReconcileObservation(ProcessLiveness.PROVEN_DEAD,
        ProcessIdentityObservation(2101, 2101, "native-runtime-test", "fixture-boot"),
        True, ProviderWriterState.RELEASED, f.session_id)


def _sealed(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch)
    turn, observation = _turn(f)
    reference = f.runtime.operator_harness.seal_native_conversation_result(
        turn=turn, observation=observation, **f.lease)
    return f, reference


def _reserve(f, reference, operation=None, *, kind="graceful_stop"):
    operation = operation or OperationId("ohf-op:native-idle:" + f.generation.process_generation_id)
    f.runtime.operator_harness.reserve_generation_operation(
        generation=f.generation, operation_id=operation, operation_kind=kind,
        native_idle_result=reference, **f.lease)
    return operation


def _apply(f, reference, operation, *, observed=None):
    f.runtime.operator_harness.apply_generation_operation(
        generation=f.generation, operation_id=operation, operation_kind="graceful_stop",
        observation=observed or _dead(f), native_idle_result=reference, **f.lease)


def _composition(f, stop):
    port = ExecutiveOperatorHarnessPort(f.runtime,
        rt.AttemptLease(attempt=f.dispatch.attempt, lease_token=f.dispatch.lease_token))
    adapter = SimpleNamespace(graceful_stop=stop)
    orchestrator = OperatorHarnessOrchestrator(port, adapter,
        attestation_reader=lambda *a: pytest.fail("closure cannot invent fresh attestation"))
    session = OperatorStartHandle(f.epoch.attempt_id, f.epoch, f.generation,
                                  SessionStartObservation(f.session_id, _dead(f).observed_process))
    return orchestrator, session


def _state(f):
    with f.runtime.store.read() as connection:
        generation = dict(connection.execute("SELECT * FROM process_generations WHERE process_generation_id=?",
                                              (f.generation.process_generation_id,)).fetchone())
        quota = dict(connection.execute("SELECT * FROM worker_quota_classes WHERE held_attempt_id=?",
                                         (f.epoch.attempt_id,)).fetchone())
    return generation, quota


def test_original_idle_stop_fences_send_and_retains_same_attempt_across_expiry_resume(tmp_path, monkeypatch):
    f, reference = _sealed(tmp_path, monkeypatch)
    calls = []
    stop_id = OperationId("ohf-op:native-idle:" + f.generation.process_generation_id)
    def stop(generation, *, operation_id):
        calls.append((generation, operation_id))
        intent = f.runtime.events.get_event_by_command_id(operation_id.command_id)
        assert intent.payload["native_idle_result"] == reference.to_wire()
        # This occurs after INTENT but before the physical close result. The
        # same Runtime event prevents a racing Send or another close.
        with pytest.raises(rt.StateConflict, match="close INTENT"):
            f.runtime.operator_harness.reserve_turn(epoch=f.epoch, generation=f.generation,
                operation_id=OperationId("ohf-op:racing-native-send"), **f.lease)
        with pytest.raises(rt.StateConflict, match="close INTENT"):
            _reserve(f, reference, OperationId("ohf-op:duplicate-native-close"))
        return _dead(f)
    orchestrator, session = _composition(f, stop)
    assert orchestrator.graceful_stop(session, operation_id=stop_id,
                                      native_idle_result=reference) == _dead(f)
    assert calls == [(f.generation, stop_id)]
    applied = f.runtime.events.get_event_by_command_id(
        operation_receipt_command_id(stop_id, OperationReceiptKind.APPLIED))
    payload = applied.payload
    assert payload["executive_writer_released"] is False
    assert payload["native_idle_result"] == reference.to_wire()
    generation, quota = _state(f)
    assert generation["ended_at_ms"] is not None and generation["executive_writer_held"] == 1
    assert generation["provider_writer_state"] == ProviderWriterState.RELEASED.value
    assert quota["held_attempt_id"] == f.epoch.attempt_id
    assert f.runtime.operator_harness.current_writer_generation(f.epoch) == f.generation
    with pytest.raises(rt.StateConflict):
        f.runtime.current_harness_binding_source(f.epoch.attempt_id)
    assert len([e for e in f.runtime.events.list_events()
                if e.event_type == "OHF_RECONCILE_OBSERVED"]) == 1
    # An exact APPLIED read does not dispatch another physical close.
    _apply(f, reference, stop_id)
    with pytest.raises(rt.StateConflict):
        orchestrator.graceful_stop(session, operation_id=stop_id, native_idle_result=reference)
    assert len(calls) == 1

    old_lease = dict(f.lease)
    now = f.runtime.store.now_ms() + 3_700_000
    f.runtime = rt.Runtime.at(f.runtime.store.root, clock=lambda: now, lease_seconds=3600)
    replacement = f.runtime.attempts.takeover_expired_operator_harness(
        f.epoch.attempt_id, expected_fence_generation=f.dispatch.attempt.fence_generation,
        lease_owner="native-idle-recovery-fixture", lease_seconds=3600)
    assert replacement.attempt.fence_generation == old_lease["fence_generation"] + 1
    f.lease = dict(fence_generation=replacement.attempt.fence_generation, lease_token=replacement.lease_token)
    with pytest.raises(rt.StateConflict):
        f.runtime.operator_harness.reserve_same_epoch_resume(epoch=f.epoch, old_generation=f.generation,
            operation_id=OperationId("ohf-op:stale-idle-resume"), **old_lease)
    resumed = _resume(f)
    assert resumed.generation.generation_number == 2 and resumed.epoch == f.epoch
    assert resumed.session_id == f.session_id
    assert f.runtime.operator_harness.native_conversation_result(
        attempt_id=f.epoch.attempt_id, reference=reference)["turn"]["process_generation_id"] == f.generation.process_generation_id
    turn, observation = _turn(resumed, 2)
    successor = f.runtime.operator_harness.seal_native_conversation_result(
        turn=turn, observation=observation, **f.lease)
    assert f.runtime.operator_harness.native_conversation_result(
        attempt_id=f.epoch.attempt_id, reference=successor)["predecessor_result"] == reference.to_wire()
    with pytest.raises(rt.StateConflict):
        _reserve(resumed, successor, OperationId("ohf-op:no-g2-idle-disposition"))
    with pytest.raises(rt.StateConflict):
        f.runtime.operator_harness.reserve_same_epoch_resume(epoch=f.epoch, old_generation=resumed.generation,
            operation_id=OperationId("ohf-op:no-third-native-generation"), **f.lease)


@pytest.mark.parametrize("invalid", ["stale", "digest", "wire", "unacknowledged", "unsealed", "cancel"])
def test_idle_reservation_requires_exact_latest_flushed_g1(tmp_path, monkeypatch, invalid):
    f, reference = _sealed(tmp_path, monkeypatch)
    if invalid == "stale":
        turn, observation = _turn(f, 2)
        f.runtime.operator_harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    elif invalid == "digest":
        reference = replace(reference, seal_digest="f" * 64)
    elif invalid == "wire":
        reference = reference.to_wire()
    elif invalid == "unacknowledged":
        f.runtime.operator_harness.reserve_turn(epoch=f.epoch, generation=f.generation,
            operation_id=OperationId("ohf-op:unacknowledged-before-close"), **f.lease)
    elif invalid == "unsealed":
        _turn(f, 2)
    operation = OperationId("ohf-op:refused-native-idle")
    with pytest.raises(rt.StateConflict):
        _reserve(f, reference, operation, kind="cancel" if invalid == "cancel" else "graceful_stop")
    assert f.runtime.events.get_event_by_command_id(operation.command_id) is None
    assert _state(f)[0]["ended_at_ms"] is None


@pytest.mark.parametrize("change", ["omit_ref", "add_ref", "wrong_process", "missing_session", "wrong_owner"])
def test_apply_cannot_relabel_original_disposition_or_observation(tmp_path, monkeypatch, change):
    f, reference = _sealed(tmp_path, monkeypatch)
    reserved = None if change == "add_ref" else reference
    operation = _reserve(f, reserved)
    applied_ref = None if change == "omit_ref" else reference
    observed = _dead(f)
    if change == "wrong_process":
        observed = replace(observed, observed_process=ProcessIdentityObservation(9991, 9991, "other", "fixture-boot"))
    elif change == "missing_session":
        observed = replace(observed, observed_provider_session_id=None)
    elif change == "wrong_owner":
        _corrupt_fixture(f.runtime, "events", "UPDATE events SET job_id=? WHERE command_id=?",
                         (f.root.job_id, operation.command_id))
    with pytest.raises(rt.StateConflict):
        _apply(f, applied_ref, operation, observed=observed)
    assert f.runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.APPLIED)) is None
    assert _state(f)[0]["ended_at_ms"] is None


def test_native_containment_keeps_original_custody_until_tx8(tmp_path, monkeypatch):
    f, reference = _sealed(tmp_path, monkeypatch)
    operation = _reserve(f, None)
    with pytest.raises(rt.StateConflict, match="close INTENT"):
        _turn(f, 2)
    _apply(f, None, operation)
    generation, _ = _state(f)
    assert generation["executive_writer_held"] == 1
    applied = f.runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.APPLIED))
    assert "native_idle_result" not in applied.payload
    assert applied.payload["executive_writer_released"] is False
    assert f.runtime.operator_harness.current_writer_generation(f.epoch) == f.generation
    with pytest.raises(rt.StateConflict):
        f.runtime.current_harness_binding_source(f.epoch.attempt_id)
    f.runtime.operator_harness.record_reconcile_observation(
        generation=f.generation, observation=_dead(f), **f.lease)
    f.runtime.operator_harness.abandon_epoch(epoch=f.epoch, generation=f.generation, **f.lease)
    with pytest.raises(rt.StateConflict):
        f.runtime.operator_harness.current_writer_generation(f.epoch)


def test_unknown_idle_close_keeps_original_fence_and_reconciles_without_replay(tmp_path, monkeypatch):
    f, reference = _sealed(tmp_path, monkeypatch)
    calls = []
    def lost(generation, *, operation_id):
        calls.append(operation_id)
        raise OSError("inert stop return lost")
    orchestrator, session = _composition(f, lost)
    operation = OperationId("ohf-op:unknown-original-native-idle")
    with pytest.raises(OperatorEffectUnknown):
        orchestrator.graceful_stop(session, operation_id=operation, native_idle_result=reference)
    assert f.runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.EFFECT_UNKNOWN)) is not None
    with pytest.raises(OperatorEffectUnknown):
        orchestrator.graceful_stop(session, operation_id=operation, native_idle_result=reference)
    with pytest.raises(rt.StateConflict):
        _reserve(f, reference, OperationId("ohf-op:no-close-failover"))
    with pytest.raises(rt.StateConflict):
        _turn(f, 2)
    with pytest.raises(rt.StateConflict):
        _resume(f)
    assert calls == [operation]
    # Canonical observation of the original target, not another stop, enables
    # original same-Session recovery.
    f.runtime.operator_harness.record_reconcile_observation(
        generation=f.generation, observation=_dead(f), **f.lease)
    assert _resume(f).generation.generation_number == 2
    assert calls == [operation]
