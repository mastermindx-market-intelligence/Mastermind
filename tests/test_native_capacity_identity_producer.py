"""Actual Bridge -> fixed backend -> realm/source/kernel producer composition.

Only OS custody/kernel reads are virtualized. No service or provider is run.
"""
import asyncio
import builtins
import copy
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import codex_provider_realm as realm
from control_plane import executive_fabric_bridge_broker as bridge
from control_plane.codex_worker import ProcessInspector
from control_plane.executive_fabric_adapter import FabricHostBinding
from control_plane.executive_worker_broker import BROKER_REQUEST_SCHEMA_VERSION, BrokerPolicy, PeerCredentials
from integrations.session_bridge.bound_launch_capture import fabric_attended_backend as backend
from ops.executive_os.capacity_source_contract import (
    CapacitySourceContractError, validate_native_identity_observation,
)
from ops.executive_os.host_capacity_probe import current_boot_reference, HostCapacityProbeError
from tests.test_native_subscription_capacity_enrollment import bound
from tests.test_subscription_realm_owner import enrolled

BOOT = '2bb7c22f-1697-4b5b-94b6-61f10fc94367'
NEXT_BOOT = '8b09ce35-a820-4e61-b10d-ea22c57ec306'


@pytest.fixture
def native(bound, monkeypatch, tmp_path, request):
    owner = bound.publish()
    physical_host = bound.f.config['native_capacity_enrollment']['host_ref']
    if getattr(request, 'param', None) == 'legacy':
        del bound.f.config['native_capacity_enrollment']
        owner = bound.f.load()
    kernels = []
    def kernel(_self):
        kernels.append(BOOT)
        return BOOT
    monkeypatch.setattr(ProcessInspector, 'boot_session_id', kernel)
    # Virtualize only Bridge config root ownership without changing the actual
    # realm/credential fstat observations in the already-admitted worker fixture.
    class BridgeOS:
        def __getattr__(self, key): return getattr(os, key)
        def fstat(self, fd):
            s = os.fstat(fd)
            return SimpleNamespace(st_uid=0, **{k: getattr(s, k) for k in
                ('st_mode', 'st_dev', 'st_ino', 'st_size', 'st_mtime_ns')})
    monkeypatch.setattr(bridge, 'os', BridgeOS())
    monkeypatch.setattr(bridge, '_trusted_parent_chain', lambda _path: None)
    path = tmp_path / 'bridge.json'
    path.write_text(json.dumps(dict(schema_version=bridge.CONFIG_SCHEMA_VERSION,
        adapter_id=bridge.ADAPTER_ID, bridge_uid=470, control_uid=450,
        launchd_socket_name='AttendedFabric', socket_path=str(tmp_path/'query.sock'),
        workspace_root=str(tmp_path/'workspaces'), run_root=str(tmp_path/'runs'),
        max_request_bytes=65536, max_response_bytes=262144,
        request_timeout_seconds=10, validation_commands=[])))
    config = bridge.load_config(path)
    workspaces, runs = tmp_path/'workspaces', tmp_path/'runs'
    workspaces.mkdir(); runs.mkdir()
    # The real policy constructor also reads the private HOME ownership. Keep
    # this one OS metadata boundary consistent with the dedicated UID fixture.
    original_lstat = Path.lstat
    def worker_home_stat(path, *args, **kwargs):
        s = original_lstat(path, *args, **kwargs)
        if path == bound.f.home:
            values = {key: getattr(s, key) for key in dir(s) if key.startswith('st_')}
            return SimpleNamespace(**{**values, 'st_uid': 470, 'st_gid': 470})
        return s
    monkeypatch.setattr(Path, 'lstat', worker_home_stat)
    policy = BrokerPolicy(control_uid=450, worker_uid=470, worker_gid=470,
        worker_id='minimax-finite-01', worker_user='_mastermind_minimax',
        workspace_root=workspaces, run_root=runs, provider_home=bound.f.home,
        require_assignment_seal=True)
    physical = FabricHostBinding(socket_path=str(config.socket_path),
        host_ref=physical_host,
        worker_id=policy.worker_id, worker_uid=470, worker_gid=470, bridge_uid=470,
        provider='minimax', model='MiniMax-M3', provider_home=str(policy.provider_home),
        worker_source_config_digest=owner._config_sha256, execution_profile_digest='a'*64,
        service_source_sha256='b'*64, binary_sha256='c'*64, permission_profile_sha256='d'*64)
    # Actual fixed factory verifies typed policy/route and the dedicated current
    # OS principal. Its resources themselves still confer no Runtime authority.
    resources = backend._FixedOwnerResources(preparation={'policy': policy}, physical=physical,
        binary_pin=None, routing_root_id='fixture-root', routing_parent_run_id='fixture-parent',
        active_dir=tmp_path/'active', credential_realm_owner=owner,
        credential_loader=lambda: pytest.fail('query cannot load a credential'))
    actual_backend = backend.create_attended_backend(config, owner_resources=resources)
    service = bridge.FabricBridgeBroker(config, actual_backend)
    request = dict(schema_version=BROKER_REQUEST_SCHEMA_VERSION, request_id='read-native-1',
                   operation='native-capacity-observation', payload={'nonce': '1'*32})
    def query(uid=450):
        return asyncio.run(service.execute(request, peer=PeerCredentials(uid=uid, gid=450)))
    return SimpleNamespace(bound=bound, owner=owner, service=service, backend=actual_backend,
                           kernels=kernels, request=request, query=query)


