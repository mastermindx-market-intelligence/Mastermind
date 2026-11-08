"""Native completion uses original Runtime close/abandon/terminal owners.

All provider/process observations and enabling policy in this fixture are inert.
The transaction, reference, claim, quota, and COO behavior under test are real.
"""
import asyncio
import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from control_plane import executive_runtime as rt
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.native_conversation_result import NATIVE_CONVERSATION_TERMINAL_SCHEMA
from control_plane.operator_harness_contract import (
    OperationId, OperationReceiptKind, ProcessIdentityObservation, ProcessLiveness,
    ProviderWriterState, ReconcileObservation, SessionStartObservation, operation_receipt_command_id,
)
from control_plane.operator_harness_orchestrator import (
    OperatorEffectUnknown, OperatorHarnessOrchestrator, OperatorStartHandle,
)
from test_dsh_native_idle_close import _sealed
from test_dsh_native_runtime_result import _turn
from test_dsh_native_runtime_resume import _resume
from test_dsh_native_supervisor_conversation import _case as supervisor_case


def _dead(f):
    number = f.generation.generation_number
    return ReconcileObservation(ProcessLiveness.PROVEN_DEAD,
        ProcessIdentityObservation(2101 if number == 1 else 2102,
            2101 if number == 1 else 2102,
            "native-runtime-test" if number == 1 else "native-resumed-test", "fixture-boot"),
        True, ProviderWriterState.RELEASED, f.session_id)


def _driver(f, stop):
    lease = rt.AttemptLease(f.runtime.attempts.get_attempt(f.epoch.attempt_id), f.lease["lease_token"])
    driver = OperatorHarnessOrchestrator(ExecutiveOperatorHarnessPort(f.runtime, lease),
        SimpleNamespace(graceful_stop=stop), attestation_reader=lambda *a: pytest.fail("close re-attested"))
    session = OperatorStartHandle(f.epoch.attempt_id, f.epoch, f.generation,
                                  SessionStartObservation(f.session_id, _dead(f).observed_process))
    return driver, session


def _close(f, reference, *, idle=False):
    calls = []
    def stop(generation, *, operation_id):
        calls.append(operation_id)
        intent = f.runtime.events.get_event_by_command_id(operation_id.command_id)
        field = "native_idle_result" if idle else "native_terminal_result"
        assert intent.payload[field] == reference.to_wire()
        with pytest.raises(rt.StateConflict, match="close INTENT"):
            f.runtime.operator_harness.reserve_turn(epoch=f.epoch, generation=f.generation,
                operation_id=OperationId("ohf-op:no-send-during-final-close"), **f.lease)
        return _dead(f)
    driver, session = _driver(f, stop)
    operation = OperationId(("ohf-op:idle:" if idle else "ohf-op:final:") + f.generation.process_generation_id)
    driver.graceful_stop(session, operation_id=operation,
        **({"native_idle_result": reference} if idle else {"native_terminal_result": reference}))
    assert calls == [operation]
    applied = f.runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.APPLIED))
    assert applied.payload["executive_writer_released"] is False
    return operation


def _abandon(f):
    f.runtime.operator_harness.abandon_epoch(epoch=f.epoch, **f.lease)


def _terminal(f, reference):
    return f.runtime.operator_harness.native_conversation_terminal_payload(
        attempt_id=f.epoch.attempt_id, reference=reference)


