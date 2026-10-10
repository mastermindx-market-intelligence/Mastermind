"""Actual composed recovery, with synthetic Runtime and broker observations only."""
from __future__ import annotations

import asyncio
import dataclasses
from types import SimpleNamespace

import pytest

from control_plane import executive_worker_broker as broker
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.executive_service import ExecutiveControlService
from control_plane.executive_supervisor import ProcessPresence
from control_plane.remote_attempt_transport import (
    AttemptBoundRemoteWorkerAdapter, RemoteAttemptTransportError,
)
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from scripts import executive_os_phase1c as cli
from test_ceo_submit_armed_composition import _raw, _write
from test_executive_service import _proof_absence
from test_remote_attempt_transport import (
    HOST_A, WORKER, QUOTA, _claimed_runtime, _host_binding, _join,
    _lost_requeued_runtime,
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


def _composed_lost(tmp_path, monkeypatch, *, adapter_id="codex-cli", source_fault=None):
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
    adapter = AttemptBoundRemoteWorkerAdapter(runtime, lambda h, w: current[0])
    original = adapter._controller_for_attempt(lease.attempt)
    current[0] = dataclasses.replace(binding, **{field: value})
    monkeypatch.setattr(RemoteWorkerBrokerClient, "request_sync", lambda *a, **k: pytest.fail("identity drift reached I/O"))
    with pytest.raises((broker.BrokerStateError, RemoteAttemptTransportError)):
        adapter._controller_for_attempt(lease.attempt)
    assert adapter._controllers[lease.attempt.attempt_id] is original


def test_cached_active_controller_never_retains_cancel_authority_after_lost(tmp_path, monkeypatch):
    runtime, job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
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
    with pytest.raises((broker.BrokerStateError, StateConflict)):
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
