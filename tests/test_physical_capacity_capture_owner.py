"""Original broker/Event transactions with synthetic owner probes only."""
import dataclasses
import json
import time

import pytest
from control_plane import executive_physical_admission as admission
from control_plane import physical_capacity_capture_owner as capture
from control_plane.executive_physical_resources import PhysicalResourceRefusal
from tests.test_finite_initial_transaction import unbegun, snap


def compose(s):
    return admission.compose(s.runtime.store, s.operation, None, job_id=s.job.job_id,
        root_job_id=s.job.root_job_id, parent_job_id=s.job.parent_job_id,
        dispatch_command_id=s.command, provider_row=s.provider_row,
        monotonic_deadline=time.monotonic() + 15)


def reserve(s, caller, reservation):
    return s.runtime.broker.reserve_physical(reservation, caller_context=caller)


def begin(s, caller, reservation, reserved):
    return s.runtime.broker.begin_physical({"reservation": {**reservation, "command_id": caller.begin_command_id},
        "commitments": [{"commitment_id": c["commitment_id"], "allocation_generation": c["allocation_generation"], "expected_revision": c["revision"]}
                        for c in reserved["receipt"]["commitments"]]}, caller_context=caller)


def test_same_capture_is_saved_in_original_reserve_and_begin_without_extra_collector_calls(unbegun, monkeypatch):
    s = unbegun
    calls = []
    for name in ("_collect_pressure", "_collect_capacity"):
        original = getattr(admission, name)
        def wrapped(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)
        monkeypatch.setattr(admission, name, wrapped)
    caller, reservation = compose(s)
    observations = json.loads(caller.observations_json)
    reserved = reserve(s, caller, reservation)
    assert reserved["code"] == "RESERVED"
    begun = begin(s, caller, reservation, reserved)
    assert begun["code"] == "BEGUN"
    for command in (caller.reserve_command_id, caller.begin_command_id):
        event = s.runtime.store.get_event_by_command_id(command)
        retained = event.payload["capacity_capture"]
        assert retained["snapshot"] == observations["host_capacity_evidence"]["snapshot"]
        assert retained["snapshot_sha256"] == observations["host_capacity_evidence"]["snapshot_sha256"]
        assert retained["binding"]["request_fingerprint"] == caller.fingerprint
        assert retained["binding"]["source_commit_sha"] == "e" * 40
        assert retained["capability"] == "OBSERVATION_ONLY"
        assert retained["can_place_work"] is False
        raw = json.dumps(retained)
        assert str(s.world.policy_path) not in raw
        assert "observations_json" not in raw and "subject_digest" not in raw
    assert calls == ["_collect_pressure", "_collect_capacity"]


def test_lost_reply_replay_preserves_original_event_and_capture_bytes(unbegun):
    s = unbegun
    caller, reservation = compose(s)
    reserved = reserve(s, caller, reservation)
    begun = begin(s, caller, reservation, reserved)
    before = snap(s)
    originals = [s.runtime.store.get_event_by_command_id(c) for c in (caller.reserve_command_id, caller.begin_command_id)]
    assert reserve(s, caller, reservation)["code"] == "RECONCILED"
    assert begin(s, caller, reservation, reserved)["fresh_begin"] is False
    assert snap(s) == before
    assert [s.runtime.store.get_event_by_command_id(c) for c in (caller.reserve_command_id, caller.begin_command_id)] == originals


@pytest.mark.parametrize("phase", ["reserve", "begin"])
def test_failure_after_event_rolls_back_capture_event_and_debits(unbegun, monkeypatch, phase):
    s = unbegun
    caller, reservation = compose(s)
    reserved = reserve(s, caller, reservation) if phase == "begin" else None
    before = snap(s)
    original = s.runtime.broker._physical_guard
    def fail(request, context, connection, stage, epoch):
        result = original(request, context, connection, stage, epoch)
        if stage == "after_event" and (request.get("reservation", request)["command_id"] ==
                                       (caller.begin_command_id if phase == "begin" else caller.reserve_command_id)):
            raise RuntimeError("synthetic rollback boundary")
        return result
    monkeypatch.setattr(s.runtime.broker, "_physical_guard", fail)
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        if phase == "begin":
            begin(s, caller, reservation, reserved)
        else:
            reserve(s, caller, reservation)
    assert snap(s) == before