@pytest.mark.parametrize("path", ["g1", "idle-g1", "g2-no-turn", "g2-with-turn"])
def test_native_terminal_releases_original_capacity_without_a_planner_envelope(tmp_path, monkeypatch, path):
    f, initial = _sealed(tmp_path, monkeypatch)
    reference = initial
    if path != "g1":
        _close(f, initial, idle=True)
        if path.startswith("g2"):
            f = _resume(f)
            if path == "g2-with-turn":
                turn, observed = _turn(f, 2)
                reference = f.runtime.operator_harness.seal_native_conversation_result(
                    turn=turn, observation=observed, **f.lease)
    if path != "idle-g1":
        _close(f, reference)
    _abandon(f)
    payload = _terminal(f, reference)
    assert payload["schema_version"] == NATIVE_CONVERSATION_TERMINAL_SCHEMA
    assert payload["closed_generation_id"] == f.generation.process_generation_id
    assert payload["native_result"] == reference.to_wire()
    assert "result_envelope" not in payload
    if path == "g2-no-turn":
        result = f.runtime.operator_harness.native_conversation_result(attempt_id=f.epoch.attempt_id, reference=reference)
        assert result["turn"]["process_generation_id"] != payload["closed_generation_id"]
    completed = f.runtime.attempts.complete_attempt(f.epoch.attempt_id, payload=payload, **f.lease)
    assert completed.status is rt.JobStatus.COMPLETED
    attempt = f.runtime.attempts.get_attempt(f.epoch.attempt_id)
    assert attempt.status is rt.AttemptStatus.COMPLETED
    quota = f.runtime.workers.get_quota_class(f.epoch.worker_id, "dsh-native")
    assert quota.active_attempt_id is None
    assert f.runtime.operator_harness.native_conversation_result(
        attempt_id=f.epoch.attempt_id, reference=initial)["job_id"] == f.job.job_id
    before = f.runtime.events.list_events()
    outcome = CooCycle(f.runtime).run_once(f.root.job_id)
    assert outcome.action == "NO_ACTION" and len(f.runtime.jobs.list_jobs()) == 2
    assert f.runtime.events.list_events() == before
    replay = f.runtime.attempts.dispatch_cycle_job(f.job.job_id, command_id=f.dispatch.command_id,
                                                      worker_id=f.epoch.worker_id)
    assert replay.outcome == "TERMINAL" and replay.lease_token is None
    terminal_events = [e for e in f.runtime.events.list_events()
                       if e.event_type == "JOB_COMPLETED" and e.attempt_id == f.epoch.attempt_id]
    assert len(terminal_events) == 1
    assert terminal_events[0].payload["native_terminal_digest"] == rt.orchestration_digest(payload)
    assert not any(e.event_type == "ORCHESTRATION_ROLE_RESULT_SEALED" for e in before)


@pytest.mark.parametrize("invalid", ["stale", "unacknowledged", "unsealed", "wire", "both"])
def test_native_final_intent_refuses_invalid_or_unsettled_result_before_stop(tmp_path, monkeypatch, invalid):
    f, reference = _sealed(tmp_path, monkeypatch)
    if invalid == "stale":
        turn, observed = _turn(f, 2)
        f.runtime.operator_harness.seal_native_conversation_result(turn=turn, observation=observed, **f.lease)
    elif invalid == "unacknowledged":
        f.runtime.operator_harness.reserve_turn(epoch=f.epoch, generation=f.generation,
            operation_id=OperationId("ohf-op:unacknowledged-before-final"), **f.lease)
    elif invalid == "unsealed":
        _turn(f, 2)
    calls = []
    driver, session = _driver(f, lambda *a, **k: calls.append(True))
    operation = OperationId("ohf-op:refused-native-final")
    options = dict(native_terminal_result=reference.to_wire() if invalid == "wire" else reference)
    if invalid == "both": options["native_idle_result"] = reference
    with pytest.raises(rt.StateConflict):
        driver.graceful_stop(session, operation_id=operation, **options)
    assert not calls and f.runtime.events.get_event_by_command_id(operation.command_id) is None


