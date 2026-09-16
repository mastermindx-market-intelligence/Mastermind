"""Packet05 source falsifier; opt-in only, not a production worker/canary.

Run with pytest explicitly. ``requirement`` cases intentionally remain RED
until the incumbent shared writer implements the sustained observation seam.
Other cases characterize current behavior; passing them does not fix the gap.
Only synthetic provider messages and temporary Executive databases are used.
"""
from __future__ import annotations

import json
import socket
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
from test_ohf_p1b_runtime_orchestrator import (
    FakeAdapter, _runtime_lease, _profile, _orchestrator, _op,
)
from control_plane.executive_runtime import Runtime, JobStatus
from control_plane.operator_harness_contract import NormalizedEvent, EventCursor, TurnRef
from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrationError


class YieldAwaitingDecision(RuntimeError):
    """Synthetic provider reports no terminal candidate while work is paused."""

class YieldAdapter(FakeAdapter):
    def __init__(self, profile, kind, *, candidate_ready=False, foreign=False):
        super().__init__(profile)
        self.kind, self.candidate_ready, self.foreign = kind, candidate_ready, foreign
        self.observed = ()

    def read_events(self, cursor, *, timeout_seconds=30.0):
        self.calls.append("read_events")
        self.observed = (NormalizedEvent(
            attempt_id=cursor.attempt_id,
            session_epoch_id=cursor.session_epoch_id,
            process_generation_id="foreign-generation" if self.foreign else cursor.process_generation_id,
            turn_id=cursor.turn_id, kind=self.kind,
            provider_event_id="synthetic-return-one",
            payload_redacted={"reason": "Harmless fixture decision required"},
        ),)
        return self.observed, replace(cursor, local_sequence=cursor.local_sequence + 1)

    def collect_candidate_result(self, turn):
        if not self.candidate_ready:
            self.calls.append("collect_candidate_result")
            raise YieldAwaitingDecision("No terminal candidate exists")
        return super().collect_candidate_result(turn)


def persisted_observations(runtime, attempt_id):
    return [item for event in runtime.events.list_events(attempt_id=attempt_id)
            for item in event.payload.get("events", []) if isinstance(item, dict)]

