"""L1B3-5: crash between the persisted adapter receipt and record_process.

The launch receipt is durable evidence the launch TOOK EFFECT and names the
provider session; the attempt row has no identity because the process died
before ``record_process``.  These tests pin the one added reattach path:
``adopt_attempt(..., reattach_provider_session_id=…)`` records the identity
in the SAME CAS adoption transaction, and ``reconcile_restart`` consults an
injected ``provider_receipt_reader`` so an identity-less claim is adopted
under its receipt — never expired and requeued into a second launch.

Run: TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
     -p no:cacheprovider tests/test_executive_supervisor_provider_reattach.py
"""
import pytest

import control_plane.executive_supervisor as owner
from control_plane.executive_runtime import StateConflict
from tests.test_executive_supervisor import (
    FakeAdapter,
    FakeInspector,
    _runtime_and_job,
    _supervisor,
)

RECEIPT_SESSION = "mcp:launch:b48db002cb8495bd8de7d2c27ba512bd719a69598f9b2c0687d2907f5feca52e"


def _claimed_identity_less(runtime, job_id):
    """A CLAIMED attempt whose launch took effect but whose process identity
    never landed on the row — the exact L1B3-5 crash window."""
    lease = runtime.broker.claim(job_id, lease_owner="dead-original-owner")
    assert lease is not None
    attempt = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert attempt.pid is None and attempt.provider_session_id is None
    return lease, attempt


# ---------------------------------------------------------------------------
# the runtime adoption primitive
# ---------------------------------------------------------------------------

def test_adopt_without_identity_still_refuses_without_a_receipt_session(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease, attempt = _claimed_identity_less(runtime, job_id)
    with pytest.raises(StateConflict, match="no durable process/provider identity"):
        runtime.attempts.adopt_attempt(
            lease.attempt.attempt_id,
            expected_fence_generation=attempt.fence_generation,
            lease_owner="restart-supervisor",
        )


def test_adopt_with_receipt_session_records_identity_in_the_same_cas(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease, attempt = _claimed_identity_less(runtime, job_id)

    adopted = runtime.attempts.adopt_attempt(
        lease.attempt.attempt_id,
        expected_fence_generation=attempt.fence_generation,
        lease_owner="restart-supervisor",
        reattach_provider_session_id=RECEIPT_SESSION,
    )
    row = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert row.provider_session_id == RECEIPT_SESSION
    assert row.pid is None  # a provider session, never an invented local pid
    assert row.fence_generation == attempt.fence_generation + 1
    assert row.lease_owner == "restart-supervisor"
    assert adopted.lease_token != lease.lease_token  # prior owner is stale

    # the identity became durable in the SAME transaction, as an event
    events = runtime.store.list_events(attempt_id=lease.attempt.attempt_id)
    recorded = [e for e in events
                if e.event_type == "ATTEMPT_PROCESS_RECORDED"]
    assert len(recorded) == 1
    payload = dict(recorded[0].payload)
    assert payload["process_kind"] == "provider"
    assert payload["provider_session_id"] == RECEIPT_SESSION
    assert payload["reattached_from_receipt"] is True

    # the old fence is stale for every later adopter
    with pytest.raises(StateConflict, match="stale adoption fence"):
        runtime.attempts.adopt_attempt(
            lease.attempt.attempt_id,
            expected_fence_generation=attempt.fence_generation,
            lease_owner="other-supervisor",
            reattach_provider_session_id=RECEIPT_SESSION,
        )


def test_adopt_with_receipt_session_never_rewrites_an_existing_identity(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease, _ = _claimed_identity_less(runtime, job_id)
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="mcp:launch:original",
    )
    with pytest.raises(StateConflict, match="already has a durable"):
        runtime.attempts.adopt_attempt(
            lease.attempt.attempt_id,
            expected_fence_generation=lease.attempt.fence_generation,
            lease_owner="restart-supervisor",
            reattach_provider_session_id=RECEIPT_SESSION,
        )


# ---------------------------------------------------------------------------
# reconcile_restart consults the injected receipt reader
# ---------------------------------------------------------------------------

def _unbound_receipt_adapter(runtime):
    adapter = FakeAdapter(FakeInspector())
    adapter.presence = lambda _attempt: owner.ProcessPresence.UNKNOWN
    adapter.absence_verified = lambda _attempt: False
    adapter.terminate = lambda _attempt: pytest.fail(
        "an identity-less claim must not be signalled")
    return adapter


def test_unbound_claim_with_durable_receipt_adopts_and_never_requeues(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease, attempt = _claimed_identity_less(runtime, job_id)
    adapter = _unbound_receipt_adapter(runtime)
    supervisor = _supervisor(
        runtime, tmp_path, adapter,
        provider_receipt_reader=lambda _attempt_id: {
            "provider_session_id": RECEIPT_SESSION,
        })
    outcomes = supervisor.reconcile_restart(requeue_lost=True)

    assert [item.status for item in outcomes] == [
        owner.ReconcileStatus.LIVE_QUARANTINED]
    row = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    # adopted under the receipt's identity, fence rotated to this supervisor
    assert row.provider_session_id == RECEIPT_SESSION
    assert row.fence_generation == attempt.fence_generation + 1
    assert row.lease_owner == supervisor.instance_id
    assert row.status is owner.AttemptStatus.CLAIMED
    # the one-initiator invariant: no requeue, no second attempt, job intact
    assert runtime.jobs.get_job(job_id).status is owner.JobStatus.RUNNING
    attempts = [a for a in runtime.attempts.list_attempts()
                if a.job_id == job_id]
    assert len(attempts) == 1


def test_unbound_claim_without_reader_keeps_the_existing_quarantine(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease, _ = _claimed_identity_less(runtime, job_id)
    adapter = _unbound_receipt_adapter(runtime)
    supervisor = _supervisor(runtime, tmp_path, adapter)  # no reader injected
    outcomes = supervisor.reconcile_restart(requeue_lost=True)

    # pre-existing behavior unchanged: ambiguous, no fence rotation, no
    # identity invented — the reader is the only new discriminator
    assert [item.status for item in outcomes] == [
        owner.ReconcileStatus.IDENTITY_AMBIGUOUS]
    row = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert row.provider_session_id is None
    assert row.status is owner.AttemptStatus.CLAIMED
    assert row.lease_owner == "dead-original-owner"


def test_reader_returning_garbage_is_ignored_not_trusted(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease, _ = _claimed_identity_less(runtime, job_id)
    adapter = _unbound_receipt_adapter(runtime)
    for bad in (None, {}, {"provider_session_id": "  "},
                {"provider_session_id": 123}):
        supervisor = _supervisor(
            runtime, tmp_path, adapter, provider_receipt_reader=lambda _a: bad)
        outcomes = supervisor.reconcile_restart(requeue_lost=True)
        assert [item.status for item in outcomes] == [
            owner.ReconcileStatus.IDENTITY_AMBIGUOUS], bad
        row = runtime.attempts.get_attempt(lease.attempt.attempt_id)
        assert row.provider_session_id is None, bad
        assert row.lease_owner == "dead-original-owner", bad


def test_constructor_rejects_a_non_callable_reader(tmp_path):
    runtime, _, _ = _runtime_and_job(tmp_path)
    from control_plane.executive_supervisor import SupervisorError
    with pytest.raises(SupervisorError, match="receipt reader"):
        _supervisor(runtime, tmp_path, FakeAdapter(FakeInspector()),
                    provider_receipt_reader="not-callable")