@pytest.mark.parametrize("field", ["native_result", "closed_generation_id", "effective_grant_digest", "schema_version", "extra"])
def test_terminal_payload_cannot_replace_original_result_or_closure(tmp_path, monkeypatch, field):
    f, reference = _sealed(tmp_path, monkeypatch)
    _close(f, reference)
    _abandon(f)
    payload = copy.deepcopy(_terminal(f, reference))
    if field == "native_result":
        payload[field]["event_id"] += 1
    elif field == "extra":
        payload["transcript"] = "not a result reference"
    else:
        payload[field] = "changed"
    with pytest.raises(rt.StateConflict):
        f.runtime.attempts.complete_attempt(f.epoch.attempt_id, payload=payload, **f.lease)
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.RUNNING
    assert f.runtime.workers.get_quota_class(f.epoch.worker_id, "dsh-native").active_attempt_id == f.epoch.attempt_id


def test_native_terminal_requires_physical_close_and_original_abandonment(tmp_path, monkeypatch):
    f, reference = _sealed(tmp_path, monkeypatch)
    with pytest.raises(rt.StateConflict):
        _terminal(f, reference)
    _close(f, reference)
    with pytest.raises(rt.StateConflict):
        _terminal(f, reference)
    _abandon(f)
    assert _terminal(f, reference)["native_result"] == reference.to_wire()
    with pytest.raises(rt.StateConflict):
        f.runtime.attempts.complete_attempt(f.epoch.attempt_id,
            payload={"schema_version": "mastermind.orchestration_terminal_receipt/v1"}, **f.lease)


def test_native_terminal_cannot_complete_a_legacy_creator(tmp_path):
    from tests.test_native_retained_runtime import _retained
    runtime, supervisor, retained, adapter = _retained(tmp_path)
    driver = supervisor._orchestrator(retained.lease, adapter)
    driver.graceful_stop(retained.session, operation_id=OperationId("ohf-op:legacy-native-schema-refusal"))
    lease = dict(fence_generation=retained.lease.attempt.fence_generation, lease_token=retained.lease.lease_token)
    runtime.operator_harness.abandon_epoch(epoch=retained.session.epoch, **lease)
    with pytest.raises(rt.StateConflict, match="original native creator"):
        runtime.attempts.complete_attempt(retained.session.attempt_id,
            payload={"schema_version": NATIVE_CONVERSATION_TERMINAL_SCHEMA}, **lease)


def test_unknown_final_close_reconciles_original_target_without_repeat_stop(tmp_path, monkeypatch):
    f, reference = _sealed(tmp_path, monkeypatch)
    calls = []
    def lost(generation, *, operation_id):
        calls.append(operation_id)
        raise OSError("inert final stop return lost")
    driver, session = _driver(f, lost)
    operation = OperationId("ohf-op:unknown-native-final")
    with pytest.raises(OperatorEffectUnknown):
        driver.graceful_stop(session, operation_id=operation, native_terminal_result=reference)
    with pytest.raises(OperatorEffectUnknown):
        driver.graceful_stop(session, operation_id=operation, native_terminal_result=reference)
    with pytest.raises(rt.StateConflict):
        _turn(f, 2)
    f.runtime.operator_harness.record_reconcile_observation(generation=f.generation,
        observation=_dead(f), **f.lease)
    _abandon(f)
    f.runtime.attempts.complete_attempt(f.epoch.attempt_id, payload=_terminal(f, reference), **f.lease)
    assert calls == [operation]


def test_retained_native_supervisor_uses_same_final_terminal_owner(tmp_path, monkeypatch):
    f, supervisor, lease, adapters, _ = supervisor_case(tmp_path, monkeypatch)
    retained = supervisor._run_claimed(f.job, lease, retain_native=True)
    asyncio.run(supervisor.finish_retained_native_job(retained))
    assert adapters[0].stop_calls == 1
    completed = f.runtime.jobs.get_job(f.job.job_id)
    assert completed.status is rt.JobStatus.COMPLETED
    assert completed.result["schema_version"] == NATIVE_CONVERSATION_TERMINAL_SCHEMA
    assert completed.result["native_result"] == retained.native_result.to_wire()


