"""Retirement uses the actual global transaction on inert temporary files."""
import copy
import json
import os
from types import SimpleNamespace

import pytest

from control_plane.fabric_attended_routing import (
    RETIRED_FINITE_FIELD, installed_control_placements, retired_finite_selection,
)
from ops.executive_os import autonomy_control as owner
from ops.executive_os import attended_control_retirement as retirement
from ops.executive_os import attended_control_staging as staging
from tests.test_attended_control_staging import installed, replace_fixture, retained_disarm
from tests.test_executive_autonomy_control import SHA
from tests.test_attended_worker_definition import inputs


@pytest.fixture
def selected(installed, monkeypatch):
    original = installed
    host = retirement.ProductionFiniteRetirementHost()
    for name in ('effective_uid', 'require_exact_install', 'require_services_already_stopped',
                 'require_service_uids_quiescent', 'require_runtime_quiescent', 'read_delta',
                 '_read_validated_control_candidate'):
        monkeypatch.setattr(host, name, getattr(original.host, name))
    monkeypatch.setattr(host, 'validate_acceptance', lambda sha: 'e'*64)
    monkeypatch.setattr(host, 'quiesce_control_uid_for_arm', lambda: ())
    control = dict(json.loads(original.control), **copy.deepcopy(original.delta))
    replace_fixture(owner.CONTROL_CONFIG, owner.encode_config(control))
    fixture = SimpleNamespace(host=host, marker=original.marker, delta=original.delta,
        control=owner.CONTROL_CONFIG.read_bytes(), worker=original.worker)
    yield fixture
    if host._transaction_owner_fd is not None:
        host._release_transaction_owner()


def retire(fixture):
    return retirement.execute_retirement(fixture.host, SHA, owner.sha256_bytes(fixture.control))


def test_retirement_preserves_raw_predecessors_and_unrelated_fields(selected):
    fixture = selected
    old_receipt = retained_disarm(fixture)
    old_receipt_raw = owner.AUTONOMY_RECEIPT.read_bytes()
    txid = retire(fixture)
    current = json.loads(owner.CONTROL_CONFIG.read_bytes())
    old = json.loads(fixture.control)
    assert {key: value for key, value in current.items() if key != RETIRED_FINITE_FIELD} == {
        key: value for key, value in old.items() if key not in staging.NATIVE_FIELDS}
    assert owner.WORKER_CONFIG.read_bytes() == fixture.worker
    assert current[RETIRED_FINITE_FIELD]['transaction_id'] == txid
    assert current[RETIRED_FINITE_FIELD]['selection'] == fixture.delta
    raw, document, tx = retirement._read_predecessor()
    assert document['prior_control'].encode() == fixture.control
    assert document['prior_worker'].encode() == fixture.worker
    assert document['prior_disarmed_receipt'].encode() == old_receipt_raw
    assert tx.transaction_id == txid
    assert retirement._path().stat().st_mode & 0o777 == 0o400
    assert current[RETIRED_FINITE_FIELD]['predecessor_sha256'] == owner.sha256_bytes(raw)
    receipt = json.loads(owner.AUTONOMY_RECEIPT.read_bytes())
    assert {key: value for key, value in receipt.items() if key not in {
        'control_config_sha256', 'prior_control_config_sha256', 'transaction_id'}} == {
        key: value for key, value in old_receipt.items() if key not in {
        'control_config_sha256', 'prior_control_config_sha256', 'transaction_id'}}
    assert not fixture.marker.exists()


