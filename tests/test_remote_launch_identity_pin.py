"""Canonical pre-I/O pin; all Runtime rows and TLS files are synthetic."""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.executive_runtime import AttemptStatus, Runtime, StateConflict
from control_plane.executive_worker_broker import BrokerStateError
from control_plane.remote_attempt_transport import (
    AttemptBoundRemoteWorkerAdapter, RemoteAttemptTransportError,
)
from test_remote_attempt_transport import (
    _claimed_runtime, _host_binding, _spec, _process_ref, _FakeAttemptFleet,
)

PIN = "remote_launch_identity"


@pytest.fixture(autouse=True)
def _no_remote_io(monkeypatch):
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    async def forbidden(*args, **kwargs):
        pytest.fail("synthetic pin test attempted remote I/O")
    monkeypatch.setattr(RemoteWorkerBrokerClient, "_open_connection", forbidden)


def _ambiguous(tmp_path):
    runtime, job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
    current = [_host_binding(tmp_path)]
    calls = []

    class Fleet(_FakeAttemptFleet):
        async def start(self, spec):
            # Assertion is at the first simulated I/O, not after the return.
            durable = Runtime.at(tmp_path / "runtime").attempts.get_attempt(spec.run_id)
            assert durable.launch_metadata[PIN]["sha256"]
            calls.append(spec.run_id)
            return await super().start(spec)

    def factory(resolved):
        return Fleet(resolved.worker_id, process_ref=_process_ref(resolved.attempt_id),
                     fail_start=True)

    adapter = AttemptBoundRemoteWorkerAdapter(
        runtime, lambda h, w: current[0], fleet_factory=factory,
    )
    spec = _spec(tmp_path, run_id=lease.attempt.attempt_id, job_id=job.job_id)
    with pytest.raises(RuntimeError, match="simulated ambiguous start"):
        asyncio.run(adapter.start(spec, lease=lease))
    assert calls == [lease.attempt.attempt_id]
    assert adapter._controllers == {}
    return runtime, lease, current, adapter, spec


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("drift", [
    "endpoint", "worker_uid", "worker_gid", "worker_user", "adapter_id",
    "expected_server_fingerprint", "client_cert_path", "client_key_path", "ca_path",
    "certificate_contents", "ca_contents",
])
def test_first_controller_refuses_physical_identity_drift(tmp_path, restart, drift):
    runtime, lease, current, adapter, spec = _ambiguous(tmp_path)
    before = runtime.attempts.get_attempt(spec.run_id)
    original = current[0]
    if drift in {"worker_uid", "worker_gid", "worker_user", "adapter_id"}:
        value = {"worker_uid": 452, "worker_gid": 452,
                 "worker_user": "_other", "adapter_id": "claude-code"}[drift]
        current[0] = dataclasses.replace(original, **{drift: value})
    elif drift in {"certificate_contents", "ca_contents"}:
        path = original.transport.client_cert_path if drift == "certificate_contents" else original.transport.ca_path
        path.write_bytes(b"different synthetic public certificate")
    else:
        if drift == "endpoint":
            value = ("endpoint-b.example.test", 7443)
        elif drift == "expected_server_fingerprint":
            value = "e" * 64
        else:
            value = tmp_path / ("other-" + drift)
            value.write_bytes(b"fixture")
        current[0] = dataclasses.replace(
            original, transport=dataclasses.replace(original.transport, **{drift: value}),
        )
    if restart:
        runtime = Runtime.at(tmp_path / "runtime")
        adapter = AttemptBoundRemoteWorkerAdapter(runtime, lambda h, w: current[0])
    with pytest.raises((BrokerStateError, RemoteAttemptTransportError)):
        adapter._controller_for_attempt(before)
    assert adapter._controllers == {}
    assert runtime.attempts.get_attempt(spec.run_id) == before


def test_stable_pin_survives_runtime_restart_and_lease_adoption(tmp_path):
    runtime, lease, current, adapter, spec = _ambiguous(tmp_path)
    pin = runtime.attempts.get_attempt(spec.run_id).launch_metadata[PIN]
    runtime = Runtime.at(tmp_path / "runtime")
    fresh = AttemptBoundRemoteWorkerAdapter(runtime, lambda h, w: current[0])
    assert fresh._controller_for_attempt(runtime.attempts.get_attempt(spec.run_id)).expected_worker_uid == 451
    runtime.attempts.record_process(
        spec.run_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="fixture-session",
    )
    adopted = runtime.attempts.adopt_attempt(
        spec.run_id, expected_fence_generation=lease.attempt.fence_generation,
        lease_owner="fresh-controller",
    )
    fresh = AttemptBoundRemoteWorkerAdapter(runtime, lambda h, w: current[0])
    controller = fresh._controller_for_attempt(adopted.attempt)
    assert controller.client.binding.endpoint == current[0].transport.endpoint
    assert controller.expected_worker_uid == current[0].worker_uid
    assert runtime.attempts.get_attempt(spec.run_id).launch_metadata[PIN] == pin
    with pytest.raises((BrokerStateError, RemoteAttemptTransportError, StateConflict)):
        asyncio.run(fresh.start(spec, lease=adopted))


