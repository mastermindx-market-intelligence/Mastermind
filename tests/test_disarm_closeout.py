"""Original-journal recovery in disposable storage; no installed host calls."""
import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from ops.executive_os import autonomy_control as owner
from ops.executive_os import control_observation as publisher
from ops.executive_os import disarm_closeout as recovery
from tests.test_executive_autonomy_control import (
    _inprocess_marker_host, _harness_configs, NOW, SHA,
)


@pytest.fixture
def incident(monkeypatch, tmp_path):
    real_publish = publisher._publish
    real_publish_for_transaction = publisher.publish_for_transaction
    root, marker = _inprocess_marker_host(monkeypatch, tmp_path)
    monkeypatch.setattr(publisher, 'publish_for_transaction', real_publish_for_transaction)
    creator = owner.ProductionTransactionHost()
    prior = creator.begin_disarm(SHA, recovery.ORIGINAL_TRANSACTION)
    tx = owner.TransactionContext(recovery.ORIGINAL_TRANSACTION, SHA, prior,
                                 owner.derive_candidate_configs(prior, armed=False), None)
    creator.write_candidates(tx)
    creator.replace_worker_config(tx)
    creator.replace_control_config(tx)
    creator.write_autonomy_receipt(tx, owner.build_transaction_receipt(tx, state='DISARMED', now=NOW))
    creator._release_transaction_owner()
    monkeypatch.setattr(recovery, 'ORIGINAL_SHA', SHA)
    monkeypatch.setattr(recovery, 'ORIGINAL_MANIFEST', hashlib.sha256((marker/'transaction.json').read_bytes()).hexdigest())
    monkeypatch.setattr(recovery, 'ORIGINAL_RECEIPT', hashlib.sha256(owner.AUTONOMY_RECEIPT.read_bytes()).hexdigest())
    monkeypatch.setattr(recovery, 'ORIGINAL_OBSERVATION', hashlib.sha256(b'original stale observation').hexdigest())
    monkeypatch.setattr(recovery, 'ORIGINAL_FILE_IDENTITIES', {
        relative: recovery._identity_digest(root/relative)
        for relative in recovery.ORIGINAL_FILE_IDENTITIES})
    monkeypatch.setattr(recovery, 'ORIGINAL_MANIFEST_IDENTITY',
                       recovery._identity_digest(marker/'transaction.json'))
    info = marker.lstat()
    monkeypatch.setattr(recovery, 'ORIGINAL_DIRECTORY', (info.st_dev, info.st_ino))
    state = dict(writes=0, observed=b'original stale observation', calls=[], live=False,
                 lost_reply=False, absent_write=False)
    def repair_source(sha):
        assert sha == 'b'*40
        state['calls'].append('repair-source')
    def installed_source(host):
        state['calls'].append('original-source')
    monkeypatch.setattr(recovery, '_verify_repair_source', repair_source)
    monkeypatch.setattr(recovery, '_verify_original_source', installed_source)
    def stopped(self):
        if state['live']:
            raise owner.ArmAdmissionError('services_not_stopped')
    monkeypatch.setattr(owner.ProductionTransactionHost, 'require_services_already_stopped', stopped)
    monkeypatch.setattr(publisher, '_retained', lambda: state['observed'])
    def publish(sha, *, allow_publication, control_sha256):
        state['calls'].append(('publish', allow_publication))
        assert sha == SHA
        expected = control_sha256.encode()
        if allow_publication:
            assert json.loads((marker/'transaction.json').read_bytes())['phase'] == recovery.CLOSEOUT_STARTED
            state['writes'] += 1
            if not state['absent_write']:
                state['observed'] = expected
            if state['lost_reply']:
                raise OSError('lost publication acknowledgement')
        elif state['observed'] != expected:
            raise owner.TransactionEffectUnknown()
        return hashlib.sha256(expected).hexdigest()
    monkeypatch.setattr(publisher, '_publish', publish)
    paths = (owner.CONTROL_CONFIG, owner.WORKER_CONFIG, owner.AUTONOMY_RECEIPT)
    original = {str(p): (p.read_bytes(), tuple(p.lstat())) for p in paths}
    return SimpleNamespace(root=root, marker=marker, state=state, original=original,
                           paths=paths, tx=tx, real_publish=real_publish)


def preserved(incident):
    assert {str(p): (p.read_bytes(), tuple(p.lstat())) for p in incident.paths} == incident.original


def alter_fixture(path, raw):
    # Fault injection into disposable caller-owned fixture files only. Restore
    # their mode so the test reaches content/lineage guards, not write access.
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(mode | stat.S_IWUSR)
    try:
        path.write_bytes(raw)
    finally:
        path.chmod(mode)