@pytest.fixture(autouse=True)
def no_internet(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Network forbidden in packet05 source probe")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


def drive_yield(tmp_path, kind, *, candidate_ready=False, foreign=False):
    runtime, job, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = YieldAdapter(profile, kind, candidate_ready=candidate_ready, foreign=foreign)
    _, orchestrator = _orchestrator(runtime, lease, adapter)
    session = orchestrator.start_attempt(attempt_id=lease.attempt.attempt_id,
        requested=profile, operation_id=_op("packet05-start"))
    error = None
    try:
        orchestrator.run_turn(session, operation_id=_op("packet05-turn"))
    except OperatorHarnessOrchestrationError as exc:
        error = type(exc).__name__
    rows = runtime.events.list_events(attempt_id=lease.attempt.attempt_id)
    print(json.dumps({"kind": kind, "candidate_ready": candidate_ready,
        "foreign": foreign, "error": error, "job_id": job.job_id,
        "attempt_id": lease.attempt.attempt_id, "event_types": [e.event_type for e in rows],
        "observations_retained": len(persisted_observations(runtime, lease.attempt.attempt_id)),
        "fixture_only": True}, sort_keys=True))
    return runtime, job, lease, adapter, orchestrator, session, error

@pytest.mark.parametrize("kind", ["BLOCKED", "DECISION_REQUEST"])
def test_requirement_nonterminal_observation_survives_restart(tmp_path, kind):
    runtime, job, lease, adapter, _, _, error = drive_yield(tmp_path, kind)
    assert adapter.observed
    reopened = Runtime.at(tmp_path, clock=runtime.store.now_ms)
    retained = persisted_observations(reopened, lease.attempt.attempt_id)
    assert any(e.get("provider_event_id") == "synthetic-return-one" for e in retained), (
        "MISSING_JOIN: observed nonterminal return never reached durable Executive evidence"
    )


@pytest.mark.parametrize("kind", ["BLOCKED", "DECISION_REQUEST"])
def test_control_candidate_completion_retains_same_observation(tmp_path, kind):
    runtime, job, lease, _, _, _, error = drive_yield(tmp_path, kind, candidate_ready=True)
    assert error is None
    assert len(persisted_observations(runtime, lease.attempt.attempt_id)) == 1
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.RUNNING


@pytest.mark.parametrize("kind", ["BLOCKED", "DECISION_REQUEST"])
def test_control_foreign_generation_cannot_persist_as_candidate(tmp_path, kind):
    runtime, _, lease, _, _, _, error = drive_yield(
        tmp_path, kind, candidate_ready=True, foreign=True)
    assert error is not None
    assert persisted_observations(runtime, lease.attempt.attempt_id) == []

@pytest.mark.parametrize("fresh_wrapper", [False, True])
def test_control_applied_turn_is_not_replayed(tmp_path, fresh_wrapper):
    runtime, _, lease, adapter, orchestrator, session, error = drive_yield(tmp_path, "BLOCKED")
    assert error == "OperatorOperationApplied"
    if fresh_wrapper:
        _, orchestrator = _orchestrator(Runtime.at(tmp_path, clock=runtime.store.now_ms), lease, adapter)
    before = adapter.calls.count("begin_turn")
    try:
        orchestrator.run_turn(session, operation_id=_op("packet05-turn"))
    except Exception:
        pass
    assert adapter.calls.count("begin_turn") == before


@pytest.mark.parametrize("kind", ["BLOCKED", "DECISION_REQUEST"])
def test_control_missing_candidate_retains_start_not_semantic_return(tmp_path, kind):
    runtime, job, lease, _, _, _, error = drive_yield(tmp_path, kind)
    rows = runtime.events.list_events(attempt_id=lease.attempt.attempt_id)
    assert error == "OperatorOperationApplied"
    assert "OPERATOR_OPERATION_APPLIED" in {e.event_type for e in rows}
    assert "OHF_CANDIDATE_RESULT_RECORDED" not in {e.event_type for e in rows}
    assert persisted_observations(runtime, lease.attempt.attempt_id) == []
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.RUNNING


def observe_native_batch(tmp_path, *, interrupt=False):
    from test_codex_operator_adapter import _make_harness, _start
    from control_plane.codex_operator_adapter import CodexAdapterError
    harness = _make_harness(tmp_path, fault_server=True,
        extra_env={"OHF_FAKE_DELAY_COMPLETION": "1"})
    try:
        _, _, launch = _start(harness)
        turn = TurnRef("packet05-fixture-turn", harness.epoch.session_epoch_id,
            harness.generation.process_generation_id, harness.epoch.attempt_id)
        started = harness.adapter.begin_turn(operation_id=_op("native-yield"),
            turn=turn, generation=harness.generation, launch=launch)
        assert started.acknowledged
        state = harness.adapter._state(harness.generation)
        # Synthetic item on the already-bound fake provider turn; no provider authority.
        harness.adapter._ingest_turn_notifications(state, turn, [{"method": "item/completed",
            "params": {"threadId": state.provider_session_id, "item": {
                "id": "synthetic-yield-item", "type": "agentMessage",
                "text": "BLOCKED: harmless fixture decision required"}}}])
        if interrupt:
            harness.adapter.interrupt_turn(turn, operation_id=_op("fixture-interrupt"))
        error, returned = None, ()
        try:
            returned, _ = harness.adapter.read_events(EventCursor(turn.attempt_id,
                turn.session_epoch_id, turn.process_generation_id, turn_id=turn.turn_id),
                timeout_seconds=0.05 if not interrupt else 1.0)
        except CodexAdapterError as exc:
            error = type(exc).__name__ + ":" + exc.failure_class.value
        seen = tuple(state.events)
        print(json.dumps({"native_fixture_only": True, "interrupted": interrupt,
            "error": error, "buffered_kinds": [e.kind for e in seen],
            "returned_kinds": [e.kind for e in returned]}, sort_keys=True))
        return seen, returned, error
    finally:
        for state in harness.adapter._generations.values():
            state.client.close()


def test_requirement_available_native_batch_does_not_wait_for_terminal(tmp_path):
    seen, returned, error = observe_native_batch(tmp_path)
    assert any(e.provider_event_id == "synthetic-yield-item" for e in seen)
    assert any(e.provider_event_id == "synthetic-yield-item" for e in returned), (
        "MISSING_PRODUCER_SEAM: available nonterminal item waits on turn/completed; " + str(error)
    )


def test_control_same_native_turn_returns_after_explicit_interrupt(tmp_path):
    _, returned, error = observe_native_batch(tmp_path, interrupt=True)
    assert error is None
    assert any(e.kind == "turn/completed" for e in returned)
    assert any(e.provider_event_id == "synthetic-yield-item" for e in returned)


def test_control_current_normalizer_is_metadata_not_semantic_body(tmp_path):
    seen, _, _ = observe_native_batch(tmp_path)
    item = next(e for e in seen if e.provider_event_id == "synthetic-yield-item")
    assert item.kind == "item/completed"
    assert item.payload_redacted == {"method": "item/completed"}
