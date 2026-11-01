"""Prospective origin composition over real migration/prepare/restore owners.

The inherited fixture discloses synthetic Root/account/seal/process/assignment
inputs. Only raw stat device observations are additionally controlled here;
actual bytes, inodes, clocks, modes, SQLite, held FDs and protocol joins execute.
These cases prove source behavior, never historical volume or live Root custody.
"""
import copy
import os
from pathlib import Path
import json
import pwd
import stat
import sys
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance_maintenance as maintenance
from ops.executive_os import schema_upgrade_evidence as evidence
from ops.executive_os import persistent_origin as origin
from tests.test_executive_persistent_origin import filesystem
from tests import test_executive_installed_migration_successor as installed
from tests import test_executive_prepared_migration_successor as prepared
from tests.test_executive_spent_ctime_qualification import _no_external_effects


@pytest.fixture
def tmp_path(filesystem):
    # Real guarded owners retain ancestor identities. Avoid the concurrently
    # changing global pytest/temp namespace; keep this scenario under the
    # existing exclusively owned canonical-HOME TemporaryDirectory.
    path = filesystem.base/'scenario'
    path.mkdir(mode=0o700)
    return path


@pytest.fixture
def device_epoch(monkeypatch, filesystem, tmp_path):
    """Change raw kernel-observation inputs, never receipts or validators."""
    real_stat, real_lstat, real_fstat, real_open = os.stat, os.lstat, os.fstat, os.open
    state = SimpleNamespace(device=real_stat(filesystem.anchor).st_dev, foreign={},
                            tracked=set(filesystem.owner))

    def StatObservation(value):
        fields = list(value)
        fields[2] = state.foreign.get(value.st_ino,
            state.device if value.st_ino in state.tracked else value.st_dev)
        extra = {key:getattr(value, key) for key in dir(value)
                 if key.startswith('st_') and key not in
                 {'st_mode', 'st_ino', 'st_dev', 'st_nlink', 'st_uid', 'st_gid', 'st_size'}}
        # Preserve the native stat_result type and every nondevice timestamp,
        # including nanoseconds; the real symlink ACL contract requires it.
        return os.stat_result(fields, extra)

    def named(call, path, *args, **kwargs):
        value = call(path, *args, **kwargs)
        if not isinstance(path, int) and Path(path).is_relative_to(tmp_path):
            state.tracked.add(value.st_ino)
        return StatObservation(value)

    def opened(path, *args, **kwargs):
        fd = real_open(path, *args, **kwargs)
        parent = kwargs.get('dir_fd')
        if (Path(path).is_relative_to(tmp_path)
                or (parent is not None and real_fstat(parent).st_ino in state.tracked)):
            state.tracked.add(real_fstat(fd).st_ino)
        return fd

    monkeypatch.setattr(os, 'stat', lambda *a, **k: named(real_stat, *a, **k))
    monkeypatch.setattr(os, 'lstat', lambda *a, **k: named(real_lstat, *a, **k))
    monkeypatch.setattr(os, 'fstat', lambda *a, **k: StatObservation(real_fstat(*a, **k)))
    monkeypatch.setattr(os, 'open', opened)
    yield state
    # Restore raw observations before dependent real TemporaryDirectory cleanup.
    monkeypatch.setattr(os, 'stat', real_stat)
    monkeypatch.setattr(os, 'lstat', real_lstat)
    monkeypatch.setattr(os, 'fstat', real_fstat)
    monkeypatch.setattr(os, 'open', real_open)


@pytest.mark.parametrize('changed_device', [False, True])
def test_whole_installed_prepare_admission_finish_carry_keeps_history(
        tmp_path, monkeypatch, device_epoch, changed_device):
    actual_fixture = installed._installed_fixture
    captured = {}

    def produce_old_then_observe_current(*args):
        f = actual_fixture(*args)
        captured['fixture'] = f
        captured['old_device'] = device_epoch.device
        if changed_device:
            device_epoch.device += 100
        return f

    monkeypatch.setattr(installed, '_installed_fixture', produce_old_then_observe_current)
    # The accepted real-owner journey includes prepare/requalify, admission,
    # actual proof/backup/restore, finish with live WAL and later carry-history.
    installed.test_actual_normal_installed_P_to_R_prepare_admit_restore_finish_and_carry(
        tmp_path, monkeypatch)
    f = captured['fixture']
    assert {row['device'] for row in f.material['origin_records']} == {captured['old_device']}
    assert maintenance.sealed_json(maintenance.bundle_path(installed.R)/
                                   maintenance._V5_TO_V7_EVIDENCE_NAME) == f.material
    prepared._assert_parent_unchanged(f)
    # A later opening must also handle acceptance backups from the intervening
    # epoch without pretending they share the original migration observation.
    device_epoch.device += 100
    maintenance.validate_prior_carry_binding(maintenance.descriptor_for('1'*40))
    prepared._assert_parent_unchanged(f)


