"""Original Attempt transport selection; fixtures never enroll a host."""
import asyncio
import copy
import dataclasses
import hashlib
import json

import pytest

from control_plane import executive_fabric_composition as module
from test_executive_fabric_composition import binding, document, installed, root_stats


def remote_document(tmp_path):
    route = binding()
    transport = dict(host_ref=route['host_ref'], worker_id=route['worker_id'],
        physical_binding_sha256=module.FabricHostBinding(**route).digest,
        endpoint_host='127.0.0.1', endpoint_port=8443,
        expected_server_fingerprint='a'*64, timeout_seconds=30)
    for key in ('ca_path', 'client_cert_path', 'client_key_path'):
        path = tmp_path / key
        path.write_text('inert fixture, never loaded as TLS')
        path.chmod(0o600)
        transport[key] = str(path)
    return dict(schema_version='mastermind.executive_fabric_bindings/v2',
                bindings=[route], remote_transports=[transport])


def payload(physical):
    return dict(binding=dict(root_id='root-1', job_id='job-1', attempt_id='attempt-1',
        effective_grant_digest='b'*64, commission_sha256='c'*64),
        physical_binding_sha256=physical.digest, run_id='attempt-1')


def source(tmp_path):
    d = remote_document(tmp_path)
    path, digest = installed(tmp_path, json.dumps(d).encode())
    return module.FabricBindingSource.from_path(path, digest), d


def test_running_event_loop_is_classified_no_effect(tmp_path, root_stats):
    from control_plane.remote_worker_transport import TransportError, TransportEffect
    selected, _ = source(tmp_path); physical = selected.bindings[0]
    p = payload(physical); client = selected.client_for(physical, p)
    async def scenario():
        with pytest.raises(TransportError) as failed: client.request_sync('status', p)
        assert failed.value.classification is TransportEffect.NO_EFFECT
        assert failed.value.code == 'sync_context_invalid'
    asyncio.run(scenario())


def test_optional_runtime_generation_binding_remains_exactly_once(tmp_path, root_stats, monkeypatch):
    from control_plane.remote_worker_transport import TransportValidationError
    selected, _ = source(tmp_path); physical = selected.bindings[0]
    p = payload(physical); client = selected.client_for(physical, p)
    client.bind_payload_identity(session_epoch_id='epoch-1', process_generation_id='generation-1')
    with pytest.raises(TransportValidationError):
        client.bind_payload_identity(session_epoch_id='epoch-1', process_generation_id='generation-2')
    async def forbidden(*a, **kw): pytest.fail('retargeted generation reached transport')
    monkeypatch.setattr(client._client, 'request', forbidden)
    with pytest.raises(module.FabricCompositionError):
        asyncio.run(client.request('status', {**p, 'process_generation_id': 'generation-2'}))


def test_cancelled_modifying_transport_retains_unknown_effect(tmp_path, root_stats, monkeypatch):
    from control_plane.remote_worker_transport import TransportError, TransportEffect
    selected, _ = source(tmp_path); physical = selected.bindings[0]
    p = payload(physical); client = selected.client_for(physical, p)
    async def cancellation(*a, **kw): raise asyncio.CancelledError()
    monkeypatch.setattr(client._client, 'request', cancellation)
    with pytest.raises(TransportError) as failed: asyncio.run(client.request('start', p))
    assert failed.value.classification is TransportEffect.EFFECT_UNKNOWN
    with pytest.raises(asyncio.CancelledError): asyncio.run(client.request('status', p))


def test_v2_remote_transport_can_be_selected_without_touching_local_socket(tmp_path, root_stats, monkeypatch):
    selected, _ = source(tmp_path)
    physical = selected.bindings[0]
    client = selected.client_for(physical, payload(physical))
    assert client.identity['host_ref'] == physical.host_ref
    assert client.identity['worker_id'] == physical.worker_id
    assert client.identity['attempt_id'] == 'attempt-1'


def test_v1_selects_original_local_client(tmp_path, root_stats, monkeypatch):
    from control_plane import executive_fabric_adapter as adapter
    path, digest = installed(tmp_path)
    selected = module.FabricBindingSource.from_path(path, digest)
    sentinel = object()
    monkeypatch.setattr(adapter, '_fixed_client', lambda physical: sentinel)
    assert selected.client_for(selected.bindings[0], payload(selected.bindings[0])) is sentinel


