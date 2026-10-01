"""AD-RET2 Phase A: real Runtime/port/orchestrator, synthetic native boundary.

No provider, service, deployment or authority transfer. Terminal-only callers
must opt in before receiving a nonterminal receipt.
"""
from dataclasses import replace

import pytest

from test_ohf_p1b_runtime_orchestrator import (
    FakeAdapter, _runtime_lease, _profile, _orchestrator, _op,
)
from test_slack_agent_dialogue_turn_watcher import _body
from control_plane.executive_runtime import Runtime, JobStatus, StateConflict
from control_plane.operator_harness_contract import NormalizedEvent
from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrationError


class BoundaryAdapter(FakeAdapter):
    def __init__(self, profile, kind="BLOCKED", *, boundary=True):
        super().__init__(profile)
        self.kind, self.boundary = kind, boundary
        self.events = ()
        self.candidate_calls = 0

    def read_events(self, cursor, *, timeout_seconds=30.0):
        self.cursor = cursor
        material = NormalizedEvent(
            attempt_id=cursor.attempt_id, session_epoch_id=cursor.session_epoch_id,
            process_generation_id=cursor.process_generation_id, turn_id=cursor.turn_id,
            kind=self.kind, provider_event_id="fixture-yield-1",
            payload_redacted={"body": _body(self.kind), "source_event_time_ms": None,
                              "replaces_event_id": None},
        )
        end = replace(material, kind="turn/completed", provider_event_id="fixture-end-1",
                      payload_redacted={"method": "turn/completed"})
        self.events = (material, end) if self.boundary else (material,)
        self.events = getattr(self, "transform", lambda value: value)(self.events)
        self.next_cursor = replace(cursor, local_sequence=len(self.events))
        return self.events, self.next_cursor

    def collect_candidate_result(self, turn):
        self.candidate_calls += 1
        if self.kind == "PROGRESS":
            return super().collect_candidate_result(turn)
        raise RuntimeError("fixture has a material yield, not a terminal candidate")


def setup(tmp_path, kind="BLOCKED", *, boundary=True):
    runtime, job, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = BoundaryAdapter(profile, kind, boundary=boundary)
    port, orchestrator = _orchestrator(runtime, lease, adapter)
    session = orchestrator.start_attempt(attempt_id=lease.attempt.attempt_id,
        requested=profile, operation_id=_op("ad-ret2-start"))
    return runtime, job, lease, profile, adapter, port, orchestrator, session


def drive(state, *, allow=True):
    return state[6].run_turn(state[7], operation_id=_op("ad-ret2-turn"),
                             allow_semantic_yield=allow)


def observations(runtime, attempt_id):
    return [e for e in runtime.events.list_events(attempt_id=attempt_id)
            if e.event_type == "OHF_SEMANTIC_YIELD_OBSERVED"]


