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


def observation_document(tmp_path):
    data = remote_document(tmp_path)
    data['hermes_role_metadata_read'] = {
        'host_ref': data['bindings'][0]['host_ref'],
        'worker_id': data['bindings'][0]['worker_id'],
        'expected_host_binding_sha256': 'b' * 64,
        'expected_implementation_sha': 'c' * 40,
    }
    return data


def observation_source(tmp_path):
    data = observation_document(tmp_path)
    path, digest = installed(tmp_path, json.dumps(data).encode())
    return module.FabricBindingSource.from_path(path, digest), data


@pytest.mark.parametrize('version', ['local', 'remote'])
def test_no_explicit_hermes_selection_has_no_reader_or_network(tmp_path, root_stats, monkeypatch, version):
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    def forbidden(*a, **kw): pytest.fail('unselected source acquired a host client')
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'for_host_observation', forbidden)
    data = document() if version == 'local' else remote_document(tmp_path)
    path, digest = installed(tmp_path, json.dumps(data).encode())
    assert module.FabricBindingSource.from_path(path, digest).hermes_roles_reader() is None


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(hermes_role_metadata_read=None),
    lambda d: d.update(hermes_role_metadata_read=[]),
    lambda d: d['hermes_role_metadata_read'].update(unknown=True),
    lambda d: d['hermes_role_metadata_read'].pop('expected_implementation_sha'),
    lambda d: d['hermes_role_metadata_read'].update(expected_implementation_sha='bad'),
    lambda d: d['hermes_role_metadata_read'].update(expected_host_binding_sha256='A' * 64),
    lambda d: d['hermes_role_metadata_read'].update(host_ref='different-host'),
    lambda d: d['hermes_role_metadata_read'].update(worker_id='different-worker'),
    lambda d: d['hermes_role_metadata_read'].update(worker_id=[]),
    lambda d: d.update(schema_version=module.CONFIG_SCHEMA_VERSION),
])
def test_hermes_selection_is_closed_and_cannot_choose_another_transport(tmp_path, root_stats, mutation):
    data = observation_document(tmp_path); mutation(data)
    path, digest = installed(tmp_path, json.dumps(data).encode())
    with pytest.raises(module.FabricCompositionError):
        module.FabricBindingSource.from_path(path, digest)


def test_hermes_reader_uses_one_existing_host_only_client(tmp_path, root_stats, monkeypatch):
    from common import workspace_byok_read_contract as wire
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    selected, data = observation_source(tmp_path)
    calls = []
    async def read(client):
        calls.append(client)
        assert client.identity == {} and client.allowed_operations == frozenset()
        assert client._host_observation == (
            data['bindings'][0]['host_ref'], 'b' * 64, 'c' * 40)
        assert client.binding is selected._remote_index[
            (data['bindings'][0]['host_ref'], data['bindings'][0]['worker_id'])].binding
        return wire.unavailable()
    def forbidden(*a, **kw): pytest.fail('host observation acquired an Attempt client')
    monkeypatch.setattr(module.FabricBindingSource, 'client_for', forbidden)
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'request', forbidden)
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'read_hermes_roles', read)
    reader = selected.hermes_roles_reader()
    assert asyncio.iscoroutinefunction(reader)
    assert asyncio.run(reader()) == wire.unavailable()
    assert len(calls) == 1


@pytest.mark.parametrize('when', ['before', 'during'])
@pytest.mark.parametrize('changed', ['composition', 'certificate'])
def test_hermes_reader_discards_changed_source_or_transport(tmp_path, root_stats, monkeypatch, when, changed):
    from pathlib import Path
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    from common import workspace_byok_read_contract as wire
    selected, data = observation_source(tmp_path)
    calls = []
    path = selected.path if changed == 'composition' else Path(data['remote_transports'][0]['client_cert_path'])
    def change(): path.write_bytes(path.read_bytes() + b' ')
    async def read(client):
        calls.append(client)
        if when == 'during': change()
        return wire.unavailable()
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'read_hermes_roles', read)
    reader = selected.hermes_roles_reader()
    if when == 'before': change()
    assert asyncio.run(reader()) == wire.unavailable('SOURCE_CHANGED')
    assert len(calls) == (0 if when == 'before' else 1)


def host_read_document(tmp_path, *, execution=False):
    data = remote_document(tmp_path)
    route = data['remote_transports'][0]
    read = dict(schema=module.HERMES_HOST_READ_SCHEMA, host_ref=route['host_ref'],
                transport={k: v for k, v in route.items()
                           if k not in {'host_ref', 'worker_id', 'physical_binding_sha256'}},
                expected_host_binding_sha256='b' * 64, expected_implementation_sha='c' * 40)
    return dict(schema_version=module.HOST_READ_CONFIG_SCHEMA_VERSION,
                bindings=data['bindings'] if execution else [],
                remote_transports=data['remote_transports'] if execution else [],
                hermes_role_metadata_read=read)