@pytest.mark.parametrize('mutation', [
    lambda d: d['remote_transports'][0].update(physical_binding_sha256='0'*64),
    lambda d: d['remote_transports'][0].update(worker_id='different-worker'),
    lambda d: d['remote_transports'][0].update(endpoint_host='8.8.8.8'),
    lambda d: d['remote_transports'][0].update(endpoint_host=True),
    lambda d: d['remote_transports'][0].update(endpoint_port=True),
    lambda d: d['remote_transports'][0].update(timeout_seconds=float('inf')),
    lambda d: d['remote_transports'][0].update(unknown='value'),
    lambda d: d['remote_transports'].append(copy.deepcopy(d['remote_transports'][0])),
])
def test_remote_configuration_cannot_retarget_or_widen(tmp_path, root_stats, mutation):
    d = remote_document(tmp_path)
    mutation(d)
    path, digest = installed(tmp_path, json.dumps(d).encode())
    with pytest.raises(module.FabricCompositionError):
        module.FabricBindingSource.from_path(path, digest)


def test_original_command_and_seal_are_forwarded_and_other_parent_refuses(tmp_path, root_stats, monkeypatch):
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    selected, _ = source(tmp_path)
    p = payload(selected.bindings[0]); calls = []
    async def send(self, operation, value, **kwargs):
        calls.append((operation, copy.deepcopy(value)))
        return {'retained': True}
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'request', send)
    client = selected.client_for(selected.bindings[0], p)
    command = {**p, 'control_start': {'original': 'projection'}}
    assert asyncio.run(client.request('start', command)) == {'retained': True}
    assert calls[-1] == ('start', command)
    assert asyncio.run(client.request('assignment-seal', p)) == {'retained': True}
    other = copy.deepcopy(p); other['binding']['root_id'] = 'other-parent'
    with pytest.raises(module.FabricCompositionError):
        asyncio.run(client.request('status', other))
    assert len(calls) == 2


def test_configuration_replacement_refuses_before_transport(tmp_path, root_stats, monkeypatch):
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    selected, _ = source(tmp_path); physical = selected.bindings[0]
    p = payload(physical); client = selected.client_for(physical, p)
    async def forbidden(*args, **kwargs):
        pytest.fail('transport crossed changed configuration')
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'request', forbidden)
    selected.path.write_bytes(selected.path.read_bytes() + b' ')
    with pytest.raises(module.FabricCompositionError):
        asyncio.run(client.request('status', p))


def test_tls_identity_replacement_refuses_before_transport(tmp_path, root_stats, monkeypatch):
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    selected, d = source(tmp_path); physical = selected.bindings[0]
    p = payload(physical); client = selected.client_for(physical, p)
    async def forbidden(*args, **kwargs):
        pytest.fail('transport crossed replaced TLS material')
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'request', forbidden)
    from pathlib import Path
    Path(d['remote_transports'][0]['client_key_path']).write_text('changed fixture')
    with pytest.raises(module.FabricCompositionError):
        asyncio.run(client.request('status', p))


def test_source_change_during_response_is_not_returned_as_valid(tmp_path, root_stats, monkeypatch):
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    selected, _ = source(tmp_path); physical = selected.bindings[0]
    p = payload(physical); client = selected.client_for(physical, p)
    async def changed(*args, **kwargs):
        selected.path.write_bytes(selected.path.read_bytes() + b' ')
        return {'retained': True}
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'request', changed)
    with pytest.raises(module.FabricCompositionError):
        asyncio.run(client.request('status', p))


def test_source_change_after_start_preserves_uncertain_effect(tmp_path, root_stats, monkeypatch):
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    from control_plane.remote_worker_transport import TransportError, TransportEffect
    selected, _ = source(tmp_path); physical = selected.bindings[0]
    p = payload(physical); client = selected.client_for(physical, p)
    calls = []
    async def changed(operation, value, **kwargs):
        calls.append(operation)
        selected.path.write_bytes(selected.path.read_bytes() + b' ')
        return {'started': True}
    monkeypatch.setattr(client._client, 'request', changed)
    with pytest.raises(TransportError) as failed:
        asyncio.run(client.request('start', p))
    assert failed.value.classification is TransportEffect.EFFECT_UNKNOWN
    assert calls == ['start']


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(physical_binding_sha256='0'*64),
    lambda p: p.update(run_id='other-attempt'),
    lambda p: p.update(launch_spec={'worker_id': 'other-worker'}),
    lambda p: p['binding'].update(effective_grant_digest='0'*64),
])
def test_exact_original_coordinates_cannot_be_retargeted(tmp_path, root_stats, monkeypatch, mutation):
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    selected, _ = source(tmp_path); physical = selected.bindings[0]
    p = payload(physical); client = selected.client_for(physical, p)
    async def forbidden(*args, **kwargs):
        pytest.fail('transport crossed a retargeted original Attempt')
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'request', forbidden)
    mutation(p)
    with pytest.raises(module.FabricCompositionError):
        asyncio.run(client.request('status', p))
