"""Real Runtime/OHF follow-up turns preserve the initially accepted plan."""
from __future__ import annotations

from dataclasses import replace

import pytest


from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.executive_runtime import AttemptLease, StateConflict, _json_dumps
from control_plane.operator_harness_contract import (
    CandidateResult, EventCursor, NormalizedEvent, OperationId,
    ProcessIdentityObservation, SessionStartObservation, TurnStartObservation,
    compare_launch,
)
from control_plane.operator_harness_orchestrator import (
    OperatorHarnessOrchestrator, OperatorSessionReceipt, OperatorEffectUnknown,
    OperatorHarnessOrchestrationError,
)
from tests.test_interactive_tx5_runtime import (
    _attestation, _canonical_plan, _observation_for_plan, _profile,
    _started_interactive,
)


class _Provider:
    """Provider fixture only; transaction, lease and seal owners are real."""
    def __init__(self, runtime, root, dispatch, epoch, generation):
        self.runtime, self.root, self.dispatch = runtime, root, dispatch
        self.epoch, self.generation = epoch, generation
        self.started = []
        self.raw_reads = []

    def begin_turn(self, *, operation_id, turn, generation, launch):
        self.started.append(turn)
        return TurnStartObservation(f"native-{turn.turn_id}", True)

    def read_events(self, cursor, *, timeout_seconds):
        event = NormalizedEvent(
            cursor.attempt_id, cursor.session_epoch_id,
            cursor.process_generation_id, cursor.turn_id, "turn.completed",
            payload_redacted={"status": "complete"})
        return (event,), EventCursor(
            cursor.attempt_id, cursor.session_epoch_id,
            cursor.process_generation_id, local_sequence=1,
            turn_id=cursor.turn_id)

    def collect_candidate_result(self, turn):
        return CandidateResult(
            turn.attempt_id, turn.session_epoch_id,
            turn.process_generation_id, "e" * 64, "Useful bounded follow-up.")

    def observe_raw_role_result(self, turn):
        self.raw_reads.append(turn.turn_id)
        return _observation_for_plan(
            self.runtime, self.dispatch, self.epoch, self.generation, turn,
            _canonical_plan(self.runtime, self.root, self.dispatch))


def _driver(tmp_path):
    runtime, root, parent, dispatch, epoch, generation = _started_interactive(tmp_path)
    profile = _profile(dispatch)
    observed = _attestation(profile)
    session = OperatorSessionReceipt(
        dispatch.attempt.attempt_id, epoch, generation,
        SessionStartObservation(
            "SESSION-INTERACTIVE",
            ProcessIdentityObservation(2101, 2101, "interactive-start", "boot")),
        observed, compare_launch(profile, observed))
    port = ExecutiveOperatorHarnessPort(
        runtime, AttemptLease(dispatch.attempt, str(dispatch.lease_token)))
    provider = _Provider(runtime, root, dispatch, epoch, generation)
    driver = OperatorHarnessOrchestrator(
        port, provider, attestation_reader=lambda *_args: observed)
    return runtime, parent, port, provider, session, driver


def test_first_interactive_driver_turn_still_seals_the_plan(tmp_path):
    runtime, parent, port, provider, session, driver = _driver(tmp_path)
    first = driver.run_turn(session, operation_id=OperationId("ohf-op:driver:first"))
    seal = runtime.events.get_event_by_command_id(
        f"orchestration-result-seal:{session.attempt_id}")
    assert seal is not None
    assert seal.payload["turn_id"] == first.turn.turn_id
    assert provider.raw_reads == [first.turn.turn_id]
    assert runtime.jobs.get_job(parent.job_id).status.value == "RUNNING"


