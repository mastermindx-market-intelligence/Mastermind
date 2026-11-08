"""Actual Control/client/TLS/gateway/Unix path; broker replies are fixtures."""
from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest

from control_plane import remote_attempt_transport as rt
from control_plane.executive_worker_broker import BROKER_RESPONSE_SCHEMA_VERSION
from control_plane.operator_harness_contract import ProfileValidation
from control_plane.operator_harness_wire import requested_execution_profile, to_wire
from control_plane.remote_worker_transport import BrokerTransportBinding, TransportError
from test_claimed_operator_control_composition import capture
from test_remote_operator_endpoint import case, binding
from tests.test_remote_worker_gateway import _gateway_fixture, _close_gateway, _cert_sha256, _openssl_available


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def test_control_builds_selected_endpoint_instead_of_primary(case, tmp_path, monkeypatch):
    runtime, job, lease, requested, flat, calls = case
    sources = []
    def source(h, w):
        sources.append((h, w)); return binding(case)
    _, supervisor, primary_client = capture(tmp_path, monkeypatch, runtime=runtime,
        remote_operator_binding_source=source)
    assert sources == []
    adapter = supervisor._adapter_for_attempt(lease, requested, lambda t: '', recovery=False)
    assert adapter.client is not primary_client
    assert adapter.client.identity['worker_id'] == lease.attempt.worker_id
    assert len(sources) == 1 and calls == []


def test_control_rejects_two_competing_constructors_before_io(monkeypatch):
    from scripts import executive_os_phase1c as cli
    with pytest.raises(cli.ServiceError, match='conflicts'):
        cli._service_from_config({}, remote_operator_binding_source=lambda h, w: None,
            claimed_operator_adapter_factory=lambda *a, **k: None)