def test_missing_pin_refuses_before_building_recovery_controller(tmp_path):
    runtime, job, lease = _claimed_runtime(tmp_path)
    binding = _host_binding(tmp_path)
    adapter = AttemptBoundRemoteWorkerAdapter(runtime, lambda h, w: binding)
    with pytest.raises((BrokerStateError, RemoteAttemptTransportError)):
        adapter._controller_for_attempt(lease.attempt)
    assert adapter._controllers == {}
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id) == lease.attempt


@pytest.mark.parametrize("fault", ["missing_lease", "wrong_token", "stale_fence", "claim_moves", "binding_moves", "expired_lease", "client_identity_moves", "certificate_moves"])
def test_launch_refuses_before_io_when_lease_or_identity_moves(tmp_path, fault):
    runtime, job, lease = _claimed_runtime(tmp_path)
    current = [_host_binding(tmp_path)]
    fleets = []
    def factory(resolution):
        fleet = _FakeAttemptFleet(resolution.worker_id, process_ref=_process_ref(resolution.attempt_id))
        fleets.append(fleet)
        if fault == "claim_moves":
            runtime.attempts.heartbeat_attempt(
                lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
            )
        if fault == "binding_moves":
            current[0] = dataclasses.replace(current[0], worker_gid=452)
        if fault == "client_identity_moves":
            resolution.client.identity["worker_id"] = "foreign-worker"
        if fault == "certificate_moves":
            current[0].transport.client_cert_path.write_bytes(b"different certificate")
        if fault == "expired_lease":
            now = runtime.store.now_ms()
            runtime.store.now_ms = lambda: now + 86400000
        return fleet
    adapter = AttemptBoundRemoteWorkerAdapter(runtime, lambda h, w: current[0], fleet_factory=factory)
    supplied = lease
    if fault == "missing_lease": supplied = None
    if fault == "wrong_token": supplied = dataclasses.replace(lease, lease_token="wrong")
    if fault == "stale_fence":
        supplied = dataclasses.replace(lease, attempt=dataclasses.replace(lease.attempt, fence_generation=999))
    spec = _spec(tmp_path, run_id=lease.attempt.attempt_id, job_id=job.job_id)
    with pytest.raises((BrokerStateError, RemoteAttemptTransportError, StateConflict)):
        asyncio.run(adapter.start(spec, lease=supplied))
    assert all(fleet.start_calls == 0 for fleet in fleets)


def test_process_registration_keeps_pin_and_rejects_overwrite(tmp_path):
    runtime, lease, current, adapter, spec = _ambiguous(tmp_path)
    before = runtime.attempts.get_attempt(spec.run_id)
    with pytest.raises(StateConflict):
        runtime.attempts.record_process(
            spec.run_id, fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, provider_session_id="fixture-session",
            launch_metadata={PIN: {"sha256": "f" * 64}},
        )
    assert runtime.attempts.get_attempt(spec.run_id) == before
    recorded = runtime.attempts.record_process(
        spec.run_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="fixture-session",
        launch_metadata={"other": "preserved"},
    )
    assert recorded.launch_metadata == {PIN: before.launch_metadata[PIN], "other": "preserved"}


def test_lost_proof_recovery_preserves_pin_and_narrows_operations(tmp_path):
    runtime, lease, current, adapter, spec = _ambiguous(tmp_path)
    active = adapter._controller_for_attempt(runtime.attempts.get_attempt(spec.run_id))
    runtime.attempts.record_process(spec.run_id, fence_generation=lease.attempt.fence_generation,
                                  lease_token=lease.lease_token, provider_session_id="fixture")
    runtime.attempts.mark_running(spec.run_id, fence_generation=lease.attempt.fence_generation,
                                 lease_token=lease.lease_token)
    runtime.attempts.mark_lost(spec.run_id, fence_generation=lease.attempt.fence_generation,
                              lease_token=lease.lease_token, reason="process identity absent during supervisor restart",
                              verified_process_absent=True)
    runtime.jobs.requeue_job(spec.job_id)
    lost = runtime.attempts.get_attempt(spec.run_id)
    assert lost.status is AttemptStatus.LOST
    narrowed = adapter._controller_for_attempt(lost)
    assert narrowed is not active
    assert narrowed.client.allowed_operations == frozenset({"status"})
    # An old cached ref/spec cannot restore broader collect/cancel/sweep access.
    cached_ref = adapter._fleets[spec.run_id].process_ref
    with pytest.raises(RemoteAttemptTransportError):
        adapter._fleet_for_ref(cached_ref)
    with pytest.raises(RemoteAttemptTransportError):
        adapter._fleet_for_spec(spec)
    with pytest.raises(RemoteAttemptTransportError):
        adapter.uid_sweep_receipt(cached_ref)
    with pytest.raises(RemoteAttemptTransportError):
        asyncio.run(adapter.cleanup_unbound_run(spec.run_id))
    with pytest.raises(BrokerStateError, match="no restart-cancellation UID sweep"):
        narrowed.uid_sweep_receipt(lost)


