"""Regressions for durable acquisition ownership and exact evidence consumption."""
from __future__ import annotations

import copy
import dataclasses
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_plane import coo_observation as observation
from control_plane import coo_external_observation as external
from control_plane import executive_runtime as runtime_module
from control_plane.executive_authority import ExecutiveAuthorityPolicy
from control_plane.executive_orchestration_result import OrchestrationResultError, _validate_plan
from control_plane.executive_runtime import Runtime, StateConflict, _validated_plan_admission
from ops.fabric_launch.finite_watch import SourceUnavailable
from test_coo_external_observation import (
    CLOCK, DEADLINE, HEAD, RUN_ID, _FakeNetwork, _counts, _create_work, _cycle, _events,
    _prepared, ci_facts, ci_source, gate,
)


def _advance(case, host=True):
    return case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host if host else None)


def _admission(case):
    return next(event.payload for event in case.runtime.events.list_events(
        job_id=case.root.job_id) if event.event_type == "COO_PLAN_ADMITTED")["steps"][0]["observation"]


def test_v6_normalization_cannot_smuggle_a_valid_v2_external_gate(tmp_path):
    network = _FakeNetwork([ci_facts()])
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)
    with case.runtime.store.read() as connection:
        root = connection.execute("SELECT * FROM jobs WHERE job_id=?", (case.root.job_id,)).fetchone()
        _admitted, body = _validated_plan_admission(connection, root)
    assert _validate_plan(body, outer={
        "expected_root_job_id": case.root.job_id, "run_id": body["plan_attempt_id"]}) == body
    body = copy.deepcopy(body)
    body["schema_version"] = "mastermind.execution_plan/v6"
    before = _counts(case.runtime)
    with pytest.raises(OrchestrationResultError, match="plan version"):
        _validate_plan(body, outer={
            "expected_root_job_id": case.root.job_id, "run_id": body["plan_attempt_id"]})
    assert _counts(case.runtime) == before and not network.calls


@pytest.mark.parametrize("denied", [False, True])
def test_another_runtime_cannot_take_over_a_live_read_after_its_timeout(tmp_path, denied):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def reader(source, **budget):
        calls.append(source)
        entered.set()
        assert release.wait(5)
        if denied:
            raise SourceUnavailable({"code": "GH_AUTH_REFUSED", "terminal": True})
        return {"facts": ci_facts(), "api_calls": 3, "response_bytes": 100}

    case = _prepared(tmp_path, gates=[gate(ci_source(), timeout=1000)], reader=reader)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_advance, case)
        try:
            assert entered.wait(5)
            case.clock[0] = DEADLINE + 1
            reopened = Runtime.at(case.path, clock=lambda: case.clock[0])
            waiting = reopened.jobs.advance_cycle_observation(
                case.root.job_id, "step-1", observation_host=case.host)
            assert waiting["disposition"] == "UNRESOLVED" and not waiting["created"]
            assert len(calls) == 1
            assert len(_events(case, observation.RESERVATION_EVENT_TYPE)) == 1
            assert not _events(case, observation.EVENT_TYPE)
        finally:
            release.set()
        result = future.result(timeout=5)
    assert result["disposition"] == ("DENIED" if denied else "EXPIRED")
    replay = _advance(case, host=False)
    assert replay["record"] == result["record"] and not replay["created"]
    assert len(calls) == 1
    with pytest.raises(StateConflict):
        _create_work(case)


def test_a_hash_correct_record_without_a_reservation_never_opens_work(tmp_path):
    network = _FakeNetwork([ci_facts()])
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)
    admitted = _admission(case)
    disposition, snapshot = external.evaluate_sample(ci_source(), ci_facts())
    record = observation.make_external_record(
        admitted, sample_index=999, reservation_command_id="unrelated-reservation",
        started_at_ms=CLOCK, finished_at_ms=CLOCK, disposition=disposition,
        snapshot=snapshot, previous_snapshot_digest=None, api_calls=1, response_bytes=64)
    with case.runtime.store.transaction() as connection:
        case.runtime.store.append_event(
            connection, aggregate_type="job", aggregate_id=case.root.job_id,
            event_type=observation.EVENT_TYPE, actor="coo", job_id=case.root.job_id,
            attempt_id=admitted["plan_attempt_id"], payload=record,
            command_id=observation.record_command_id(admitted, 999), timestamp_ms=CLOCK)
    with pytest.raises(StateConflict, match="reservation"):
        _advance(case, host=False)
    with pytest.raises(StateConflict, match="reservation"):
        _create_work(case)
    assert not network.calls