@pytest.mark.anyio
@pytest.mark.skipif(not _openssl_available(), reason='openssl unavailable')
@pytest.mark.parametrize('case', ['codex', 'claude'], indirect=True)
async def test_control_selected_endpoint_crosses_real_mtls_and_fixed_unix(case, tmp_path, monkeypatch):
    runtime, job, lease, requested, flat, unused = case
    # Restore the unit fixture's network trap; this test uses ephemeral TLS keys.
    monkeypatch.undo()
    from tests import test_remote_worker_gateway as gateway_tests
    monkeypatch.setattr(gateway_tests, 'HOST_REF', flat.host_ref)
    fixture = await _gateway_fixture(tmp_path, allowed_operations={'ohf-validate'},
        allowed_worker_ids={lease.attempt.worker_id})
    forwarded = []
    async def broker_reply(reader, writer):
        try:
            message = json.loads(await reader.readline())
            forwarded.append(message)
            profile = requested_execution_profile(message['payload']['requested'])
            response = dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,
                request_id=message['request_id'], operation=message['operation'], ok=True,
                result={'validation': to_wire(ProfileValidation(profile, True, ()))})
            writer.write((json.dumps(response) + '\n').encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    fixture.unix_server.close(); await fixture.unix_server.wait_closed()
    fixture.broker_socket.unlink()
    fixture.unix_server = await asyncio.start_unix_server(broker_reply, path=str(fixture.broker_socket))
    transport = BrokerTransportBinding(endpoint=('localhost', fixture.endpoint[1]),
        ca_path=fixture.config.ca_path, client_cert_path=fixture.control_cert,
        client_key_path=fixture.control_key,
        expected_server_fingerprint=_cert_sha256(fixture.config.certificate_path))
    try:
        host = dataclasses.replace(binding(case), transport=transport)
        _, supervisor, primary = capture(tmp_path, monkeypatch, runtime=runtime,
            remote_operator_binding_source=lambda h, w: host)
        adapter = supervisor._adapter_for_attempt(lease, requested, lambda t: '', recovery=False)
        result = await asyncio.to_thread(adapter.validate_requested_profile, requested)
        assert result.accepted and result.requested == requested
        assert adapter.client is not primary
        assert len(forwarded) == 1 and forwarded[0]['operation'] == 'ohf-validate'
        assert forwarded[0]['payload']['requested']['worker_id'] == lease.attempt.worker_id
        wrong_pin = dataclasses.replace(host,
            transport=dataclasses.replace(transport, expected_server_fingerprint='f' * 64))
        refused = rt.build_claimed_remote_operator_factory(runtime, lambda h, w: wrong_pin)(
            lease.attempt, requested, lambda t: '', recovery=False)
        with pytest.raises(TransportError):
            await asyncio.to_thread(refused.validate_requested_profile, requested)
        assert len(forwarded) == 1
        wrong_worker = dataclasses.replace(requested, worker_id='foreign-worker')
        with pytest.raises(TransportError):
            await asyncio.to_thread(adapter.validate_requested_profile, wrong_worker)
        assert len(forwarded) == 1
    finally:
        await _close_gateway(fixture)



def _remote_only_case(tmp_path, provider="codex"):
    from control_plane.executive_runtime import Runtime
    from control_plane.operator_harness_contract import (
        CapabilityManifest, NativeHelperPolicy, RequestedExecutionProfile, WorkspaceIdentity,
    )
    from test_remote_attempt_transport import WORKER, QUOTA, _host_binding, _join
    runtime = Runtime.at(tmp_path / "remote-only-runtime")
    runtime.workers.register_worker(WORKER, provider=provider, account_label="fixture",
        worker_type="fixture", capabilities=["research"], quota_classes={QUOTA: {
            "capabilities": ["research"], "metadata": {"capacity_join": _join()}}})
    logical = str(tmp_path / "exists-only-on-selected-worker")
    job = runtime.jobs.create_job("remote workspace connection", requested_authorities=["READ"],
        worktree=logical, constraints={"base_sha": "b"*40, "eligible_quota_classes": [QUOTA]},
        attempt_limit=1)
    lease = runtime.attempts.claim_job(job.job_id, worker_id=WORKER, quota_class=QUOTA,
                                     lease_owner="remote-workspace-fixture")
    identity = WorkspaceIdentity(logical, "b"*40, 901, 902, 903, 904)
    requested = RequestedExecutionProfile(WORKER,
        "claude" if provider == "claude" else "openai-codex", "fixture-exact-model",
        "claude-agent-sdk" if provider == "claude" else "codex-app-server",
        "a"*64, "0.147.0", identity, "read-only", "never", "disabled",
        CapabilityManifest(), NativeHelperPolicy.DISABLED, lease.attempt.authority_policy_hash,
        expected_config_digest="e"*64)
    return runtime, job, lease, requested, _host_binding(tmp_path), []


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_actual_control_connects_remote_workspace_and_endpoint_from_same_owner(tmp_path, monkeypatch, provider):
    from pathlib import Path
    remote = _remote_only_case(tmp_path, provider)
    runtime, _, lease, requested, flat, calls = remote
    assert not Path(requested.workspace.workspace_path).exists()
    observations = []
    def source(host_ref, worker_id):
        observations.append((host_ref, worker_id))
        return binding(remote)
    _, supervisor, _ = capture(tmp_path, monkeypatch, runtime=runtime,
                               remote_operator_binding_source=source)
    current_job = runtime.jobs.get_job(lease.attempt.job_id)
    observed = supervisor._workspace_identity(current_job, lease.attempt)
    assert observed == requested.workspace
    adapter = supervisor._adapter_for_attempt(lease, requested, lambda turn: "fixture", recovery=False)
    assert adapter.client.identity["worker_id"] == lease.attempt.worker_id
    assert observations == [(flat.host_ref, lease.attempt.worker_id)] * 2
    assert calls == []


@pytest.mark.parametrize("field,value", [
    ("host_ref", "host-"+"d"*64), ("worker_id", "different-worker"),
    ("worker_source_config_digest", "e"*64),
])
def test_workspace_binding_source_refuses_wrong_selected_identity(tmp_path, field, value):
    remote = _remote_only_case(tmp_path)
    runtime, _, lease, requested, flat, calls = remote
    producer = rt.build_claimed_remote_workspace_identity_source(
        runtime, lambda *args: binding(remote, **{field: value}))
    with pytest.raises(rt.RemoteAttemptTransportError):
        producer(lease.attempt, runtime.jobs.get_job(lease.attempt.job_id))
    assert calls == []


def test_workspace_binding_source_cannot_repoint_or_borrow_a_claim(tmp_path):
    remote = _remote_only_case(tmp_path)
    runtime, _, lease, requested, flat, calls = remote
    observed = []
    def source(*args):
        observed.append(True)
        return binding(remote)
    producer = rt.build_claimed_remote_workspace_identity_source(runtime, source)
    with pytest.raises(rt.RemoteAttemptTransportError):
        producer(dataclasses.replace(lease.attempt, worker_id="foreign-worker"),
                 runtime.jobs.get_job(lease.attempt.job_id))
    assert observed == []


def test_workspace_claim_movement_during_binding_read_refuses(tmp_path):
    remote = _remote_only_case(tmp_path)
    runtime, _, lease, requested, flat, calls = remote
    def source(*args):
        runtime.jobs.cancel_job(lease.attempt.job_id)
        return binding(remote)
    producer = rt.build_claimed_remote_workspace_identity_source(runtime, source)
    with pytest.raises(rt.RemoteAttemptTransportError):
        producer(lease.attempt, runtime.jobs.get_job(lease.attempt.job_id))
    assert calls == []


def test_workspace_source_failure_never_falls_back_to_control_local_path(tmp_path, monkeypatch):
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisorError
    remote = _remote_only_case(tmp_path)
    runtime, _, lease, requested, flat, calls = remote
    def source(*args):
        raise OSError("private source failure")
    _, supervisor, _ = capture(tmp_path, monkeypatch, runtime=runtime,
                               remote_operator_binding_source=source)
    with pytest.raises(ExecutiveOperatorSupervisorError, match="source refused"):
        supervisor._workspace_identity(runtime.jobs.get_job(lease.attempt.job_id), lease.attempt)
    assert calls == []


def test_endpoint_rechecks_physical_identity_after_workspace_projection(tmp_path, monkeypatch):
    remote = _remote_only_case(tmp_path)
    runtime, _, lease, requested, flat, calls = remote
    source_calls = []
    def source(*args):
        source_calls.append(True)
        return binding(remote, workspace=(requested.workspace if len(source_calls) == 1
                       else dataclasses.replace(requested.workspace, inode=903)))
    _, supervisor, _ = capture(tmp_path, monkeypatch, runtime=runtime,
                               remote_operator_binding_source=source)
    assert supervisor._workspace_identity(runtime.jobs.get_job(lease.attempt.job_id), lease.attempt) == requested.workspace
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisorError
    with pytest.raises(ExecutiveOperatorSupervisorError, match="claimed operator construction refused"):
        supervisor._adapter_for_attempt(lease, requested, lambda turn: "fixture", recovery=False)
    assert len(source_calls) == 2 and calls == []


@pytest.mark.parametrize("field,value", [
    ("workspace_path", "/wrong/logical/worktree"), ("base_sha", "f"*40),
    ("device", True), ("device", -1), ("inode", 0), ("uid", -1), ("gid", False),
])
def test_workspace_projection_refuses_wrong_logical_or_physical_facts(tmp_path, field, value):
    remote = _remote_only_case(tmp_path)
    runtime, _, lease, requested, flat, calls = remote
    wrong = dataclasses.replace(requested.workspace, **{field: value})
    producer = rt.build_claimed_remote_workspace_identity_source(
        runtime, lambda *args: binding(remote, workspace=wrong))
    with pytest.raises(rt.RemoteAttemptTransportError):
        producer(lease.attempt, runtime.jobs.get_job(lease.attempt.job_id))
    assert calls == []


def test_workspace_projection_preserves_heartbeat_only_movement(tmp_path):
    remote = _remote_only_case(tmp_path)
    runtime, _, lease, requested, flat, calls = remote
    def source(*args):
        runtime.attempts.heartbeat_attempt(lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
        return binding(remote)
    producer = rt.build_claimed_remote_workspace_identity_source(runtime, source)
    assert producer(lease.attempt, runtime.jobs.get_job(lease.attempt.job_id)) == requested.workspace
    assert calls == []


def test_detached_job_cannot_relabel_the_remote_workspace(tmp_path):
    remote = _remote_only_case(tmp_path)
    runtime, _, lease, requested, flat, calls = remote
    host_reads = []
    producer = rt.build_claimed_remote_workspace_identity_source(
        runtime, lambda *args: host_reads.append(args) or binding(remote))
    wrong = dataclasses.replace(runtime.jobs.get_job(lease.attempt.job_id),
                                constraints={"base_sha": "f"*40})
    with pytest.raises(rt.RemoteAttemptTransportError):
        producer(lease.attempt, wrong)
    assert host_reads == []
