"""Trusted Control composition reaches the existing Attempt-bound transport."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from control_plane import executive_worker_broker as broker
from control_plane.executive_runtime import Runtime
from control_plane.remote_attempt_transport import (
    AttemptBoundRemoteWorkerAdapter,
    RemoteAttemptTransportError,
)
from scripts import executive_os_phase1c as cli
from test_ceo_submit_armed_composition import _raw, _write
from test_remote_attempt_transport import HOST_A, WORKER, _claimed_runtime, _spec


def _compose(tmp_path, monkeypatch, runtime, **kwargs):
    raw = cli.load_control_config(_write(tmp_path, _raw(tmp_path)))
    captured = {}
    client = object()
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **k: client)
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda name: object())

    def capture(config, **bindings):
        captured.update(bindings)
        return SimpleNamespace(config=config)

    monkeypatch.setattr(cli, "ExecutiveControlService", capture)
    service = cli._service_from_config(raw, **kwargs)
    return service, captured["supervisor_factory"](runtime), client


def _forbid_local_adapter(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("remote composition fell back to the local worker")

    monkeypatch.setattr(broker, "RemoteCodexWorkerAdapter", forbidden)


def test_omitted_remote_source_preserves_local_worker_and_controller(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path / "runtime")
    service, supervisor, client = _compose(tmp_path, monkeypatch, runtime)
    assert isinstance(supervisor.adapter, broker.RemoteCodexWorkerAdapter)
    assert isinstance(supervisor.process_controller, broker.RemoteWorkerProcessController)
    assert supervisor.adapter.client is client
    assert supervisor.process_controller.client is client
    assert service.config.ceo_submit_armed is False


def test_remote_composition_defers_source_and_uses_its_recovery_controller(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path / "runtime")
    calls = []

    def source(host, worker):
        calls.append((host, worker))
        raise AssertionError("composition must not resolve a carrier before claim")

    _forbid_local_adapter(monkeypatch)
    service, supervisor, _ = _compose(
        tmp_path, monkeypatch, runtime, remote_worker_binding_source=source
    )
    assert isinstance(supervisor.adapter, AttemptBoundRemoteWorkerAdapter)
    assert supervisor.adapter.runtime is runtime
    assert supervisor.adapter.binding_source is source
    assert supervisor.process_controller is supervisor.adapter.process_controller
    assert calls == []
    assert service.config.ceo_submit_armed is False


def test_invalid_source_is_refused_before_client_or_socket_construction(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid source reached socket construction")

    monkeypatch.setattr(broker, "WorkerBrokerClient", forbidden)
    monkeypatch.setattr(cli, "activate_launchd_socket", forbidden)
    with pytest.raises(cli.ServiceError, match="remote worker binding source must be callable"):
        cli._service_from_config({}, remote_worker_binding_source=object())


@pytest.mark.parametrize("raises", [False, True])
def test_claimed_missing_remote_source_never_falls_back(tmp_path, monkeypatch, raises):
    runtime, job, lease = _claimed_runtime(tmp_path)
    calls = []

    def source(host, worker):
        calls.append((host, worker))
        if raises:
            raise OSError("unavailable trusted source")
        return None

    _forbid_local_adapter(monkeypatch)
    _, supervisor, _ = _compose(
        tmp_path, monkeypatch, runtime, remote_worker_binding_source=source
    )
    assert calls == []
    spec = _spec(tmp_path, run_id=lease.attempt.attempt_id, job_id=job.job_id)
    with pytest.raises(RemoteAttemptTransportError) as error:
        asyncio.run(supervisor.adapter.start(spec))
    assert error.value.code == "HOST_BINDING_UNAVAILABLE"
    assert calls == [(HOST_A, WORKER)]
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id) == lease.attempt


def test_remote_validation_uses_current_attempt_and_rejects_foreign_run(tmp_path, monkeypatch):
    runtime, job, lease = _claimed_runtime(tmp_path)
    _, supervisor, _ = _compose(
        tmp_path, monkeypatch, runtime, remote_worker_binding_source=lambda h, w: None
    )
    spec = _spec(tmp_path, run_id=lease.attempt.attempt_id, job_id=job.job_id)
    assert supervisor.adapter.validation_commands_for_spec(spec) == ()
    with pytest.raises(cli.ServiceError, match="lost Job/Attempt identity"):
        supervisor.adapter.validation_commands_for_spec(
            SimpleNamespace(job_id=job.job_id, run_id="foreign-attempt")
        )