def record(state, receipt, **changes):
    runtime, _, lease, _, adapter, *_ = state
    args = dict(turn=receipt.turn, events=adapter.events, cursor=adapter.next_cursor,
                fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
    args.update(changes)
    return runtime.operator_harness.record_semantic_yield(**args)


@pytest.mark.parametrize("kind", ["BLOCKED", "DECISION_REQUEST"])
def test_missing_candidate_yield_is_durable_without_terminalizing(tmp_path, kind):
    state = setup(tmp_path, kind)
    runtime, job, lease, profile, adapter, *_ = state
    receipt = drive(state)
    assert adapter.candidate_calls == 0
    assert receipt.requires_response is True
    assert not hasattr(receipt, "candidate")
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.RUNNING
    rows = observations(Runtime.at(tmp_path, clock=runtime.store.now_ms), lease.attempt.attempt_id)
    assert len(rows) == 1 and receipt.command_id == rows[0].command_id
    payload = rows[0].payload
    assert payload["source_revision"] == profile.workspace.base_sha
    assert payload["job_id"] == job.job_id and payload["worker_id"] == lease.attempt.worker_id
    assert payload["turn"]["process_generation_id"] == state[7].generation.process_generation_id
    assert payload["provider_native_turn_id"]
    assert payload["source_event_time_ms"] is None
    assert payload["routing_state"] == "PENDING_ACTION_TARGET"
    assert payload["action_target"] is None and payload["authority_granted"] is False
    assert payload["consumption_receipt"] is None
    assert not {"JOB_COMPLETED", "JOB_FAILED", "OHF_EPOCH_ABANDONED"}.intersection(
        e.event_type for e in runtime.events.list_events(attempt_id=lease.attempt.attempt_id))


def test_exact_replay_preserves_one_durable_event(tmp_path):
    state = setup(tmp_path)
    receipt = drive(state)
    assert record(state, receipt) == receipt.command_id
    original = observations(state[0], state[2].attempt.attempt_id)[0]
    reopened = Runtime.at(tmp_path, clock=state[0].store.now_ms)
    state = (reopened, *state[1:])
    assert record(state, receipt) == receipt.command_id
    assert observations(reopened, state[2].attempt.attempt_id) == [original]


def test_changed_payload_conflicts_and_preserves_original(tmp_path):
    state = setup(tmp_path)
    receipt = drive(state)
    event = state[4].events[0]
    changed = replace(event, payload_redacted={**event.payload_redacted,
        "body": {**event.payload_redacted["body"], "reason": "Different blocker"}})
    with pytest.raises(StateConflict):
        record(state, receipt, events=(changed, state[4].events[1]))
    assert len(observations(state[0], state[2].attempt.attempt_id)) == 1


@pytest.mark.parametrize("field,value", [
    ("attempt_id", "foreign-attempt"), ("session_epoch_id", "foreign-epoch"),
    ("process_generation_id", "foreign-generation"), ("turn_id", "foreign-turn"),
    ("turn_id", None), ("provider_event_id", None),
])
def test_foreign_or_unknown_source_identity_refuses(tmp_path, field, value):
    state = setup(tmp_path)
    receipt = drive(state)
    changed = replace(state[4].events[0], **{field: value})
    with pytest.raises(StateConflict):
        record(state, receipt, events=(changed, state[4].events[1]))


@pytest.mark.parametrize("extra", [
    {"actor": "sol"}, {"action_target": "newest-tab"},
    {"replaces_event_id": "unaccepted-replacement"}, {"source_event_time_ms": True},
])
def test_payload_cannot_grant_actor_or_correction_authority(tmp_path, extra):
    state = setup(tmp_path)
    receipt = drive(state)
    event = state[4].events[0]
    changed = replace(event, payload_redacted={**event.payload_redacted, **extra})
    with pytest.raises(StateConflict):
        record(state, receipt, events=(changed, state[4].events[1]))


def test_inflight_batch_is_not_a_completed_native_boundary(tmp_path):
    state = setup(tmp_path, boundary=False)
    with pytest.raises(OperatorHarnessOrchestrationError):
        drive(state)
    assert observations(state[0], state[2].attempt.attempt_id) == []


def test_progress_does_not_create_attention(tmp_path):
    state = setup(tmp_path, "PROGRESS")
    receipt = drive(state)
    assert receipt.candidate and state[4].candidate_calls == 1
    assert observations(state[0], state[2].attempt.attempt_id) == []


def test_terminal_only_caller_is_not_silently_given_yield_receipt(tmp_path):
    state = setup(tmp_path)
    with pytest.raises(OperatorHarnessOrchestrationError):
        drive(state, allow=False)
    assert state[4].candidate_calls == 1
    assert observations(state[0], state[2].attempt.attempt_id) == []


def test_pending_yield_cannot_be_bypassed_by_new_work_turn(tmp_path):
    state = setup(tmp_path)
    drive(state)
    calls = state[4].calls.count("begin_turn")
    with pytest.raises(StateConflict, match="semantic yield"):
        state[6].run_turn(state[7], operation_id=_op("unrelated-continue"))
    assert state[4].calls.count("begin_turn") == calls


def test_wrong_lease_does_not_reaccept_yield(tmp_path):
    state = setup(tmp_path)
    receipt = drive(state)
    with pytest.raises(StateConflict):
        record(state, receipt, lease_token="foreign-lease")
    assert len(observations(state[0], state[2].attempt.attempt_id)) == 1


def test_candidate_cannot_overwrite_a_durable_yield(tmp_path):
    state = setup(tmp_path)
    receipt = drive(state)
    candidate = FakeAdapter.collect_candidate_result(state[4], receipt.turn)
    with pytest.raises(StateConflict, match="semantic yield"):
        state[5].finish_operator_candidate(state[2].attempt.attempt_id, receipt.turn,
            candidate, state[4].events, state[4].next_cursor)


def test_pre_reserved_other_work_cannot_bypass_pending_attention(tmp_path):
    state = setup(tmp_path)
    state[5].begin_operator_turn(state[2].attempt.attempt_id,
        state[7].generation, _op("pre-reserved"))
    drive(state)
    before = state[4].calls.count("begin_turn")
    with pytest.raises(StateConflict, match="semantic yield"):
        state[6].run_turn(state[7], operation_id=_op("pre-reserved"))
    assert state[4].calls.count("begin_turn") == before


@pytest.mark.parametrize("mutation", ["subordinate", "mixed-ruling", "non-string-key",
    "duplicate-source-id", "unpaused", "oversized", "nonfinite"])
def test_malformed_first_batch_never_gets_durable_acceptance(tmp_path, mutation):
    state = setup(tmp_path)
    def transform(events):
        first, end = events
        if mutation == "subordinate":
            return (replace(first, native_subordinate_id="untrusted-child"), end)
        if mutation == "mixed-ruling":
            return (replace(first, kind="RULING"), first, end)
        if mutation == "non-string-key":
            return (replace(end, kind="progress", payload_redacted={1: "ambiguous"}), first, end)
        if mutation == "duplicate-source-id":
            return (first, replace(end, provider_event_id=first.provider_event_id))
        if mutation == "unpaused":
            return (replace(first, payload_redacted={**first.payload_redacted,
                "body": {**first.payload_redacted["body"], "work_paused": False}}), end)
        if mutation == "oversized":
            return (first, replace(end, payload_redacted={"padding": "a" * 65537}))
        return (first, replace(end, payload_redacted={"nonfinite": float("nan")}))
    state[4].transform = transform
    with pytest.raises(OperatorHarnessOrchestrationError):
        drive(state)
    assert observations(state[0], state[2].attempt.attempt_id) == []


def test_stop_keeps_historical_yield_but_refuses_fresh_acceptance(tmp_path):
    state = setup(tmp_path)
    receipt = drive(state)
    state[6].graceful_stop(state[7], operation_id=_op("ad-ret2-stop"))
    with pytest.raises(StateConflict):
        record(state, receipt)
    with pytest.raises(StateConflict):
        state[6].run_turn(state[7], operation_id=_op("late-continue"))
    assert len(observations(state[0], state[2].attempt.attempt_id)) == 1


def test_progress_cannot_replace_a_pending_decision(tmp_path):
    state = setup(tmp_path, "DECISION_REQUEST")
    receipt = drive(state)
    original = observations(state[0], state[2].attempt.attempt_id)
    changed = replace(state[4].events[0], kind="PROGRESS",
        payload_redacted={"body": _body("PROGRESS"), "source_event_time_ms": None,
                          "replaces_event_id": None})
    with pytest.raises(StateConflict):
        record(state, receipt, events=(changed, state[4].events[-1]))
    assert observations(state[0], state[2].attempt.attempt_id) == original


def test_observation_time_cannot_refresh_original_source_time(tmp_path):
    state = setup(tmp_path)
    def source_time(events):
        first, end = events
        return (replace(first, payload_redacted={**first.payload_redacted,
                        "source_event_time_ms": 1}), end)
    state[4].transform = source_time
    receipt = drive(state)
    original = observations(state[0], state[2].attempt.attempt_id)[0]
    now = state[0].store.now_ms()
    reopened = Runtime.at(tmp_path, clock=lambda: now + 1000)
    state = (reopened, *state[1:])
    assert record(state, receipt) == receipt.command_id
    assert observations(reopened, state[2].attempt.attempt_id) == [original]
    assert original.payload["source_event_time_ms"] == 1


@pytest.mark.parametrize("opt_in", [1, "true", None])
def test_nonboolean_opt_in_refuses_before_provider_turn(tmp_path, opt_in):
    state = setup(tmp_path)
    with pytest.raises(OperatorHarnessOrchestrationError):
        drive(state, allow=opt_in)
    assert state[4].calls.count("begin_turn") == 0
