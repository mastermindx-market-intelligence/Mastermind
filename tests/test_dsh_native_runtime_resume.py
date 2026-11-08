"""Native G1 evidence and current G2 authority through the original Runtime owner."""
from types import SimpleNamespace

import pytest

from control_plane import executive_runtime as rt
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
from control_plane.operator_harness_contract import (
    OperationId, ProcessIdentityObservation, ProcessLiveness, ProviderWriterState, ReconcileObservation,
)
from test_dsh_native_runtime_result import _started_native, _turn, _attestation
from dataclasses import replace


def _release(f, *, writer=ProviderWriterState.RELEASED):
    f.runtime.operator_harness.record_reconcile_observation(generation=f.generation,
        observation=ReconcileObservation(ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(2101, 2101, "native-runtime-test", "fixture-boot"),
            True, writer, f.session_id), **f.lease)


def _resume(f):
    harness = f.runtime.operator_harness
    op = OperationId("ohf-op:native-original-resume")
    generation = harness.reserve_same_epoch_resume(epoch=f.epoch, old_generation=f.generation,
                                                   operation_id=op, **f.lease)
    # A reserved, undispatched operation reconciles the same original allocation.
    assert harness.reserve_same_epoch_resume(epoch=f.epoch, old_generation=f.generation,
                                             operation_id=op, **f.lease) == generation
    process = ProcessIdentityObservation(2102, 2102, "native-resumed-test", "fixture-boot")
    harness.bind_resume_result(epoch=f.epoch, generation=generation, operation_id=op,
                               provider_session_id=f.session_id, process=process, **f.lease)
    principal = OperatorPrincipalObservation(
        attempt_id=f.epoch.attempt_id, worker_id=f.epoch.worker_id,
        process_generation_id=generation.process_generation_id, provider_session_id=f.session_id,
        process_identity=dict(pid=process.pid, pgid=process.pgid,
            process_start_identity=process.process_start_identity, boot_id=process.boot_id),
        os_principal_name="native-test-only", os_principal_uid=9301,
        provider_home_identity=dict(path="/tmp/dsh-native-fixture-home", device=1, inode=2,
                                   uid=9301, gid=9301, mode=0o700),
        observed_at_ms=f.runtime.store.now_ms())
    harness.seal_attestation(generation=generation, requested=f.requested,
        attestation=replace(_attestation(f.requested), effective_plugins_or_apps=("mastermind-company",)),
        principal_observation=principal, **f.lease)
    values = vars(f).copy()
    values["generation"] = generation
    return SimpleNamespace(**values)


def test_native_cold_resume_preserves_initial_seal_and_supports_separate_g2_turns(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch)
    harness = f.runtime.operator_harness
    first, observation = _turn(f)
    initial = harness.seal_native_conversation_result(turn=first, observation=observation, **f.lease)
    initial_payload = harness.native_conversation_result(attempt_id=first.attempt_id, reference=initial)
    _release(f)
    resumed = _resume(f)
    assert resumed.generation.generation_number == 2
    assert resumed.epoch == f.epoch
    assert harness.current_writer_generation(f.epoch) == resumed.generation
    assert harness.native_conversation_result(attempt_id=first.attempt_id, reference=initial) == initial_payload
    previous = initial
    for ordinal in (2, 3):
        turn, observation = _turn(resumed, ordinal)
        reference = harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
        payload = harness.native_conversation_result(attempt_id=turn.attempt_id, reference=reference)
        assert payload["predecessor_result"] == previous.to_wire()
        assert payload["turn"]["process_generation_id"] == resumed.generation.process_generation_id
        previous = reference
    assert initial_payload["turn"]["process_generation_id"] == f.generation.process_generation_id
    with f.runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM process_generations WHERE session_epoch_id=?",
                                  (f.epoch.session_epoch_id,)).fetchone()[0] == 2
    # Existing generation bound remains explicit; this slice does not invent G3.
    with pytest.raises(rt.StateConflict):
        harness.reserve_same_epoch_resume(epoch=f.epoch, old_generation=resumed.generation,
                                           operation_id=OperationId("ohf-op:no-third-generation"), **f.lease)


@pytest.mark.parametrize("state", ["live_writer", "unknown_writer", "candidate_only", "unresolved_turn"])
def test_native_resume_requires_original_release_and_every_flushed_predecessor(tmp_path, monkeypatch, state):
    f = _started_native(tmp_path, monkeypatch)
    harness = f.runtime.operator_harness
    first, observation = _turn(f, candidate=state != "unresolved_turn")
    if state in {"live_writer", "unknown_writer"}:
        harness.seal_native_conversation_result(turn=first, observation=observation, **f.lease)
    if state != "live_writer":
        _release(f, writer=ProviderWriterState.UNKNOWN if state == "unknown_writer" else ProviderWriterState.RELEASED)
    operation = OperationId("ohf-op:refused-native-resume")
    with pytest.raises(rt.StateConflict):
        harness.reserve_same_epoch_resume(epoch=f.epoch, old_generation=f.generation,
                                           operation_id=operation, **f.lease)
    assert f.runtime.store.find_event_by_command_id(operation.command_id) is None
    with f.runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM process_generations").fetchone()[0] == 1
