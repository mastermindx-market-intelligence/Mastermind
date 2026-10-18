"""Integration tests: original Runtime SQL owner -> finalized receipt -> pure OHF metadata.

All source writes are to a private tmp_path SQLite fixture. These tests NEVER
call a real operator/provider, acquire production leases, or publish a route.
"""
from __future__ import annotations

import json

import pytest

from control_plane.ceo_intent import submit_intent
from control_plane.executive_runtime import (
    Runtime, RuntimeReadUnavailable, RuntimeRoleResultOverBudget, StateConflict,
)
from control_plane.operator_activity_projection import (
    ActivityProjectionRefusal, RetainedActivitySnapshot,
    project_retained_operator_activity,
)
from tests.test_executive_os_phase1fc import _register, _v2_intent
from tests import test_interactive_tx5_runtime as tx5
from tests.test_runtime_admitted_plan_read import _bound, _corrupt

WORK_REF = "WS:OHF-ACTIVITY"
SECRET = "PRIVATE-TOOL-INPUT-AND-TOKEN-EXCLUDE"


@pytest.fixture
def original(tmp_path, monkeypatch):
    """Genuine sealed, attested Operator Harness Attempt; not a regular planner."""
    existing_intent = tx5._intent
    monkeypatch.setattr(
        tx5, "_intent",
        lambda intent_id: {**existing_intent(intent_id), "workstream": WORK_REF},
    )
    runtime, root, child, dispatch, _epoch, _generation = tx5._started_interactive(tmp_path)
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.execution_mode == "OPERATOR_HARNESS"
    return runtime, root, child, attempt


def seed_candidate(
    original,
    index=1,
    *,
    raw_summary=SECRET,
    kind="claude/tool_use",
):
    runtime, root, child, attempt = original
    turn_id = f"TURN-RETAINED-{index}"
    turn = {
        "turn_id": turn_id,
        "attempt_id": attempt.attempt_id,
        "session_epoch_id": "EPOCH-1",
        "process_generation_id": "GEN-1",
    }
    fields = {
        key: turn[key]
        for key in ("attempt_id", "session_epoch_id", "process_generation_id")
    }
    event = {
        **fields, "turn_id": turn_id, "kind": kind,
        "provider_event_id": SECRET,
        "native_subordinate_id": SECRET,
        "payload_redacted": {
            "private_operator_tool_input": SECRET,
            "private_path": "/private/home/worker/.secrets",
        },
    }
    body = {
        "schema_version": "mastermind.operator_harness_candidate_evidence/v1",
        "turn": turn,
        "candidate": {
            **fields, "artifact_digest": None,
            "summary": raw_summary, "complete_job_permitted": False,
        },
        "events": [event],
        "cursor": {
            **fields, "turn_id": turn_id,
            "local_sequence": 1, "provider_replay_cursor": SECRET,
        },
    }
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="operator_turn", aggregate_id=turn_id,
            event_type="OHF_CANDIDATE_RESULT_RECORDED",
            command_id="ohf-candidate:" + turn_id,
            actor="supervisor", job_id=child.job_id,
            attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id, quota_class=attempt.quota_class,
            payload=body,
        )


def _read(reader, original):
    _runtime, root, child, attempt = original
    with reader.observe_bounded_read() as observation:
        snapshot = observation.read_retained_operator_activity_bounded(
            root.job_id, child.job_id, attempt.attempt_id,
        )
    return snapshot, observation.receipt


def _project(original, snapshot, receipt):
    _runtime, root, child, attempt = original
    return project_retained_operator_activity(
        snapshot, receipt,
        work_ref=WORK_REF, root_job_id=root.job_id,
        job_id=child.job_id, attempt_id=attempt.attempt_id,
    )


def test_original_runtime_bounded_read_and_finite_receipt_real_sql(original):
    seed_candidate(original)
    runtime, _root, _child, attempt = original
    before = len(runtime.events.list_events(attempt_id=attempt.attempt_id))
    with _bound(runtime) as (reader, _namespace, _binding):
        snapshot, receipt = _read(reader, original)
    assert isinstance(snapshot, RetainedActivitySnapshot)
    assert receipt.state == "SAME"
    assert snapshot.observation_source_identity == receipt.source_identity
    assert snapshot.root_metadata.work_ref == WORK_REF
    assert len(snapshot.events) == 1
    assert len(runtime.events.list_events(attempt_id=attempt.attempt_id)) == before
    view = _project(original, snapshot, receipt)
    assert view["availability"] == "RETAINED"
    assert view["normalized_events_in_sample"] == 1
    assert view["candidate_receipts_in_sample"] == 1
    assert view["rows"][0]["category"] == "TOOL_ACTIVITY"
    assert view["rows"][0]["candidate_event_id"] == snapshot.events[0].event_id
    assert view["source"]["live_worker_count"] is None
    assert SECRET not in json.dumps(view)
    assert "/private/home" not in json.dumps(view)
    assert "candidate_recorded_at" in view["rows"][0]


