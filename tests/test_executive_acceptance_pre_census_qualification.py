"""Root issuer: real v5/selected/deeper/canary validators, synthetic host principal.

Existing fixture's accepted-ancestor and assignment inputs remain synthetic;
release/account/launchctl/ancestor policy observers map to disposable paths.
Actual SQLite, full eight-table projection, held leaves, lock, closed wire,
publication modes and final source revalidation remain production code.
"""
import hashlib
import json
import os
from types import SimpleNamespace
from pathlib import Path

import pytest
from control_plane import executive_backup as backup
from control_plane import fs_security
from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_acceptance_v5_to_v7 import (
    _preflight_fixture, _v5_to_v7_args, _no_external_effects, MIDDLE, SUCCESSOR,
)

OLD = '9'*40


def _fixture(tmp_path, monkeypatch, *, logical=False):
    f = _preflight_fixture(tmp_path, monkeypatch, logical=logical)
    database = f.runtime.store.path
    monkeypatch.setattr(backup, '_PRE_CENSUS_DATABASE', database)
    monkeypatch.setattr(backup, '_PRE_CENSUS_RELEASES', m.SYSTEM_ROOT/'releases')
    monkeypatch.setattr(backup, '_pre_census_control_identity', lambda: (os.getuid(), os.getgid()))
    # Explicit principal/host-policy seam, preserving real leaf checks and
    # ancestor identity brackets without requiring Root on the test host.
    monkeypatch.setattr(backup, 'os', SimpleNamespace(**{
        key: getattr(os, key) for key in dir(os) if key != 'geteuid'}, geteuid=lambda: 0))
    def ancestors(path, uid, gid):
        return tuple((str(p), p.lstat().st_dev, p.lstat().st_ino,
                      p.lstat().st_uid, p.lstat().st_gid, p.lstat().st_mode)
                     for p in path.parents)
    monkeypatch.setattr(backup, '_pre_census_ancestors', ancestors)
    monkeypatch.setattr(fs_security, 'has_macos_acl', lambda *args, **kwargs: False)
    monkeypatch.setattr(m, '_require_pre_census_stopped', lambda: None)
    monkeypatch.setattr(backup, '_SCHEMA_UPGRADE_RELEASE_OBSERVER', lambda: {
        'release_root': str(m.SYSTEM_ROOT/'releases'/SUCCESSOR), 'release_sha': SUCCESSOR,
        'release_tree_sha': 'b'*40, 'release_manifest_sha256': 'c'*64})
    (m.SYSTEM_ROOT/'releases'/SUCCESSOR).mkdir(parents=True, mode=0o700)
    barrier = database.parent/backup._UPGRADE_BARRIER_NAME
    payload = dict(schema_version=backup.UPGRADE_BARRIER_SCHEMA,
        operation_id='a'*32, database_path=str(database),
        tool_release_root=str(m.SYSTEM_ROOT/'releases'/OLD), release_sha=OLD,
        tool_release_tree_sha='b'*40, tool_release_manifest_sha256='c'*64,
        control_uid=os.getuid(), created_at='2026-10-23T16:00:00+00:00')
    barrier.write_bytes(backup._upgrade_receipt_bytes(payload)); barrier.chmod(0o600)
    f.barrier, f.barrier_payload = barrier, payload
    f.args = _v5_to_v7_args(f, qualify_v5_pre_census_continuation=True,
                            expected_operation_id=None, expected_barrier_sha256=None)
    f.destination = database.parent/backup.PRE_CENSUS_QUALIFICATION_NAME
    return f


def test_root_qualification_real_source_and_final_readable_contract(tmp_path, monkeypatch):
    f = _fixture(tmp_path, monkeypatch)
    barrier = f.barrier.read_bytes(), f.barrier.stat().st_ino
    selected = {p: p.read_bytes() for bundle in (f.middle_bundle, f.deeper_bundle) for p in bundle.iterdir()}
    result = m.prepare(f.args)
    payload = json.loads(f.destination.read_bytes())
    assert result['operation_id'] == f.barrier_payload['operation_id']
    assert result['qualification_identity']['sha256'] == hashlib.sha256(f.destination.read_bytes()).hexdigest()
    assert payload['original_barrier']['payload'] == f.barrier_payload
    assert payload['original_tool']['sha'] == OLD
    assert payload['recovery_tool']['sha'] == SUCCESSOR
    assert payload['selected_source']['sha'] == MIDDLE
    assert payload['backup_inventory_sha256'] == m.digest(m.inventory([Path(f.config['backup_root'])]))
    assert payload == backup._validate_pre_census_qualification(payload)
    assert f.destination.stat().st_mode & 0o777 == 0o440
    assert (f.barrier.read_bytes(), f.barrier.stat().st_ino) == barrier
    assert selected == {p: p.read_bytes() for p in selected}
    assert not m.bundle_path(SUCCESSOR).exists()
    assert not Path(str(f.runtime.store.path)+'-wal').exists()
    assert not Path(str(f.runtime.store.path)+'-shm').exists()


@pytest.mark.parametrize('fault', ['operation', 'barrier-cas', 'receipt', 'intent',
                                  'qualification', 'backup-extra', 'sequence'])
