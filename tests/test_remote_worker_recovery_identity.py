"""Actual composed recovery, with synthetic Runtime and broker observations only."""
from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_worker_broker as broker
from control_plane.executive_runtime import AttemptStatus, Runtime, StateConflict
from control_plane.executive_service import ExecutiveControlService
from control_plane.executive_supervisor import ProcessPresence, ReconcileStatus, SupervisorError
from control_plane.remote_attempt_transport import (
    AttemptBoundRemoteWorkerAdapter, RemoteAttemptTransportError, REMOTE_RECOVERY_OPERATIONS,
)
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from scripts import executive_os_phase1c as cli
from test_ceo_submit_armed_composition import _raw, _write
from test_executive_service import _proof_absence
from test_remote_attempt_transport import (
    HOST_A, WORKER, QUOTA, _claimed_runtime, _host_binding, _join,
    _lost_requeued_runtime, _pin_remote_claim,
)


def _broker_absence(attempt, *, adapter_id="codex-cli", uid=451):
    sweep = _proof_absence(attempt)
    startup = sweep.pop("preceding_broker_startup_sweep")
    sweep["worker_uid"] = startup["worker_uid"] = uid
    return dict(
        adapter_id=adapter_id, broker_pid=sweep["broker_pid"], worker_uid=uid,
        active_run_id=None, active_operator_attempt_id=None,
        active_operator_generation_id=None, starting=False, validation_busy=False,
        status_sweep_busy=False, quarantined_reason=None,
        status_sweep=sweep, startup_sweep=startup,
    )


def _fake_status(monkeypatch, attempt, *, adapter_id="codex-cli", uid=451, fault=None):
    calls = []

    def request_sync(self, operation, payload):
        assert self.allowed_operations == frozenset({"status"})
        assert operation == "status"
        calls.append(dict(payload))
        if "run_id" in payload:
            raise broker.RemoteBrokerError("BrokerRunNotFound", "fixture missing run")
        result = _broker_absence(attempt, adapter_id=adapter_id, uid=uid)
        if fault is not None:
            fault(result)
        return result

    monkeypatch.setattr(RemoteWorkerBrokerClient, "request_sync", request_sync)
    return calls


def _fake_unbound_status(monkeypatch, attempt, *, adapter_id="codex-cli", fault=None):
    def request_sync(self, operation, payload):
        assert self.allowed_operations == REMOTE_RECOVERY_OPERATIONS
        if "run_id" in payload:
            assert payload["run_id"] == attempt.attempt_id
            if operation == "cancel":
                return {"uid_sweep": _broker_absence(attempt)["status_sweep"]}
            assert operation == "status"
            # The broker retained the run, but its start result never reached
            # control, so no persisted ProcessRef can match the exact Attempt.
            return {"run": {"run_id": attempt.attempt_id}}
        assert operation == "status" and payload == {"fresh_uid_sweep": True}
        status = _broker_absence(attempt, adapter_id=adapter_id)
        if fault is not None:
            fault(status)
        return status

    monkeypatch.setattr(RemoteWorkerBrokerClient, "request_sync", request_sync)


def _composed_claim(tmp_path, monkeypatch, *, adapter_id="codex-cli", source_fault=None):
    raw = cli.load_control_config(_write(tmp_path, _raw(
        tmp_path, worker_id=WORKER, quota_class=QUOTA,
    )))
    captures = {}
    binding = _host_binding(tmp_path)
    binding = dataclasses.replace(binding, adapter_id=adapter_id)

    def source(host, worker):
        assert (host, worker) == (HOST_A, WORKER)
        return source_fault(binding) if source_fault else binding

    def capture(config, **kwargs):
        captures.update(kwargs)
        return SimpleNamespace(config=config)

    monkeypatch.setattr(cli, "ExecutiveControlService", capture)
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda name: object())
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **k: object())
    composed = cli._service_from_config(raw, remote_worker_binding_source=source)
    provider = "anthropic" if adapter_id == "claude-code" else "codex"
    config = dataclasses.replace(composed.config, provider=provider)
    service = ExecutiveControlService(
        config,
        proof_capacity_recovery_observer=captures["proof_capacity_recovery_observer"],
        proof_capacity_recovery_worker_uid=captures["proof_capacity_recovery_worker_uid"],
    )
    runtime = Runtime.at(config.runtime_root)
    service.runtime = runtime
    supervisor = captures["supervisor_factory"](runtime)
    assert supervisor.process_controller is supervisor.adapter.process_controller
    runtime.workers.register_worker(
        WORKER, provider=provider, account_label="fixture", worker_type=adapter_id,
        capabilities=["code", "research", "tests"],
        quota_classes={QUOTA: {
            "provider": provider, "model": config.model,
            "effort": config.effort, "cost_class": config.cost_class,
            "capabilities": ["code", "research", "tests"],
            "metadata": {"capacity_join": _join()},
        }},
    )
    nonce = "a" * 32
    job = runtime.jobs.create_job(**service._proof_contract(
        workspace=config.proof_workspace_root / ("proof-" + nonce),
        branch=config.proof_branch + "-" + nonce,
    ))
    assert service._is_fixed_proof_job(job)
    lease = runtime.attempts.claim_job(
        job.job_id, worker_id=WORKER, quota_class=QUOTA, lease_owner="fixture",
    )
    assert lease is not None
    pinned = _pin_remote_claim(runtime, lease, binding)
    lease = dataclasses.replace(lease, attempt=pinned)
    return service, supervisor, job, lease, binding