def test_real_original_flock_one_publication_existing_cleanup_no_config_or_receipt_rewrite(incident):
    result = recovery.reconcile(repair_sha='b'*40)
    assert result.transaction_id == recovery.ORIGINAL_TRANSACTION
    assert result.status == 'UNARMED'
    assert incident.state['writes'] == 1
    assert not incident.marker.exists()
    preserved(incident)


@pytest.mark.parametrize('field,value', [
    ('operation', 'ARM'), ('transaction_id', 'autonomy-'+'2'*12),
    ('expected_sha', 'd'*40), ('phase', publisher.PUBLICATION_PHASE),
    ('phase', publisher.ROLLBACK_PUBLICATION_PHASE), ('phase', 'LOCKED'),
    ('target_control_sha256', 'd'*64), ('extra', 'unadmitted'),
])
def test_non_original_or_ambiguous_journal_has_no_effect(incident, field, value):
    path = incident.marker/'transaction.json'
    value_doc = json.loads(path.read_bytes()); value_doc[field] = value
    alter_fixture(path, owner._encoded_json(value_doc))
    before = path.read_bytes()
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.reconcile(repair_sha='b'*40)
    assert path.read_bytes() == before
    assert incident.state['writes'] == 0
    preserved(incident)


@pytest.mark.parametrize('fault', ['receipt','archive','config','candidate','extra-file','services'])
def test_admission_requires_exact_original_objects_and_stopped_services(incident, fault):
    if fault == 'receipt':
        alter_fixture(owner.AUTONOMY_RECEIPT, b'{}')
    elif fault == 'archive':
        alter_fixture(incident.marker/'prior-control.json', b'{}')
    elif fault == 'config':
        alter_fixture(owner.CONTROL_CONFIG, b'{}')
    elif fault == 'candidate':
        candidate, _ = owner.ProductionTransactionHost._candidate_paths(recovery.ORIGINAL_TRANSACTION)
        candidate.symlink_to(owner.CONTROL_CONFIG)
    elif fault == 'extra-file':
        (incident.marker/'extra').write_bytes(b'hold')
    else:
        incident.state['live'] = True
    before = (incident.marker/'transaction.json').read_bytes()
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.reconcile(repair_sha='b'*40)
    assert incident.state['writes'] == 0
    assert (incident.marker/'transaction.json').read_bytes() == before


def test_live_original_owner_blocks_recovery(incident):
    active = owner.ProductionTransactionHost()
    active._claim_transaction_owner()
    try:
        with pytest.raises(owner.TransactionEffectUnknown):
            recovery.reconcile(repair_sha='b'*40)
        assert incident.state['writes'] == 0
    finally:
        active._release_transaction_owner()


@pytest.mark.parametrize('observation_after', ['exact','absent','stale'])
def test_lost_publication_ack_allows_only_readback_not_second_write(incident, observation_after):
    incident.state['lost_reply'] = True
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.reconcile(repair_sha='b'*40)
    assert incident.state['writes'] == 1
    assert json.loads((incident.marker/'transaction.json').read_bytes())['phase'] == recovery.CLOSEOUT_STARTED
    preserved(incident)
    incident.state['lost_reply'] = False
    if observation_after != 'exact':
        incident.state['observed'] = None if observation_after == 'absent' else b'stale'
        with pytest.raises(owner.TransactionEffectUnknown):
            recovery.reconcile(repair_sha='b'*40)
        assert incident.marker.exists()
    else:
        result = recovery.reconcile(repair_sha='b'*40)
        assert result.transaction_id == recovery.ORIGINAL_TRANSACTION
        assert not incident.marker.exists()
    assert incident.state['writes'] == 1
    preserved(incident)


def test_journal_ack_loss_before_publication_never_reenters_write_branch(incident, monkeypatch):
    original = owner.ProductionTransactionHost._persist_phase
    def loss(self, transaction, phase, **kwargs):
        original(self, transaction, phase, **kwargs)
        raise OSError('journal fsync reply lost')
    monkeypatch.setattr(owner.ProductionTransactionHost, '_persist_phase', loss)
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.reconcile(repair_sha='b'*40)
    monkeypatch.setattr(owner.ProductionTransactionHost, '_persist_phase', original)
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.reconcile(repair_sha='b'*40)
    assert incident.state['writes'] == 0
    assert incident.marker.exists()
    preserved(incident)


def test_cleanup_failure_does_not_republish_or_rewrite(incident, monkeypatch):
    def cleanup(*args):
        raise OSError('cleanup refused')
    monkeypatch.setattr(owner.ProductionTransactionHost, '_remove_candidate', cleanup)
    for _ in range(2):
        with pytest.raises(owner.TransactionEffectUnknown):
            recovery.reconcile(repair_sha='b'*40)
    assert incident.state['writes'] == 1
    assert incident.marker.exists()
    preserved(incident)


