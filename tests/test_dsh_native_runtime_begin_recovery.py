"""Original native uncertain begin through real Runtime journal and result owners."""
from dataclasses import replace
import json

import pytest

from control_plane import executive_runtime as rt
from control_plane.executive_orchestration_principal import digest
from control_plane.native_conversation_result import (
    NativeConversationBeginObservation, NativeConversationResultObservation,
)
from control_plane.operator_harness_contract import (
    CandidateResult, EventCursor, NormalizedEvent, OperationId, TurnStartObservation,
)
from control_plane.operator_harness_wire import to_wire
from integrations.deepseek_harness.native_protocol import NativeClaim, NativeResult, NativeTerminal
from test_dsh_native_runtime_result import _started_native, _turn, _attestation, _corrupt_fixture
from test_dsh_native_runtime_resume import _release, _resume


def pending(f, *, phase="begin_turn", ordinal=1):
    h = f.runtime.operator_harness
    op = OperationId(f"ohf-op:original-native-uncertain:{ordinal}")
    turn = h.reserve_turn(epoch=f.epoch, generation=f.generation, operation_id=op, **f.lease)
    assert h.commit_provider_dispatch(attempt_id=turn.attempt_id, operation_id=op,
                                     operation_kind="begin_turn", **f.lease)
    assert h.record_effect_unknown(attempt_id=turn.attempt_id, operation_id=op,
        phase=phase, detail="original claim waiter elapsed", **f.lease)
    claim = NativeClaim(op.command_id, ordinal, f.session_id, f"original-message-{ordinal}", ordinal, ordinal*10)
    observed = replace(_attestation(f.requested), effective_plugins_or_apps=("mastermind-company",))
    ack = NativeConversationBeginObservation(turn, f.generation, claim,
                                             digest(to_wire(f.requested)), digest(to_wire(observed)))
    return op, turn, ack


def seal(f, turn, ack, *, claim=None):
    h = f.runtime.operator_harness
    claim = claim or ack.native_claim
    result = NativeResult("end_turn", NativeTerminal(claim.operation_id, claim.request_id,
        claim, claim.through_seq+5, claim.native_turn+1, 2))
    observation = NativeConversationResultObservation.from_native(turn, f.session_id, result)
    h.record_candidate_evidence(turn=turn,
        candidate=CandidateResult(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                                  result.artifact_digest, "original recovered answer"),
        events=(NormalizedEvent(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                                turn.turn_id, "native_terminal", payload_redacted={"through_seq": claim.through_seq+5}),),
        cursor=EventCursor(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                           local_sequence=1, turn_id=turn.turn_id), **f.lease)
    return h.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)


@pytest.mark.parametrize("phase", ["begin_turn", "begin_turn_ack", "bind_turn_result", "begin_turn_dispatch"])
def test_original_unknown_is_preserved_while_native_ack_and_answer_are_recovered(tmp_path, monkeypatch, phase):
    f = _started_native(tmp_path, monkeypatch)
    h = f.runtime.operator_harness
    op, turn, ack = pending(f, phase=phase)
    original = f.runtime.events.get_event_by_command_id(op.command_id+":effect-unknown")
    assert original is not None and original.payload["phase"] == phase
    command = h.reconcile_native_begin(turn=turn, operation_id=op, observation=ack, **f.lease)
    assert command == op.command_id+":reconciled"
    event = f.runtime.events.get_event_by_command_id(command)
    assert h.reconcile_native_begin(turn=turn, operation_id=op, observation=ack, **f.lease) == command
    assert f.runtime.events.get_event_by_command_id(command) == event
    assert f.runtime.events.get_event_by_command_id(op.command_id+":effect-unknown") == original
    assert f.runtime.events.get_event_by_command_id(op.command_id+":applied") is None
    with pytest.raises(rt.StateConflict):
        h.acknowledge_turn(turn=turn, operation_id=op, observation=ack.start, **f.lease)
    with f.runtime.store.read() as connection:
        assert rt._interactive_in_flight_turn_id(connection, turn.process_generation_id) == turn.turn_id
        assert connection.execute("SELECT COUNT(*) FROM events WHERE aggregate_id=?", (op.command_id,)).fetchone()[0] == 4
    with pytest.raises(rt.StateConflict):
        h.reserve_turn(epoch=f.epoch, generation=f.generation, operation_id=OperationId("ohf-op:no-second-send"), **f.lease)
    stop = OperationId("ohf-op:stop-original-recovered-turn")
    h.reserve_turn_operation(turn=turn, operation_id=stop, operation_kind="interrupt_turn", **f.lease)
    ref = seal(f, turn, ack)
    payload = h.native_conversation_result(attempt_id=turn.attempt_id, reference=ref)
    assert payload["schema_version"] == "mastermind.dsh_native_conversation_result_seal/v2"
    assert payload["tx5_ack_kind"] == "OPERATOR_OPERATION_RECONCILED"
    assert payload["tx5_ack_command_id"] == command and "tx5_applied_command_id" not in payload
    assert payload["observation"]["native_claim"] == ack.native_claim.to_wire()
    assert h.current_writer_generation(f.epoch) == f.generation
    # Stop owns the original acknowledged turn; its receipt does not create another begin.
    h.apply_turn_operation(turn=turn, operation_id=stop, operation_kind="interrupt_turn", **f.lease)
    second, observation = _turn(f, 2)
    next_ref = h.seal_native_conversation_result(turn=second, observation=observation, **f.lease)
    assert h.native_conversation_result(attempt_id=second.attempt_id, reference=next_ref)["predecessor_result"] == ref.to_wire()
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.RUNNING