def test_empty_original_runtime_is_not_a_zero_worker_claim(original):
    runtime = original[0]
    with _bound(runtime) as (reader, _namespace, _binding):
        snapshot, receipt = _read(reader, original)
    view = _project(original, snapshot, receipt)
    assert view["availability"] == "NO_RETAINED_CANDIDATES"
    assert view["rows"] == []
    assert view["source"]["global_event_total"] is None
    assert view["source"]["live_worker_count"] is None


def test_unbound_runtime_source_witness_cannot_be_accepted(original):
    runtime = original[0]
    snapshot, receipt = _read(runtime, original)
    assert receipt.state == "UNKNOWN"
    with pytest.raises(ActivityProjectionRefusal, match="SOURCE_UNAVAILABLE"):
        _project(original, snapshot, receipt)


@pytest.mark.parametrize("wrong", ["root", "job", "attempt"])
def test_forged_root_job_attempt_refuses_before_returning_evidence(original, wrong):
    runtime, root, child, attempt = original
    kwargs = {
        "root_job_id": root.job_id, "job_id": child.job_id,
        "attempt_id": attempt.attempt_id,
    }
    kwargs[{"root": "root_job_id", "job": "job_id", "attempt": "attempt_id"}[wrong]] = (
        "JOB-999" if wrong != "attempt" else "ATT-" + "9" * 32
    )
    with _bound(runtime) as (reader, _namespace, _binding):
        with pytest.raises((StateConflict, RuntimeReadUnavailable)):
            with reader.observe_bounded_read() as obs:
                obs.read_retained_operator_activity_bounded(**kwargs)
        with pytest.raises(StateConflict, match="receipt"):
            _ = obs.receipt


def test_not_original_direct_child_or_missing_workstream_refuses(original):
    runtime, root, child, attempt = original
    # Attempt remained the same. Only the fixture's relationship is corrupted
    # after temporarily dropping SQL immutability triggers; never in production.
    _corrupt(runtime, lambda con: con.execute(
        "UPDATE jobs SET parent_job_id=NULL WHERE job_id=?", (child.job_id,),
    ))
    with _bound(runtime) as (reader, _namespace, _binding):
        with pytest.raises(RuntimeReadUnavailable):
            with reader.observe_bounded_read() as obs:
                obs.read_retained_operator_activity_bounded(
                    root.job_id, child.job_id, attempt.attempt_id,
                )


def test_truncation_of_more_than_64_original_candidate_records_is_explicit(original):
    for index in range(1, 66):
        seed_candidate(original, index=index, kind="item/completed")
    runtime = original[0]
    with _bound(runtime) as (reader, _namespace, _binding):
        snapshot, receipt = _read(reader, original)
    assert snapshot.source_truncated is True
    assert len(snapshot.events) == 64
    assert snapshot.events[0].aggregate_id == "TURN-RETAINED-2"
    assert snapshot.events[-1].aggregate_id == "TURN-RETAINED-65"
    result = _project(original, snapshot, receipt)
    assert result["availability"] == "PARTIAL"
    assert result["candidate_receipts_in_sample"] == 64
    assert result["normalized_events_in_sample"] == 64
    assert result["omitted_in_sample"] == 32
    assert len(result["rows"]) == 32
    assert result["source"]["source_truncated"] is True


def test_bounded_metadata_read_rejects_large_payload_before_raw_projection(original):
    seed_candidate(original, raw_summary="S" * 265_000)
    runtime, root, child, attempt = original
    with _bound(runtime) as (reader, _namespace, _binding):
        with pytest.raises(RuntimeRoleResultOverBudget):
            with reader.observe_bounded_read() as observation:
                observation.read_retained_operator_activity_bounded(
                    root.job_id, child.job_id, attempt.attempt_id,
                )
        with pytest.raises(StateConflict):
            _ = observation.receipt


def test_original_single_selection_budget_does_not_allow_second_event_read(original):
    runtime, root, child, attempt = original
    with _bound(runtime) as (reader, _namespace, _binding):
        with pytest.raises(StateConflict):
            with reader.observe_bounded_read() as observer:
                observer.read_retained_operator_activity_bounded(
                    root.job_id, child.job_id, attempt.attempt_id,
                )
                observer.read_retained_operator_activity_bounded(
                    root.job_id, child.job_id, attempt.attempt_id,
                )
        with pytest.raises(StateConflict):
            _ = observer.receipt