def _seed_external_events(case, *, reservation_change=None, record_metadata=None):
    admitted = _admission(case)
    reservation = observation.make_reservation(
        admitted, sample_index=1, source_kind="github_ci",
        source_digest=external.source_digest(admitted["spec"]["source"]),
        reserved_at_ms=CLOCK, deadline_at_ms=DEADLINE,
        reserved_api_calls=3, reserved_response_bytes=65536, sample_timeout_ms=5000)
    if reservation_change:
        reservation.update(reservation_change)
    disposition, snapshot = external.evaluate_sample(ci_source(), ci_facts())
    record = observation.make_external_record(
        admitted, sample_index=1,
        reservation_command_id=observation.reservation_command_id(admitted, 1),
        started_at_ms=CLOCK, finished_at_ms=CLOCK, disposition=disposition,
        snapshot=snapshot, previous_snapshot_digest=None, api_calls=1, response_bytes=64)
    metadata = dict(aggregate_type="job", aggregate_id=case.root.job_id,
                    event_type=observation.EVENT_TYPE, actor="coo", job_id=case.root.job_id,
                    attempt_id=admitted["plan_attempt_id"], payload=record,
                    command_id=observation.record_command_id(admitted, 1), timestamp_ms=CLOCK)
    if record_metadata:
        metadata.update(record_metadata)
    # Seed an invalid historical producer directly; never disable or alter the
    # immutable-events triggers to manufacture corruption after the fact.
    with case.runtime.store.transaction() as connection:
        case.runtime.store.append_event(
            connection, aggregate_type="job", aggregate_id=case.root.job_id,
            event_type=observation.RESERVATION_EVENT_TYPE, actor="coo", job_id=case.root.job_id,
            attempt_id=admitted["plan_attempt_id"], payload=reservation,
            command_id=observation.reservation_command_id(admitted, 1), timestamp_ms=CLOCK)
        case.runtime.store.append_event(connection, **metadata)


@pytest.mark.parametrize("field", [
    "actor", "aggregate_id", "job_id", "attempt_id", "worker_id", "quota_class",
])
def test_record_envelope_is_validated_on_every_settled_read(tmp_path, field):
    network = _FakeNetwork([ci_facts()])
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)
    values = {"actor": "another-owner", "aggregate_id": case.planner.job_id,
              "job_id": case.planner.job_id, "attempt_id": None,
              "worker_id": case.dispatch.attempt.worker_id, "quota_class": "codex-coo"}
    _seed_external_events(case, record_metadata={field: values[field]})
    with pytest.raises(StateConflict, match="envelope"):
        _advance(case, host=False)
    with pytest.raises(StateConflict, match="envelope"):
        _create_work(case)
    assert not network.calls


@pytest.mark.parametrize("field,value", [
    ("source_digest", "f" * 64), ("reserved_api_calls", 1),
    ("reserved_response_bytes", 262144), ("sample_index", 2),
])
def test_reservation_source_and_charges_are_revalidated(tmp_path, field, value):
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=_FakeNetwork([ci_facts()]))
    _seed_external_events(case, reservation_change={field: value})
    with pytest.raises(StateConflict):
        _advance(case, host=False)
    with pytest.raises(StateConflict):
        _create_work(case)


@pytest.mark.parametrize("overrun", ["api_calls", "response_bytes"])
def test_over_budget_reader_result_preserves_unsettled_original(tmp_path, overrun):
    calls = []

    def reader(source, **budget):
        calls.append(source)
        return {"facts": ci_facts(),
                "api_calls": budget["max_api_calls"] + (overrun == "api_calls"),
                "response_bytes": budget["max_response_bytes"] + (overrun == "response_bytes")}

    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=reader)
    with pytest.raises(StateConflict, match="reserved budget"):
        _advance(case)
    case.runtime = Runtime.at(case.path, clock=lambda: case.clock[0])
    assert _advance(case)["disposition"] == "UNRESOLVED"
    assert len(calls) == 1
    assert len(_events(case, observation.RESERVATION_EVENT_TYPE)) == 1
    assert not _events(case, observation.EVENT_TYPE)