def test_inactive_selection_is_not_a_placement_and_allows_separate_paid_owner(selected):
    retire(selected)
    control = json.loads(owner.CONTROL_CONFIG.read_bytes())
    from scripts.executive_os_phase1c import ServiceError, _staged_fabric_binding_source
    from ops.executive_os import paid_control_staging
    assert _staged_fabric_binding_source(control) is None
    assert installed_control_placements(dict(control, coo_autonomy_armed=True,
                                             coo_foreground_only=True)) == ()
    current = selected.host.checked_configs(SHA)
    paid_delta = {'canonical_paid_fabric': {
        'bindings_path': str(paid_control_staging.DEFINITION/'bindings.json'),
        'bindings_sha256': 'f'*64}}
    paid = paid_control_staging.candidate(current, paid_delta)
    assert paid.control[RETIRED_FINITE_FIELD] == control[RETIRED_FINITE_FIELD]
    assert retirement.retained_selection(paid.control) == selected.delta
    with pytest.raises(ServiceError):
        staging.candidate(current, selected.delta)


def test_native_stanza_is_retained_only_when_joined_to_the_same_definition(selected):
    selected.delta['native_capacity_v2'] = {'macro_release': 'd'*40, 'producer_sha256': 'e'*64}
    control = dict(json.loads(selected.control), native_capacity_v2=copy.deepcopy(
        selected.delta['native_capacity_v2']))
    replace_fixture(owner.CONTROL_CONFIG, owner.encode_config(control))
    selected.control = owner.CONTROL_CONFIG.read_bytes()
    retire(selected)
    current = json.loads(owner.CONTROL_CONFIG.read_bytes())
    assert 'native_capacity_v2' not in current
    assert retirement.retained_selection(current)['native_capacity_v2'] == selected.delta['native_capacity_v2']


def test_foreign_native_stanza_refuses_before_marker(selected):
    control = dict(json.loads(selected.control), native_capacity_v2={
        'macro_release': 'd'*40, 'producer_sha256': 'e'*64})
    replace_fixture(owner.CONTROL_CONFIG, owner.encode_config(control))
    selected.control = owner.CONTROL_CONFIG.read_bytes()
    with pytest.raises(ValueError):
        retire(selected)
    assert not selected.marker.exists() and not retirement._path().exists()


@pytest.mark.parametrize('gate', ['require_exact_install', 'require_services_already_stopped',
    'validate_acceptance', 'require_runtime_quiescent'])
def test_failed_lifecycle_gate_cannot_publish(selected, monkeypatch, gate):
    def refuse(*args):
        raise ValueError('original source gate refused')
    monkeypatch.setattr(selected.host, gate, refuse)
    with pytest.raises(ValueError):
        retire(selected)
    assert owner.CONTROL_CONFIG.read_bytes() == selected.control
    assert not selected.marker.exists() and not retirement._path().exists()


@pytest.mark.parametrize('fault', ['cleanup_refused', 'strict_gate_refused'])
def test_incomplete_cleanup_is_retained_and_never_permits_target_write(selected, monkeypatch, fault):
    calls = []
    def cleanup():
        retained = json.loads(selected.host._quiescence_path().read_bytes())
        assert retained['observations'][-1]['status'] == 'STARTED'
        assert retained['observations'][-1]['signalled_pids'] is None
        calls.append('fixed-control-uid')
        if fault == 'cleanup_refused':
            raise owner.ArmAdmissionError('service_uid_process_live')
        return (51001,)
    def strict():
        raise owner.ArmAdmissionError('service_uid_process_live')
    monkeypatch.setattr(selected.host, 'quiesce_control_uid_for_arm', cleanup)
    if fault == 'strict_gate_refused':
        monkeypatch.setattr(selected.host, 'require_service_uids_quiescent', strict)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    assert calls == ['fixed-control-uid']
    assert owner.CONTROL_CONFIG.read_bytes() == selected.control
    assert not retirement._path().exists() and selected.marker.exists()
    log = json.loads(selected.host._quiescence_path().read_bytes())
    assert log['observations'][0]['status'] == 'UNKNOWN'
    assert log['observations'][0]['refusal_code'] == 'service_uid_process_live'
    assert log['observations'][0]['signalled_pids'] == (None if fault == 'cleanup_refused' else [51001])