@pytest.mark.parametrize('fault', ['foreign-origin', 'foreign-anchor', 'inode', 'size',
                                  'sha256', 'payload_digest', 'mode', 'uid', 'gid',
                                  'nlink', 'mtime_ns', 'ctime_ns', 'missing-role',
                                  'mixed-history', 'nested-history'])
def test_prepared_history_drift_refuses_without_target_publication(
        tmp_path, monkeypatch, device_epoch, fault):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    device_epoch.device += 100
    material = copy.deepcopy(f.material)
    row = material['origin_records'][0]
    if fault == 'foreign-origin':
        device_epoch.foreign[Path(row['path']).stat().st_ino] = device_epoch.device + 1
    elif fault == 'foreign-anchor':
        device_epoch.foreign[origin.DATA_VOLUME_ANCHOR.stat().st_ino] = device_epoch.device + 1
    elif fault == 'missing-role':
        material['origin_records'].pop()
    elif fault == 'mixed-history':
        row['device'] += 1
    elif fault == 'nested-history':
        material['chain']['pre_census_reconciliation']['qualification_identity']['device'] += 1
    elif fault in ('sha256', 'payload_digest'):
        row[fault] = '0' * 64
    else:
        row[fault] += 1
    with pytest.raises((evidence.SchemaUpgradeEvidenceError, origin.PersistentOriginError,
                        ValueError, OSError)):
        with evidence.open_prepared_successor_v5_to_v7_evidence(f.runtime_root, installed.R, material):
            pytest.fail('unqualified original exposed DATA')
    assert not maintenance.bundle_path(installed.R).exists()
    prepared._assert_parent_unchanged(f)


def test_generic_initial_still_uses_exact_original_device(tmp_path, monkeypatch, device_epoch):
    f = installed._installed_fixture(tmp_path, monkeypatch)
    from control_plane import executive_backup
    monkeypatch.setattr(executive_backup, '_SCHEMA_UPGRADE_RELEASE_OBSERVER', lambda:dict(
        release_root=str(maintenance.SYSTEM_ROOT/'releases'/installed.P),
        release_sha=installed.P, release_tree_sha='b'*40, release_manifest_sha256='c'*64))
    device_epoch.device += 100
    with pytest.raises(evidence.RetainedChainInvalid, match='spent ctime preflight origin differs'):
        with evidence.open_v5_to_v7_evidence(f.runtime_root, installed.P):
            pytest.fail('generic original INITIAL was widened')


@pytest.mark.parametrize('fault', [None, 'inode', 'mode', 'mtime_ns', 'foreign'])
def test_actual_terminal_receipt_reader_keeps_nondevice_identity(
        tmp_path, monkeypatch, device_epoch, fault):
    from tests.test_executive_worker_broker import FakeSweeper
    workspace, runs, receipts = (tmp_path/name for name in ('workspace', 'runs', 'receipts'))
    for path in (workspace, runs, receipts):
        path.mkdir(mode=0o700)
    run, receipt_dir = runs/'ATT-one', receipts/'ATT-one'
    run.mkdir(mode=0o700); receipt_dir.mkdir(mode=0o700)
    def identity(path):
        info = path.lstat()
        return dict(path=str(path), device=info.st_dev, inode=info.st_ino,
            uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode),
            mtime_ns=info.st_mtime_ns)
    record = dict(schema_version='mastermind.executive_assignment_seal/v1',
        passed=True, control_uid=os.getuid(), job_id='JOB-one', attempt_id='ATT-one',
        uid_sweep=FakeSweeper().sweep('status_absence').to_dict(),
        paths={key:dict(after=identity(path), worker_traversal_revoked=True)
               for key, path in {'workspace':workspace, 'run':run}.items()})
    if fault in ('inode', 'mode', 'mtime_ns'):
        record['paths']['workspace']['after'][fault] += 1
    receipt = receipt_dir/'assignment-seal-receipt.json'
    receipt.write_text(json.dumps(record)); receipt.chmod(0o600)
    raw = receipt.read_bytes()
    device_epoch.device += 100
    if fault == 'foreign':
        device_epoch.foreign[workspace.lstat().st_ino] = device_epoch.device + 1
    monkeypatch.setattr(pwd, 'getpwnam', lambda user:SimpleNamespace(pw_uid=os.getuid()))
    with origin.CurrentDataVolumeGuard() as volume:
        guard = evidence._EvidenceGuard(os.getuid(), os.getgid())
        guard.current_volume = volume
        view = evidence.RetainedV5ToV7Evidence(phase=evidence.EVIDENCE_PHASE_HISTORICAL,
            guard=guard, material={}, source_v5_database=receipt, source_v5_content_digest='',
            target_v7_database=receipt, target_v7_database_identity={},
            control_config_bytes=b'', control_config_identity={}, backup_root=receipts)
        config = dict(receipts_root=str(receipts), worker_runs_root=str(runs), worker_uid=os.getuid())
        args = (config, SimpleNamespace(job_id='JOB-one', worktree=str(workspace)),
                SimpleNamespace(attempt_id='ATT-one'))
        if fault is None:
            assert maintenance.terminal_assignment(*args, _evidence=view) == {
                'assignment_seal_sha256':__import__('hashlib').sha256(raw).hexdigest()}
        else:
            with pytest.raises((maintenance.MaintenanceError, origin.PersistentOriginError)):
                maintenance.terminal_assignment(*args, _evidence=view)
        assert receipt.read_bytes() == raw