def test_followup_driver_returns_without_resealing_the_initial_plan(tmp_path):
    runtime, parent, port, provider, session, driver = _driver(tmp_path)
    first = driver.run_turn(session, operation_id=OperationId("ohf-op:driver:first"))
    seal_key = f"orchestration-result-seal:{session.attempt_id}"
    before = runtime.events.get_event_by_command_id(seal_key)
    followup = driver.run_turn(
        session, operation_id=OperationId("ohf-op:driver:followup"))
    after = runtime.events.get_event_by_command_id(seal_key)
    assert followup.turn.turn_id != first.turn.turn_id
    assert followup.candidate.summary == "Useful bounded follow-up."
    assert before == after
    assert provider.raw_reads == [first.turn.turn_id]
    assert len(provider.started) == 2
    assert runtime.events.get_event_by_command_id(
        f"ohf-candidate:{followup.turn.turn_id}") is not None
    assert runtime.jobs.get_job(parent.job_id).status.value == "RUNNING"


def _first(tmp_path):
    runtime, parent, port, provider, session, driver = _driver(tmp_path)
    first = driver.run_turn(session, operation_id=OperationId("ohf-op:driver:first"))
    return runtime, parent, port, provider, session, driver, first


def test_followup_does_not_require_another_structured_plan(tmp_path):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    def no_second_plan(_turn):
        raise AssertionError("a conversational follow-up is not another plan")
    provider.observe_raw_role_result = no_second_plan
    second = driver.run_turn(session, operation_id=OperationId("ohf-op:driver:text"))
    assert second.candidate.summary == "Useful bounded follow-up."
    assert runtime.jobs.get_job(parent.job_id).status.value == "RUNNING"


def test_eight_real_driver_turns_work_but_ninth_still_refuses(tmp_path):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    key = f"orchestration-result-seal:{session.attempt_id}"
    initial = runtime.events.get_event_by_command_id(key)
    for ordinal in range(2, 9):
        result = driver.run_turn(
            session, operation_id=OperationId(f"ohf-op:driver:limit:{ordinal}"))
        assert result.candidate.complete_job_permitted is False
    with pytest.raises(StateConflict, match="cardinality"):
        driver.run_turn(session, operation_id=OperationId("ohf-op:driver:limit:9"))
    assert len(provider.started) == 8
    assert provider.raw_reads == [first.turn.turn_id]
    assert runtime.events.get_event_by_command_id(key) == initial


def test_new_driver_reconstructs_plan_and_does_not_replay_applied_operation(tmp_path):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    new_driver = OperatorHarnessOrchestrator(
        port, provider, attestation_reader=lambda *_args: session.observed)
    second = new_driver.run_turn(
        session, operation_id=OperationId("ohf-op:driver:restart"))
    restarted = OperatorHarnessOrchestrator(
        port, provider, attestation_reader=lambda *_args: session.observed)
    with pytest.raises(StateConflict, match="not retryable"):
        restarted.run_turn(session, operation_id=OperationId("ohf-op:driver:restart"))
    assert len(provider.started) == 2
    assert provider.raw_reads == [first.turn.turn_id]
    assert second.turn.turn_id != first.turn.turn_id


def test_plan_projection_is_zero_write(tmp_path):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    with runtime.store.read() as connection:
        before = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    one = port.existing_interactive_plan_seal(session.attempt_id, session.generation)
    two = port.existing_interactive_plan_seal(session.attempt_id, session.generation)
    with runtime.store.read() as connection:
        after = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert isinstance(one, str) and len(one) == 64 and one == two
    assert after == before


@pytest.mark.parametrize("field,value", [
    ("generation_number", 2), ("worker_id", "foreign-worker"),
    ("session_epoch_id", "foreign-epoch"),
])
def test_forged_generation_is_refused_before_provider(tmp_path, field, value):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    changed = replace(session, generation=replace(session.generation, **{field: value}))
    with pytest.raises(StateConflict):
        driver.run_turn(changed, operation_id=OperationId("ohf-op:driver:foreign"))
    assert len(provider.started) == 1


def test_wrong_attempt_cannot_borrow_an_interactive_plan(tmp_path):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    with pytest.raises(StateConflict, match="different AttemptLease"):
        port.existing_interactive_plan_seal("foreign-attempt", session.generation)
    assert len(provider.started) == 1