@pytest.mark.parametrize('fault', ['other_operation', 'other_id', 'unknown_phase', 'owner_missing', 'archive_drift'])
def test_unrelated_or_unknown_transaction_cannot_authorize_cleanup(selected, monkeypatch, fault):
    original = selected.host._create_marker
    def claim(tx, **kwargs):
        original(tx, **kwargs)
        if fault == 'owner_missing':
            selected.host._active_transaction = None
        elif fault == 'archive_drift':
            path = selected.marker/'prior-control.json'
            path.chmod(0o600); path.write_bytes(b'{}\n'); path.chmod(0o400)
        else:
            manifest = selected.host._manifest()
            if fault == 'other_operation':
                manifest['operation'] = staging.OPERATION
            elif fault == 'other_id':
                manifest['transaction_id'] = 'autonomy-'+'f'*12
            else:
                manifest['phase'] = 'UNKNOWN'
            owner._atomic_file(selected.host._manifest_path(), owner._encoded_json(manifest),
                               mode=0o400, uid=0, gid=0, replace=True)
    def forbidden():
        pytest.fail('unknown original transaction reached the quiescer')
    monkeypatch.setattr(selected.host, '_create_marker', claim)
    monkeypatch.setattr(selected.host, 'quiesce_control_uid_for_arm', forbidden)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    assert owner.CONTROL_CONFIG.read_bytes() == selected.control
    assert selected.marker.exists() and not retirement._path().exists()


def test_validator_spawn_is_cleaned_only_after_full_rechecks_then_strict_gate(selected, monkeypatch):
    events = []
    live = []
    validate = selected.host.validate_candidates
    def candidate_validation(tx):
        validate(tx)
        live.append(51001)
        events.append('validator-created-ambient')
    def acceptance(sha):
        events.append('acceptance')
        return 'e'*64
    def cleanup():
        events.append('cleanup')
        found = tuple(live)
        live.clear()
        return found
    def strict():
        events.append('strict')
        if live:
            raise owner.ArmAdmissionError('service_uid_process_live')
    monkeypatch.setattr(selected.host, 'validate_candidates', candidate_validation)
    monkeypatch.setattr(selected.host, 'validate_acceptance', acceptance)
    monkeypatch.setattr(selected.host, 'quiesce_control_uid_for_arm', cleanup)
    monkeypatch.setattr(selected.host, 'require_service_uids_quiescent', strict)
    retire(selected)
    spawned = events.index('validator-created-ambient')
    assert events[spawned + 1:spawned + 4] == ['acceptance', 'cleanup', 'strict']
    log = json.loads(selected.host._quiescence_path().read_bytes())
    assert all(row['status'] == 'SUCCEEDED' for row in log['observations'])
    assert [row['signalled_pids'] for row in log['observations']] == [[], [51001], [], []]


def test_unknown_cleanup_after_control_write_cannot_be_retried_by_reconcile(selected, monkeypatch):
    calls = []
    def cleanup():
        calls.append(len(calls) + 1)
        if len(calls) == 3:
            raise owner.ArmAdmissionError('service_uid_process_unknown')
        return ()
    monkeypatch.setattr(selected.host, 'quiesce_control_uid_for_arm', cleanup)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    assert len(calls) == 3
    assert owner.CONTROL_CONFIG.read_bytes() != selected.control
    selected.host._release_transaction_owner()
    with pytest.raises(owner.TransactionEffectUnknown):
        selected.host.reconcile_retirement(SHA)
    assert len(calls) == 3 and selected.marker.exists()
    log = json.loads(selected.host._quiescence_path().read_bytes())
    assert log['observations'][-1]['status'] == 'UNKNOWN'


@pytest.mark.parametrize('field', ['coo_autonomy_armed', 'coo_operator_harness_armed',
    'coo_foreground_only', 'ceo_submit_armed', 'fabric_bridge_armed'])