@pytest.mark.parametrize("restart", [False, True])
def test_unbound_cleanup_refuses_drift_before_cached_or_fresh_io(tmp_path, restart):
    runtime, lease, current, adapter, spec = _ambiguous(tmp_path)
    cached = adapter._fleets[spec.run_id]
    current[0] = dataclasses.replace(current[0], worker_gid=452)
    if restart:
        adapter = AttemptBoundRemoteWorkerAdapter(
            Runtime.at(tmp_path / "runtime"), lambda h, w: current[0],
        )
    with pytest.raises(RemoteAttemptTransportError):
        asyncio.run(adapter.cleanup_unbound_run(spec.run_id))
    assert cached.cleanup_calls == []


def test_repin_cannot_replace_or_replay_ambiguous_start(tmp_path):
    runtime, lease, current, adapter, spec = _ambiguous(tmp_path)
    before = runtime.attempts.get_attempt(spec.run_id)
    for digest in (before.launch_metadata[PIN]["sha256"], "f" * 64):
        with pytest.raises(StateConflict, match="already attempted"):
            runtime.attempts.pin_remote_launch_identity(
                spec.run_id, fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token, expected_version=before.version,
                identity_digest=digest,
            )
    assert runtime.attempts.get_attempt(spec.run_id) == before
    assert len(runtime.attempts.list_attempts(job_id=spec.job_id)) == 1


@pytest.mark.parametrize("heartbeat_at", ["after_pin", "after_recovery_resolution"])
def test_same_lease_post_pin_heartbeat_does_not_refuse_launch(tmp_path, monkeypatch, heartbeat_at):
    """Deterministically interleave a real canonical heartbeat, without threads."""
    from control_plane.remote_attempt_transport import RemoteTransportPurpose
    runtime, job, lease = _claimed_runtime(tmp_path)
    binding = _host_binding(tmp_path)
    events = {}
    fleets = []
    now = runtime.store.now_ms()
    monkeypatch.setattr(runtime.store, "now_ms", lambda: now)

    def heartbeat():
        nonlocal now
        now += 1000
        events["heartbeat"] = runtime.attempts.heartbeat_attempt(
            lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, extend_seconds=7200,
        )

    pin = runtime.attempts.pin_remote_launch_identity
    def pin_then_heartbeat(*args, **kwargs):
        events["pin"] = pin(*args, **kwargs)
        if heartbeat_at == "after_pin":
            heartbeat()
        return events["pin"]
    monkeypatch.setattr(runtime.attempts, "pin_remote_launch_identity", pin_then_heartbeat)

    class Adapter(AttemptBoundRemoteWorkerAdapter):
        def _resolve_attempt(self, attempt, *, purpose):
            result = super()._resolve_attempt(attempt, purpose=purpose)
            if purpose is RemoteTransportPurpose.RECOVERY and heartbeat_at == "after_recovery_resolution":
                heartbeat()
            return result

    def factory(resolution):
        fleet = _FakeAttemptFleet(resolution.worker_id, process_ref=_process_ref(resolution.attempt_id))
        fleets.append(fleet)
        return fleet
    adapter = Adapter(runtime, lambda h, w: binding, fleet_factory=factory)
    spec = _spec(tmp_path, run_id=lease.attempt.attempt_id, job_id=job.job_id)
    result = asyncio.run(adapter.start(spec, lease=lease))
    assert result.run_id == spec.run_id and fleets[0].start_calls == 1
    pinned, current = events["pin"], events["heartbeat"]
    changed = {field.name for field in dataclasses.fields(pinned)
               if getattr(pinned, field.name) != getattr(current, field.name)}
    assert changed == {"version", "heartbeat_at", "lease_expires_at"}
    assert current.version == pinned.version + 1
    assert current.launch_metadata[PIN] == pinned.launch_metadata[PIN]
    assert runtime.attempts.get_attempt(spec.run_id) == current
    with pytest.raises(BrokerStateError, match="already has an attempt carrier"):
        asyncio.run(adapter.start(spec, lease=lease))
    assert fleets[0].start_calls == 1


