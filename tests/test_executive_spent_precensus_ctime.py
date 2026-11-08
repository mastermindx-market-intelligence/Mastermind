"""Inert current-boundary admission; host/account/seal observations are seams.

The old Root attestation fixture is inherited. The old and new Control intent,
real SQLite migrations/backups/drills/receipts and census wire remain actual.
No fixture claims to explain the host's ctime change or to replay its checkpoint.
"""
import json
import os
import sqlite3

import pytest

from control_plane import executive_backup as b
from ops.executive_os import acceptance_maintenance as m
from test_executive_precensus_recovery import control_recovery


@pytest.fixture
def spent_case(control_recovery, monkeypatch):
    s = control_recovery
    monkeypatch.setattr(m, '_require_pre_census_stopped', lambda: None)
    historical = b.create_offline_backup(s.database, s.backups, expected_schema_version=5)
    s.historical = {p: p.read_bytes() for p in (s.backups / os.path.basename(historical.database_path),
                                               s.backups / os.path.basename(historical.manifest_path))}
    # The inherited Root authority is explicitly a fixture seam. Bind its
    # permitted inventory before creating the genuine old Control intent.
    s.qualification['backup_inventory_sha256'] = m.digest(b._pre_census_backup_inventory(s.backups))
    s.qpath.chmod(0o600)
    s.qpath.write_bytes(b._upgrade_receipt_bytes(s.qualification))
    s.qpath.chmod(0o440)
    lock = s.database.parent / b.DEFAULT_SERVICE_LOCK_NAME
    marker = s.database.parent / b.DEFAULT_SERVICE_MARKER_NAME
    with b._offline_restore_lock(lock, marker, require_existing=True) as fd:
        old = b._PreCensusContinuation(s.database, s.backups, s.release,
            s.original['operation_id'], s.identity['sha256'], fd)
        try:
            old.reserve()
        finally:
            old.close()
    s.old_intent_path = s.database.parent / b.PRE_CENSUS_CONTINUATION_NAME
    s.old_intent = json.loads(s.old_intent_path.read_bytes())
    s.old_intent_identity = b._pre_census_artifact_identity(s.old_intent_path,
        uid=os.geteuid(), gid=os.getegid(), mode=0o600)
    s.immutable = {p: p.read_bytes() for p in (s.barrier, s.qpath, s.old_intent_path)}
    # Deliberate owned-fixture metadata change, not an asserted checkpoint cause.
    s.database.chmod(0o600)
    fd = os.open(s.database, os.O_RDONLY)
    try:
        current = b._pre_census_database_origin(s.database, fd, os.geteuid(), os.getegid())
    finally:
        os.close(fd)
    b._validate_spent_pre_census_ctime_origin(s.qualification['database'], current)
    previous = s.qualification['recovery_tool']
    s.release = 'f' * 40
    release_root = b._PRE_CENSUS_RELEASES / s.release
    release_root.mkdir()
    tool = {'root': str(release_root), 'sha': s.release, 'tree_sha': 'd' * 40,
            'manifest_sha256': 'd' * 64}
    assert previous['sha'] != tool['sha'] != s.original['release_sha']
    monkeypatch.setattr(b, '_SCHEMA_UPGRADE_RELEASE_OBSERVER', lambda: {
        'release_root': tool['root'], 'release_sha': tool['sha'],
        'release_tree_sha': tool['tree_sha'], 'release_manifest_sha256': tool['manifest_sha256']})
    s.root_receipt = {'schema_version': b.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_SCHEMA,
        'operation_id': s.original['operation_id'], 'original_barrier_identity': s.identity,
        'qualification_identity': b._pre_census_artifact_identity(s.qpath,
            uid=0, gid=os.getegid(), mode=0o440),
        'spent_continuation_identity': s.old_intent_identity, 'recovery_tool': tool,
        'database': current, 'created_at': '2026-10-24T03:00:00Z'}
    s.root_path = s.database.parent / b.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_NAME
    s.root_path.write_bytes(b._upgrade_receipt_bytes(s.root_receipt))
    s.root_path.chmod(0o440)
    s.root_identity = b._pre_census_artifact_identity(s.root_path,
        uid=0, gid=os.getegid(), mode=0o440)
    return s