def test_any_armed_selection_refuses_before_effect(selected, field):
    value = dict(json.loads(selected.control), **{field: True})
    replace_fixture(owner.CONTROL_CONFIG, owner.encode_config(value))
    selected.control = owner.CONTROL_CONFIG.read_bytes()
    with pytest.raises((ValueError, owner.ArmAdmissionError)):
        retire(selected)
    assert not selected.marker.exists() and not retirement._path().exists()


def test_exact_control_preimage_and_original_archive_are_required(selected):
    with pytest.raises(ValueError, match='preimage'):
        retirement.execute_retirement(selected.host, SHA, 'f'*64)
    retirement._path().write_bytes(b'original operation evidence')
    with pytest.raises(ValueError, match='already exists'):
        retire(selected)
    assert retirement._path().read_bytes() == b'original operation evidence'
    assert not selected.marker.exists()


def test_predecessor_budget_refuses_before_original_marker(selected, monkeypatch):
    prior, _ = selected.host._retirement_configs(SHA)
    monkeypatch.setattr(owner, '_MAX_JSON_BYTES', 32)
    with pytest.raises(ValueError, match='reader budget'):
        retirement.predecessor_bytes(prior, transaction_id='autonomy-'+'a'*12,
                                     expected_sha=SHA, receipt=b'')
    assert not selected.marker.exists() and not retirement._path().exists()


def test_missing_pair_never_replays_control_replacement(selected, monkeypatch):
    retained_disarm(selected)
    replace = selected.host.replace_control_config
    writes = []
    def lose(tx):
        writes.append(tx.transaction_id)
        replace(tx)
        raise OSError('lost original Control response')
    monkeypatch.setattr(selected.host, 'replace_control_config', lose)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    selected.host._release_transaction_owner()
    with pytest.raises(owner.TransactionEffectUnknown):
        selected.host.reconcile_retirement(SHA)
    assert len(writes) == 1 and selected.marker.exists()
    assert retirement._path().exists()


def test_lost_receipt_response_reconciles_exact_original_postimages(selected, monkeypatch):
    retained_disarm(selected)
    original = owner._atomic_file
    writes = []
    def lose(path, raw, **kwargs):
        original(path, raw, **kwargs)
        if path == owner.AUTONOMY_RECEIPT:
            writes.append(raw)
            raise OSError('lost original disarm receipt response')
    monkeypatch.setattr(owner, '_atomic_file', lose)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    txid = selected.host._manifest()['transaction_id']
    selected.host._release_transaction_owner()
    assert selected.host.reconcile_retirement(SHA) == txid
    assert len(writes) == 1 and not selected.marker.exists()
    assert retirement._path().exists()


def test_unpublished_control_is_never_written_by_reconciliation(selected, monkeypatch):
    def refuse(tx):
        raise OSError('candidate validation interrupted')
    monkeypatch.setattr(selected.host, 'validate_candidates', refuse)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    selected.host._release_transaction_owner()
    with pytest.raises(owner.TransactionEffectUnknown):
        selected.host.reconcile_retirement(SHA)
    assert selected.marker.exists()
    assert owner.CONTROL_CONFIG.read_bytes() == selected.control
    assert retirement._path().exists()


def test_definition_drift_after_marker_preserves_original_evidence(selected, monkeypatch):
    original = selected.host.validate_candidates
    def drift(tx):
        original(tx)
        selected.delta['fabric_bindings_sha256'] = 'b'*64
    monkeypatch.setattr(selected.host, 'validate_candidates', drift)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    assert owner.CONTROL_CONFIG.read_bytes() == selected.control
    assert selected.marker.exists()
    assert retirement._read_predecessor()[2].prior_configs.control_bytes == selected.control