@pytest.mark.parametrize('fault', [None, 'foreign-file', 'foreign-link', 'extra',
                                  'inode', 'mixed-history', 'bytes'])
def test_inventory_checks_every_current_entry_and_keeps_complete_namespace(
        tmp_path, monkeypatch, device_epoch, fault):
    if fault == 'foreign-link' and sys.platform != 'darwin':
        pytest.skip('native Darwin symlink ACL acquisition is unavailable on this host')
    root = tmp_path/'preserved'
    root.mkdir(mode=0o700)
    file = root/'payload'; file.write_bytes(b'original'); file.chmod(0o600)
    link = root/'reference'
    if sys.platform == 'darwin':
        link.symlink_to('payload')
    child = root/'child'; child.mkdir(mode=0o700)
    baseline = maintenance.inventory([root])
    before = copy.deepcopy(baseline)
    if fault == 'inode': baseline[str(root)]['inode'] += 1
    elif fault == 'mixed-history': baseline[str(child)]['device'] += 1
    device_epoch.device += 100
    if fault == 'foreign-file': device_epoch.foreign[file.lstat().st_ino] = device_epoch.device+1
    elif fault == 'foreign-link': device_epoch.foreign[link.lstat().st_ino] = device_epoch.device+1
    elif fault == 'extra': (root/'foreign').write_bytes(b'added')
    elif fault == 'bytes': file.write_bytes(b'changed!')
    with origin.CurrentDataVolumeGuard() as volume:
        guard = evidence._EvidenceGuard(os.getuid(), os.getgid())
        guard.current_volume = volume
        view = evidence.RetainedV5ToV7Evidence(phase=evidence.EVIDENCE_PHASE_HISTORICAL,
            guard=guard, material={}, source_v5_database=file, source_v5_content_digest='',
            target_v7_database=file, target_v7_database_identity={},
            control_config_bytes=b'', control_config_identity={}, backup_root=root)
        if fault in ('foreign-file', 'foreign-link', 'mixed-history'):
            with pytest.raises((maintenance.MaintenanceError, origin.PersistentOriginError)):
                maintenance._migration_inventory_matches(view, baseline, [root])
        else:
            assert maintenance._migration_inventory_matches(view, baseline, [root]) is (fault is None)
        if fault is None:
            assert baseline == before
            # Existing generic inventory semantics remain exact across time.
            with pytest.raises(maintenance.MaintenanceError, match='preserved artifact changed'):
                maintenance.verify_inventory(baseline)


def test_closed_persistent_opening_never_falls_back_to_unheld_equality(filesystem):
    volume = origin.CurrentDataVolumeGuard()
    device = volume.current_device
    guard = evidence._EvidenceGuard(os.getuid(), os.getgid())
    guard.current_volume = volume
    guard.historical_device = device
    view = evidence.RetainedV5ToV7Evidence(phase=evidence.EVIDENCE_PHASE_HISTORICAL,
        guard=guard, material={}, source_v5_database=filesystem.anchor,
        source_v5_content_digest='', target_v7_database=filesystem.anchor,
        target_v7_database_identity={}, control_config_bytes=b'',
        control_config_identity={}, backup_root=filesystem.anchor)
    guard.close()
    for operation in (view.check,
            lambda: view._persistent_record_matches({'device': device}, {'device': device}),
            lambda: view._require_current_path(filesystem.anchor),
            lambda: maintenance._migration_inventory_matches(view, {}, [])):
        with pytest.raises(origin.PersistentOriginError, match='closed'):
            operation()