def _continue(s):
    return b.continue_spent_v5_to_v6_pre_census_ctime(s.database, s.backups,
        release_sha=s.release, expected_operation_id=s.original['operation_id'],
        expected_barrier_sha256=s.identity['sha256'],
        expected_spent_continuation_sha256=s.old_intent_identity['sha256'],
        expected_reconciliation_sha256=s.root_identity['sha256'])


def test_real_current_boundary_backup_p56_c56_and_normal67(spent_case, monkeypatch, capsys):
    s = spent_case
    checkpoint = b._checkpoint_quiesced_wal
    committed = []
    monkeypatch.setattr(b, '_SCHEMA_UPGRADE_TEST_HOOK', lambda phase:
        committed.append(phase) if phase == 'after_v6_commit_before_checkpoint' else None)
    def checkpoint_new_commit(path):
        assert committed, 'spent pre-admission checkpoint was replayed'
        return checkpoint(path)
    monkeypatch.setattr(b, '_checkpoint_quiesced_wal', checkpoint_new_commit)
    from scripts import executive_os_migrate as cli
    assert cli.main(['--continue-spent-v5-to-v6-pre-census-ctime', '--database', str(s.database),
        '--backup-directory', str(s.backups), '--release-sha', s.release,
        '--expected-operation-id', s.original['operation_id'], '--expected-barrier-sha256', s.identity['sha256'],
        '--expected-spent-continuation-sha256', s.old_intent_identity['sha256'],
        '--expected-reconciliation-sha256', s.root_identity['sha256']]) == 0
    assert json.loads(capsys.readouterr().out)['release_sha'] == s.release
    for p, raw in s.immutable.items():
        if p != s.barrier:
            assert p.read_bytes() == raw
    assert not s.barrier.exists()
    for path, raw in s.historical.items():
        assert path.read_bytes() == raw
    p56 = json.loads((s.database.parent / b._UPGRADE_V5_TO_V6_PREFLIGHT_NAME).read_bytes())
    assert p56['schema_version'] == b.SPENT_PRE_CENSUS_CTIME_PREFLIGHT_SCHEMA
    assert set(p56['pre_census_reconciliation']) == {
        'qualification_identity', 'spent_continuation_identity',
        'reconciliation_identity', 'continuation_identity'}
    assert p56['pre_census_reconciliation']['spent_continuation_identity'] == s.old_intent_identity
    assert len(p56['quiesce_writer_census']['open_files']) == 3
    with pytest.raises(b.ExecutiveSchemaUpgradeError, match='already spent'):
        _continue(s)
    monkeypatch.setattr(b, '_checkpoint_quiesced_wal', checkpoint)
    b.upgrade_v6_to_v7(s.database, s.backups, release_sha=s.release)
    assert b.verify_backup(s.database, expected_schema_version=7)
    assert not s.fd_paths


@pytest.mark.parametrize('key', ['path', 'device', 'inode', 'uid', 'gid', 'mode', 'nlink', 'size', 'mtime_ns', 'sha256'])
def test_only_a_different_ctime_epoch_is_admissible(spent_case, key):
    s = spent_case
    old = s.qualification['database']
    new = dict(s.root_receipt['database'])
    new[key] = new[key] + 1 if isinstance(new[key], int) else ('0' * 64 if key == 'sha256' else '/foreign')
    with pytest.raises(b.ExecutiveSchemaUpgradeError):
        b._validate_spent_pre_census_ctime_origin(old, new)


def test_equal_semantics_but_different_bytes_refuse(spent_case):
    s = spent_case
    old = s.qualification['database']
    c = sqlite3.connect(s.database)
    try:
        c.execute('PRAGMA user_version=17')
    finally:
        c.close()
    os.utime(s.database, ns=(s.database.stat().st_atime_ns, old['mtime_ns']))
    actual = b._upgrade_v5_retained_state(s.database, version=5)
    assert actual['full_v5_content_digest'] == s.qualification['full_v5_content_digest']
    fd = os.open(s.database, os.O_RDONLY)
    try:
        current = b._pre_census_database_origin(s.database, fd, os.geteuid(), os.getegid())
    finally:
        os.close(fd)
    assert current['sha256'] != old['sha256']
    with pytest.raises(b.ExecutiveSchemaUpgradeError):
        b._validate_spent_pre_census_ctime_origin(old, current)
    with pytest.raises(b.ExecutiveSchemaUpgradeError):
        _continue(s)
    assert not (s.database.parent / b.SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME).exists()