def test_recovered_g1_history_survives_original_same_session_g2(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch)
    h = f.runtime.operator_harness
    op, turn, ack = pending(f)
    h.reconcile_native_begin(turn=turn, operation_id=op, observation=ack, **f.lease)
    ref = seal(f, turn, ack)
    payload = h.native_conversation_result(attempt_id=turn.attempt_id, reference=ref)
    _release(f)
    resumed = _resume(f)
    assert resumed.epoch == f.epoch and resumed.generation.generation_number == 2
    assert h.native_conversation_result(attempt_id=turn.attempt_id, reference=ref) == payload
    with pytest.raises(rt.StateConflict):
        h.reconcile_native_begin(turn=turn, operation_id=op, observation=ack, **f.lease)
    second, observation = _turn(resumed, 2)
    next_ref = h.seal_native_conversation_result(turn=second, observation=observation, **f.lease)
    assert h.native_conversation_result(attempt_id=second.attempt_id, reference=next_ref)["predecessor_result"] == ref.to_wire()


@pytest.mark.parametrize("field,value", [
    ("request_id", "1"), ("message_id", "foreign-message"), ("through_seq", 11),
])
def test_recovered_answer_requires_the_entire_original_claim(tmp_path, monkeypatch, field, value):
    f = _started_native(tmp_path, monkeypatch)
    h = f.runtime.operator_harness
    op, turn, ack = pending(f)
    h.reconcile_native_begin(turn=turn, operation_id=op, observation=ack, **f.lease)
    with pytest.raises(rt.StateConflict, match="claim differs"):
        seal(f, turn, ack, claim=replace(ack.native_claim, **{field: value}))


@pytest.mark.parametrize("change", [
    "operation", "turn", "generation", "session", "profile", "attestation", "dispatch-missing",
    "unknown-missing", "unknown-phase", "intent-actor", "dispatch-worker", "unknown-job",
    "released", "changed-replay", "unknown-after-reconciled", "reconciled-actor",
])
def test_native_begin_reconciliation_refuses_foreign_or_unowned_evidence(tmp_path, monkeypatch, change):
    f = _started_native(tmp_path, monkeypatch)
    h = f.runtime.operator_harness
    op, turn, ack = pending(f)
    if change in {"changed-replay", "unknown-after-reconciled", "reconciled-actor"}:
        h.reconcile_native_begin(turn=turn, operation_id=op, observation=ack, **f.lease)
    if change == "operation": op = OperationId("ohf-op:foreign")
    elif change == "turn": turn = replace(turn, turn_id="foreign-turn")
    elif change == "generation": ack = replace(ack, generation=replace(ack.generation, generation_number=2))
    elif change == "session": ack = replace(ack, native_claim=replace(ack.native_claim, session_id="foreign-session"))
    elif change == "profile": ack = replace(ack, requested_profile_digest="a"*64)
    elif change == "attestation": ack = replace(ack, observed_attestation_digest="b"*64)
    elif change == "released": _release(f)
    elif change == "changed-replay": ack = replace(ack, native_claim=replace(ack.native_claim, message_id="changed-message"))
    else:
        if change.endswith("-missing"):
            suffix = ":dispatch" if change.startswith("dispatch") else ":effect-unknown"
            _corrupt_fixture(f.runtime, "events", "DELETE FROM events WHERE command_id=?", (op.command_id+suffix,))
        elif change in {"unknown-phase", "unknown-after-reconciled"}:
            with f.runtime.store.read() as connection:
                event = connection.execute("SELECT payload_json FROM events WHERE command_id=?", (op.command_id+":effect-unknown",)).fetchone()
            payload = json.loads(event[0])
            payload["phase"] = "collect_turn_result"
            _corrupt_fixture(f.runtime, "events", "UPDATE events SET payload_json=? WHERE command_id=?",
                (json.dumps(payload, sort_keys=True, separators=(",", ":")), op.command_id+":effect-unknown"))
        else:
            suffix, column = {"intent-actor": ("", "actor"), "dispatch-worker": (":dispatch", "worker_id"),
                "unknown-job": (":effect-unknown", "job_id"), "reconciled-actor": (":reconciled", "actor")}[change]
            value = f.root.job_id if column == "job_id" else (None if column == "worker_id" else "foreign")
            _corrupt_fixture(f.runtime, "events", f"UPDATE events SET {column}=? WHERE command_id=?", (value, op.command_id+suffix))
    with pytest.raises(rt.StateConflict):
        h.reconcile_native_begin(turn=turn, operation_id=op, observation=ack, **f.lease)