def test_qualification_initial_refusal_writes_no_child(tmp_path, monkeypatch, fault):
    f = _fixture(tmp_path, monkeypatch)
    if fault == 'operation': f.args.expected_operation_id = '0'*32
    elif fault == 'barrier-cas': f.args.expected_barrier_sha256 = '0'*64
    elif fault in ('receipt', 'intent', 'qualification'):
        name = {'receipt': backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME,
                'intent': backup.PRE_CENSUS_CONTINUATION_NAME,
                'qualification': backup.PRE_CENSUS_QUALIFICATION_NAME}[fault]
        (f.barrier.parent/name).write_bytes(b'foreign')
    elif fault == 'backup-extra':
        (Path(f.config['backup_root'])/'unexplained').write_bytes(b'foreign')
    else:
        import sqlite3
        connection = sqlite3.connect(f.runtime.store.path)
        connection.execute('PRAGMA journal_mode=DELETE')
        connection.execute('UPDATE sqlite_sequence SET seq=seq+1'); connection.commit(); connection.close()
    before = f.destination.read_bytes() if f.destination.exists() else None
    with pytest.raises((m.MaintenanceError, backup.ExecutiveSchemaUpgradeError, OSError)):
        m.prepare(f.args)
    assert (f.destination.read_bytes() if f.destination.exists() else None) == before
    assert f.barrier.exists()


@pytest.mark.parametrize('fault', ['late-receipt', 'late-inventory', 'late-barrier', 'late-old-tool'])
def test_final_boundary_retains_quarantine_without_valid_publication(tmp_path, monkeypatch, fault):
    f = _fixture(tmp_path, monkeypatch)
    real = m._qualify_v5_source_only
    calls = 0
    def qualify(*args, **kwargs):
        nonlocal calls
        result = real(*args, **kwargs); calls += 1
        if calls == 2:
            if fault == 'late-receipt':
                (f.barrier.parent/backup._UPGRADE_V6_TO_V7_COMPLETION_NAME).write_text('{}')
            elif fault == 'late-inventory':
                (Path(f.config['backup_root'])/'late').write_bytes(b'foreign')
            elif fault == 'late-barrier':
                f.barrier.write_bytes(f.barrier.read_bytes()+b' ')
            else:
                monkeypatch.setattr(m._evidence_owner(), '_verify_pinned_release', lambda *a: {})
        return result
    monkeypatch.setattr(m, '_qualify_v5_source_only', qualify)
    with pytest.raises((m.MaintenanceError, backup.ExecutiveSchemaUpgradeError, OSError)):
        m.prepare(f.args)
    assert f.barrier.exists()
    assert not f.destination.exists() or f.destination.stat().st_mode & 0o777 == 0o600
    assert not (f.barrier.parent/backup.PRE_CENSUS_CONTINUATION_NAME).exists()


@pytest.mark.parametrize('fault', ['non-root', 'mixed-action', 'mixed-selector', 'caller-dto'])
def test_explicit_action_never_accepts_caller_authority(tmp_path, monkeypatch, fault):
    f = _fixture(tmp_path, monkeypatch)
    if fault == 'non-root':
        monkeypatch.setattr(m.os, 'geteuid', lambda: os.getuid())
    elif fault == 'mixed-action':
        f.args.qualify_v5_source_only = True
    elif fault == 'mixed-selector':
        f.args.supersede_unstarted_preproof_sha = MIDDLE
    else:
        with pytest.raises(m.MaintenanceError, match='actual Root owner'):
            m._ServiceAdmissionLock(f.config, _pre_census_barrier=SimpleNamespace(
                payload=f.barrier_payload, identity={}, check=lambda: None))
        assert not f.destination.exists()
        return
    with pytest.raises(m.MaintenanceError):
        m.prepare(f.args)
    assert not f.destination.exists()


@pytest.mark.parametrize('fault', ['descriptor', 'raw-descriptor', 'baseline', 'inventory', 'canary', 'config'])
def test_consumer_binds_held_qualification_to_actual_selected_source(tmp_path, monkeypatch, fault):
    f = _fixture(tmp_path, monkeypatch)
    m.prepare(f.args)
    qualification = json.loads(f.destination.read_bytes())
    view = SimpleNamespace(material={'schema_version': m._evidence_owner().RECOVERED_MATERIAL_SCHEMA_VERSION},
                           pre_census_qualification=qualification)
    config_raw = (m.SYSTEM_ROOT/'config/control.json').read_bytes()
    m._bind_pre_census_selected(view, MIDDLE, f.middle, config_raw)
    key = {'descriptor':'descriptor_sha256','raw-descriptor':'descriptor_raw_sha256',
           'baseline':'baseline_sha256','inventory':'inventory_sha256',
           'canary':'prior_canary_sha256'}.get(fault)
    if key: qualification['selected_source'][key] = '0'*64
    else: config_raw += b' '
    with pytest.raises(m.MaintenanceError, match='selected source or control preimage'):
        m._bind_pre_census_selected(view, MIDDLE, f.middle, config_raw)


def test_root_qualification_preserves_normal_logical_var_mapping(tmp_path, monkeypatch):
    f = _fixture(tmp_path, monkeypatch, logical=True)
    result = m.prepare(f.args)
    value = json.loads(f.destination.read_bytes())
    assert value["database"]["path"] == str(f.runtime.store.path)
    assert value["host"]["runtime_root"] == str(f.runtime_root)
    assert value["host"]["backup_root"] == str(f.runtime_root.parent/"backups")
    assert result["operation_id"] == f.barrier_payload["operation_id"]
    assert value["backup_inventory_sha256"] == m.digest(m.inventory([f.runtime_root.parent/"backups"]))