def test_retained_native_supervisor_consumes_original_idle_disposition(tmp_path, monkeypatch):
    f, supervisor, lease, adapters, _ = supervisor_case(tmp_path, monkeypatch)
    retained = supervisor._run_claimed(f.job, lease, retain_native=True)
    reference = asyncio.run(supervisor.idle_retained_native_job(retained))
    assert reference == retained.native_result and adapters[0].stop_calls == 1
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.RUNNING
    assert f.runtime.operator_harness.current_writer_generation(retained.session.epoch) == retained.session.generation
    with pytest.raises(rt.StateConflict):
        supervisor._require_retained_native(retained)
    # Already-closed G1 goes through existing post-shutdown completion, without
    # a second graceful stop. The original result reference remains the input.
    asyncio.run(supervisor.finish_retained_native_job(retained))
    asyncio.run(supervisor.finish_retained_native_job(retained))
    assert adapters[0].stop_calls == 1
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.COMPLETED


def test_final_applied_before_abandonment_remains_recoverable_after_lease_expiry(tmp_path, monkeypatch):
    f, reference = _sealed(tmp_path, monkeypatch)
    _close(f, reference)
    old = dict(f.lease)
    now = f.runtime.store.now_ms() + 3_700_000
    f.runtime = rt.Runtime.at(f.runtime.store.root, clock=lambda: now, lease_seconds=3600)
    replacement = f.runtime.attempts.takeover_expired_operator_harness(
        f.epoch.attempt_id, expected_fence_generation=old["fence_generation"],
        lease_owner="native-final-reconcile-fixture", lease_seconds=3600)
    f.lease = dict(fence_generation=replacement.attempt.fence_generation, lease_token=replacement.lease_token)
    with pytest.raises(rt.StateConflict):
        f.runtime.operator_harness.abandon_epoch(epoch=f.epoch, **old)
    with pytest.raises(rt.StateConflict, match="final closure"):
        _resume(f)
    _abandon(f)
    f.runtime.attempts.complete_attempt(f.epoch.attempt_id, payload=_terminal(f, reference), **f.lease)
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.COMPLETED


@pytest.mark.parametrize("idle", [False, True])
def test_cancellation_after_native_close_intent_does_not_erase_physical_receipt(tmp_path, monkeypatch, idle):
    f, reference = _sealed(tmp_path, monkeypatch)
    def stop(generation, *, operation_id):
        f.runtime.jobs.cancel_job(f.job.job_id)
        return _dead(f)
    driver, session = _driver(f, stop)
    operation = OperationId("ohf-op:native-close-cancellation-race")
    driver.graceful_stop(session, operation_id=operation,
        **({"native_idle_result": reference} if idle else {"native_terminal_result": reference}))
    assert f.runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.APPLIED)) is not None
    assert f.runtime.attempts.get_attempt(f.epoch.attempt_id).status is rt.AttemptStatus.CANCEL_REQUESTED
    _abandon(f)
    with pytest.raises(rt.StateConflict):
        f.runtime.attempts.complete_attempt(f.epoch.attempt_id, payload=_terminal(f, reference), **f.lease)
    f.runtime.attempts.acknowledge_cancel(f.epoch.attempt_id, **f.lease)
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.CANCELLED


@pytest.mark.parametrize("idle", [False, True])
def test_new_native_close_after_cancellation_still_refuses_before_effect(tmp_path, monkeypatch, idle):
    f, reference = _sealed(tmp_path, monkeypatch)
    f.runtime.jobs.cancel_job(f.job.job_id)
    calls = []
    driver, session = _driver(f, lambda *a, **k: calls.append(True))
    operation = OperationId("ohf-op:no-native-close-after-cancel")
    with pytest.raises(rt.StateConflict, match="running Attempt"):
        driver.graceful_stop(session, operation_id=operation,
            **({"native_idle_result": reference} if idle else {"native_terminal_result": reference}))
    assert not calls and f.runtime.events.get_event_by_command_id(operation.command_id) is None