def test_final_retained_read_brackets_the_anchor_named_identity(tmp_path, monkeypatch, filesystem):
    original = tmp_path/'original'; original.write_bytes(b'exact original'); original.chmod(0o600)
    guard = evidence._EvidenceGuard(os.getuid(), os.getgid())
    guard.current_volume = origin.CurrentDataVolumeGuard()
    guard.hold(evidence._qualify_control_file(original, role='test-original', kind='config',
        profile=evidence._CustodyProfile(uid=os.getuid(), gid=os.getgid(), mode=0o600), limit=100))
    actual_read = evidence._read_descriptor
    def last_read_then_replace(*args):
        raw = actual_read(*args)
        filesystem.anchor.rename(filesystem.base/'retired-anchor')
        filesystem.anchor.mkdir(mode=0o700)
        return raw
    monkeypatch.setattr(evidence, '_read_descriptor', last_read_then_replace)
    try:
        with pytest.raises(origin.PersistentOriginError, match='changed'):
            guard.check()
    finally:
        guard.close()


@pytest.mark.parametrize('kind', ['file', 'link'])
def test_inventory_rejects_foreign_sample_even_if_restored_before_later_entry(
        tmp_path, monkeypatch, device_epoch, kind):
    if kind == 'link' and sys.platform != 'darwin':
        pytest.skip('native Darwin symlink ACL acquisition is unavailable on this host')
    root = tmp_path/'preserved'; root.mkdir(mode=0o700)
    target = root/'a-sampled'
    if kind == 'file':
        target.write_bytes(b'same bytes'); target.chmod(0o600)
    else:
        target.symlink_to('fixed text')
    later = root/'z-later'; later.write_bytes(b'later'); later.chmod(0o600)
    baseline = maintenance.inventory([root])
    device_epoch.device += 100
    sampled_inode = target.lstat().st_ino
    device_epoch.foreign[sampled_inode] = device_epoch.device+1
    # The old inventory-first implementation would sample foreign entry
    # metadata, then restore it on visiting the later entry, and finally accept
    # fresh lstat membership. Actual data/path predicates execute here.
    actual_lstat = os.lstat
    def restore_on_later(path, *args, **kwargs):
        if Path(path) == later:
            device_epoch.foreign.pop(sampled_inode, None)
        return actual_lstat(path, *args, **kwargs)
    monkeypatch.setattr(os, 'lstat', restore_on_later)
    with origin.CurrentDataVolumeGuard() as volume:
        guard = evidence._EvidenceGuard(os.getuid(), os.getgid()); guard.current_volume = volume
        view = evidence.RetainedV5ToV7Evidence(phase=evidence.EVIDENCE_PHASE_HISTORICAL,
            guard=guard, material={}, source_v5_database=later, source_v5_content_digest='',
            target_v7_database=later, target_v7_database_identity={}, control_config_bytes=b'',
            control_config_identity={}, backup_root=root)
        with pytest.raises(origin.PersistentOriginError, match='outside'):
            maintenance._migration_inventory_matches(view, baseline, [root])


def test_inventory_file_descriptor_device_drift_during_read_refuses(
        tmp_path, monkeypatch, device_epoch):
    root = tmp_path/'preserved'; root.mkdir(mode=0o700)
    file = root/'payload'; file.write_bytes(b'exact'); file.chmod(0o600)
    baseline = maintenance.inventory([root])
    device_epoch.device += 100
    inode = file.lstat().st_ino
    actual_read = os.pread
    def read_then_drift(fd, *args):
        raw = actual_read(fd, *args)
        if os.fstat(fd).st_ino == inode:
            device_epoch.foreign[inode] = device_epoch.device+1
        return raw
    monkeypatch.setattr(os, 'pread', read_then_drift)
    with origin.CurrentDataVolumeGuard() as volume:
        guard = evidence._EvidenceGuard(os.getuid(), os.getgid()); guard.current_volume = volume
        view = evidence.RetainedV5ToV7Evidence(phase=evidence.EVIDENCE_PHASE_HISTORICAL,
            guard=guard, material={}, source_v5_database=file, source_v5_content_digest='',
            target_v7_database=file, target_v7_database_identity={}, control_config_bytes=b'',
            control_config_identity={}, backup_root=root)
        with pytest.raises(maintenance.MaintenanceError, match='changed during read'):
            maintenance._migration_inventory_matches(view, baseline, [root])