@pytest.mark.parametrize('phase', ['barrier_persisted', 'preflight_persisted', 'after_m6_statement:01',
    'after_v6_commit_before_checkpoint', 'recovered_barrier_removed_before_completion'])
def test_failure_retains_all_authorities_and_refuses_replay_or67(spent_case, monkeypatch, phase):
    s = spent_case
    def fail(point):
        if point == phase:
            raise RuntimeError('owned fixture fault')
    monkeypatch.setattr(b, '_SCHEMA_UPGRADE_TEST_HOOK', fail)
    with pytest.raises(b.ExecutiveSchemaUpgradeError):
        _continue(s)
    assert (s.database.parent / b.SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME).exists()
    for p in (s.qpath, s.old_intent_path):
        assert p.read_bytes() == s.immutable[p]
    with pytest.raises(b.ExecutiveSchemaUpgradeError):
        _continue(s)
    with pytest.raises((b.ExecutiveSchemaUpgradeError, b.BackupVerificationError)):
        b.upgrade_v6_to_v7(s.database, s.backups, release_sha=s.release)


@pytest.mark.parametrize('extra', [
    ['--inspect-v5-to-v6-pre-census-barrier'], ['--resume-v5-to-v6-pre-census'],
    ['--transition', 'v5-to-v6'], ['--from-version', '5'],
])
def test_new_cli_action_is_exclusive(extra):
    from scripts import executive_os_migrate as cli
    with pytest.raises(SystemExit) as error:
        cli.main(['--continue-spent-v5-to-v6-pre-census-ctime', *extra])
    assert error.value.code == 2


@pytest.mark.parametrize('missing', ['--expected-operation-id', '--expected-barrier-sha256',
    '--expected-spent-continuation-sha256', '--expected-reconciliation-sha256'])
def test_new_cli_requires_every_exact_cas_selector(monkeypatch, missing):
    from scripts import executive_os_migrate as cli
    monkeypatch.setattr(b, 'continue_spent_v5_to_v6_pre_census_ctime',
        lambda *a, **k: pytest.fail('incomplete CLI entered an effect'))
    args = ['--continue-spent-v5-to-v6-pre-census-ctime', '--database', '/fixture',
            '--backup-directory', '/fixture-backups', '--release-sha', 'f' * 40]
    for name in ['--expected-operation-id', '--expected-barrier-sha256',
                 '--expected-spent-continuation-sha256', '--expected-reconciliation-sha256']:
        if name != missing:
            args.extend([name, 'a' * (32 if name == '--expected-operation-id' else 64)])
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


@pytest.mark.parametrize('adverse', ['late_ctime', 'backup_residue', 'root_partial', 'old_intent_missing'])
def test_present_state_drift_refuses_before_new_reservation(spent_case, adverse):
    s = spent_case
    if adverse == 'late_ctime':
        s.database.chmod(0o600)
    elif adverse == 'backup_residue':
        (s.backups / 'unexplained-residue').write_bytes(b'fixture')
    elif adverse == 'root_partial':
        s.root_path.chmod(0o600)
    else:
        s.old_intent_path.unlink()
    with pytest.raises((b.ExecutiveSchemaUpgradeError, OSError)):
        _continue(s)
    assert not (s.database.parent / b.SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME).exists()


def test_new_residue_cannot_bypass_old_or_ordinary_entry(spent_case):
    s = spent_case
    s.qpath.unlink()
    s.old_intent_path.unlink()
    s.barrier.unlink()
    with pytest.raises(b.ExecutiveSchemaUpgradeError, match='ctime reconciliation residue'):
        b.resume_v5_to_v6_pre_census(s.database, s.backups, release_sha=s.release,
            expected_operation_id=s.original['operation_id'], expected_barrier_sha256=s.identity['sha256'])
    with pytest.raises(b.ExecutiveSchemaUpgradeError, match='recovery residue'):
        b.upgrade_v5_to_v6(s.database, s.backups, release_sha=s.release)


@pytest.mark.parametrize('ctime', [None, True, -1, '123'])
def test_ctime_is_never_a_caller_boolean_or_string(spent_case, ctime):
    new = dict(spent_case.root_receipt['database'], ctime_ns=ctime)
    with pytest.raises(b.ExecutiveSchemaUpgradeError):
        b._validate_spent_pre_census_ctime_origin(spent_case.qualification['database'], new)