@pytest.mark.parametrize('fault', ['hash', 'missing', 'mode', 'hardlink', 'acl', 'symlink'])
def test_retained_membership_never_accepts_untrusted_predecessor(selected, monkeypatch, fault):
    retire(selected)
    control = json.loads(owner.CONTROL_CONFIG.read_bytes())
    archive = retirement._path()
    if fault == 'hash':
        control[RETIRED_FINITE_FIELD]['predecessor_sha256'] = 'f'*64
    elif fault == 'missing':
        archive.unlink()
    elif fault == 'mode':
        archive.chmod(0o444)
    elif fault == 'hardlink':
        os.link(archive, archive.with_suffix('.link'))
    elif fault == 'acl':
        monkeypatch.setattr(owner, '_has_acl', lambda path: path == archive)
    elif fault == 'symlink':
        original = archive.with_suffix('.original')
        archive.rename(original)
        archive.symlink_to(original)
    with pytest.raises(Exception):
        retirement.retained_selection(control)


@pytest.mark.parametrize('fault', ['extra', 'active', 'path', 'native', 'tx', 'release'])
def test_closed_inactive_projection_never_grants_new_selection(selected, fault):
    retire(selected)
    control = json.loads(owner.CONTROL_CONFIG.read_bytes())
    value = control[RETIRED_FINITE_FIELD]
    if fault == 'extra':
        value['enabled'] = True
    elif fault == 'active':
        control['fabric_attended_probe'] = selected.delta['fabric_attended_probe']
    elif fault == 'path':
        value['selection']['fabric_bindings_path'] = '/foreign/bindings.json'
    elif fault == 'native':
        value['selection']['native_capacity_v2'] = {'macro_release': 'x', 'producer_sha256': 'e'*64}
    elif fault == 'tx':
        value['transaction_id'] = 'different-owner'
    elif fault == 'release':
        value['release_sha'] = 'unknown'
    with pytest.raises(ValueError):
        retired_finite_selection(control)


def test_cli_offers_no_path_identity_or_reactivation_override():
    args = owner._parser().parse_args(['finite-control-retire', '--expected-sha', SHA,
                                       '--expected-control-sha256', 'a'*64])
    assert args.command == 'finite-control-retire'
    for extra in (['--config', '/tmp/other.json'], ['--worker-uid', '501'], ['--arm']):
        with pytest.raises(SystemExit):
            owner._parser().parse_args(['finite-control-retire', '--expected-sha', SHA,
                                       '--expected-control-sha256', 'a'*64, *extra])


def test_normal_owner_dispatches_closed_retirement_command(selected, capsys):
    rc = owner.main(['finite-control-retire', '--expected-sha', SHA,
        '--expected-control-sha256', owner.sha256_bytes(selected.control)], host=selected.host)
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result['code'] == 'finite_control_retired'
    assert result['state'] == 'UNARMED' and result['status'] == 'FINITE_CONTROL_RETIRED'
    assert result['transaction_id'] == json.loads(owner.CONTROL_CONFIG.read_bytes())[
        RETIRED_FINITE_FIELD]['transaction_id']
    assert result['replayed'] is False and not selected.marker.exists()


def test_retirement_does_not_create_a_disarm_receipt_when_original_was_absent(selected):
    retire(selected)
    assert not owner.AUTONOMY_RECEIPT.exists()


def test_lost_final_reply_reads_completed_original_without_any_new_write(selected, monkeypatch):
    retained_disarm(selected)
    txid = retire(selected)
    reads = []
    def projection(tx):
        reads.append(tx.transaction_id)
    monkeypatch.setattr(selected.host, 'verify_completed_observation', projection)
    def no_effect(*args, **kwargs):
        pytest.fail('completed original reconciliation attempted a write')
    monkeypatch.setattr(owner, '_atomic_file', no_effect)
    monkeypatch.setattr(selected.host, '_create_marker', no_effect)
    monkeypatch.setattr(selected.host, 'replace_control_config', no_effect)
    assert selected.host.reconcile_retirement(SHA) == txid
    assert reads == [txid] and not selected.marker.exists()