def test_plain_data_cannot_supply_current_recovery_custody(monkeypatch):
    host = owner.ProductionTransactionHost()
    host._disarm_closeout_qualification = SimpleNamespace(pid=os.getpid())
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.verify_admitted_readback(host, object())


def test_repair_source_must_be_root_sealed_and_distinct_installed_release(monkeypatch):
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    for sha in [recovery.ORIGINAL_SHA, 'b'*40, 'bad']:
        with pytest.raises(owner.TransactionEffectUnknown):
            recovery._verify_repair_source(sha)


def test_original_source_changed_from_adjudicated_type_guard_refuses(monkeypatch):
    host = owner.ProductionTransactionHost()
    monkeypatch.setattr(host, 'require_exact_install', lambda sha: sha)
    monkeypatch.setattr(owner, '_read_root_file', lambda *a,**kw: (b'different entry code',None))
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery._verify_original_source(host)


@pytest.mark.parametrize('relative', ['control.json', 'autonomy-state-v1.json',
    'autonomy-transaction.lock/prior-control.json', 'autonomy-transaction.lock/transaction.json'])
def test_identical_bytes_on_a_replacement_generation_do_not_rebind(incident, relative):
    path = incident.root/relative
    raw, mode = path.read_bytes(), stat.S_IMODE(path.stat().st_mode)
    temporary = path.with_name(path.name+'.replacement')
    temporary.write_bytes(raw); temporary.chmod(mode); temporary.replace(path)
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.reconcile(repair_sha='b'*40)
    assert incident.state['writes'] == 0
    assert incident.marker.exists()


def test_generation_change_after_journal_boundary_blocks_publication(incident, monkeypatch):
    original = owner.ProductionTransactionHost._persist_phase
    def change(self, transaction, phase, **kwargs):
        original(self, transaction, phase, **kwargs)
        path = owner.CONTROL_CONFIG
        temporary = path.with_name(path.name+'.replacement')
        temporary.write_bytes(path.read_bytes())
        temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        temporary.replace(path)  # Same bytes, changed inode under the existing lock.
    monkeypatch.setattr(owner.ProductionTransactionHost, '_persist_phase', change)
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.reconcile(repair_sha='b'*40)
    assert incident.state['writes'] == 0
    assert json.loads((incident.marker/'transaction.json').read_bytes())['phase'] == recovery.CLOSEOUT_STARTED


def test_partial_cleanup_is_unknown_and_cannot_recreate_original_archives(incident, monkeypatch):
    original = Path.unlink
    def partial(self, *args, **kwargs):
        if self == incident.marker/'prior-worker.json':
            raise OSError('second archive removal failed')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', partial)
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.reconcile(repair_sha='b'*40)
    assert not (incident.marker/'prior-control.json').exists()
    assert incident.state['writes'] == 1
    with pytest.raises(owner.TransactionEffectUnknown):
        recovery.reconcile(repair_sha='b'*40)
    assert not (incident.marker/'prior-control.json').exists()
    assert incident.state['writes'] == 1
    preserved(incident)


def test_composes_real_projection_publisher_and_existing_terminal_cleanup(incident, monkeypatch):
    # Real _publish handles stable snapshots, atomic publication and readback.
    # Only trusted-OS metadata reads and the observation path are inert adapters.
    contract = publisher.contract
    target = json.dumps(dict(schema=contract.SCHEMA, source_release_sha=SHA,
        control_sha256=incident.tx.candidates.control_sha256,
        control_identity=[7, 10, 0o100440, 0, contract.CONTROL_UID, 1, 100, 100, 200],
        control_uid=contract.CONTROL_UID, python_runtime_provenance_digest='b'*64,
        control_acl_absent=True),sort_keys=True).encode()
    monkeypatch.setattr(publisher, '_publish', incident.real_publish)
    monkeypatch.setattr(publisher, '_snapshot', lambda sha:(target, ()))
    observation_path = incident.root/'control-observation.json'
    monkeypatch.setattr(contract, 'OBSERVATION_PATH', str(observation_path))
    atomic = owner._atomic_file
    def publish(path, raw, **kwargs):
        if path != observation_path:
            return atomic(path, raw, **kwargs)
        assert json.loads((incident.marker/'transaction.json').read_bytes())['phase'] == recovery.CLOSEOUT_STARTED
        incident.state['writes'] += 1
        incident.state['observed'] = raw
    monkeypatch.setattr(owner, '_atomic_file', publish)
    recovery.reconcile(repair_sha='b'*40)
    assert incident.state['observed'] == target
    assert incident.state['writes'] == 1
    assert not incident.marker.exists()
    preserved(incident)