def test_v3_read_has_no_physical_execution_identity(tmp_path, root_stats, monkeypatch):
    from common import workspace_byok_read_contract as wire
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    data = host_read_document(tmp_path)
    path, digest = installed(tmp_path, json.dumps(data).encode())
    selected = module.FabricBindingSource.from_path(path, digest)
    assert selected.bindings == () and not selected.has_execution_bindings
    assert not selected._index and not selected._remote_index
    calls = []
    async def read(client):
        calls.append(client)
        assert client.identity == {} and client.allowed_operations == frozenset()
        assert client._host_observation == (data['hermes_role_metadata_read']['host_ref'], 'b' * 64, 'c' * 40)
        return wire.unavailable()
    def forbidden(*a, **kw): pytest.fail('observation acquired execution capability')
    monkeypatch.setattr(module.FabricBindingSource, 'client_for', forbidden)
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'request', forbidden)
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'read_hermes_roles', read)
    assert asyncio.run(selected.hermes_roles_reader()()) == wire.unavailable()
    assert len(calls) == 1


@pytest.mark.parametrize('mutation', [
    lambda d: d.pop('hermes_role_metadata_read'),
    lambda d: d.update(hermes_role_metadata_read=None),
    lambda d: d.update(bindings=None),
    lambda d: d.update(remote_transports=None),
    lambda d: d.update(schema_version=module.REMOTE_CONFIG_SCHEMA_VERSION),
    lambda d: d['hermes_role_metadata_read'].update(worker_id='invented'),
    lambda d: d['hermes_role_metadata_read'].update(host_ref=[]),
    lambda d: d['hermes_role_metadata_read'].update(expected_implementation_sha='bad'),
    lambda d: d['hermes_role_metadata_read']['transport'].update(worker_id='invented'),
    lambda d: d['hermes_role_metadata_read']['transport'].update(endpoint_host='8.8.8.8'),
    lambda d: d['hermes_role_metadata_read']['transport'].update(endpoint_port=True),
])
def test_v3_empty_execution_requires_closed_valid_read(tmp_path, root_stats, mutation):
    data = host_read_document(tmp_path); mutation(data)
    path, digest = installed(tmp_path, json.dumps(data).encode())
    with pytest.raises(module.FabricCompositionError):
        module.FabricBindingSource.from_path(path, digest)


def test_v3_preserves_execution_and_refuses_conflicting_host_transport(tmp_path, root_stats):
    data = host_read_document(tmp_path, execution=True)
    before = copy.deepcopy(data)
    path, digest = installed(tmp_path, json.dumps(data).encode())
    selected = module.FabricBindingSource.from_path(path, digest)
    assert selected.has_execution_bindings
    assert dataclasses.asdict(selected.bindings[0]) == before['bindings'][0]
    assert selected._remote_index[(selected.bindings[0].host_ref, selected.bindings[0].worker_id)].binding == selected._hermes_role_metadata_read.transport.binding
    data['hermes_role_metadata_read']['transport']['endpoint_port'] += 1
    path, digest = installed(tmp_path, json.dumps(data).encode())
    with pytest.raises(module.FabricCompositionError, match='Conflicting transports'):
        module.FabricBindingSource.from_path(path, digest)


@pytest.mark.parametrize('when', ['before', 'during'])
@pytest.mark.parametrize('changed', ['composition', 'certificate', 'identity'])
def test_v3_read_discards_source_or_tls_drift(tmp_path, root_stats, monkeypatch, when, changed):
    from pathlib import Path
    from common import workspace_byok_read_contract as wire
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    data = host_read_document(tmp_path)
    path, digest = installed(tmp_path, json.dumps(data).encode())
    selected = module.FabricBindingSource.from_path(path, digest)
    target = path if changed != 'certificate' else Path(data['hermes_role_metadata_read']['transport']['client_cert_path'])
    calls = []
    def change():
        if changed == 'identity':
            replacement = target.with_suffix('.replacement')
            replacement.write_bytes(target.read_bytes()); replacement.chmod(0o600); replacement.replace(target)
        else:
            target.write_bytes(target.read_bytes() + b' ')
    async def read(client):
        calls.append(client)
        if when == 'during': change()
        return wire.unavailable()
    monkeypatch.setattr(RemoteWorkerBrokerClient, 'read_hermes_roles', read)
    if when == 'before': change()
    assert asyncio.run(selected.hermes_roles_reader()()) == wire.unavailable('SOURCE_CHANGED')
    assert len(calls) == (0 if when == 'before' else 1)


@pytest.mark.parametrize('execution', [False, True])
def test_paid_control_coexists_only_with_validated_metadata_only_source(tmp_path, root_stats, monkeypatch, execution):
    from scripts import executive_os_phase1c as entry
    from control_plane import executive_paid_fabric_composition as paid
    from control_plane import fabric_attended_routing as attended
    data = host_read_document(tmp_path, execution=execution)
    path, digest = installed(tmp_path, json.dumps(data).encode())
    raw = dict(fabric_bindings_path=str(path), fabric_bindings_sha256=digest,
               proof_base_sha='c' * 40, control_environment_attestation_path=str(tmp_path / 'attestation'))
    monkeypatch.setattr(entry, 'load_control_config', lambda _: raw)
    monkeypatch.setattr(paid, 'installed_paid_source', lambda *a, **kw: object())
    monkeypatch.setattr(attended, 'installed_control_placements', lambda _: ())
    class ReachedNextStartupBoundary(Exception): pass
    def reached(*a, **kw): raise ReachedNextStartupBoundary()
    monkeypatch.setattr(entry, '_load_control_environment_attestation', reached)
    error = entry.ServiceError if execution else ReachedNextStartupBoundary
    with pytest.raises(error):
        asyncio.run(entry._serve_from_config(path, _installed_control=True))
