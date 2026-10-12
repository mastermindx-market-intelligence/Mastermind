"""Restart source recovery uses persisted identity and current Runtime fences."""
from dataclasses import replace

import pytest

from control_plane.executive_runtime import StateConflict
from control_plane.wake_persist import WakeLedgerRepository
from integrations.slack_agent_dialogue.persisted_wake_carrier import RequesterAnswerWakeExtension
from tests.test_w6c2_consultation_runtime import (
    _runtime_at, _consultations, _requester_answer_projection,
)


def prepared(tmp_path, *, persist=True):
    runtime = _runtime_at(tmp_path)
    owner = _consultations(runtime, tmp_path)
    projection = _requester_answer_projection(runtime, owner, tmp_path)
    if persist:
        RequesterAnswerWakeExtension(
            WakeLedgerRepository(runtime), projection,
        ).persist_requested_if_current(owner)
    return runtime, owner, projection


def test_restart_reconstructs_exact_source_without_packet_or_new_event(tmp_path):
    runtime, _, projection = prepared(tmp_path)
    before = runtime.events.list_events()
    restarted = _consultations(runtime, tmp_path)
    with runtime.store.transaction() as connection:
        recovered = restarted.recover_requester_answer_attention(
            projection.obligation, connection=connection,
        )
    assert recovered == projection
    assert runtime.events.list_events() == before


@pytest.mark.parametrize("mode", [
    "missing_request", "source_drift", "emitted_at_drift", "writer_lost",
    "consumed", "duplicate_answer", "duplicate_intent",
])
def test_recovery_holds_missing_ambiguous_stale_or_consumed_source(tmp_path, mode):
    runtime, owner, projection = prepared(tmp_path, persist=mode != "missing_request")
    obligation = projection.obligation
    if mode == "source_drift":
        obligation = replace(obligation, source_ref="consultation_answer_attention:" + "f" * 64)
    if mode == "emitted_at_drift":
        obligation = replace(obligation, emitted_at="2099-12-31T23:59:59Z")
    with runtime.store.transaction() as connection:
        if mode == "writer_lost":
            connection.execute("UPDATE process_generations SET executive_writer_held=0")
        elif mode in {"consumed", "duplicate_answer"}:
            answer = next(event for event in runtime.events.list_events(
                aggregate_type="consultation", aggregate_id=projection.identity.consultation_id,
                connection=connection,
            ) if event.event_type == "ANSWER_AVAILABLE")
            payload = dict(answer.payload)
            event_type = answer.event_type
            if mode == "consumed":
                event_type = "CONSUMED_BY_REQUESTER"
                payload["answer_message_key"] = payload["message_key"]
                payload["fact"] = event_type
            runtime.store.append_event(
                connection, aggregate_type="consultation",
                aggregate_id=answer.aggregate_id, event_type=event_type,
                job_id=answer.job_id, attempt_id=answer.attempt_id,
                payload=payload, command_id="consult:" + answer.aggregate_id + ":fixture-corrupt-" + mode,
            )
        elif mode == "duplicate_intent":
            runtime.store.append_event(
                connection, aggregate_type="consultation",
                aggregate_id=projection.identity.consultation_id, event_type="INTENT",
                job_id=projection.identity.requester_job_id,
                attempt_id=projection.identity.requester_attempt_id,
                payload={}, command_id="consult:" + projection.identity.consultation_id + ":duplicate-intent",
            )
    before = runtime.events.list_events()
    with runtime.store.transaction() as connection:
        with pytest.raises(StateConflict):
            owner.recover_requester_answer_attention(obligation, connection=connection)
    assert runtime.events.list_events() == before


def test_recovery_uses_owned_read_snapshot_without_writes(tmp_path):
    runtime, owner, projection = prepared(tmp_path)
    before = runtime.events.list_events()
    with runtime.store.read() as connection:
        recovered = owner.recover_requester_answer_attention(
            projection.obligation, connection=connection,
        )
    assert recovered == projection
    assert runtime.events.list_events() == before