def test_lost_final_reply_with_missing_observation_stays_unknown(selected, monkeypatch):
    retire(selected)
    def missing(tx):
        raise owner.TransactionEffectUnknown()
    monkeypatch.setattr(selected.host, 'verify_completed_observation', missing)
    with pytest.raises(owner.TransactionEffectUnknown):
        selected.host.reconcile_retirement(SHA)
    assert not selected.marker.exists() and retirement._path().exists()


def test_acceptance_retains_exact_group_evidence_without_active_selector(selected, monkeypatch):
    from tests.test_attended_worker_group_acceptance import target
    from control_plane import executive_fabric_composition, fabric_attended_canary
    import grp
    subject = target()
    selected_path = selected.delta['fabric_attended_probe']['worker_config_path']
    physical = SimpleNamespace(provider='minimax', host_ref='actual-retained-host',
        worker_id='minimax-finite-01', worker_source_config_digest='b'*64, digest='c'*64)
    class Source:
        bindings = (physical,)
        expected_sha256 = selected.delta['fabric_bindings_sha256']
        def __call__(self, host_ref, worker_id):
            assert (host_ref, worker_id) == (physical.host_ref, physical.worker_id)
            return physical
    def read_binding(path, digest):
        assert (path, digest) == (selected.delta['fabric_bindings_path'], Source.expected_sha256)
        return Source()
    def read_definition(path, bound):
        assert str(path) == selected_path and bound is physical
        return dict(worker_uid=470, worker_gid=470, worker_user='_mastermind_minimax',
            control_uid=450, control_gid=450, allowed_supplementary_gids=[],
            provider_home='/private/var/db/mastermind-executive/workers/minimax-finite-01/provider-home')
    monkeypatch.setattr(executive_fabric_composition.FabricBindingSource, 'from_path', read_binding)
    monkeypatch.setattr(fabric_attended_canary, 'definition', read_definition)
    monkeypatch.setattr(grp, 'getgrgid', lambda gid: SimpleNamespace(gr_name='_mastermind_minimax'))
    args = dict(control_uid=450, control_gid=450, primary_worker_uid=451,
                primary_worker_gid=451, ops_gid=453)
    before = subject._attended_worker_membership(json.loads(selected.control), **args)
    retire(selected)
    current = json.loads(owner.CONTROL_CONFIG.read_bytes())
    assert subject._attended_worker_membership(current, **args) == before
    assert installed_control_placements(current) == ()
    retirement._path().chmod(0o444)
    with pytest.raises(subject.AcceptanceError, match='predecessor'):
        subject._attended_worker_membership(current, **args)


@pytest.mark.parametrize('edge', ['historical_source', 'principal_drift', 'loaded',
    'live_uid', 'definition_drift', 'directory_custody'])