def test_error_denial_replays_and_never_reads_again(tmp_path):
    network = _FakeNetwork(error=SourceUnavailable({"code": "GH_AUTH_REFUSED", "terminal": True}))
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)
    first = _advance(case)
    assert first["disposition"] == "DENIED"
    case.runtime = Runtime.at(case.path, clock=lambda: case.clock[0])
    assert _advance(case, host=False)["record"] == first["record"]
    assert len(network.calls) == 1
    with pytest.raises(StateConflict, match="not satisfied"):
        _create_work(case)


def test_transient_error_is_closed_and_can_use_a_new_bounded_reservation(tmp_path):
    calls = []

    def reader(source, **budget):
        calls.append(source)
        if len(calls) == 1:
            raise SourceUnavailable({"code": "GH_API_TIMEOUT"})
        return {"facts": ci_facts(), "api_calls": 3, "response_bytes": 100}

    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=reader)
    first = _advance(case)
    assert first["disposition"] == "UNAVAILABLE"
    case.runtime = Runtime.at(case.path, clock=lambda: case.clock[0])
    second = _advance(case)
    assert second["disposition"] == "MATERIAL"
    assert second["record"]["sample_index"] == 2
    assert len(_events(case, observation.RESERVATION_EVENT_TYPE)) == 2


def test_original_denial_settles_when_fresh_finite_effects_are_no_longer_permitted(
    tmp_path, monkeypatch
):
    ended = [False]
    fresh = runtime_module._finite_fresh_effect
    settled = runtime_module._finite_existing_effect
    settlement_calls = []

    def require_fresh(*args):
        if ended[0]:
            raise StateConflict("finite control context has expired")
        return fresh(*args)

    def require_original(*args):
        settlement_calls.append(args[2])
        return settled(*args)

    def reader(source, **budget):
        ended[0] = True
        raise SourceUnavailable({"code": "GH_AUTH_REFUSED", "terminal": True})

    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=reader)
    monkeypatch.setattr(runtime_module, "_finite_fresh_effect", require_fresh)
    monkeypatch.setattr(runtime_module, "_finite_existing_effect", require_original)
    result = _advance(case)
    assert result["disposition"] == "DENIED"
    assert settlement_calls == [case.root.job_id]
    assert _advance(case, host=False)["record"] == result["record"]


def test_cancellation_during_read_retains_a_nonmaterial_original_result(tmp_path):
    holder = {}

    def reader(source, **budget):
        holder["case"].runtime.jobs.cancel_job(holder["case"].root.job_id)
        return {"facts": ci_facts(), "api_calls": 3, "response_bytes": 100}

    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=reader)
    holder["case"] = case
    result = _advance(case)
    assert result["disposition"] == "EXPIRED"
    assert _advance(case, host=False)["record"] == result["record"]
    with pytest.raises(StateConflict):
        _create_work(case)


def test_committed_material_survives_acquisition_deadline_and_policy_drift(tmp_path, monkeypatch):
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=_FakeNetwork([ci_facts()]))
    result = _advance(case)
    case.clock[0] = DEADLINE + 1
    policy = ExecutiveAuthorityPolicy.load()
    monkeypatch.setattr(ExecutiveAuthorityPolicy, "load", classmethod(
        lambda cls, path=None: dataclasses.replace(policy, sha256="9" * 64)))
    replay = _advance(case, host=False)
    assert replay["record"] == result["record"]
    with pytest.raises(StateConflict, match="policy drifted"):
        _create_work(case)


