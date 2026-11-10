"""Original COO API-requester receipt through real Runtime claim/result owners.

No native identity, running provider, installed grant or socket is simulated as
proved. Inert OHF completion uses the incumbent TX-5 and terminal seal helpers.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from common import coo_requester_return_contract as wire
from control_plane.ceo_intent import submit_intent
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.executive_runtime import (
    ExpectedChildSelection, OrchestrationDispatchOutcome, Runtime, StateConflict,
    expected_child_selection,
)
from tests.test_executive_os_phase1fc import _register, _v2_intent, _complete_ohf_role
from tests.test_hermes_selected_child_ingress import _admit_work_child

WORK = "WS:EXECUTIVE-CAPACITY-FABRIC"
CAPABILITY = "c" * 64


def _current():
    return None


def _fixture(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    _register(runtime, "worker-1")
    root = runtime.jobs.get_job(submit_intent(runtime, _v2_intent(
        business_impact="routine", workstream=WORK))["job_id"])
    child = _admit_work_child(SimpleNamespace(
        runtime=runtime, config=SimpleNamespace(worker_id="worker-1")), root)
    command = f"coo-cycle:{root.job_id}:dispatch:{child.job_id}:attempt:1"
    selection = ExpectedChildSelection(
        **{key: getattr(child, key) for key in (
            "root_job_id", "parent_job_id", "job_id", "plan_attempt_id",
            "plan_digest", "plan_step_id", "repair_round")},
        expected_current_attempt_id=None, attempt_ordinal=1, command_id=command)
    context = PrincipalAdmissionContext(WORK, "a" * 64, "authority:coo-test", "b" * 64)
    return SimpleNamespace(runtime=runtime, root=root, child=child, command=command,
                           selection=selection, context=context, capability=CAPABILITY)


def _claim(f, *, retained=True, guard=_current):
    private = dict(requester_context=f.context,
                   requester_capability_profile_digest=f.capability) if retained else {}
    with expected_child_selection(f.selection, admission_guard=guard, **private):
        outcome = f.runtime.attempts.dispatch_cycle_job(
            f.child.job_id, command_id=f.command, worker_id="worker-1")
    assert isinstance(outcome, OrchestrationDispatchOutcome)
    return outcome


def _finish(f, dispatch):
    _complete_ohf_role(f.runtime, dispatch, {
        "schema_version": "mastermind.work_result/v1", "root_job_id": f.root.job_id,
        "plan_attempt_id": f.child.plan_attempt_id, "plan_digest": f.child.plan_digest,
        "plan_step_id": f.child.plan_step_id, "repair_round": 0,
        "artifacts": [], "evidence_digests": []}, identity_seed=62003)


def _read(f, **changes):
    options = dict(job_id=f.child.job_id, command_id=f.command, context=f.context,
                   capability_profile_digest=f.capability, currentness_guard=_current)
    options.update(changes)
    return f.runtime.coo_selected_child_requester_return(**options)


def _request(f):
    return {"action": wire.ACK_ACTION, "command": f.command, "result": _read(f)}


def _ack(f, request=None, **changes):
    options = dict(context=f.context, capability_profile_digest=f.capability,
                   currentness_guard=_current)
    options.update(changes)
    return f.runtime.acknowledge_coo_selected_child_result(request or _request(f), **options)


def _events(f, event_type=wire.CONSUMPTION_EVENT):
    with f.runtime.store.read() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM events WHERE event_type=? ORDER BY event_id", (event_type,))]


def _corrupt_event(f, command, mutate):
    """Corrupt only the disposable database; restore immutability before commit."""
    with f.runtime.store.transaction() as connection:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='events_are_immutable_update'").fetchone()[0]
        row = dict(connection.execute("SELECT * FROM events WHERE command_id=?", (command,)).fetchone())
        mutate(row)
        connection.execute("DROP TRIGGER events_are_immutable_update")
        for key in ("payload_json", "actor", "job_id", "attempt_id", "worker_id", "quota_class", "aggregate_type", "aggregate_id", "created_at_ms"):
            connection.execute(f"UPDATE events SET {key}=? WHERE command_id=?", (row[key], command))
        connection.execute(trigger)


def test_original_claim_and_canonical_result_precede_explicit_acknowledgment(tmp_path):
    f = _fixture(tmp_path)
    dispatch = _claim(f)
    event = f.runtime.store.get_event_by_command_id(f.command)
    claim = event.payload["selected_child_requester"]
    assert claim == wire.validate_claim({"schema_version": wire.CLAIM_SCHEMA, "family": wire.FAMILY,
        "context": dataclasses.asdict(f.context), "capability_profile_digest": f.capability,
        "selection": dataclasses.asdict(f.selection)})
    with pytest.raises(StateConflict):
        _read(f)  # an actual claim/ACK is not terminal evidence
    assert not _events(f)
    _finish(f, dispatch)
    original = _read(f)
    for _ in range(3):
        assert _read(f) == original
    assert original["consumption"] is None and not _events(f)
    assert original["parent_consumed"] is False and original["acceptance"] == "not_accepted"
    result = _ack(f, {"action": wire.ACK_ACTION, "command": f.command, "result": original})
    assert result["consumption"]["family"] == wire.FAMILY
    assert wire.identity(result) == wire.identity(original)
    assert _read(f) == result
    assert _ack(f, {"action": wire.ACK_ACTION, "command": f.command, "result": original}) == result
    assert _ack(f) == result  # replay with returned receipt is the same operation
    assert len(_events(f)) == 1
    assert len(_events(f, "JOB_CLAIMED")) == 2  # original planner + original work
    assert f.runtime.jobs.get_job(f.child.job_id).attempt_count == 1
    assert not _events(f, "PARENT_RESULT_CONSUMED")
    # Family receipt is not a new Job lifecycle transition and cannot disturb
    # the canonical completion reader used by COO aggregation/independent review.
    assert f.runtime.validated_role_completion(
        job_id=f.child.job_id, expected_attempt_id=dispatch.attempt.attempt_id)


def test_legacy_claim_replay_never_adopts_current_requester(tmp_path):
    f = _fixture(tmp_path)
    dispatch = _claim(f, retained=False)
    replay = _claim(f)
    assert replay.attempt.attempt_id == dispatch.attempt.attempt_id
    assert "selected_child_requester" not in f.runtime.store.get_event_by_command_id(f.command).payload
    _finish(f, dispatch)
    assert _read(f) is None and not _events(f)


def test_claim_guard_revocation_rolls_back_requester_and_attempt(tmp_path):
    f = _fixture(tmp_path)
    def revoked():
        raise StateConflict("mission revoked")
    with pytest.raises(StateConflict, match="revoked"):
        _claim(f, guard=revoked)
    assert f.runtime.store.get_event_by_command_id(f.command) is None
    assert f.runtime.jobs.get_job(f.child.job_id).current_attempt_id is None
    assert not _events(f)


@pytest.mark.parametrize("field,value", [
    ("principal_binding_digest", "d" * 64), ("authority_generation_digest", "d" * 64),
    ("work_ref", "WS:FOREIGN-MISSION"), ("mission_authority_ref", "authority:foreign"),
])
def test_foreign_or_stale_principal_cannot_read_or_ack_original_result(tmp_path, field, value):
    f = _fixture(tmp_path)
    _finish(f, _claim(f))
    request = _request(f)
    foreign = dataclasses.replace(f.context, **{field: value})
    assert _read(f, context=foreign) is None
    with pytest.raises(StateConflict):
        _ack(f, request, context=foreign)
    assert not _events(f)


@pytest.mark.parametrize("field,value", [
    ("attempt_id", "attempt-foreign"), ("root_job_id", "JOB-900"),
    ("parent_job_id", "JOB-900"), ("job_id", "JOB-900"),
    ("requester_binding_digest", "d" * 64), ("result_envelope_digest", "d" * 64),
    ("terminal_evidence_digest", "d" * 64), ("work_ref", "WS:FOREIGN-MISSION"),
])
def test_changed_reviewed_descriptor_never_records_consumption(tmp_path, field, value):
    f = _fixture(tmp_path)
    _finish(f, _claim(f))
    request = _request(f)
    request["result"][field] = value
    with pytest.raises(StateConflict):
        _ack(f, request)
    assert not _events(f)


def test_changed_capability_and_precommit_revocation_cannot_ack(tmp_path):
    f = _fixture(tmp_path)
    _finish(f, _claim(f))
    request = _request(f)
    assert _read(f, capability_profile_digest="d" * 64) is None
    with pytest.raises(StateConflict):
        _ack(f, request, capability_profile_digest="d" * 64)
    calls = []
    def guard():
        calls.append(1)
        if len(calls) == 3:
            raise StateConflict("revoked before commit")
    with pytest.raises(StateConflict, match="revoked before commit"):
        _ack(f, request, currentness_guard=guard)
    assert len(calls) == 3 and not _events(f)


def test_concurrent_acknowledgment_and_lost_response_reconcile_one_original_receipt(tmp_path):
    f = _fixture(tmp_path)
    _finish(f, _claim(f))
    request = _request(f)
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _: _ack(f, request), range(8)))
    assert all(item == receipts[0] for item in receipts)
    assert len(_events(f)) == 1
    # Pretend the successful response was lost; read the original command and
    # original result instead of dispatching again or selecting another child.
    reopened = Runtime.at(tmp_path / "runtime")
    f.runtime = reopened
    assert _read(f) == receipts[0]
    assert _ack(f, request) == receipts[0]
    assert len(_events(f)) == 1 and len(_events(f, "JOB_CLAIMED")) == 2


def test_original_uncertain_dispatch_must_reconcile_before_ack(tmp_path):
    f = _fixture(tmp_path)
    dispatch = _claim(f)
    f.runtime.jobs.record_cycle_dispatch_effect_unknown(f.root.job_id,
        selected_job_id=f.child.job_id, dispatch_command_id=f.command)
    _finish(f, dispatch)
    with pytest.raises(StateConflict, match="uncertain"):
        _read(f)
    assert not _events(f)
    exact = f.runtime.attempts.dispatch_cycle_job(
        f.child.job_id, command_id=f.command, worker_id="worker-1")
    f.runtime.jobs.reconcile_cycle_dispatch_effect(f.root.job_id,
        selected_job_id=f.child.job_id, dispatch_command_id=f.command, receipt=exact)
    assert _ack(f)["consumption"] is not None
    assert len(_events(f, "JOB_CLAIMED")) == 2


@pytest.mark.parametrize("field,value", [
    ("actor", "foreign-owner"), ("worker_id", "worker-1"), ("quota_class", "default"),
    ("aggregate_type", "job"), ("aggregate_id", "foreign"), ("created_at_ms", 0),
])
def test_malformed_retained_acknowledgment_is_not_repaired_or_reissued(tmp_path, field, value):
    f = _fixture(tmp_path)
    _finish(f, _claim(f))
    request = _request(f)
    original = _ack(f, request)
    command = wire.consumption_command_id(original["attempt_id"])
    _corrupt_event(f, command, lambda row: row.update({field: value}))
    with pytest.raises(StateConflict):
        _read(f)
    with pytest.raises(StateConflict):
        _ack(f, request)
    assert len(_events(f)) == 1


def test_malformed_retained_requester_never_falls_back_to_legacy(tmp_path):
    f = _fixture(tmp_path)
    _finish(f, _claim(f))
    def mutate(row):
        payload = json.loads(row["payload_json"])
        payload["selected_child_requester"]["native_parent_consumed"] = True
        row["payload_json"] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    _corrupt_event(f, f.command, mutate)
    with pytest.raises(StateConflict, match="malformed"):
        _read(f)
    assert not _events(f)