@pytest.mark.parametrize("lost_at", ["abandon", "complete", "reconcile-before", "reconcile-after"])
def test_native_finalizer_reconciles_lost_original_returns_without_repeating_stop(tmp_path, monkeypatch, lost_at):
    f, supervisor, lease, adapters, _ = supervisor_case(tmp_path, monkeypatch)
    retained = supervisor._run_claimed(f.job, lease, retain_native=True)
    owner, method = ((f.runtime.attempts, "complete_attempt") if lost_at == "complete"
                     else (f.runtime.operator_harness, "abandon_epoch") if lost_at == "abandon"
                     else (f.runtime.operator_harness, "record_reconcile_observation"))
    original = getattr(owner, method)
    calls = []
    def lost(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1 and lost_at == "reconcile-before":
            raise OSError("inert original reconcile recording unavailable")
        value = original(*args, **kwargs)
        if len(calls) == 1:
            raise OSError("inert original committed return lost")
        return value
    monkeypatch.setattr(owner, method, lost)
    asyncio.run(supervisor.finish_retained_native_job(retained))
    events = f.runtime.events.list_events()
    assert adapters[0].stop_calls == 1
    assert sum(e.event_type == "JOB_COMPLETED" for e in events) == 1
    assert sum(e.event_type == "OHF_EPOCH_ABANDONED" for e in events) == 1
    assert not any(e.event_type in {"JOB_FAILED", OperationReceiptKind.EFFECT_UNKNOWN.value} for e in events)
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.COMPLETED
    before = f.runtime.events.list_events()
    asyncio.run(supervisor.finish_retained_native_job(retained))
    assert asyncio.run(supervisor.abort_retained_native_job(retained, reason="lost caller return")) is True
    assert f.runtime.events.list_events() == before and adapters[0].stop_calls == 1


def test_native_finalizer_continues_after_abandonment_without_generic_failure(tmp_path, monkeypatch):
    f, supervisor, lease, adapters, _ = supervisor_case(tmp_path, monkeypatch)
    retained = supervisor._run_claimed(f.job, lease, retain_native=True)
    original = f.runtime.attempts.complete_attempt
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise OSError("inert terminal bookkeeping unavailable before commit")
        return original(*args, **kwargs)
    monkeypatch.setattr(f.runtime.attempts, "complete_attempt", unavailable)
    with pytest.raises(OSError):
        asyncio.run(supervisor.finish_retained_native_job(retained))
    assert asyncio.run(supervisor.abort_retained_native_job(retained, reason="service cleanup")) is False
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.RUNNING
    asyncio.run(supervisor.finish_retained_native_job(retained))
    assert adapters[0].stop_calls == 1
    assert sum(e.event_type == "OHF_EPOCH_ABANDONED" for e in f.runtime.events.list_events()) == 1
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.COMPLETED


def test_native_unknown_close_stays_with_original_target_and_abort_preserves_result(tmp_path, monkeypatch):
    f, supervisor, lease, adapters, _ = supervisor_case(tmp_path, monkeypatch)
    retained = supervisor._run_claimed(f.job, lease, retain_native=True)
    calls = []
    def unknown(*args, **kwargs):
        calls.append(True)
        raise OSError("inert effect return unknown; original target still alive")
    monkeypatch.setattr(adapters[0], "graceful_stop", unknown)
    with pytest.raises(rt.StateConflict, match="original physical reconciliation"):
        asyncio.run(supervisor.finish_retained_native_job(retained))
    assert asyncio.run(supervisor.abort_retained_native_job(retained, reason="service cleanup")) is False
    with pytest.raises(rt.StateConflict, match="original physical reconciliation"):
        asyncio.run(supervisor.finish_retained_native_job(retained))
    assert calls == [True]
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.RUNNING


def test_native_supervisor_close_cancellation_uses_original_acknowledgment(tmp_path, monkeypatch):
    f, supervisor, lease, adapters, _ = supervisor_case(tmp_path, monkeypatch)
    retained = supervisor._run_claimed(f.job, lease, retain_native=True)
    original = adapters[0].graceful_stop
    def cancel_during(*args, **kwargs):
        f.runtime.jobs.cancel_job(f.job.job_id)
        return original(*args, **kwargs)
    monkeypatch.setattr(adapters[0], "graceful_stop", cancel_during)
    asyncio.run(supervisor.finish_retained_native_job(retained))
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.CANCELLED
    before = f.runtime.events.list_events()
    asyncio.run(supervisor.finish_retained_native_job(retained))
    assert before == f.runtime.events.list_events() and adapters[0].stop_calls == 1
    assert sum(e.event_type == "JOB_CANCELLED" for e in before) == 1
    assert not any(e.event_type == "JOB_COMPLETED" for e in before)


def test_native_tx8_refuses_stale_g1_after_g2_allocation_atomically(tmp_path, monkeypatch):
    f, reference = _sealed(tmp_path, monkeypatch)
    old_generation = f.generation
    _close(f, reference, idle=True)
    f = _resume(f)
    _close(f, reference)
    with pytest.raises(rt.StateConflict, match="latest exact physical generation"):
        f.runtime.operator_harness.abandon_epoch(epoch=f.epoch, generation=old_generation,
                                                native_terminal_result=reference, **f.lease)
    with f.runtime.store.read() as connection:
        assert connection.execute("SELECT state FROM harness_session_epochs WHERE session_epoch_id=?",
                                  (f.epoch.session_epoch_id,)).fetchone()[0] == "CURRENT"
    f.runtime.operator_harness.abandon_epoch(epoch=f.epoch, generation=f.generation,
                                            native_terminal_result=reference, **f.lease)
    f.runtime.attempts.complete_attempt(f.epoch.attempt_id, payload=_terminal(f, reference), **f.lease)


@pytest.mark.parametrize("drift", ["job-result", "event", "quota-held"])
def test_completed_native_readback_requires_original_atomic_proof(tmp_path, monkeypatch, drift):
    f, reference = _sealed(tmp_path, monkeypatch)
    _close(f, reference)
    _abandon(f)
    f.runtime.attempts.complete_attempt(f.epoch.attempt_id, payload=_terminal(f, reference), **f.lease)
    assert _terminal(f, reference)["status"] == "COMPLETED"
    with f.runtime.store.transaction() as connection:
        if drift == "job-result":
            connection.execute("UPDATE jobs SET result_json='{}' WHERE job_id=?", (f.job.job_id,))
        elif drift == "event":
            f.runtime.store.append_event(connection, aggregate_type="job", aggregate_id=f.job.job_id,
                event_type="JOB_COMPLETED", job_id=f.job.job_id, attempt_id=f.epoch.attempt_id,
                worker_id=f.dispatch.attempt.worker_id, quota_class=f.dispatch.attempt.quota_class,
                payload={})
        else:
            connection.execute("UPDATE worker_quota_classes SET status='BUSY',held_attempt_id=? WHERE worker_id=? AND quota_class=?",
                               (f.epoch.attempt_id, f.dispatch.attempt.worker_id, f.dispatch.attempt.quota_class))
    with pytest.raises(rt.StateConflict):
        _terminal(f, reference)


@pytest.mark.parametrize("unknown", [False, True])
def test_native_tx8_rechecks_physical_closure_in_original_transaction(tmp_path, monkeypatch, unknown):
    f, supervisor, lease, adapters, _ = supervisor_case(tmp_path, monkeypatch)
    retained = supervisor._run_claimed(f.job, lease, retain_native=True)
    original = f.runtime.operator_harness.abandon_epoch
    injected = []
    def changed(*args, **kwargs):
        if not injected:
            injected.append(True)
            observed = adapters[0].reconcile(retained.session.generation)
            observed = replace(observed,
                process_liveness=ProcessLiveness.UNKNOWN if unknown else ProcessLiveness.ALIVE,
                observed_process=ProcessIdentityObservation() if unknown else observed.observed_process,
                provider_writer_state=ProviderWriterState.RELEASED if unknown else ProviderWriterState.HELD)
            f.runtime.operator_harness.record_reconcile_observation(
                generation=retained.session.generation, observation=observed,
                fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
        return original(*args, **kwargs)
    monkeypatch.setattr(f.runtime.operator_harness, "abandon_epoch", changed)
    with pytest.raises(rt.StateConflict):
        asyncio.run(supervisor.finish_retained_native_job(retained))
    with f.runtime.store.read() as connection:
        assert connection.execute("SELECT state FROM harness_session_epochs WHERE session_epoch_id=?",
            (retained.session.epoch.session_epoch_id,)).fetchone()[0] == "CURRENT"
    assert asyncio.run(supervisor.abort_retained_native_job(retained, reason="changed closure evidence")) is False
    asyncio.run(supervisor.finish_retained_native_job(retained))
    assert adapters[0].stop_calls == 1
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.COMPLETED


def test_cancelled_native_unsealed_followup_reads_original_cancellation_without_success_claim(tmp_path, monkeypatch):
    f, supervisor, lease, adapters, _ = supervisor_case(tmp_path, monkeypatch)
    retained = supervisor._run_claimed(f.job, lease, retain_native=True)
    _turn(f, 2, candidate=False)
    f.runtime.jobs.cancel_job(f.job.job_id)
    assert asyncio.run(supervisor.abort_retained_native_job(retained, reason="cancel unsealed followup")) is True
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.CANCELLED
    assert adapters[0].cancel_calls == 1 and adapters[0].stop_calls == 0
    before = f.runtime.events.list_events()
    asyncio.run(supervisor.finish_retained_native_job(retained))
    assert asyncio.run(supervisor.abort_retained_native_job(retained, reason="lost cancellation return")) is True
    assert f.runtime.events.list_events() == before
    assert not any(e.event_type == "JOB_COMPLETED" for e in before)


def test_native_containment_applied_keeps_takeover_shape_and_cannot_resume(tmp_path, monkeypatch):
    f, reference = _sealed(tmp_path, monkeypatch)
    driver, session = _driver(f, lambda *a, **k: _dead(f))
    operation = OperationId("ohf-op:native-containment-crash")
    driver.graceful_stop(session, operation_id=operation)
    applied = f.runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.APPLIED))
    assert applied.payload["executive_writer_released"] is False
    old = dict(f.lease)
    now = f.runtime.store.now_ms() + 3_700_000
    f.runtime = rt.Runtime.at(f.runtime.store.root, clock=lambda: now, lease_seconds=3600)
    replacement = f.runtime.attempts.takeover_expired_operator_harness(f.epoch.attempt_id,
        expected_fence_generation=old["fence_generation"], lease_owner="native-containment-reconcile", lease_seconds=3600)
    f.lease = dict(fence_generation=replacement.attempt.fence_generation, lease_token=replacement.lease_token)
    with pytest.raises(rt.StateConflict, match="final closure"):
        _resume(f)
    before = f.runtime.events.list_events()
    with pytest.raises(rt.StateConflict):
        _turn(f, 2)
    assert f.runtime.events.list_events() == before
    f.runtime.operator_harness.record_reconcile_observation(
        generation=f.generation, observation=_dead(f), **f.lease)
    f.runtime.operator_harness.abandon_epoch(epoch=f.epoch, generation=f.generation, **f.lease)
    f.runtime.attempts.fail_attempt(f.epoch.attempt_id,
        payload=rt.JobPayload(summary="Original native containment settled.", current_state="failed_closed"), **f.lease)
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.FAILED