@pytest.mark.parametrize("initial", ["timeout", "false-ack", "applied-collection"])
def test_original_orchestrator_recovers_without_reentering_dispatch(tmp_path, monkeypatch, initial):
    from test_dsh_native_runtime_result import _orchestrator
    from control_plane.operator_harness_orchestrator import NativeTurnPending, OperatorEffectUnknown
    from integrations.deepseek_harness.native_connection import NativeEffectUnknown
    f = _started_native(tmp_path, monkeypatch)
    orchestrator, port, adapter, session = _orchestrator(f)
    op = OperationId("ohf-op:orchestrated-original-uncertain")
    state = {"ready": False, "collect_failure": initial == "applied-collection"}
    original_begin, original_read = adapter.begin_turn, adapter.read_events
    def begin(**kwargs):
        value = original_begin(**kwargs)
        if initial == "false-ack": return TurnStartObservation(None, False)
        if initial == "timeout": raise NativeEffectUnknown("NATIVE_CLAIM_UNOBSERVED")
        return value
    def observe(**kwargs):
        assert kwargs == dict(operation_id=op, turn=adapter.turn, generation=f.generation)
        if not state["ready"]: return None
        return NativeConversationBeginObservation(adapter.turn, f.generation, adapter.result.terminal.claim,
                                                   digest(to_wire(f.requested)), digest(to_wire(session.observed)))
    def read(*args, **kwargs):
        if state["collect_failure"]: raise TimeoutError("original native terminal not yet observed")
        return original_read(*args, **kwargs)
    monkeypatch.setattr(adapter, "begin_turn", begin)
    monkeypatch.setattr(adapter, "observe_native_begin", observe, raising=False)
    monkeypatch.setattr(adapter, "read_events", read)
    with pytest.raises(NativeTurnPending) as pending_error:
        orchestrator.run_turn(session, operation_id=op)
    original_turn = pending_error.value.turn
    assert original_turn == adapter.turn and adapter.calls == 1
    original_unknown = f.runtime.events.get_event_by_command_id(op.command_id+":effect-unknown")
    if initial == "applied-collection":
        assert original_unknown is None
    else:
        assert original_unknown is not None
    state.update(ready=True, collect_failure=True)
    active = []
    with pytest.raises(NativeTurnPending) as collecting:
        orchestrator.recover_native_turn(session, operation_id=op, expected_turn=original_turn,
                                         _on_turn_applied=lambda turn: active.append(turn))
    assert isinstance(collecting.value.__cause__, TimeoutError)
    assert active == [original_turn] and adapter.calls == 1
    assert f.runtime.events.get_event_by_command_id(op.command_id+":effect-unknown") == original_unknown
    with pytest.raises(OperatorEffectUnknown if initial != "applied-collection" else RuntimeError):
        orchestrator.run_turn(session, operation_id=op)
    state["collect_failure"] = False
    receipt = orchestrator.recover_native_turn(session, operation_id=op, expected_turn=original_turn)
    assert receipt.turn == original_turn and receipt.native_result is not None and adapter.calls == 1
    payload = f.runtime.operator_harness.native_conversation_result(
        attempt_id=original_turn.attempt_id, reference=receipt.native_result)
    assert payload["observation"]["native_claim"] == adapter.result.terminal.claim.to_wire()
    assert payload["schema_version"].endswith("/v1" if initial == "applied-collection" else "/v2")
    with f.runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events WHERE command_id=?", (op.command_id+":dispatch",)).fetchone()[0] == 1
    assert f.runtime.events.get_event_by_command_id(op.command_id+":effect-unknown") == original_unknown