def test_actual_definition_consumer_retires_only_the_preserved_finite_owner(monkeypatch, inputs, edge):
    from pathlib import Path
    from ops.executive_os.attended_worker_definition import build_finite_worker_artifacts
    from control_plane import executive_worker_broker
    old_manifest = b'the retained historical finite service manifest'
    inputs.update(worker_id='minimax-finite-01', worker_user='_mastermind_minimax',
        worker_group='_mastermind_minimax', worker_uid=470, worker_gid=470,
        definition_dir=staging.FINITE_DEFINITION_DIR,
        socket_path='/var/run/mastermind-executive/fabric-minimax-finite-01.sock',
        release_manifest_sha256=owner.sha256_bytes(old_manifest), service_source_sha256=None)
    artifacts = build_finite_worker_artifacts(**inputs)
    host = retirement.ProductionFiniteRetirementHost()
    monkeypatch.setattr(Path, 'lstat', lambda self: SimpleNamespace(
        st_mode=0o40777 if edge == 'directory_custody' else 0o40755, st_uid=0))
    monkeypatch.setattr(owner, '_has_acl', lambda path: False)
    reads = []
    def protected(path, **kwargs):
        assert kwargs == dict(modes=frozenset({0o444}), uid=0, gid=0)
        assert str(path.parent) == staging.FINITE_DEFINITION_DIR
        reads.append(path.name)
        raw = artifacts[path.name]
        if edge == 'definition_drift' and path.name == 'worker.json':
            raw = raw + b' '
        return raw, None
    monkeypatch.setattr(owner, '_read_root_file', protected)
    monkeypatch.setattr(retirement.pwd, 'getpwnam', lambda name: SimpleNamespace(
        pw_uid=471 if edge == 'principal_drift' else 470, pw_gid=470))
    monkeypatch.setattr(host, '_loaded_observe_only', lambda label: edge == 'loaded')
    monkeypatch.setattr(executive_worker_broker, '_ps_pids_for_uid',
                        lambda uid: (51001,) if edge == 'live_uid' else ())
    if edge == 'historical_source':
        delta = host.read_delta()
        assert delta['fabric_bindings_sha256'] == owner.sha256_bytes(artifacts['bindings.json'])
        assert reads == ['worker.json', 'bindings.json']
    else:
        with pytest.raises(ValueError):
            host.read_delta()


@pytest.mark.parametrize('artifact', ['predecessor', 'quiescence'])
def test_first_publication_preserves_late_occupant(selected, monkeypatch, artifact):
    from pathlib import Path
    from ops.executive_os import capacity_host_artifacts
    target = retirement._path() if artifact == 'predecessor' else selected.host._quiescence_path()
    raw = b'late original owner evidence\n'
    occupied = []
    cleanups = []
    monkeypatch.setattr(selected.host, 'quiesce_control_uid_for_arm',
                        lambda: cleanups.append('cleanup') or ())
    replace = os.replace
    exclusive = capacity_host_artifacts._rename_exclusive
    def late():
        assert not target.exists()
        target.write_bytes(raw)
        target.chmod(0o400)
        occupied.append((target.stat().st_dev, target.stat().st_ino))
    def replace_late(source, destination, *args, **kwargs):
        if Path(destination) == target and not occupied:
            late()
        return replace(source, destination, *args, **kwargs)
    def exclusive_late(source_fd, source, destination_fd, destination):
        if destination == target.name and not occupied:
            late()
        return exclusive(source_fd, source, destination_fd, destination)
    monkeypatch.setattr(os, 'replace', replace_late)
    monkeypatch.setattr(capacity_host_artifacts, '_rename_exclusive', exclusive_late)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    assert len(occupied) == 1
    assert target.read_bytes() == raw
    assert (target.stat().st_dev, target.stat().st_ino) == occupied[0]
    assert selected.host._manifest()['phase'] == 'LOCKED'
    assert len(cleanups) == (1 if artifact == 'predecessor' else 0)
    assert owner.CONTROL_CONFIG.read_bytes() == selected.control
    assert selected.marker.exists()
    assert not list(owner.CONFIG_ROOT.glob(f'.{target.name}.*.stage'))


