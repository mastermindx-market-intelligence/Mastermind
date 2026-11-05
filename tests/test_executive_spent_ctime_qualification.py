"""Fresh Root proof over a genuinely spent old operation in disposable v5 data.

Host principals, source seals, native ACL/ancestor policy and OS observations
are inherited explicit fixture seams. Actual Root issuers, old intent writer,
full v5/selected/deeper/canary validators and retained FD checks are real.
The ctime change is an injected metadata event, NOT a checkpoint reproduction.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from control_plane import executive_backup as b
from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_acceptance_pre_census_qualification import _fixture, _no_external_effects
from tests.test_executive_precensus_joined_acceptance import _control_boundary
from tests.test_executive_acceptance_v5_to_v7 import SUCCESSOR

SPENT = '7'*40


def _spent_fixture(tmp_path, monkeypatch, *, logical=False):
    f = _fixture(tmp_path, monkeypatch, logical=logical)
    database = Path(f.runtime.store.path)
    f.args.successor_sha = SPENT
    (m.SYSTEM_ROOT/'releases'/SPENT).mkdir(mode=0o700)
    def release(sha):
        return dict(release_root=str(m.SYSTEM_ROOT/'releases'/sha), release_sha=sha,
                    release_tree_sha='b'*40, release_manifest_sha256='c'*64)
    monkeypatch.setattr(b, '_SCHEMA_UPGRADE_RELEASE_OBSERVER', lambda: release(SPENT))
    m.prepare(f.args)
    q = json.loads(f.destination.read_bytes())
    _control_boundary(f, monkeypatch)
    if logical:
        # The owner accepts only the production /var alias. Map precisely the
        # two inert fixture aliases to the corresponding fixed physical roots.
        argument = b._pre_census_argument
        mappings = {str(f.config['runtime_root']): database.parents[2],
                    str(f.config['backup_root']): database.parents[3]/'backups'}
        def fixture_argument(value, fixed):
            if str(value) in mappings and mappings[str(value)] == fixed:
                return fixed
            return argument(value, fixed)
        monkeypatch.setattr(b, '_pre_census_argument', fixture_argument)
    def stop(phase):
        if phase == 'barrier_persisted':
            raise RuntimeError('intent genuinely spent before source backup')
    monkeypatch.setattr(b, '_SCHEMA_UPGRADE_TEST_HOOK', stop)
    with pytest.raises(b.ExecutiveSchemaUpgradeError, match='intent retained'):
        b.resume_v5_to_v6_pre_census(database, database.parents[3]/'backups',
            release_sha=SPENT, expected_operation_id=q['operation_id'],
            expected_barrier_sha256=q['original_barrier']['identity']['sha256'])
    monkeypatch.setattr(b, '_SCHEMA_UPGRADE_TEST_HOOK', None)
    f.spent_path = database.parent/b.PRE_CENSUS_CONTINUATION_NAME
    assert f.spent_path.exists()
    before = database.read_bytes()
    os.chmod(database, 0o600)  # explicit fixture metadata event; no SQL/checkpoint
    assert database.read_bytes() == before
    assert database.stat().st_ctime_ns != q['database']['ctime_ns']
    monkeypatch.setattr(b.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(b, '_SCHEMA_UPGRADE_RELEASE_OBSERVER', lambda: release(SUCCESSOR))
    f.args.successor_sha = SUCCESSOR
    f.args.qualify_v5_pre_census_continuation = False
    f.args.reconcile_spent_v5_pre_census_ctime = True
    f.reconciliation = database.parent/b.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_NAME
    f.q = q
    return f


@pytest.mark.parametrize('logical', [False, True])
def test_real_root_reconciles_only_new_ctime_and_preserves_old_origins(tmp_path, monkeypatch, logical):
    f = _spent_fixture(tmp_path, monkeypatch, logical=logical)
    old = {p: (p.read_bytes(), p.stat().st_ino) for p in (f.barrier, f.destination, f.spent_path)}
    result = m.prepare(f.args)
    r = json.loads(f.reconciliation.read_bytes())
    assert len(r) == 8
    assert r['database']['ctime_ns'] != f.q['database']['ctime_ns']
    assert {k:v for k,v in r['database'].items() if k != 'ctime_ns'} == {
        k:v for k,v in f.q['database'].items() if k != 'ctime_ns'}
    assert r['recovery_tool']['sha'] == SUCCESSOR
    assert f.q['recovery_tool']['sha'] == SPENT
    assert r['spent_continuation_identity']['sha256'] == hashlib.sha256(f.spent_path.read_bytes()).hexdigest()
    assert result['reconciliation_identity']['sha256'] == hashlib.sha256(f.reconciliation.read_bytes()).hexdigest()
    assert f.reconciliation.stat().st_mode & 0o777 == 0o440
    assert old == {p: (p.read_bytes(), p.stat().st_ino) for p in old}
    with pytest.raises((m.MaintenanceError, OSError)):
        m.prepare(f.args)
    assert not (f.barrier.parent/b.SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME).exists()
    assert not m.bundle_path(SUCCESSOR).exists()


@pytest.mark.parametrize('fault', ['bytes', 'sequence', 'inventory', 'canary', 'config',
                                  'receipt', 'spent-cas', 'mixed-action'])
def test_new_root_boundary_refuses_current_drift_before_publication(tmp_path, monkeypatch, fault):
    f = _spent_fixture(tmp_path, monkeypatch)
    database = Path(f.runtime.store.path)
    if fault == 'bytes':
        with database.open('ab') as handle: handle.write(b'\0')
    elif fault == 'sequence':
        import sqlite3
        connection=sqlite3.connect(database)
        connection.execute('PRAGMA journal_mode=DELETE')
        connection.execute('UPDATE sqlite_sequence SET seq=seq+1'); connection.commit(); connection.close()
    elif fault == 'inventory':
        (Path(f.config['backup_root'])/'foreign').write_bytes(b'foreign')
    elif fault == 'canary':
        Path(f.config['secret_canary_receipt_path']).write_text('{}')
    elif fault == 'config':
        path=m.SYSTEM_ROOT/'config/control.json'; path.chmod(0o600); path.write_bytes(path.read_bytes()+b' '); path.chmod(0o440)
    elif fault == 'receipt':
        (database.parent/b._UPGRADE_V5_TO_V6_PREFLIGHT_NAME).write_text('{}')
    elif fault == 'spent-cas':
        f.args.expected_spent_continuation_sha256='0'*64
    else:
        f.args.qualify_v5_pre_census_continuation=True
    with pytest.raises((m.MaintenanceError, b.ExecutiveSchemaUpgradeError, OSError, ValueError)):
        m.prepare(f.args)
    assert not f.reconciliation.exists()
    assert f.barrier.exists() and f.spent_path.exists()


@pytest.mark.parametrize('fault', ['late-inventory', 'late-ctime', 'late-spent'])
def test_late_drift_retains_private_nonreplayable_root_child(tmp_path, monkeypatch, fault):
    f = _spent_fixture(tmp_path, monkeypatch)
    real=m._qualify_v5_source_only; calls=0
    def qualify(*args, **kwargs):
        nonlocal calls
        result=real(*args, **kwargs); calls+=1
        if calls==2:
            if fault=='late-inventory': (Path(f.config['backup_root'])/'late').write_bytes(b'late')
            elif fault=='late-ctime': os.chmod(f.runtime.store.path,0o600)
            else: f.spent_path.write_bytes(f.spent_path.read_bytes()+b' ')
        return result
    monkeypatch.setattr(m,'_qualify_v5_source_only',qualify)
    with pytest.raises((m.MaintenanceError,b.ExecutiveSchemaUpgradeError,OSError,ValueError)):
        m.prepare(f.args)
    assert f.reconciliation.exists()
    assert f.reconciliation.stat().st_mode & 0o777 == 0o600
    assert f.barrier.exists() and f.spent_path.exists()
    with pytest.raises((m.MaintenanceError,b.ExecutiveSchemaUpgradeError,OSError,ValueError)):
        m.prepare(f.args)


@pytest.mark.parametrize('name', ['SPENT_PRE_CENSUS_CTIME_RECONCILIATION_NAME',
                                  'SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME'])
def test_old_root_issuer_refuses_new_residue_even_without_old_q_i(tmp_path,monkeypatch,name):
    f=_fixture(tmp_path,monkeypatch)
    (f.barrier.parent/getattr(b,name)).write_bytes(b'foreign')
    with pytest.raises(m.MaintenanceError,match='receipts or reservation'):
        m.prepare(f.args)
    assert not f.destination.exists()