def test_corrupt_initial_seal_is_refused_without_dispatch(tmp_path):
    runtime, parent, port, provider, session, driver = _driver(tmp_path)
    key = f"orchestration-result-seal:{session.attempt_id}"
    # Inject a malformed pre-existing record only into the disposable test DB.
    # Do not disable the real append-only UPDATE/DELETE guards.
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection, aggregate_type="attempt", aggregate_id=session.attempt_id,
            event_type="ORCHESTRATION_ROLE_RESULT_SEALED", command_id=key,
            actor="fixture", job_id=parent.job_id, attempt_id=session.attempt_id,
            worker_id=port.lease.attempt.worker_id, quota_class="default",
            payload={"schema_version": "mastermind.orchestration_role_result_seal/v1",
                     "role_result_digest": "0" * 64},
            timestamp_ms=runtime.store.now_ms())
    with pytest.raises(StateConflict):
        driver.run_turn(session, operation_id=OperationId("ohf-op:driver:corrupt"))
    assert provider.started == []


def test_existing_plan_event_remains_database_immutable(tmp_path):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    key = f"orchestration-result-seal:{session.attempt_id}"
    original = runtime.events.get_event_by_command_id(key)
    with pytest.raises(StateConflict, match="events are immutable"):
        with runtime.store.transaction() as connection:
            connection.execute("UPDATE events SET payload_json=? WHERE command_id=?",
                               (_json_dumps({}), key))
    assert runtime.events.get_event_by_command_id(key) == original


def test_lost_provider_reply_stays_in_flight_across_driver_recreation(tmp_path):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    def lose_reply(*, operation_id, turn, generation, launch):
        provider.started.append(turn)
        raise TimeoutError("fixture reply lost after provider dispatch")
    provider.begin_turn = lose_reply
    with pytest.raises(OperatorEffectUnknown):
        driver.run_turn(session, operation_id=OperationId("ohf-op:driver:lost"))
    recreated = OperatorHarnessOrchestrator(
        port, provider, attestation_reader=lambda *_args: session.observed)
    with pytest.raises(StateConflict, match="not retryable"):
        recreated.run_turn(session, operation_id=OperationId("ohf-op:driver:lost"))
    with pytest.raises(StateConflict, match="in-flight"):
        recreated.run_turn(session, operation_id=OperationId("ohf-op:driver:replacement"))
    assert len(provider.started) == 2


def test_concurrent_followup_cannot_start_a_second_provider_turn(tmp_path):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    real_begin = provider.begin_turn
    contender = OperatorHarnessOrchestrator(
        port, provider, attestation_reader=lambda *_args: session.observed)
    def begin_with_competitor(**kwargs):
        with pytest.raises(StateConflict, match="in-flight"):
            contender.run_turn(session, operation_id=OperationId("ohf-op:driver:contender"))
        return real_begin(**kwargs)
    provider.begin_turn = begin_with_competitor
    driver.run_turn(session, operation_id=OperationId("ohf-op:driver:incumbent"))
    assert len(provider.started) == 2


@pytest.mark.parametrize("invalid", [True, [], "bad", "A" * 64])
def test_malformed_optional_plan_projection_refuses_before_dispatch(tmp_path, invalid):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    port.existing_interactive_plan_seal = lambda *_args: invalid
    with pytest.raises(OperatorHarnessOrchestrationError, match="seal is invalid"):
        driver.run_turn(session, operation_id=OperationId("ohf-op:driver:bad-projection"))
    assert len(provider.started) == 1


def test_changed_seal_after_collection_cannot_be_reported_successful(tmp_path):
    runtime, parent, port, provider, session, driver, first = _first(tmp_path)
    reader = port.existing_interactive_plan_seal
    reads = []
    def changed_after_result(*args):
        value = reader(*args)
        reads.append(value)
        return value if len(reads) == 1 else "0" * 64
    port.existing_interactive_plan_seal = changed_after_result
    with pytest.raises(OperatorHarnessOrchestrationError, match="seal changed"):
        driver.run_turn(session, operation_id=OperationId("ohf-op:driver:post-drift"))
    assert len(provider.started) == 2
    assert runtime.events.get_event_by_command_id(
        f"ohf-candidate:{provider.started[-1].turn_id}") is not None
    assert provider.raw_reads == [first.turn.turn_id]
