"""Finite config staging uses the real global transaction, without host effects."""
import json
from types import SimpleNamespace

import pytest

from ops.executive_os import autonomy_control as owner
from ops.executive_os import attended_control_staging as staging
from tests.test_executive_autonomy_control import SHA, _inprocess_marker_host
from tests.test_attended_worker_definition import inputs


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
    monkeypatch.setattr(owner, '_read_root_file', lambda p, **kw:
        ((b'drift' if edge == 'release-drift' else manifest)
         if p.name == '.executive-release-manifest.json' else artifacts[p.name], None))
    monkeypatch.setattr(staging.pwd, 'getpwnam', lambda name:
        SimpleNamespace(pw_uid=471 if edge == 'principal-drift' else 470, pw_gid=470))
    monkeypatch.setattr(host, '_loaded_observe_only', lambda label: edge == 'loaded')
    monkeypatch.setattr(executive_worker_broker, '_ps_pids_for_uid', lambda uid:
        (123,) if edge == 'live-uid' else ())
    if edge == 'qualified':
        assert host.read_delta()['fabric_bindings_sha256'] == owner.sha256_bytes(artifacts['bindings.json'])
    else:
        with pytest.raises(ValueError): host.read_delta()