@pytest.mark.parametrize("drift", [
    "token", "fence", "lease_owner", "lease_expired", "lease_shortened", "version_rewind",
    "job_assignment", "current_attempt", "quota_holder", "quota_fence", "quota_state",
    "worker_offline", "physical_pin", "status", "authority_policy", "process_identity",
    "requested_profile", "requested_profile_digest", "effective_grant", "placement_snapshot",
    "execution_principal_snapshot", "execution_mode",
])
def test_post_pin_heartbeat_does_not_hide_authority_drift(tmp_path, drift):
    """Synthetic DB changes after resolution must still fence the first I/O."""
    import hashlib
    import json
    from control_plane.executive_runtime import PersistenceError
    from control_plane.remote_attempt_transport import RemoteTransportPurpose
    runtime, job, lease = _claimed_runtime(tmp_path)
    binding = _host_binding(tmp_path)
    fleets = []

    class Adapter(AttemptBoundRemoteWorkerAdapter):
        def _resolve_attempt(self, attempt, *, purpose):
            result = super()._resolve_attempt(attempt, purpose=purpose)
            if purpose is not RemoteTransportPurpose.RECOVERY:
                return result
            runtime.attempts.heartbeat_attempt(
                attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token, extend_seconds=7200,
            )
            with runtime.store.transaction() as connection:
                # Test-owned temporary SQLite only. No production/raw mutation path.
                columns = {
                    "token": ("lease_token", "replacement-test-token"),
                    "fence": ("fence_generation", attempt.fence_generation + 1),
                    "lease_owner": ("lease_owner", "other-owner"),
                    "lease_expired": ("lease_expires_at_ms", runtime.store.now_ms() - 1),
                    "lease_shortened": ("lease_expires_at_ms", runtime.store.now_ms() + 1000),
                    "version_rewind": ("version", attempt.version - 1),
                    "physical_pin": ("launch_metadata_json", "{}"),
                    "status": ("status", "CANCEL_REQUESTED"),
                    "authority_policy": ("authority_policy_hash", "f" * 64),
                    "process_identity": ("provider_session_id", "other-session"),
                    "requested_profile": ("requested_execution_profile_json", '{"changed":true}'),
                    "requested_profile_digest": ("requested_execution_profile_digest", "f" * 64),
                    "execution_mode": ("execution_mode", "OPERATOR_HARNESS"),
                }
                if drift in columns:
                    column, value = columns[drift]
                    connection.execute(f"UPDATE attempts SET {column}=? WHERE attempt_id=?",
                                       (value, attempt.attempt_id))
                elif drift in {"effective_grant", "placement_snapshot", "execution_principal_snapshot"}:
                    value = json.dumps({"changed": True}, sort_keys=True, separators=(",", ":"))
                    digest = hashlib.sha256(value.encode()).hexdigest()
                    connection.execute(
                        f"UPDATE attempts SET {drift}_json=?,{drift}_digest=? WHERE attempt_id=?",
                        (value, digest, attempt.attempt_id),
                    )
                elif drift == "job_assignment":
                    connection.execute("UPDATE jobs SET assigned_worker_id=NULL WHERE job_id=?", (job.job_id,))
                elif drift == "current_attempt":
                    connection.execute("UPDATE jobs SET current_attempt_id=NULL WHERE job_id=?", (job.job_id,))
                elif drift == "worker_offline":
                    connection.execute("UPDATE workers SET identity_status='OFFLINE' WHERE worker_id=?", (attempt.worker_id,))
                else:
                    column, value = {
                        "quota_holder": ("held_attempt_id", None),
                        "quota_fence": ("fence_counter", attempt.fence_generation + 1),
                        "quota_state": ("status", "ERROR"),
                    }[drift]
                    connection.execute(f"UPDATE worker_quota_classes SET {column}=? WHERE worker_id=? AND quota_class=?",
                                       (value, attempt.worker_id, attempt.quota_class))
            return result

    def factory(resolution):
        fleet = _FakeAttemptFleet(resolution.worker_id, process_ref=_process_ref(resolution.attempt_id))
        fleets.append(fleet)
        return fleet
    adapter = Adapter(runtime, lambda h, w: binding, fleet_factory=factory)
    spec = _spec(tmp_path, run_id=lease.attempt.attempt_id, job_id=job.job_id)
    with pytest.raises((StateConflict, PersistenceError)):
        asyncio.run(adapter.start(spec, lease=lease))
    assert len(fleets) == 1 and fleets[0].start_calls == 0
    assert adapter._fleets == {}