def test_ordinary_dictionary_cannot_be_attached_as_capture(unbegun):
    s = unbegun
    caller, reservation = compose(s)
    before = snap(s)
    with pytest.raises(PhysicalResourceRefusal, match="custody"):
        with s.runtime.store.transaction() as connection:
            s.runtime.broker._physical_event(connection, reservation, "fake", "reserve", "fingerprint", {}, s.clock.value,
                _capacity_capture={"snapshot": "supplied"})
    assert snap(s) == before


def test_original_capture_cannot_be_rebound_to_another_command_or_reconciliation(unbegun):
    s = unbegun
    caller, reservation = compose(s)
    context = json.loads(caller.observations_json)
    from control_plane.executive_physical_resources import evaluate_reservation
    with s.runtime.store.read() as connection:
        policy = json.loads(caller.policy_json)
        evaluation = evaluate_reservation(reservation, policy=policy, observations=context, current_charges=[], decision_time_ms=s.clock.value, production=True)
        sealed = capture.mint_capacity_capture(s.runtime.broker, caller, reservation, evaluation, connection=connection, timestamp=s.clock.value)
    with pytest.raises(PhysicalResourceRefusal):
        capture.capture_for_event(sealed, store=s.runtime.store, reservation={**reservation, "command_id": "other"}, action="reserve", original_event_id=None, timestamp=s.clock.value)
    with pytest.raises(PhysicalResourceRefusal):
        capture.capture_for_event(sealed, store=s.runtime.store, reservation=reservation, action="reserve", original_event_id=1, timestamp=s.clock.value)
    with pytest.raises(PhysicalResourceRefusal):
        capture.capture_for_event(sealed, store=s.runtime.store, reservation=reservation, action="begin", original_event_id=None, timestamp=s.clock.value)
    changed = {**reservation, "source_binding": {**reservation["source_binding"], "commit_sha": "f" * 40}}
    with pytest.raises(PhysicalResourceRefusal):
        capture.capture_for_event(sealed, store=s.runtime.store, reservation=changed, action="reserve", original_event_id=None, timestamp=s.clock.value)
    with pytest.raises(PhysicalResourceRefusal):
        capture.capture_for_event(sealed, store=s.runtime.store, reservation=reservation, action="reserve", original_event_id=None, timestamp=s.clock.value + 1)


def test_full_event_size_refuses_before_any_capture_or_debit_is_written(unbegun):
    s = unbegun
    caller, reservation = compose(s)
    from control_plane.executive_physical_resources import evaluate_reservation
    with s.runtime.store.read() as connection:
        evaluation = evaluate_reservation(reservation, policy=json.loads(caller.policy_json),
            observations=json.loads(caller.observations_json), current_charges=[], decision_time_ms=s.clock.value, production=True)
        sealed = capture.mint_capacity_capture(s.runtime.broker, caller, reservation, evaluation, connection=connection, timestamp=s.clock.value)
    before = snap(s)
    with pytest.raises(PhysicalResourceRefusal, match="Event budget"):
        with s.runtime.store.transaction() as connection:
            s.runtime.broker._physical_event(connection, reservation, "fake", "reserve", "fingerprint", {"large": "x" * 65536}, s.clock.value,
                _capacity_capture=sealed)
    assert snap(s) == before


def test_forged_physical_context_is_not_a_capture_origin(unbegun):
    s = unbegun
    caller, reservation = compose(s)
    forged = dataclasses.replace(caller, observations_json="{}")
    with s.runtime.store.read() as connection:
        with pytest.raises(PhysicalResourceRefusal):
            capture.mint_capacity_capture(s.runtime.broker, forged, reservation, {}, connection=connection, timestamp=s.clock.value)
