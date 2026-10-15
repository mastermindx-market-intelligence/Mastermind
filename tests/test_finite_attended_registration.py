"""Real Runtime identity registration, explicitly no capacity/admission grant."""
import dataclasses
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import Runtime, StateConflict, WorkerStatus
from control_plane.fabric_attended_registration import register_fixed_finite
from control_plane.fabric_attended_routing import installed_control_placements
from tests.test_installed_finite_control import finite_raw
from tests.test_attended_worker_definition import inputs
from ops.executive_os.attended_worker_definition import build_finite_worker_artifacts
from control_plane.executive_fabric_composition import _bindings
from tests.test_executive_fabric_composition import root_stats


@pytest.fixture
def joined(tmp_path, inputs):
    import json
    inputs.update(worker_id='minimax-finite-01', worker_user='_mastermind_minimax',
        worker_group='_mastermind_minimax', worker_uid=470, worker_gid=470,
        capacity_capability_id='fixture-minimax-capacity', host_ref='host-'+'a'*64)
    artifacts = build_finite_worker_artifacts(**inputs)
    physical, = _bindings(artifacts['bindings.json'])
    definition = json.loads(artifacts['worker.json'])
    source = SimpleNamespace(bindings=(physical,))
    class BindingSource:
        bindings = source.bindings
        def __call__(self, host, worker):
            assert (host, worker) == (physical.host_ref, physical.worker_id)
            return physical
    probe = SimpleNamespace(configuration=lambda selected: ({}, dict(definition), {}))
    return SimpleNamespace(runtime=Runtime.at(tmp_path/'runtime'), source=BindingSource(), probe=probe,
        placement=installed_control_placements(finite_raw())[0], definition=definition,
        physical=physical, artifacts=artifacts)


def register(s, guard=lambda: None):
    return register_fixed_finite(s.runtime, s.placement, s.source, s.probe, guard)


def test_real_registry_keeps_new_identity_offline_until_capacity_owner_qualifies(joined):
    s = joined
    row = register(s)
    assert row.status == WorkerStatus.OFFLINE
    assert row.account_label == 'mastermind-minimax'
    quota = s.runtime.workers.get_quota_class(row.worker_id, s.placement.quota_class)
    assert quota.status == WorkerStatus.OFFLINE
    assert quota.metadata['capacity_join']['capacity_capability_id'] == 'fixture-minimax-capacity'
    assert quota.metadata['capacity_join']['worker_source_config_digest'] == s.physical.worker_source_config_digest
    assert register(s).to_dict() == row.to_dict()


@pytest.mark.parametrize('edge', ['missing-id', 'bad-id', 'guard', 'wrong-worker', 'definition-drift'])
def test_unbound_or_changed_identity_never_registers(joined, edge):
    s = joined
    guard = lambda: None
    if edge == 'missing-id': del s.definition['capacity_capability_id']
    if edge == 'bad-id': s.definition['capacity_capability_id'] = '../quota'
    if edge == 'guard':
        def guard(): raise ValueError('original guard unavailable')
    if edge == 'wrong-worker': s.source.bindings = (dataclasses.replace(s.physical, worker_id='other'),)
    if edge == 'definition-drift':
        calls = []
        def config(p):
            calls.append(1)
            return {}, dict(s.definition, capacity_capability_id=('changed' if len(calls)>1 else 'fixture-minimax-capacity')), {}
        s.probe.configuration = config
    with pytest.raises((ValueError, StateConflict)): register(s, guard)
    assert s.runtime.workers.get_worker('minimax-finite-01') is None


def test_foreign_existing_worker_is_not_overwritten(joined):
    s = joined
    s.runtime.workers.register_worker('minimax-finite-01', provider='codex', account_label='foreign',
        worker_type='codex', capabilities=['research'])
    with pytest.raises(StateConflict): register(s)
    assert s.runtime.workers.get_worker('minimax-finite-01').account_label == 'foreign'


def test_guard_drift_during_final_source_read_prevents_registration(joined):
    s = joined
    state = {'valid': True, 'reads': 0}
    def guard():
        if not state['valid']:
            raise StateConflict('original config or receipt changed')
    def config(physical):
        state['reads'] += 1
        if state['reads'] == 2:
            state['valid'] = False
        return {}, dict(s.definition), {}
    s.probe.configuration = config
    with pytest.raises(StateConflict, match='original config or receipt changed'):
        register(s, guard)
    assert s.runtime.workers.get_worker('minimax-finite-01') is None