def _composed_lost(tmp_path, monkeypatch, **kwargs):
    service, supervisor, job, lease, binding = _composed_claim(
        tmp_path, monkeypatch, **kwargs,
    )
    runtime = service.runtime
    runtime.attempts.record_process(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="fixture-missing",
    )
    runtime.attempts.mark_running(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    runtime.attempts.mark_lost(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        reason="process identity absent during supervisor restart",
        verified_process_absent=True,
    )
    runtime.jobs.requeue_job(job.job_id)
    lost = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    return service, supervisor, job, lost, binding


@pytest.mark.parametrize("adapter_id", ["codex-cli", "claude-code"])
def test_composed_unbound_restart_uses_endpoint_uid_and_reaches_expiry(
    tmp_path, monkeypatch, adapter_id,
):
    service, supervisor, job, lease, binding = _composed_claim(
        tmp_path, monkeypatch, adapter_id=adapter_id,
    )
    attempt = lease.attempt
    assert attempt.status is AttemptStatus.CLAIMED
    assert attempt.pid is None and attempt.launch_metadata["remote_launch_identity"]
    assert binding.worker_uid != supervisor.worker_uid
    Path(job.worktree).mkdir(parents=True, mode=0o700)
    supervisor._run_dir(attempt.attempt_id).mkdir(parents=True, mode=0o700)
    _fake_unbound_status(monkeypatch, attempt, adapter_id=adapter_id)

    outcomes = supervisor.reconcile_restart()
    assert outcomes[0].status is ReconcileStatus.AWAITING_LEASE_EXPIRY, outcomes[0]
    receipt = json.loads(Path(outcomes[0].uid_sweep_receipt_path).read_text())
    assert receipt["uid_sweep"]["worker_uid"] == 451
    assert service.runtime.attempts.get_attempt(attempt.attempt_id) == attempt
    receipt_path = Path(outcomes[0].uid_sweep_receipt_path)
    before = receipt_path.read_bytes()

    expires = int(datetime.fromisoformat(attempt.lease_expires_at).timestamp() * 1000)
    service.runtime.store.clock = lambda: expires + 2000
    outcomes = supervisor.reconcile_restart()
    assert outcomes[0].status is ReconcileStatus.REQUEUED, outcomes[0]
    assert service.runtime.attempts.get_attempt(attempt.attempt_id).status is AttemptStatus.LOST
    assert len(service.runtime.attempts.list_attempts(job.job_id)) == 1
    assert service.runtime.jobs.get_job(job.job_id).status.value == "QUEUED"
    assert receipt_path.read_bytes() == before


@pytest.mark.parametrize("value", [None, 0, -1, True, "451"])
def test_unbound_restart_invalid_endpoint_uid_refuses_before_cleanup(tmp_path, monkeypatch, value):
    service, supervisor, _, lease, _ = _composed_claim(tmp_path, monkeypatch)
    controller = supervisor.process_controller
    monkeypatch.setattr(controller, "expected_worker_uid", lambda attempt: value)
    monkeypatch.setattr(controller, "cleanup_unbound_run",
                        lambda run_id: pytest.fail("invalid UID reached cleanup"))
    with pytest.raises(SupervisorError, match="positive worker UID"):
        supervisor._cleanup_unbound_claim(lease.attempt)
    assert service.runtime.attempts.get_attempt(lease.attempt.attempt_id) == lease.attempt


def test_unbound_restart_endpoint_uid_is_rechecked_before_seal(tmp_path, monkeypatch):
    service, supervisor, _, lease, _ = _composed_claim(tmp_path, monkeypatch)
    attempt = lease.attempt
    current_uid = [451]
    monkeypatch.setattr(supervisor.process_controller, "expected_worker_uid",
                        lambda attempt: current_uid[0])
    _fake_unbound_status(monkeypatch, attempt, fault=lambda status: current_uid.__setitem__(0, 452))

    outcomes = supervisor.reconcile_restart()
    assert outcomes[0].status is ReconcileStatus.IDENTITY_AMBIGUOUS
    assert "worker UID changed" in outcomes[0].error
    assert outcomes[0].uid_sweep_receipt_path is None
    assert outcomes[0].assignment_seal_receipt_path is None
    assert service.runtime.attempts.get_attempt(attempt.attempt_id) == attempt


@pytest.mark.parametrize("fault", ["uid", "stale", "nonpassing"])
def test_unbound_restart_foreign_or_invalid_sweep_keeps_claim_fenced(tmp_path, monkeypatch, fault):
    service, supervisor, _, lease, _ = _composed_claim(tmp_path, monkeypatch)
    attempt = lease.attempt

    def corrupt(status):
        if fault == "uid":
            status["status_sweep"]["worker_uid"] = supervisor.worker_uid
        elif fault == "stale":
            status["status_sweep"]["observed_at"] = "2000-01-01T00:00:00+00:00"
        else:
            status["status_sweep"]["passed"] = False

    _fake_unbound_status(monkeypatch, attempt, fault=corrupt)
    outcomes = supervisor.reconcile_restart()
    assert outcomes[0].status is ReconcileStatus.IDENTITY_AMBIGUOUS
    assert outcomes[0].assignment_seal_receipt_path is None
    assert service.runtime.attempts.get_attempt(attempt.attempt_id) == attempt


def test_unbound_restart_canonical_endpoint_drift_keeps_claim_fenced(tmp_path, monkeypatch):
    current = [None]
    service, supervisor, _, lease, binding = _composed_claim(
        tmp_path, monkeypatch, source_fault=lambda original: current[0] or original,
    )
    attempt = lease.attempt

    def migrate(status):
        current[0] = dataclasses.replace(binding, worker_uid=452)

    _fake_unbound_status(monkeypatch, attempt, fault=migrate)
    outcomes = supervisor.reconcile_restart()
    assert outcomes[0].status is ReconcileStatus.IDENTITY_AMBIGUOUS
    assert outcomes[0].assignment_seal_receipt_path is None
    assert service.runtime.attempts.get_attempt(attempt.attempt_id) == attempt


@pytest.mark.parametrize("adapter_id", ["codex-cli", "claude-code"])
def test_composed_recovery_validates_resolved_uid_and_replays_once(tmp_path, monkeypatch, adapter_id):
    service, supervisor, job, lost, binding = _composed_lost(
        tmp_path, monkeypatch, adapter_id=adapter_id,
    )
    assert binding.worker_uid != int(_raw(tmp_path)["worker_uid"])
    calls = _fake_status(monkeypatch, lost, adapter_id=adapter_id)
    result = asyncio.run(service._recover_proof_capacity(job.job_id, lost.attempt_id))
    assert result["status"] == "AVAILABLE"
    assert result["uid_sweep"]["worker_uid"] == binding.worker_uid
    assert service.runtime.attempts.get_attempt(lost.attempt_id) == lost
    assert service.runtime.jobs.get_job(job.job_id).status.value == "QUEUED"
    assert calls == [{"run_id": lost.attempt_id}, {"fresh_uid_sweep": True}]
    replay = asyncio.run(service._recover_proof_capacity(job.job_id, lost.attempt_id))
    assert replay == result
    assert len(calls) == 2
    events = service.runtime.events.list_events(job_id=job.job_id)
    assert sum(e.event_type == "PROOF_CAPACITY_RECOVERED" for e in events) == 1


@pytest.mark.parametrize("fault", ["adapter", "uid", "startup_uid", "startup_pid", "startup_time", "busy"])
def test_claude_restart_absence_refuses_foreign_or_stale_status(tmp_path, monkeypatch, fault):
    service, supervisor, job, lost, _ = _composed_lost(
        tmp_path, monkeypatch, adapter_id="claude-code",
    )

    def corrupt(status):
        if fault == "adapter": status["adapter_id"] = "codex-cli"
        elif fault == "uid": status["worker_uid"] = 452
        elif fault == "startup_uid": status["startup_sweep"]["worker_uid"] = 452
        elif fault == "startup_pid": status["startup_sweep"]["broker_pid"] += 1
        elif fault == "startup_time": status["startup_sweep"]["observed_at"] = lost.started_at
        elif fault == "busy": status["starting"] = True

    _fake_status(monkeypatch, lost, adapter_id="claude-code", fault=corrupt)
    assert supervisor.process_controller.presence(lost) is ProcessPresence.UNKNOWN
    before = service.runtime.workers.get_quota_class(WORKER, QUOTA)
    with pytest.raises(cli.ServiceError, match="fresh broker absence"):
        asyncio.run(service._recover_proof_capacity(job.job_id, lost.attempt_id))
    assert service.runtime.workers.get_quota_class(WORKER, QUOTA) == before


@pytest.mark.parametrize("field,value", [("worker_uid", 452), ("adapter_id", "claude-code")])
def test_cached_controller_refuses_endpoint_identity_migration_before_io(tmp_path, monkeypatch, field, value):
    runtime, _, lease = _claimed_runtime(tmp_path)
    binding = _host_binding(tmp_path)
    current = [binding]
    _pin_remote_claim(runtime, lease, binding)
    adapter = AttemptBoundRemoteWorkerAdapter(runtime, lambda h, w: current[0])
    original = adapter._controller_for_attempt(lease.attempt)
    current[0] = dataclasses.replace(binding, **{field: value})
    monkeypatch.setattr(RemoteWorkerBrokerClient, "request_sync", lambda *a, **k: pytest.fail("identity drift reached I/O"))
    with pytest.raises((broker.BrokerStateError, RemoteAttemptTransportError)):
        adapter._controller_for_attempt(lease.attempt)
    assert adapter._controllers[lease.attempt.attempt_id] is original


def test_cached_active_controller_never_retains_cancel_authority_after_lost(tmp_path, monkeypatch):
    runtime, job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
    _pin_remote_claim(runtime, lease, _host_binding(tmp_path))
    adapter = AttemptBoundRemoteWorkerAdapter(runtime, lambda h, w: _host_binding(tmp_path))
    active = adapter._controller_for_attempt(lease.attempt)
    assert "cancel" in active.client.allowed_operations
    runtime.attempts.record_process(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="fixture-missing",
    )
    runtime.attempts.mark_lost(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        reason="process identity absent during supervisor restart", verified_process_absent=True,
    )
    runtime.jobs.requeue_job(job.job_id)
    lost = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    narrowed = adapter._controller_for_attempt(lost)
    assert narrowed is not active
    assert narrowed.client.allowed_operations == frozenset({"status"})
    assert narrowed.client.identity == active.client.identity
    assert narrowed.client.binding == active.client.binding
    assert narrowed.expected_worker_uid == active.expected_worker_uid
    assert narrowed.expected_adapter_id == active.expected_adapter_id
    with pytest.raises(broker.BrokerStateError, match="no restart-cancellation UID sweep"):
        narrowed.uid_sweep_receipt(lost)
    _fake_status(monkeypatch, lost)
    assert adapter.process_controller.presence(lost) is ProcessPresence.MISSING


def test_endpoint_uid_drift_during_observation_cannot_requalify(tmp_path, monkeypatch):
    current = [None]
    service, supervisor, job, lost, binding = _composed_lost(
        tmp_path, monkeypatch, source_fault=lambda original: current[0] or original,
    )

    def migrate(status):
        current[0] = dataclasses.replace(binding, worker_uid=452)

    _fake_status(monkeypatch, lost, fault=migrate)
    before = service.runtime.workers.get_quota_class(WORKER, QUOTA)
    with pytest.raises((broker.BrokerStateError, StateConflict, RemoteAttemptTransportError)):
        asyncio.run(service._recover_proof_capacity(job.job_id, lost.attempt_id))
    assert service.runtime.workers.get_quota_class(WORKER, QUOTA) == before


@pytest.mark.parametrize("value", [None, 0, -1, True, "451"])
def test_dynamic_uid_refuses_invalid_identity_before_observer(tmp_path, monkeypatch, value):
    service, _, job, lost, _ = _composed_lost(tmp_path, monkeypatch)
    service._proof_capacity_recovery_worker_uid = lambda attempt: value
    service._proof_capacity_recovery_observer = lambda attempt: pytest.fail("invalid UID reached observer")
    with pytest.raises(StateConflict, match="worker UID"):
        asyncio.run(service._recover_proof_capacity(job.job_id, lost.attempt_id))


def test_dynamic_uid_is_reobserved_before_capacity_write(tmp_path, monkeypatch):
    service, _, job, lost, _ = _composed_lost(tmp_path, monkeypatch)
    current_uid = [451]
    service._proof_capacity_recovery_worker_uid = lambda attempt: current_uid[0]

    def observe(attempt):
        receipt = _proof_absence(attempt)
        current_uid[0] = 452
        return receipt

    service._proof_capacity_recovery_observer = observe
    before = service.runtime.workers.get_quota_class(WORKER, QUOTA)
    with pytest.raises(StateConflict, match="worker UID changed"):
        asyncio.run(service._recover_proof_capacity(job.job_id, lost.attempt_id))
    assert service.runtime.workers.get_quota_class(WORKER, QUOTA) == before


def test_claude_controller_requires_matching_adapter_for_restart(tmp_path, monkeypatch):
    service, supervisor, _, lost, binding = _composed_lost(
        tmp_path, monkeypatch, adapter_id="claude-code",
    )
    _fake_status(monkeypatch, lost, adapter_id="claude-code")
    assert supervisor.process_controller.presence(lost) is ProcessPresence.MISSING
    controller = supervisor.adapter._controller_for_attempt(lost)
    assert controller.expected_adapter_id == binding.adapter_id
