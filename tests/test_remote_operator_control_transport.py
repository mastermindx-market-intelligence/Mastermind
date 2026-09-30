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