def test_actual_authenticated_query_produces_boot_bound_unknown_facts(native, monkeypatch):
    credential = native.bound.f.credential
    inode = credential.stat().st_ino
    read = os.read
    def guarded_read(fd, count):
        assert os.fstat(fd).st_ino != inode, 'credential bytes cannot be read'
        return read(fd, count)
    monkeypatch.setattr(realm.os, 'read', guarded_read)
    for module, name in ((builtins, 'open'), (io, 'open')):
        original = getattr(module, name)
        def guarded_open(path, *args, _original=original, **kwargs):
            if isinstance(path, int):
                assert os.fstat(path).st_ino != inode
            else:
                assert Path(path) != credential
            return _original(path, *args, **kwargs)
        monkeypatch.setattr(module, name, guarded_open)
    response = native.query()
    assert response['ok'] is True and response['result']['nonce'] == '1'*32
    value = response['result']['observation']
    assert value['host_ref'] == 'host-'+'1'*64
    assert value['capability_generation'] == 3 and value['realm_generation'] == 2
    assert value['boot_ref'] == current_boot_reference()
    assert value['realm_auth']['state'] == value['provider_health']['state'] == 'unknown'
    assert value['cooling']['active'] is None and value['quota_horizons'] == []
    assert str(native.bound.f.home) not in json.dumps(response)
    assert BOOT not in json.dumps(response)
    assert validate_native_identity_observation(value) == value
    assert native.backend._backend is None and native.backend._attempted is False
    assert native.backend._probe_task is None and native.backend._probe_busy is False
    # Repeated reads are observations; they consume no Attempt/assignment slot.
    assert native.query()['ok'] is True


@pytest.mark.parametrize('uid', [0, 470, 501])
def test_foreign_peer_refused_before_any_owner_acquisition(native, uid):
    with pytest.raises(bridge.BridgeProtocolError, match='authenticated Control'):
        native.query(uid)
    assert native.kernels == []


@pytest.mark.parametrize('payload', [{'nonce': 'bad'}, {'nonce': '1'*32, 'host_ref': 'foreign'},
    {'nonce': '1'*32, 'observed_at': 'caller-clock'}, {}, {'nonce': True}])
def test_request_cannot_select_identity_clock_source_or_path(native, payload):
    native.request['payload'] = payload
    with pytest.raises(bridge.BridgeProtocolError): native.query()
    assert native.kernels == []


def test_current_service_identity_is_required(native, monkeypatch):
    monkeypatch.setattr(realm.os, 'geteuid', lambda: 471)
    with pytest.raises(bridge.BridgeProtocolError, match='configured principal'): native.query()
    assert native.kernels == []


def test_boot_change_during_real_source_collection_refuses(native, monkeypatch):
    boots = iter((BOOT, NEXT_BOOT))
    monkeypatch.setattr(ProcessInspector, 'boot_session_id', lambda _self: next(boots))
    with pytest.raises(bridge.BridgeProtocolError, match='Current native observation is unavailable'):
        native.query()
    assert native.backend._attempted is False


def test_root_revocation_invalidates_real_collection(native):
    native.bound.f.path.write_text('{}')
    with pytest.raises(bridge.BridgeProtocolError, match='Current native observation is unavailable'):
        native.query()
    assert native.kernels == []


@pytest.mark.parametrize('native', ['legacy'], indirect=True)
def test_legacy_service_does_not_acquire_native_facts_without_opt_in(native):
    with pytest.raises(bridge.BridgeProtocolError, match='Current native observation is unavailable'):
        native.query()
    assert native.kernels == [] and native.backend._attempted is False


def test_root_change_after_first_source_read_is_not_returned(native, monkeypatch):
    def changed(_self):
        native.bound.f.path.write_text('{}')
        return BOOT
    monkeypatch.setattr(ProcessInspector, 'boot_session_id', changed)
    with pytest.raises(bridge.BridgeProtocolError, match='Current native observation is unavailable'):
        native.query()
    assert native.backend._attempted is False


@pytest.mark.parametrize('raw', ['adapter-1', 'not-a-uuid', '0'*32, BOOT+'\n', None])
def test_kernel_fallback_or_malformed_epoch_is_not_boot_provenance(raw, monkeypatch):
    monkeypatch.setattr(ProcessInspector, 'boot_session_id', lambda _self: raw)
    with pytest.raises(HostCapacityProbeError, match='BOOT_IDENTITY_UNAVAILABLE'):
        current_boot_reference()


def test_boot_representation_normalizes_one_epoch_without_changing_enrollment(monkeypatch):
    monkeypatch.setattr(ProcessInspector, 'boot_session_id', lambda _self: BOOT)
    first = current_boot_reference()
    monkeypatch.setattr(ProcessInspector, 'boot_session_id', lambda _self: BOOT.upper())
    assert current_boot_reference() == first
    monkeypatch.setattr(ProcessInspector, 'boot_session_id', lambda _self: NEXT_BOOT)
    assert current_boot_reference() != first


@pytest.mark.parametrize('fault', ['extra', 'auth', 'health', 'cooling', 'quota', 'generation', 'time'])
def test_projection_never_admits_invented_positive_provider_facts(native, fault):
    value = copy.deepcopy(native.query()['result']['observation'])
    if fault == 'extra': value['config_path'] = '/private/provider/config'
    if fault == 'auth': value['realm_auth']['state'] = 'ready'
    if fault == 'health': value['provider_health']['state'] = 'available'
    if fault == 'cooling': value['cooling']['active'] = False
    if fault == 'quota': value['quota_horizons'] = [{'remaining': 100}]
    if fault == 'generation': value['capability_generation'] = True
    if fault == 'time': value['observed_at'] = 'not-time'
    with pytest.raises(CapacitySourceContractError): validate_native_identity_observation(value)