def test_actual_operator_handler_invokes_bound_registration_and_preserves_reply(joined):
    import asyncio
    from control_plane.executive_service import ExecutiveControlService, CONTROL_PROTOCOL_VERSION
    from tests.test_executive_service import _config
    s = joined
    service = ExecutiveControlService(_config(s.runtime.store.root),
        attended_worker_registration=lambda runtime: register(s))
    service.runtime = s.runtime
    service._register_worker = lambda: {'primary': 'unchanged'}
    result = asyncio.run(service._dispatch_request({'version': CONTROL_PROTOCOL_VERSION, 'command': 'register-worker', 'args': {}}))
    assert result == {'primary': 'unchanged'}
    assert s.runtime.workers.get_worker('minimax-finite-01').status == WorkerStatus.OFFLINE


def test_actual_factory_and_operator_handler_reach_same_runtime(joined, tmp_path, monkeypatch, root_stats):
    import asyncio
    import hashlib
    from control_plane import executive_worker_broker as broker
    from control_plane.executive_service import CONTROL_PROTOCOL_VERSION
    from control_plane.executive_fabric_composition import FabricBindingSource
    from control_plane.fabric_attended_canary import AttendedControlProbeSource
    from scripts import executive_os_phase1c as cli
    from tests.test_ceo_submit_armed_composition import _raw, _write
    s = joined
    path = tmp_path/'bindings.json'
    path.write_bytes(s.artifacts['bindings.json'])
    path.chmod(0o600)
    source = FabricBindingSource.from_path(path, hashlib.sha256(path.read_bytes()).hexdigest())
    raw = cli.load_control_config(_write(tmp_path, _raw(tmp_path)))
    raw.update(coo_foreground_only=True, coo_autonomy_armed=True)
    probe = AttendedControlProbeSource.from_startup(tmp_path/'control.json', raw,
        {'config_sha256': 'a'*64})
    # Only host transport/metadata boundaries are inert; the real factory,
    # service command, secondary callback and SQLite registry remain joined.
    monkeypatch.setattr(AttendedControlProbeSource, 'configuration',
        lambda self, physical: (raw, dict(s.definition), {}))
    monkeypatch.setattr(broker, 'WorkerBrokerClient', lambda *a, **kw: object())
    import socket
    monkeypatch.setattr(cli, 'activate_launchd_socket',
        lambda name: SimpleNamespace(family=socket.AF_UNIX, type=socket.SOCK_STREAM,
            getsockname=lambda: str(raw['control_socket_path']), getsockopt=lambda *a: 1))
    guarded = []
    service = cli._service_from_config(raw, fabric_worker_binding_source=source,
        fabric_attended_probe_source=probe, attended_work_placements=(s.placement,),
        autonomy_guard=lambda: guarded.append(True))
    service.runtime = s.runtime
    service._register_worker = lambda: {'primary': 'unchanged'}
    request = {'version': CONTROL_PROTOCOL_VERSION, 'command': 'register-worker', 'args': {}}
    with pytest.raises(StateConflict, match='AWAITING_CANARY'):
        asyncio.run(service._dispatch_request(request))
    assert s.runtime.workers.get_worker('minimax-finite-01') is None
    # Readiness is an explicit fixture prerequisite, never set by registration.
    service._service_state = 'READY'
    result = asyncio.run(service._dispatch_request(request))
    assert result == {'primary': 'unchanged'} and guarded
    assert s.runtime.workers.get_worker('minimax-finite-01').status == WorkerStatus.OFFLINE


def test_capacity_definition_field_reaches_strict_reader(inputs, tmp_path):
    import json
    from scripts import executive_os_phase1c_worker as worker
    artifacts = build_finite_worker_artifacts(**dict(inputs,
        capacity_capability_id='fixture-minimax-capacity'))
    path = tmp_path/'worker.json'
    path.write_bytes(artifacts['worker.json'])
    path.chmod(0o600)
    assert worker._load_config(path, require_root_owner=False)['capacity_capability_id'] == 'fixture-minimax-capacity'
    value = json.loads(path.read_bytes())
    value['capacity_capability_id'] = '../capacity'
    path.write_text(json.dumps(value))
    with pytest.raises(worker.WorkerConfigError, match='capacity identity'):
        worker._load_config(path, require_root_owner=False)
