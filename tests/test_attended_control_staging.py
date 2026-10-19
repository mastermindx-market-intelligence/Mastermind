"""Finite config staging uses the real global transaction, without host effects."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import autonomy_control as owner
from ops.executive_os import attended_control_staging as staging
from tests.test_executive_autonomy_control import SHA, _inprocess_marker_host
from tests.test_attended_worker_definition import inputs
from tests.test_executive_fabric_composition import root_stats
from tests.test_fabric_attended_routing import router


def replace_fixture(path, raw):
    temporary = path.with_suffix('.fixture')
    temporary.write_bytes(raw)
    temporary.chmod(0o440)
    temporary.replace(path)


@pytest.fixture
def installed(monkeypatch, tmp_path):
    root, marker = _inprocess_marker_host(monkeypatch, tmp_path)
    value = json.loads(owner.CONTROL_CONFIG.read_bytes())
    value.update(coo_autonomy_armed=False, coo_operator_harness_armed=False,
                 coo_foreground_only=False, ceo_submit_armed=False)
    replace_fixture(owner.CONTROL_CONFIG, owner.encode_config(value))
    worker = json.loads(owner.WORKER_CONFIG.read_bytes())
    worker['operator_harness_armed'] = False
    replace_fixture(owner.WORKER_CONFIG, owner.encode_config(worker))
    host = staging.ProductionFiniteStagingHost()
    monkeypatch.setattr(host, 'effective_uid', lambda: 0)
    monkeypatch.setattr(host, 'require_exact_install', lambda sha: sha)
    monkeypatch.setattr(host, 'require_services_already_stopped', lambda: None)
    monkeypatch.setattr(host, 'require_service_uids_quiescent', lambda: None)
    monkeypatch.setattr(host, 'require_runtime_quiescent', lambda config: None)
    delta = dict(fabric_bridge_armed=False,
        fabric_bindings_path=staging.FINITE_DEFINITION_DIR+'/bindings.json',
        fabric_bindings_sha256='a'*64,
        fabric_attended_probe={'worker_config_path':staging.FINITE_DEFINITION_DIR+'/worker.json'})
    monkeypatch.setattr(host, 'read_delta', lambda: dict(delta))
    def validate(tx):
        path, _ = host._candidate_paths(tx.transaction_id)
        raw = path.read_bytes()
        return json.loads(raw), raw, owner.WORKER_CONFIG.read_bytes()
    monkeypatch.setattr(host, '_read_validated_control_candidate', validate)
    s = SimpleNamespace(host=host, marker=marker, delta=delta,
        control=owner.CONTROL_CONFIG.read_bytes(), worker=owner.WORKER_CONFIG.read_bytes())
    yield s
    if host._transaction_owner_fd is not None:
        host._release_transaction_owner()


def stage(s):
    return staging.execute_staging(s.host, SHA, owner.sha256_bytes(s.control))


def retained_disarm(s):
    prior = s.host.checked_configs(SHA)
    unchanged = owner.CandidateConfigs(prior.control, prior.worker, prior.control_bytes,
        prior.worker_bytes, prior.control_sha256, prior.worker_sha256)
    tx = owner.TransactionContext('autonomy-'+'1'*12, SHA, prior, unchanged, None)
    receipt = owner.build_transaction_receipt(tx, state='DISARMED', now=datetime.now(timezone.utc))
    owner.AUTONOMY_RECEIPT.write_bytes(owner._encoded_json(receipt))
    owner.AUTONOMY_RECEIPT.chmod(0o444)
    return receipt


def test_current_disarmed_receipt_stays_bound_without_refreshing_authority(installed):
    s = installed
    old = retained_disarm(s)
    tx = stage(s)
    current, metadata = owner.load_receipt_file(owner.AUTONOMY_RECEIPT)
    from control_plane.executive_autonomy import validate_disarmed_interlock_document
    validate_disarmed_interlock_document(current, metadata=metadata,
        control_config_sha256=owner.sha256_bytes(owner.CONTROL_CONFIG.read_bytes()),
        worker_config_sha256=owner.sha256_bytes(s.worker))
    assert current['transaction_id'] == tx
    assert {k: v for k, v in current.items() if k not in {
        'control_config_sha256', 'prior_control_config_sha256', 'transaction_id'}} == {
        k: v for k, v in old.items() if k not in {
        'control_config_sha256', 'prior_control_config_sha256', 'transaction_id'}}
    assert not s.marker.exists()


def test_lost_receipt_response_reconciles_without_second_write(installed, monkeypatch):
    s = installed
    retained_disarm(s)
    original = owner._atomic_file
    writes = []
    def lost(path, raw, **kw):
        original(path, raw, **kw)
        if path == owner.AUTONOMY_RECEIPT:
            writes.append(raw)
            raise OSError('lost original receipt publication reply')
    monkeypatch.setattr(owner, '_atomic_file', lost)
    with pytest.raises(owner.TransactionEffectUnknown): stage(s)
    assert len(writes) == 1 and s.marker.exists()
    s.host._release_transaction_owner()
    s.host.reconcile_staging(SHA)
    assert len(writes) == 1 and not s.marker.exists()


def test_config_published_without_receipt_is_unknown_not_completed(installed, monkeypatch):
    s = installed
    old = retained_disarm(s)
    original = s.host.replace_control_config
    def lost(tx):
        original(tx)
        raise OSError('lost config response before paired receipt')
    monkeypatch.setattr(s.host, 'replace_control_config', lost)
    with pytest.raises(owner.TransactionEffectUnknown): stage(s)
    s.host._release_transaction_owner()
    with pytest.raises(owner.TransactionEffectUnknown): s.host.reconcile_staging(SHA)
    assert s.marker.exists()
    assert json.loads(owner.AUTONOMY_RECEIPT.read_bytes()) == old


@pytest.mark.parametrize('change', [{'state': 'ARMED'}, {'control_config_sha256': 'e'*64}])
def test_invalid_present_disarm_never_rebinds_or_changes_config(installed, change):
    s = installed
    old = retained_disarm(s)
    owner.AUTONOMY_RECEIPT.chmod(0o600)
    owner.AUTONOMY_RECEIPT.write_bytes(owner._encoded_json(dict(old, **change)))
    owner.AUTONOMY_RECEIPT.chmod(0o444)
    with pytest.raises(Exception): stage(s)
    assert owner.CONTROL_CONFIG.read_bytes() == s.control and not s.marker.exists()


def test_absent_receipt_is_not_created(installed):
    stage(installed)
    assert not owner.AUTONOMY_RECEIPT.exists()


def test_present_empty_receipt_refuses_before_marker_or_config_publication(installed):
    s = installed
    owner.AUTONOMY_RECEIPT.write_bytes(b'')
    owner.AUTONOMY_RECEIPT.chmod(0o444)
    with pytest.raises(ValueError, match='existing disarm receipt is empty'):
        stage(s)
    assert not s.marker.exists()
    assert owner.CONTROL_CONFIG.read_bytes() == s.control
    assert owner.WORKER_CONFIG.read_bytes() == s.worker
    assert owner.AUTONOMY_RECEIPT.exists()
    assert owner.AUTONOMY_RECEIPT.read_bytes() == b''


def test_existing_global_owner_publishes_only_actual_four_field_delta(installed):
    s = installed
    tx = stage(s)
    assert tx.startswith('autonomy-') and not s.marker.exists()
    assert json.loads(owner.CONTROL_CONFIG.read_bytes()) == dict(json.loads(s.control), **s.delta)
    assert owner.WORKER_CONFIG.read_bytes() == s.worker


@pytest.mark.parametrize('gate', ['require_exact_install', 'require_services_already_stopped',
    'require_service_uids_quiescent', 'require_runtime_quiescent'])
def test_failed_host_gate_precedes_marker_and_publication(installed, monkeypatch, gate):
    def fail(*a): raise ValueError('actual gate unavailable')
    monkeypatch.setattr(installed.host, gate, fail)
    with pytest.raises(ValueError): stage(installed)
    assert not installed.marker.exists()
    assert owner.CONTROL_CONFIG.read_bytes() == installed.control


@pytest.mark.parametrize('change', [dict(ceo_submit_armed=True), dict(coo_foreground_only=True),
    dict(coo_autonomy_armed=True), dict(coo_operator_harness_armed=True),
    dict(fabric_bindings_path='/foreign/bindings.json')])
def test_armed_or_existing_foreign_selection_is_never_overwritten(installed, change):
    s = installed
    current = dict(json.loads(s.control), **change)
    replace_fixture(owner.CONTROL_CONFIG, owner.encode_config(current))
    s.control = owner.CONTROL_CONFIG.read_bytes()
    with pytest.raises((ValueError, owner.ArmAdmissionError)): stage(s)
    assert not s.marker.exists() and owner.CONTROL_CONFIG.read_bytes() == s.control


def test_changed_expected_preimage_refuses_before_marker(installed):
    with pytest.raises(ValueError):
        staging.execute_staging(installed.host, SHA, 'f'*64)
    assert not installed.marker.exists()


def test_drift_after_marker_stays_unknown_without_publication(installed, monkeypatch):
    s = installed
    original = s.host.write_candidates
    def drift(tx):
        original(tx)
        s.delta['fabric_bindings_sha256'] = 'b'*64
    monkeypatch.setattr(s.host, 'write_candidates', drift)
    with pytest.raises(owner.TransactionEffectUnknown): stage(s)
    assert s.marker.exists() and owner.CONTROL_CONFIG.read_bytes() == s.control


def test_lost_publication_response_reconciles_target_without_replacing_again(installed, monkeypatch):
    s = installed
    original = s.host.replace_control_config
    calls = []
    def lost(tx):
        calls.append(tx.transaction_id); original(tx); raise OSError('lost response')
    monkeypatch.setattr(s.host, 'replace_control_config', lost)
    with pytest.raises(owner.TransactionEffectUnknown): stage(s)
    assert s.marker.exists() and len(calls) == 1
    tx = s.host._manifest()['transaction_id']
    s.host._release_transaction_owner()
    assert s.host.reconcile_staging(SHA) == tx
    assert not s.marker.exists() and len(calls) == 1


def test_reconciliation_never_retries_unpublished_target(installed, monkeypatch):
    s = installed
    monkeypatch.setattr(s.host, 'write_candidates', lambda tx: (_ for _ in ()).throw(OSError('crash')))
    with pytest.raises(owner.TransactionEffectUnknown): stage(s)
    s.host._release_transaction_owner()
    with pytest.raises(owner.TransactionEffectUnknown): s.host.reconcile_staging(SHA)
    assert s.marker.exists() and owner.CONTROL_CONFIG.read_bytes() == s.control


def test_cli_is_fixed_staging_not_arbitrary_config_or_activation():
    args = owner._parser().parse_args(['finite-control-stage', '--expected-sha', SHA,
        '--expected-control-sha256', 'a'*64])
    assert args.command == 'finite-control-stage'
    with pytest.raises(SystemExit):
        owner._parser().parse_args(['finite-control-stage', '--expected-sha', SHA,
            '--expected-control-sha256', 'a'*64, '--config', '/tmp/arbitrary.json'])


def test_late_foreign_marker_cannot_be_adopted_during_id_allocation(installed, monkeypatch):
    s = installed
    s.marker.mkdir()
    (s.marker/'foreign.txt').write_text('original owner evidence')
    monkeypatch.setattr(s.host, '_claim_transaction_owner', lambda:
        pytest.fail('fresh allocation adopted a foreign global owner'))
    assert s.host.new_transaction_id().startswith('autonomy-')
    assert (s.marker/'foreign.txt').read_text() == 'original owner evidence'
    assert s.host._transaction_owner_fd is None


@pytest.mark.parametrize('edge', ['qualified', 'release-drift', 'principal-drift', 'loaded', 'live-uid'])
def test_real_definition_consumer_requires_selected_installed_generation(monkeypatch, inputs, edge):
    from pathlib import Path
    from ops.executive_os.attended_worker_definition import build_finite_worker_artifacts
    from control_plane import executive_worker_broker
    manifest = b'actual inert manifest bytes'
    inputs.update(worker_id='minimax-finite-01', worker_user='_mastermind_minimax',
        worker_group='_mastermind_minimax', worker_uid=470, worker_gid=470,
        definition_dir=staging.FINITE_DEFINITION_DIR,
        socket_path='/var/run/mastermind-executive/fabric-minimax-finite-01.sock',
        release_manifest_sha256=owner.sha256_bytes(manifest), service_source_sha256=None)
    artifacts = build_finite_worker_artifacts(**inputs)
    host = staging.ProductionFiniteStagingHost()
    host._finite_expected_sha = SHA
    monkeypatch.setattr(Path, 'lstat', lambda self: SimpleNamespace(st_mode=0o40755, st_uid=0))
    monkeypatch.setattr(owner, '_has_acl', lambda p: False)
    def published_file(p, **kw):
        # The reviewed publisher's nonsecret definitions and installed manifest
        # are root:wheel 0444. Binary attestation is a separate protected file.
        assert kw == dict(modes=frozenset({0o444}), uid=0, gid=0)
        return ((b'drift' if edge == 'release-drift' else manifest)
            if p.name == '.executive-release-manifest.json' else artifacts[p.name], None)
    monkeypatch.setattr(owner, '_read_root_file', published_file)
    monkeypatch.setattr(staging.pwd, 'getpwnam', lambda name:
        SimpleNamespace(pw_uid=471 if edge == 'principal-drift' else 470, pw_gid=470))
    monkeypatch.setattr(host, '_loaded_observe_only', lambda label: edge == 'loaded')
    monkeypatch.setattr(executive_worker_broker, '_ps_pids_for_uid', lambda uid:
        (123,) if edge == 'live-uid' else ())
    if edge == 'qualified':
        assert host.read_delta()['fabric_bindings_sha256'] == owner.sha256_bytes(artifacts['bindings.json'])
    else:
        with pytest.raises(ValueError): host.read_delta()


# ---------------------------------------------------------------------------
# gap-3: the staged finite composition refuses a non-bootable or TCP Control
# Room before any marker or write, and the published composition boots.
# ---------------------------------------------------------------------------


def _workspace_composition(control_uid, *, room=None, drop=()):
    """Build the closed workspace + App peer stanza shape used by the
    installed-control boot fixture, optionally dropping any of the three
    workspace keys for the partial-composition refusal cases.
    """

    value = {
        'control_uid': int(control_uid),
        'workspace_acquisition': {
            'schema': 'mastermind.workspace_acquisition_bindings.v1',
            'profiles': {
                'web': {'enabled': False, 'binding': None},
                'mac': {'enabled': False, 'binding': None},
            },
        },
        'workspace_resource_policy': {
            'schema': 'mastermind.workspace_resource_policy/v1',
            'placeholder': True,
        },
        'ceo_ingress_app_peer_uid': int(control_uid) + 17,
        'ceo_ingress_app_armed': True,
        'ceo_ingress_app_macro_root': '/macro/anywhere',
    }
    if room is not None:
        value['workspace_control_room'] = room
    else:
        from tests.executive_installed_control_fixture import unix_stanza
        value['workspace_control_room'] = unix_stanza(control_uid)
    for key in drop:
        value.pop(key, None)
    return value


def _install_workspace(s, **overrides):
    """Re-write CONTROL_CONFIG with the given overlay so the next ``stage``
    sees those keys in ``prior.control``. Updates ``s.control`` and ``s.worker``
    snapshots to keep the marker/config unchanged assertions correct. Removes
    any ``drop`` keys from the existing document first so the partial composition
    cases actually see those keys missing.
    """

    value = json.loads(s.control)
    for key in overrides.get('drop', ()):
        value.pop(key, None)
    overlay = _workspace_composition(os.geteuid(), **overrides)
    value.update(overlay)
    replace_fixture(owner.CONTROL_CONFIG, owner.encode_config(value))
    s.control = owner.CONTROL_CONFIG.read_bytes()
    return overlay


def test_staging_refuses_legacy_tcp_control_room_before_marker(installed):
    s = installed
    added = _install_workspace(s, room={'port': 8787})
    worker_before = s.worker

    with pytest.raises(ValueError) as excinfo:
        stage(s)
    message = str(excinfo.value)
    assert 'staged Control composition cannot boot' in message
    assert 'legacy TCP port stanza refused' in message
    assert not s.marker.exists()
    assert owner.CONTROL_CONFIG.read_bytes() == s.control
    assert owner.WORKER_CONFIG.read_bytes() == worker_before
    # The candidate must not have merged any finite delta into the on-disk
    # control before the refusal.
    assert 'fabric_bindings_path' not in json.loads(s.control)
    assert 'workspace_control_room' in json.loads(s.control)
    assert json.loads(s.control)['workspace_control_room'] == added['workspace_control_room']


@pytest.mark.parametrize('drop', [
    ('workspace_acquisition',),
    ('workspace_resource_policy',),
    ('workspace_control_room',),
    ('ceo_ingress_app_armed',),
])
def test_staging_refuses_partial_workspace_composition_before_marker(installed, drop):
    s = installed
    added = _install_workspace(s, drop=drop)
    worker_before = s.worker

    with pytest.raises(ValueError) as excinfo:
        stage(s)
    message = str(excinfo.value)
    assert 'staged Control composition cannot boot' in message
    assert 'workspace acquisition requires' in message
    assert not s.marker.exists()
    assert owner.CONTROL_CONFIG.read_bytes() == s.control
    assert owner.WORKER_CONFIG.read_bytes() == worker_before
    on_disk = json.loads(s.control)
    for key, value in added.items():
        if key in drop:
            assert key not in on_disk, f'{key} should have been dropped'
        else:
            assert on_disk.get(key) == value, f'{key} should have been preserved'


def _malformed_rooms(uid):
    from scripts import executive_os_phase1c as cli
    return [
        ('transport_tcp', {'transport': 'tcp',
            'socket_path': cli._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET,
            'launchd_socket_name': cli._WORKSPACE_CONTROL_ROOM_SOCKET_NAME,
            'allowed_peer_uids': [uid]}),
        ('wrong_socket_path', {'transport': 'unix',
            'socket_path': '/tmp/foreign-room.sock',
            'launchd_socket_name': cli._WORKSPACE_CONTROL_ROOM_SOCKET_NAME,
            'allowed_peer_uids': [uid]}),
        ('stranger_peer_uid', {'transport': 'unix',
            'socket_path': cli._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET,
            'launchd_socket_name': cli._WORKSPACE_CONTROL_ROOM_SOCKET_NAME,
            'allowed_peer_uids': [uid + 7]}),
        ('extra_port_key', {'transport': 'unix',
            'socket_path': cli._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET,
            'launchd_socket_name': cli._WORKSPACE_CONTROL_ROOM_SOCKET_NAME,
            'allowed_peer_uids': [uid],
            'port': 8787}),
    ]


@pytest.mark.parametrize('label,room', _malformed_rooms(os.geteuid()))
def test_staging_refuses_malformed_unix_room_before_marker(installed, label, room):
    s = installed
    worker_before = s.worker
    _install_workspace(s, room=room)

    with pytest.raises(ValueError) as excinfo:
        stage(s)
    message = str(excinfo.value)
    assert ('staged Control composition cannot boot: '
        'workspace Control Room topology refused') in message, (
        f'{label}: {message}')
    assert not s.marker.exists()
    assert owner.CONTROL_CONFIG.read_bytes() == s.control
    assert owner.WORKER_CONFIG.read_bytes() == worker_before


def test_staging_publishes_unix_room_composition_with_only_the_finite_delta(installed, monkeypatch):
    from scripts import executive_os_phase1c as cli
    monkeypatch.setattr(cli, '_CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET',
        cli._CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET, raising=False)

    s = installed
    added = _install_workspace(s)
    prior_bytes = s.control
    prior = json.loads(prior_bytes)

    tx = stage(s)
    assert tx.startswith('autonomy-')
    assert not s.marker.exists()

    published = json.loads(owner.CONTROL_CONFIG.read_bytes())
    expected = dict(prior, **s.delta)
    assert published == expected
    for key in ('workspace_acquisition', 'workspace_resource_policy', 'workspace_control_room'):
        assert published[key] == added[key]
        assert published[key] == prior[key]
    assert owner.WORKER_CONFIG.read_bytes() == s.worker