@pytest.mark.parametrize("after_commit", [False, True])
def test_receipt_first_recovery_finishes_original_candidate_without_active_reexposure(tmp_path, monkeypatch, after_commit):
    from test_dsh_native_runtime_result import _orchestrator
    from control_plane.operator_harness_orchestrator import NativeTurnPending
    f = _started_native(tmp_path, monkeypatch)
    orchestrator, port, adapter, session = _orchestrator(f)
    original_seal = port.seal_operator_native_result
    op = OperationId("ohf-op:original-candidate-recovery")
    def seal_lost(*args, **kwargs):
        if after_commit: original_seal(*args, **kwargs)
        raise OSError("original seal observation unavailable")
    monkeypatch.setattr(port, "seal_operator_native_result", seal_lost)
    monkeypatch.setattr(adapter, "observe_native_begin", lambda **_k: pytest.fail("candidate recovery read begin again"), raising=False)
    with pytest.raises(NativeTurnPending) as held:
        orchestrator.run_turn(session, operation_id=op)
    turn = held.value.turn
    monkeypatch.setattr(port, "seal_operator_native_result", original_seal)
    monkeypatch.setattr(adapter, "read_events", lambda *_a, **_k: pytest.fail("candidate recovery recollected"))
    before = f.runtime.events.list_events()
    receipt = orchestrator.recover_native_turn(session, operation_id=op, expected_turn=turn,
        _on_turn_applied=lambda *_a: pytest.fail("completed original turn was exposed as active"))
    assert receipt.turn == turn and receipt.native_result is not None and adapter.calls == 1
    if after_commit: assert f.runtime.events.list_events() == before
    with f.runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events WHERE command_id=?", ("ohf-candidate:"+turn.turn_id,)).fetchone()[0] == 1

@pytest.mark.parametrize("fault", ["contract", "target", "material", "lease", "collect-lease"])
def test_existing_native_custody_survives_recovery_source_and_lease_failures(tmp_path, monkeypatch, fault):
    from test_dsh_native_runtime_result import _orchestrator
    from control_plane.operator_harness_orchestrator import NativeTurnPending
    f = _started_native(tmp_path, monkeypatch)
    orchestrator, port, adapter, session = _orchestrator(f)
    op = OperationId("ohf-op:original-source-custody")
    original_read, original_lease = adapter.read_events, port.extend_operator_lease
    state = {"hold": True, "observations": 0}
    def observe(**kwargs):
        state["observations"] += 1
        assert kwargs == dict(operation_id=op, turn=adapter.turn, generation=f.generation)
        return NativeConversationBeginObservation(adapter.turn, f.generation, adapter.result.terminal.claim,
            digest(to_wire(f.requested)), digest(to_wire(session.observed)))
    def read(*args, **kwargs):
        if state["hold"]: raise TimeoutError("original collection remains pending")
        return original_read(*args, **kwargs)
    def lease(*args, **kwargs):
        if state["hold"] and adapter.calls: raise OSError("original post-ACK lease temporarily unreadable")
        return original_lease(*args, **kwargs)
    monkeypatch.setattr(adapter, "observe_native_begin", observe, raising=False)
    if fault == "collect-lease": monkeypatch.setattr(port, "extend_operator_lease", lease)
    else: monkeypatch.setattr(adapter, "read_events", read)
    with pytest.raises(NativeTurnPending) as held:
        orchestrator.run_turn(session, operation_id=op)
    turn = held.value.turn
    assert turn == adapter.turn and adapter.calls == 1
    assert f.runtime.events.get_event_by_command_id(op.command_id+":applied") is not None
    assert f.runtime.events.get_event_by_command_id(op.command_id+":effect-unknown") is None
    state["hold"] = False
    if fault != "collect-lease":
        name = {"contract":"operator_result_contract", "target":"original_operator_native_turn",
                "material":"operator_native_turn_result_material", "lease":"extend_operator_lease"}[fault]
        original = getattr(port, name)
        def unavailable(*_args, **_kwargs): raise OSError("original recovery source temporarily unavailable")
        monkeypatch.setattr(port, name, unavailable)
        with pytest.raises(NativeTurnPending) as pending_error:
            orchestrator.recover_native_turn(session, operation_id=op, expected_turn=turn)
        assert pending_error.value.turn == turn and pending_error.value.operation_id == op
        assert adapter.calls == 1 and state["observations"] == 0
        monkeypatch.setattr(port, name, original)
    receipt = orchestrator.recover_native_turn(session, operation_id=op, expected_turn=turn)
    assert receipt.native_result is not None and receipt.turn == turn and adapter.calls == 1
    assert f.runtime.events.get_event_by_command_id(op.command_id+":effect-unknown") is None