def test_pending_sample_yields_to_an_independent_ready_sibling(tmp_path):
    network = _FakeNetwork([ci_facts(status="in_progress")])
    case = _prepared(tmp_path, gates=[gate(ci_source()), None], reader=network)
    outcome = _cycle(case).run_once(case.root.job_id)
    assert outcome.action == "DISPATCHED"
    assert outcome.selected_job_id == case.members[0].job_id
    assert len(network.calls) == 1
    assert len(_events(case, observation.EVENT_TYPE)) == 1
    assert not any(job.plan_step_id == "step-1" for job in case.runtime.jobs.list_jobs())


def test_existing_reservation_events_rotate_zero_interval_pending_leaves(tmp_path):
    seen = []

    def reader(source, **budget):
        run_id = source["selected_runs"][0]["run_id"]
        seen.append(run_id)
        return {"facts": ci_facts(run_id=run_id, status="in_progress"),
                "api_calls": 3, "response_bytes": 100}

    case = _prepared(tmp_path, gates=[gate(ci_source()), gate(ci_source(
        runs=((RUN_ID + 1, 1),)))], reader=reader)
    for _ in range(3):
        outcome = _cycle(case).run_once(case.root.job_id)
        assert outcome.action == "NO_ACTION"
        assert outcome.receipt["reason"] == "observation_pending"
    assert seen == [RUN_ID, RUN_ID + 1, RUN_ID]


@pytest.mark.parametrize("mutation", ["run_head", "conclusion"])
def test_material_ci_requires_run_commit_and_meaningful_conclusion(tmp_path, mutation):
    facts = ci_facts()
    if mutation == "run_head":
        facts["runs"][0]["head_sha"] = "b" * 40
    else:
        facts["runs"][0]["conclusion"] = None
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=_FakeNetwork([facts]))
    result = _advance(case)
    assert result["disposition"] == ("STALE" if mutation == "run_head" else "UNAVAILABLE")
    with pytest.raises(StateConflict):
        _create_work(case)


def test_pending_gate_yields_review_pressure_without_bypassing_review_priority(tmp_path):
    from test_executive_os_phase1fc import _complete_ohf_role
    from test_executive_coo_observation import _register_independent_reviewer

    network = _FakeNetwork([ci_facts(status="in_progress")])
    case = _prepared(tmp_path, gates=[gate(ci_source()), None], reader=network,
                     review_indices=(1,))
    target = case.members[0]
    work = case.runtime.attempts.dispatch_cycle_job(
        target.job_id, command_id=f"coo-cycle:{case.root.job_id}:dispatch:{target.job_id}:attempt:1")
    _complete_ohf_role(case.runtime, work, {
        "schema_version": "mastermind.work_result/v1", "root_job_id": case.root.job_id,
        "plan_attempt_id": target.plan_attempt_id, "plan_digest": target.plan_digest,
        "plan_step_id": target.plan_step_id, "repair_round": 0,
        "artifacts": [], "evidence_digests": []}, identity_seed=8820)
    review = case.runtime.jobs.create_cycle_review(
        case.root.job_id, target.job_id,
        command_id=f"coo-cycle:{case.root.job_id}:create-review:{target.job_id}:1")
    blocked = [True]
    attempted = []

    def dispatch(job_id, command_id):
        attempted.append(job_id)
        if blocked[0] and job_id == review.job_id:
            return None
        return case.runtime.attempts.dispatch_cycle_job(job_id, command_id=command_id)

    cycle = _cycle(case, dispatch)
    first = cycle.run_once(case.root.job_id)
    assert first.action == "NO_ACTION" and first.receipt["reason"] == "observation_pending"
    retained = first.receipt["review_capacity_pressure"]
    assert retained["action"] == "NO_ACTION"
    assert retained["receipt"]["reason"] == "exact_dispatch_unavailable"
    assert review.job_id in retained["receipt"]["unavailable_job_ids"]
    assert attempted == [review.job_id] and len(network.calls) == 1
    assert case.runtime.jobs.get_job(review.job_id).attempt_count == 0
    assert not any(job.plan_step_id == "step-1" for job in case.runtime.jobs.list_jobs())

    _register_independent_reviewer(case, review)
    blocked[0] = False
    attempted.clear()
    second = cycle.run_once(case.root.job_id)
    assert second.action == "DISPATCHED" and second.selected_job_id == review.job_id
    assert attempted == [review.job_id] and len(network.calls) == 1
