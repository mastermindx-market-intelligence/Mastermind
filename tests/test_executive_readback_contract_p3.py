"""Shared producer/reader LOST reason and temporal plausibility contracts."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from control_plane.executive_runtime import StateConflict
from control_plane.executive_readback_contract import (
    MAX_EVENT_CLOCK_SKEW_MS,
    MAX_LEASE_LOOKAHEAD_MS,
    event_timestamp_within_skew,
    process_absence_error,
    valid_requeued_lost_error,
)
from integrations.mastermind_executive_app.gateway import WebCeoV2CeoIngressReadGateway
from tests.test_executive_job_terminal_result_read import _accepted, _produced_job
from tests.test_remote_attempt_transport import _claimed_runtime, _lost_requeued_runtime


def test_new_runtime_producer_serializes_typed_verified_absence(tmp_path):
    runtime, job, _ = _lost_requeued_runtime(tmp_path)
    document = _produced_job(runtime, job.job_id, tmp_path)
    assert document["data"]["latest_attempt"]["error"] == {
        "reason": "process identity absent during supervisor restart",
        "verified_process_absent": True,
        "reason_code": "supervisor_restart_absence",
    }
    assert _accepted(document)


def test_old_persisted_legacy_reason_survives_runtime_mcp_web_reader(tmp_path, monkeypatch):
    """Emulate the old writer BEFORE terminal commit; immutable rows stay sealed."""
    import control_plane.executive_runtime as runtime_owner

    legacy = {
        "reason": "historical process absence identified by operator",
        "verified_process_absent": True,
    }
    # The historical Runtime writer really commits a legacy v1 row. Never
    # UPDATE an existing terminal Attempt: the SQLite immutability trigger
    # correctly refuses such writes in production and in these tests.
    with monkeypatch.context() as patch:
        patch.setattr(runtime_owner, "process_absence_error", lambda _: dict(legacy))
        runtime, job, lost = _lost_requeued_runtime(tmp_path)

    stored = runtime.attempts.get_attempt(lost.attempt_id)
    assert stored is not None and stored.error == legacy
    document = _produced_job(runtime, job.job_id, tmp_path)
    assert document["data"]["latest_attempt"]["error"] == legacy
    assert _accepted(document)
    for row in (document["data"]["latest_attempt"], document["data"]["attempts"][-1]):
        row["error"]["reason"] += "\nforged"
    assert not _accepted(document)


@pytest.mark.parametrize("altered", [
    "other_verified_absence", "provider_session_absence", 2, None, "ROOT_OVERRIDE",
])
def test_forged_reason_code_cannot_impersonate_runtime_cause(tmp_path, altered):
    runtime, job, _ = _lost_requeued_runtime(tmp_path)
    document = _produced_job(runtime, job.job_id, tmp_path)
    for row in (document["data"]["latest_attempt"], document["data"]["attempts"][-1]):
        row["error"]["reason_code"] = altered
    assert not _accepted(document)


@pytest.mark.parametrize("bad_reason", [
    "", " leading", "trailing ", "line\nnewline", "x" * 1025,
])
def test_new_producer_rejects_unbounded_lost_diagnostics(bad_reason):
    with pytest.raises(ValueError, match="unbounded"):
        process_absence_error(bad_reason)


def test_new_unknown_diagnostic_is_typed_other_not_canonical():
    new = process_absence_error("bounded operator-specific diagnosis")
    assert new["reason_code"] == "other_verified_absence"
    assert valid_requeued_lost_error(new)
    new["reason_code"] = "supervisor_restart_absence"
    assert not valid_requeued_lost_error(new)


def test_preexisting_lease_expiry_and_operator_fence_envelopes_are_unchanged():
    for reason in ("lease_expired", "ohf_lease_expired_fenced"):
        assert valid_requeued_lost_error({"reason": reason, "expired_at_ms": 100})
        assert not valid_requeued_lost_error({
            "reason": reason, "expired_at_ms": 100, "reason_code": "other_verified_absence",
        })


def test_identical_producer_reader_future_event_boundaries():
    now = 1_800_000_000_000
    assert event_timestamp_within_skew(now + MAX_EVENT_CLOCK_SKEW_MS, now_ms=now)
    assert not event_timestamp_within_skew(
        now + MAX_EVENT_CLOCK_SKEW_MS + 1, now_ms=now
    )
    assert event_timestamp_within_skew(
        now + MAX_LEASE_LOOKAHEAD_MS, now_ms=now, lease_schedule=True
    )
    assert not event_timestamp_within_skew(
        now + MAX_LEASE_LOOKAHEAD_MS + 1, now_ms=now, lease_schedule=True
    )
    for invalid in (True, -1, "2027-01-01T00:00:00Z", None):
        assert not event_timestamp_within_skew(invalid, now_ms=now)


def _utc_from_now(delta):
    return (datetime.now(timezone.utc) + delta).isoformat(timespec="seconds")


def test_full_readback_rejects_future_job_event_without_rejecting_old_history(tmp_path):
    runtime, job, _ = _claimed_runtime(tmp_path, attempt_limit=2)
    document = _produced_job(runtime, job.job_id, tmp_path)
    assert _accepted(document)
    document["data"]["job"]["updated_at"] = _utc_from_now(timedelta(days=365))
    assert not _accepted(document)
    assert WebCeoV2CeoIngressReadGateway._valid_runtime_utc_timestamp(
        _utc_from_now(timedelta(minutes=1))
    )
    assert not WebCeoV2CeoIngressReadGateway._valid_runtime_utc_timestamp(
        _utc_from_now(timedelta(minutes=6))
    )
    assert WebCeoV2CeoIngressReadGateway._valid_runtime_utc_timestamp(
        "2020-01-01T00:00:00+00:00"
    )


def test_future_active_attempt_event_and_far_future_lease_are_distinct(tmp_path):
    runtime, job, _ = _claimed_runtime(tmp_path, attempt_limit=2)
    base = _produced_job(runtime, job.job_id, tmp_path)
    assert _accepted(base)
    forged = copy.deepcopy(base)
    for row in (forged["data"]["latest_attempt"], forged["data"]["attempts"][-1]):
        row["heartbeat_at"] = _utc_from_now(timedelta(hours=1))
    assert not _accepted(forged)
    scheduled = copy.deepcopy(base)
    for row in (scheduled["data"]["latest_attempt"], scheduled["data"]["attempts"][-1]):
        row["lease_expires_at"] = _utc_from_now(timedelta(days=12))
    assert _accepted(scheduled), "a lease is a schedule, not an observed event"
    for row in (scheduled["data"]["latest_attempt"], scheduled["data"]["attempts"][-1]):
        row["lease_expires_at"] = _utc_from_now(timedelta(days=32))
    assert not _accepted(scheduled)


def test_runtime_producer_refuses_leases_beyond_shared_readback_horizon(tmp_path):
    """A reader must not reject a lease the current producer can originate."""
    runtime, job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
    beyond = MAX_LEASE_LOOKAHEAD_MS // 1000 + 1
    with pytest.raises(StateConflict, match="lookahead ceiling"):
        runtime.attempts.claim_job(
            job.job_id, worker_id=lease.attempt.worker_id,
            quota_class=lease.attempt.quota_class,
            lease_owner="long-lease-refusal", lease_seconds=beyond,
        )
    with pytest.raises(StateConflict, match="lookahead ceiling"):
        runtime.attempts.adopt_attempt(
            lease.attempt.attempt_id,
            expected_fence_generation=lease.attempt.fence_generation,
            lease_owner="long-lease-refusal", lease_seconds=beyond,
        )
    with pytest.raises(StateConflict, match="lookahead ceiling"):
        runtime.attempts.heartbeat_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, extend_seconds=beyond,
        )
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id) == lease.attempt


@pytest.mark.parametrize("bad_reason", [
    None, 123, " trailing ", "supervisor\nforged", "x" * 1025,
])
def test_actual_runtime_mark_lost_rejects_invalid_reason_before_effect(
    tmp_path, bad_reason,
):
    runtime, _job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
    with pytest.raises(StateConflict, match="bounded verified-absence reason"):
        runtime.attempts.mark_lost(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            reason=bad_reason,
            verified_process_absent=True,
        )
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id) == lease.attempt