def test_no_durable_workstream_refuses_internal_source_selection(tmp_path):
    # An older strict-v2 root may have a valid lineage without a workstream.
    # It cannot be exposed under a caller-invented WS selector.
    from tests.test_executive_terminal_return import _completed_planner
    runtime, planner, attempt = _completed_planner(tmp_path)
    with _bound(runtime) as (reader, _namespace, _binding):
        with pytest.raises(RuntimeReadUnavailable, match="workstream"):
            with reader.observe_bounded_read() as observation:
                observation.read_retained_operator_activity_bounded(
                    planner.root_job_id, planner.job_id, attempt.attempt_id,
                )


def test_original_attempt_worker_assignment_mismatch_is_not_a_valid_activity_subject(original):
    runtime, root, child, attempt = original
    _register(runtime, "worker-b")
    _corrupt(runtime, lambda con: con.execute(
        "UPDATE jobs SET assigned_worker_id=? WHERE job_id=?", ("worker-b", child.job_id),
    ))
    with _bound(runtime) as (reader, _namespace, _binding):
        with pytest.raises(RuntimeReadUnavailable, match="Attempt identity"):
            with reader.observe_bounded_read() as observation:
                observation.read_retained_operator_activity_bounded(
                    root.job_id, child.job_id, attempt.attempt_id,
                )


def test_aggregate_source_bytes_cap_prevents_many_individually_valid_big_candidates(original):
    for index in range(1, 10):
        seed_candidate(original, index=index, raw_summary="S" * 246_000)
    runtime, root, child, attempt = original
    with _bound(runtime) as (reader, _namespace, _binding):
        with pytest.raises(RuntimeRoleResultOverBudget):
            with reader.observe_bounded_read() as observation:
                observation.read_retained_operator_activity_bounded(
                    root.job_id, child.job_id, attempt.attempt_id,
                )

def test_regular_sealed_worker_cannot_disclose_forged_ohf_candidate(tmp_path):
    """Same root/work/Job/Attempt is insufficient without the genuine OHF mode."""
    runtime = Runtime.at(tmp_path / "regular-runtime")
    _register(runtime, "worker-a")
    receipt = submit_intent(
        runtime, _v2_intent(intent_id="CEO-SEALED-WORKER-NEGATIVE", workstream=WORK_REF),
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    child = runtime.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatched = runtime.attempts.dispatch_cycle_job(
        child.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{child.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert dispatched is not None
    attempt = runtime.attempts.get_attempt(dispatched.attempt.attempt_id)
    assert attempt is not None and attempt.execution_mode != "OPERATOR_HARNESS"
    # A synthetic raw EventRegistry entry has the candidate event label but
    # never crossed the actual harness write owner. No activity is released.
    seed_candidate((runtime, root, child, attempt))
    with _bound(runtime) as (reader, _namespace, _binding):
        with pytest.raises(RuntimeReadUnavailable, match="Attempt identity"):
            with reader.observe_bounded_read() as observation:
                observation.read_retained_operator_activity_bounded(
                    root.job_id, child.job_id, attempt.attempt_id,
                )
        with pytest.raises(StateConflict):
            _ = observation.receipt

def test_real_lease_fenced_harness_candidate_to_original_runtime_read(tmp_path, monkeypatch):
    """Actual incumbent harness writer, not a synthetic EventRegistry insert."""
    previous = tx5._intent
    monkeypatch.setattr(
        tx5, "_intent",
        lambda intent_id: {**previous(intent_id), "workstream": WORK_REF},
    )
    runtime, root, child, dispatch, epoch, generation = tx5._started_interactive(tmp_path)
    operation = tx5.OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:1")
    turn = tx5._reserve_turn(runtime, dispatch, epoch, generation, 1)
    tx5._acknowledge_turn(runtime, dispatch, turn, operation)
    tx5._record_candidate(runtime, dispatch, turn)
    assert runtime.jobs.get_job(child.job_id).status.value == "RUNNING"
    with _bound(runtime) as (reader, _namespace, _binding):
        with reader.observe_bounded_read() as observation:
            snapshot = observation.read_retained_operator_activity_bounded(
                root.job_id, child.job_id, dispatch.attempt.attempt_id,
            )
        receipt = observation.receipt
    view = project_retained_operator_activity(
        snapshot, receipt, work_ref=WORK_REF, root_job_id=root.job_id,
        job_id=child.job_id, attempt_id=dispatch.attempt.attempt_id,
    )
    assert receipt.state == "SAME"
    assert snapshot.attempt.execution_mode == "OPERATOR_HARNESS"
    assert len(snapshot.events) == 1
    assert snapshot.events[0].aggregate_id == turn.turn_id
    assert view["rows"] == [{
        "candidate_event_id": snapshot.events[0].event_id,
        "turn_id": turn.turn_id, "ordinal_in_candidate": 0,
        "category": "TURN_COMPLETED",
        "candidate_recorded_at": snapshot.events[0].created_at,
    }]
    assert view["source"]["live_worker_count"] is None
    assert view["availability"] == "RETAINED"