@pytest.mark.parametrize('artifact', ['predecessor', 'quiescence'])
def test_lost_first_publication_ack_retains_original_evidence(selected, monkeypatch, artifact):
    from pathlib import Path
    from ops.executive_os import capacity_host_artifacts
    target = retirement._path() if artifact == 'predecessor' else selected.host._quiescence_path()
    calls = []
    cleanups = []
    monkeypatch.setattr(selected.host, 'quiesce_control_uid_for_arm',
                        lambda: cleanups.append('cleanup') or ())
    replace = os.replace
    exclusive = capacity_host_artifacts._rename_exclusive
    def lost():
        calls.append((target.read_bytes(), target.stat().st_dev, target.stat().st_ino))
        raise OSError('lost first retirement publication response')
    def replace_lost(source, destination, *args, **kwargs):
        result = replace(source, destination, *args, **kwargs)
        if Path(destination) == target and not calls:
            lost()
        return result
    def exclusive_lost(source_fd, source, destination_fd, destination):
        result = exclusive(source_fd, source, destination_fd, destination)
        if destination == target.name and not calls:
            lost()
        return result
    monkeypatch.setattr(os, 'replace', replace_lost)
    monkeypatch.setattr(capacity_host_artifacts, '_rename_exclusive', exclusive_lost)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    assert len(calls) == 1 and selected.host._manifest()['phase'] == 'LOCKED'
    assert len(cleanups) == (1 if artifact == 'predecessor' else 0)
    assert owner.CONTROL_CONFIG.read_bytes() == selected.control
    selected.host._release_transaction_owner()
    with pytest.raises(owner.TransactionEffectUnknown):
        selected.host.reconcile_retirement(SHA)
    assert (target.read_bytes(), target.stat().st_dev, target.stat().st_ino) == calls[0]
    assert len(calls) == 1 and len(cleanups) == (1 if artifact == 'predecessor' else 0)
    assert selected.marker.exists()


@pytest.mark.parametrize('artifact', ['predecessor', 'quiescence'])
def test_phase_drift_during_staging_cannot_publish_first_record(selected, monkeypatch, artifact):
    target = retirement._path() if artifact == 'predecessor' else selected.host._quiescence_path()
    fsync = os.fsync
    changed = []
    cleanups = []
    monkeypatch.setattr(selected.host, 'quiesce_control_uid_for_arm',
                        lambda: cleanups.append('cleanup') or ())
    def drift(descriptor):
        result = fsync(descriptor)
        if not changed:
            info = os.fstat(descriptor)
            for path in owner.CONFIG_ROOT.iterdir():
                if path.name.startswith(f'.{target.name}.'):
                    named = path.lstat()
                    if (named.st_dev, named.st_ino) == (info.st_dev, info.st_ino):
                        changed.append(path.name)
                        manifest = selected.host._manifest()
                        assert manifest['phase'] == 'LOCKED'
                        manifest['phase'] = 'CANDIDATES_WRITTEN'
                        owner._atomic_file(selected.host._manifest_path(),
                            owner._encoded_json(manifest), mode=0o400, uid=0, gid=0, replace=True)
                        break
        return result
    monkeypatch.setattr(os, 'fsync', drift)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    assert len(changed) == 1 and not target.exists()
    assert selected.host._manifest()['phase'] == 'CANDIDATES_WRITTEN'
    assert len(cleanups) == (1 if artifact == 'predecessor' else 0)
    assert owner.CONTROL_CONFIG.read_bytes() == selected.control
    assert selected.marker.exists()


def test_missing_later_journal_is_not_recreated_by_reconcile(selected, monkeypatch):
    retained_disarm(selected)
    cleanups = []
    monkeypatch.setattr(selected.host, 'quiesce_control_uid_for_arm',
                        lambda: cleanups.append('cleanup') or ())
    def retain_marker(tx):
        raise owner.TransactionEffectUnknown()
    monkeypatch.setattr(selected.host, 'complete_transaction', retain_marker)
    with pytest.raises(owner.TransactionEffectUnknown):
        retire(selected)
    assert selected.host._manifest()['phase'] == 'FINITE_RETIRE_VERIFIED'
    assert len(cleanups) == 4
    control = owner.CONTROL_CONFIG.read_bytes()
    receipt = owner.AUTONOMY_RECEIPT.read_bytes()
    journal = selected.host._quiescence_path()
    journal.unlink()
    selected.host._release_transaction_owner()
    with pytest.raises(owner.TransactionEffectUnknown):
        selected.host.reconcile_retirement(SHA)
    assert not journal.exists() and len(cleanups) == 4
    assert owner.CONTROL_CONFIG.read_bytes() == control
    assert owner.AUTONOMY_RECEIPT.read_bytes() == receipt
    assert selected.marker.exists()
