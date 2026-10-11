"""Parity of token-free authority admission with canonical lease currentness."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.executive_runtime import AttemptStatus, RuntimeProofError
from test_executive_privileged_controller import setup

ACTIVE = {AttemptStatus.CLAIMED, AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED}


def snapshot(runtime, req, connection):
    return runtime.attempts.current_authority_snapshot(connection, **req,
        timestamp=runtime.store.now_ms(), statuses=ACTIVE)


def test_current_snapshot_has_exact_current_job_attempt_without_token(setup):
    runtime, req, _, _, _ = setup
    with runtime.store.transaction() as connection:
        value = snapshot(runtime, req, connection)
    assert value.job.job_id == req["job_id"]
    assert value.attempt.attempt_id == req["attempt_id"]
    assert value.attempt.fence_generation == req["fence_generation"]
    assert "lease_token" not in str(dataclasses.asdict(value))
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.job = None


@pytest.mark.parametrize("mutation", ["stale_fence", "quota_fence", "expired", "job_link", "quota_link", "job_status", "attempt_status"])
def test_token_and_token_free_paths_share_currentness_refusals(setup, mutation):
    runtime, req, _, _, clock = setup
    with runtime.store.transaction() as connection:
        token = connection.execute("SELECT lease_token FROM attempts WHERE attempt_id=?", (req["attempt_id"],)).fetchone()[0]
        if mutation == "stale_fence": req["fence_generation"] += 1
        elif mutation == "quota_fence": connection.execute("UPDATE worker_quota_classes SET fence_counter=fence_counter+1")
        elif mutation == "expired": clock[0] += 60_000
        elif mutation == "job_link": connection.execute("UPDATE jobs SET current_attempt_id='ATT-missing'")
        elif mutation == "quota_link": connection.execute("UPDATE worker_quota_classes SET held_attempt_id=NULL,status='AVAILABLE'")
        elif mutation == "job_status": connection.execute("UPDATE jobs SET status='CHECKPOINTED'")
        elif mutation == "attempt_status": connection.execute("UPDATE attempts SET status='CANCEL_REQUESTED'")
        with pytest.raises(RuntimeProofError) as token_free:
            snapshot(runtime, req, connection)
        with pytest.raises(type(token_free.value)) as leased:
            runtime.attempts._leased_row(connection, attempt_id=req["attempt_id"],
                fence_generation=req["fence_generation"], lease_token=token,
                timestamp=runtime.store.now_ms(), statuses=ACTIVE)
        assert str(leased.value) == str(token_free.value)
        connection.rollback()  # Intentionally inconsistent links never leave this transaction.


@pytest.mark.parametrize("mode", [None, "SEALED_WORKER"])
def test_mode_gate_is_only_on_the_token_free_p2_path(setup, mode):
    runtime, req, _, _, _ = setup
    with runtime.store.transaction() as connection:
        connection.execute("UPDATE attempts SET execution_mode=?", (mode,))
        token = connection.execute("SELECT lease_token FROM attempts").fetchone()[0]
        leased = runtime.attempts._leased_row(connection, attempt_id=req["attempt_id"],
            fence_generation=req["fence_generation"], lease_token=token,
            timestamp=runtime.store.now_ms(), statuses=ACTIVE)
        assert leased["attempt_id"] == req["attempt_id"]
        if mode == "OPERATOR_HARNESS":
            with pytest.raises(RuntimeProofError): snapshot(runtime, req, connection)
        else:
            assert snapshot(runtime, req, connection).attempt.attempt_id == req["attempt_id"]


@pytest.mark.parametrize("mutation", ["wrong_job", "offline", "missing_token"])
def test_current_authority_refuses_missing_assignment_or_identity(setup, mutation):
    runtime, req, _, _, _ = setup
    with runtime.store.transaction() as connection:
        if mutation == "wrong_job": req["job_id"] = "JOB-002"
        elif mutation == "offline": connection.execute("UPDATE workers SET identity_status='OFFLINE'")
        elif mutation == "missing_token": connection.execute("UPDATE attempts SET lease_token=''")
        with pytest.raises(RuntimeProofError): snapshot(runtime, req, connection)


def test_real_operator_harness_keeps_lease_path_but_refuses_token_free_admission(tmp_path):
    from test_ohf_p1b_runtime import _lease, _profile
    runtime, lease = _lease(tmp_path)
    runtime.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, requested=_profile(lease),
    )
    req = {"job_id": lease.attempt.job_id, "attempt_id": lease.attempt.attempt_id,
           "fence_generation": lease.attempt.fence_generation}
    with runtime.store.transaction() as connection:
        row = runtime.attempts._leased_row(connection, attempt_id=req["attempt_id"],
            fence_generation=req["fence_generation"], lease_token=lease.lease_token,
            timestamp=runtime.store.now_ms(), statuses=ACTIVE)
        assert row["execution_mode"] == "OPERATOR_HARNESS"
        with pytest.raises(RuntimeProofError, match="SEALED_WORKER"):
            snapshot(runtime, req, connection)
