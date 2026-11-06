"""One unstarted v5 pre-proof preparation carries through a migrated v7 prestate.

``supersede_unstarted_preproof_v5_to_v7_v1`` is the only admission that may
select an original ``supersede_preproof_v1`` preparation after its source
release completed the offline v5->v6->v7 transitions. The working v7 prestate
is freshly sealed beside the Root upgrade evidence and the raw source control
preimage; the selected v5 lineage is never relabelled, and every selected or
deeper admission rule keeps its original semantics through the internal
old-mode view.

Every test here exercises the real owners: the real closed migrations, the
real backup/restore producers and receipts, the real acceptance summary
validator and the real joined evidence owner. Nothing substitutes a stub for a
production primitive on an accepting path. Where the joined tree cannot supply
an owner yet, the affected tests skip with that exact reason instead of
claiming the result; on the joined tree they run for real.
"""
import argparse
import copy
import fcntl
import gc
import dataclasses
import hashlib
import json
import os
import shutil
import sqlite3
import socket
import stat
import subprocess
import getpass
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance_maintenance as m
from ops.executive_os import autonomy_control as ac

# --- capability probes: honest skips, never stub owners ----------------------

try:
    from control_plane import executive_runtime as rt
except Exception:  # pragma: no cover - only on a broken checkout
    rt = None
_HAS_V7_RUNTIME = bool(
    rt is not None
    and len(getattr(rt, "_MIGRATIONS", ())) >= 7
    and hasattr(rt, "_NORMALIZED_V7_SCHEMA_DIGEST")
)

try:
    from ops.executive_os import schema_upgrade_evidence as evidence_owner
    _BRIDGE_MISSING = None
except ImportError as error:  # the Bridge returns this owner
    evidence_owner = None
    _BRIDGE_MISSING = error

# The supplied v5/newtyped/terminal fixture modules are genuine repo fixtures.
# They form an import chain into the wider checkout; when that chain is not
# present locally the fixture-consuming tests say exactly that and skip.
try:
    from tests.test_executive_acceptance_supersede_unstarted import (
        S as _FIXTURE_S, N as _FIXTURE_N,
        _fixture as unstarted_fixture, _rewrite,
    )
    from tests.test_executive_acceptance_supersede_preproof import (
        envelope, write_full_preproof_root,
    )
    _FIXTURES_MISSING = None
except Exception as error:  # pragma: no cover - partial checkout
    unstarted_fixture = _rewrite = envelope = write_full_preproof_root = None
    _FIXTURES_MISSING = error
    _FIXTURE_S, _FIXTURE_N = 'b'*40, 'c'*40

needs_v7 = pytest.mark.skipif(
    not _HAS_V7_RUNTIME,
    reason="joined runtime lacks the closed v6/v7 migrations (_MIGRATIONS[5:7])")
needs_bridge = pytest.mark.skipif(
    evidence_owner is None,
    reason="ops.executive_os.schema_upgrade_evidence owner is not joined yet")
needs_v7_bridge = pytest.mark.skipif(
    not (_HAS_V7_RUNTIME and evidence_owner is not None),
    reason="joined tree lacks the v7 runtime, the schema_upgrade_evidence owner, or both")
needs_source_fixtures = pytest.mark.skipif(
    unstarted_fixture is None,
    reason="supplied v5/newtyped/terminal fixture modules are not importable here: "
           + (f"{type(_FIXTURES_MISSING).__name__}: {_FIXTURES_MISSING}"
              if _FIXTURES_MISSING is not None else ""))

ACCEPTED = 'f'*40
DEEPER = 'b'*40
MIDDLE = 'e'*40
SUCCESSOR = 'c'*40
TOOL = 'd'*40
assert (_FIXTURE_S, _FIXTURE_N) == (DEEPER, SUCCESSOR)

_RealAdmissionLock = m._ServiceAdmissionLock


@pytest.fixture(autouse=True)
def _no_external_effects(monkeypatch):
    """Unit fixtures may not fall through into network, credentials or tools."""
    def forbidden(*args, **kwargs):
        raise AssertionError('external network/credential/process fallback in source fixture')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(os, 'system', forbidden)
    monkeypatch.setattr(getpass, 'getpass', forbidden)


def _v5_to_v7_descriptor(middle, *, evidence_sha='1'*64, source_control_sha='2'*64):
    """The closed v5-to-v7 working descriptor over one selected v5 preparation."""
    descriptor = {key: value for key, value in middle.items()
                  if key not in {'interrupted_preproof_sha', 'preproof_evidence_sha256'}}
    descriptor.update(schema_version=m.SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7,
                      successor_sha=SUCCESSOR,
                      superseded_unstarted_preproof_sha=MIDDLE,
                      superseded_descriptor_sha256=m.digest(middle),
                      schema_upgrade_evidence_sha256=evidence_sha,
                      source_control_config_sha256=source_control_sha)
    return descriptor


def _s_imode(path):
    return stat.S_IMODE(path.stat().st_mode)


def _write_private(path, raw, mode=0o400):
    """Create one exact regular file at a private mode, never truncating."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)
    os.chmod(path, mode)


# --- closed shape, view projection and the unchanged walk --------------------

@needs_source_fixtures
def test_v5_to_v7_descriptor_shape_is_closed_and_binds_distinct_releases(tmp_path, monkeypatch):
    unstarted_fixture(tmp_path, monkeypatch)
    middle = {key: 'f'*64 for key in m._DESCRIPTOR_V2_KEYS}
    for key in m._DESCRIPTOR_V2_KEYS:
        if key.endswith(('_job_id', '_attempt_id')) or key in {'worker_id', 'quota_class'}:
            middle[key] = 'fixture-' + key
        elif key.endswith('_event_id'):
            middle[key] = 1
    middle.update(schema_version=m.SCHEMA_PREPROOF, predecessor_sha=ACCEPTED,
                  successor_sha=MIDDLE, frozen_base_sha='d'*40,
                  interrupted_preproof_sha=DEEPER, preproof_evidence_sha256='3'*64,
                  superseded_descriptor_sha256='4'*64)
    descriptor = _v5_to_v7_descriptor(middle)
    assert set(descriptor) == m._DESCRIPTOR_UNSTARTED_PREPROOF_V5_TO_V7_KEYS
    assert m.SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7 in m._TERMINAL_CARRY_SCHEMAS
    bundle = m.bundle_path(SUCCESSOR)
    bundle.mkdir(parents=True)
    m.write_sealed(bundle/'descriptor.json', descriptor, public=True)
    assert m.descriptor_for(SUCCESSOR) == descriptor
    owner = object.__new__(m.Maintenance)
    owner.descriptor = descriptor
    assert owner.predecessor_recovery_required is False
    assert m.recovery_permitted(None, 'old', SUCCESSOR, 'worker', 'proof') is False
    for mutation in [{'unexpected': True}, {'superseded_unstarted_preproof_sha': SUCCESSOR},
                     {'superseded_unstarted_preproof_sha': ACCEPTED},
                     {'superseded_unstarted_preproof_sha': 'invalid'},
                     {'superseded_unstarted_preproof_sha': 5},
                     {'schema_upgrade_evidence_sha256': 'short'},
                     {'source_control_config_sha256': None},
                     {key: value for key, value in descriptor.items()
                      if key != 'source_control_config_sha256'},
                     dict(descriptor, schema_version=m.SCHEMA_UNSTARTED_PREPROOF)]:
        _rewrite(bundle/'descriptor.json', mutation)
        with pytest.raises(m.MaintenanceError):
            m.descriptor_for(SUCCESSOR)


def test_internal_v5_view_is_derived_only_from_the_selected_descriptor(tmp_path, monkeypatch):
    f = source_lineage_fixture(tmp_path, monkeypatch)
    middle = f.middle
    candidate = dict(f.candidate, baseline_sha256='9'*64, inventory_sha256='8'*64)
    view = m._unstarted_preproof_v5_to_v7_view(candidate)
    assert view['baseline_sha256'] == middle['baseline_sha256']
    assert view['inventory_sha256'] == middle['inventory_sha256']
    assert view['schema_version'] == m.SCHEMA_UNSTARTED_PREPROOF
    assert set(view) == m._DESCRIPTOR_UNSTARTED_PREPROOF_KEYS
    assert 'schema_upgrade_evidence_sha256' not in view
    assert 'source_control_config_sha256' not in view
    # The view is internal: it is never the sealed document and never hashes
    # to the working descriptor.
    assert view != candidate and m.digest(view) != m.digest(candidate)
    for foreign in [dict(candidate, schema_version=m.SCHEMA_UNSTARTED_PREPROOF),
                    {key: value for key, value in candidate.items()
                     if key != 'baseline_sha256'},
                    dict(candidate, unplanned=True),
                    {'schema_version': m.SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7},
                    'not-a-descriptor', None]:
        with pytest.raises(m.MaintenanceError):
            m._unstarted_preproof_v5_to_v7_view(foreign)


def source_lineage_fixture(tmp_path, monkeypatch):
    """Seal the unstarted v5 selected preparation with its deeper started prefix.

    The inherited unstarted fixture has a synthetic v5 store and accepted
    ancestor; this seals the middle six-entry preparation with the live
    envelope, no run marker and no acceptance leaf, exactly as the incumbent
    v5 mode leaves it before either retirement path may select it.
    """
    _candidate, deeper, before, artifacts, canary, deeper_bundle, runtime = (
        unstarted_fixture(tmp_path, monkeypatch))
    deeper['predecessor_sha'] = ACCEPTED
    _rewrite(deeper_bundle/'descriptor.json', deeper)
    root = write_full_preproof_root(runtime, deeper, monkeypatch)
    evidence, live_envelope = m.preproof_evidence(DEEPER)
    middle_bundle = m.bundle_path(MIDDLE)
    middle_bundle.mkdir()
    shutil.copyfile(deeper_bundle/'prestate.sqlite3', middle_bundle/'prestate.sqlite3')
    (middle_bundle/'prestate.sqlite3').chmod(0o400)
    middle = dict(deeper, schema_version=m.SCHEMA_PREPROOF, successor_sha=MIDDLE,
                  interrupted_preproof_sha=DEEPER,
                  superseded_descriptor_sha256=m.digest(deeper),
                  preproof_evidence_sha256=evidence,
                  prior_canary_sha256=m.digest(live_envelope))
    for filename, value in [('descriptor.json', middle),
                            ('preparing.json', {'schema_version': m.SCHEMA_PREPROOF}),
                            ('baseline.json', before), ('inventory.json', artifacts),
                            ('prior-secret-canary.json', live_envelope)]:
        m.write_sealed(middle_bundle/filename, value, public=filename == 'descriptor.json')
    candidate = _v5_to_v7_descriptor(middle)
    return SimpleNamespace(
        candidate=candidate, middle=middle, deeper=deeper, before=before,
        artifacts=artifacts, canary=canary, live_envelope=live_envelope,
        middle_bundle=middle_bundle, deeper_bundle=deeper_bundle, root=root,
        runtime=runtime)


@needs_source_fixtures
def test_view_walk_reenters_the_unchanged_selected_validators(tmp_path, monkeypatch):
    f = source_lineage_fixture(tmp_path, monkeypatch)
    paths = [*f.middle_bundle.iterdir(), *f.deeper_bundle.iterdir(), *f.root.iterdir()]
    original = {str(p): p.read_bytes() for p in paths}
    links = []
    real = m._validate_superseded_link

    def spy(descriptor, **kwargs):
        selected = real(descriptor, **kwargs)
        links.append((descriptor['schema_version'], selected['schema_version']))
        return selected

    monkeypatch.setattr(m, '_validate_superseded_link', spy)
    # The descriptor and its internal view traverse identically: the newtype
    # never reaches the link validator, which still admits only the original
    # unstarted supersede_preproof_v1 preparation.
    m.validate_superseded_binding(f.candidate, prior_canary=f.live_envelope)
    view = m._unstarted_preproof_v5_to_v7_view(f.candidate)
    m.validate_superseded_binding(view, prior_canary=f.live_envelope)
    assert links == [(m.SCHEMA_UNSTARTED_PREPROOF, m.SCHEMA_PREPROOF),
                     (m.SCHEMA_PREPROOF, m.SCHEMA_V2)] * 2
    assert original == {str(p): p.read_bytes() for p in paths}
    assert not (f.middle_bundle/'run-started.json').exists()
    assert not (f.middle_bundle/'carry-forward.json').exists()


@pytest.mark.parametrize('fault', [
    'nested-newtype', 'old-v2-selected', 'prejob-selected', 'cycle', 'depth',
    'selected-baseline', 'selected-canary', 'selected-preparing', 'selected-marker',
    'selected-carry', 'selected-extra', 'selected-schema', 'selected-digest',
    'deeper-marker', 'live-canary', 'canary-binding',
])
@needs_source_fixtures
def test_view_walk_keeps_every_old_refusal(tmp_path, monkeypatch, fault):
    f = source_lineage_fixture(tmp_path, monkeypatch)
    candidate = dict(f.candidate)
    if fault == 'nested-newtype':
        candidate['superseded_unstarted_preproof_sha'] = SUCCESSOR
    elif fault == 'old-v2-selected':
        candidate['superseded_unstarted_preproof_sha'] = DEEPER
        candidate['superseded_descriptor_sha256'] = m.digest(f.deeper)
    elif fault == 'prejob-selected':
        candidate['superseded_unstarted_preproof_sha'] = ACCEPTED
    elif fault == 'cycle':
        candidate['superseded_unstarted_preproof_sha'] = candidate['successor_sha']
    elif fault == 'depth':
        candidate['predecessor_sha'] = DEEPER
    elif fault == 'selected-baseline':
        _rewrite(f.middle_bundle/'baseline.json', {'drift': True})
    elif fault == 'selected-canary':
        _rewrite(f.middle_bundle/'prior-secret-canary.json', {'drift': True})
    elif fault == 'selected-preparing':
        _rewrite(f.middle_bundle/'preparing.json', {'schema_version': m.SCHEMA_V2})
    elif fault == 'selected-marker':
        m.write_sealed(f.middle_bundle/'run-started.json',
                       {'schema_version': m.SCHEMA_PREPROOF,
                        'descriptor_sha256': m.digest(f.middle)}, public=True)
    elif fault == 'selected-carry':
        m.write_sealed(f.middle_bundle/'carry-forward.json',
                       {'schema_version': m.SCHEMA_PREPROOF, 'passed': True}, public=True)
    elif fault == 'selected-extra':
        (f.middle_bundle/'extra.bin').write_bytes(b'x')
    elif fault == 'selected-schema':
        _rewrite(f.middle_bundle/'descriptor.json',
                 dict(f.middle, schema_version=m.SCHEMA_PREJOB))
    elif fault == 'selected-digest':
        candidate['superseded_descriptor_sha256'] = '4'*64
    elif fault == 'deeper-marker':
        _rewrite(f.deeper_bundle/'run-started.json',
                 {'schema_version': m.SCHEMA_V2, 'descriptor_sha256': '0'*64})
    elif fault == 'canary-binding':
        candidate['prior_canary_sha256'] = '0'*64
    args = {'prior_canary': {'drift': True} if fault == 'live-canary' else f.live_envelope}
    if fault in {'selected-baseline', 'selected-canary', 'selected-preparing',
                 'selected-marker', 'selected-carry', 'selected-extra', 'selected-schema',
                 'selected-digest', 'deeper-marker'}:
        args['before'] = f.before
        args['artifacts'] = f.artifacts
    with pytest.raises(m.MaintenanceError):
        m.validate_superseded_binding(candidate, **args)


@needs_source_fixtures
def test_incumbent_v5_mode_still_refuses_the_v5_to_v7_selection(tmp_path, monkeypatch):
    f = source_lineage_fixture(tmp_path, monkeypatch)
    incumbent = {key: value for key, value in f.candidate.items()
                 if key not in {'schema_upgrade_evidence_sha256',
                                'source_control_config_sha256'}}
    incumbent.update(schema_version=m.SCHEMA_SUPERSEDE, superseded_unstarted_sha=MIDDLE)
    # The incumbent unstarted selector never selects a pre-proof preparation.
    with pytest.raises(m.MaintenanceError,
                       match='superseded descriptor or accepted ancestor mismatch'):
        m.validate_superseded_binding(incumbent)
    # The old mode also keeps refusing the preproof preparation itself.
    old_candidate = dict(f.candidate, superseded_unstarted_preproof_sha=DEEPER,
                         superseded_descriptor_sha256=m.digest(f.deeper))
    with pytest.raises(m.MaintenanceError,
                       match='superseded descriptor or accepted ancestor mismatch'):
        m.validate_superseded_binding(m._unstarted_preproof_v5_to_v7_view(old_candidate),
                                      prior_canary=f.live_envelope)


# --- frozen evidence material, tool release and origin records ---------------

def _material(runtime_root, backup_root, release_sha=TOOL):
    return {'schema_version': evidence_owner.MATERIAL_SCHEMA_VERSION,
            'phase': evidence_owner.EVIDENCE_PHASE_INITIAL,
            'host': {'runtime_root': str(runtime_root), 'backup_root': str(backup_root),
                     'control_uid': 450, 'control_gid': 450},
            'chain': {'tool_release': {'root': str(Path(runtime_root)/'releases'/release_sha),
                                       'sha': release_sha, 'tree_sha': 'b'*40,
                                       'manifest_sha256': 'c'*64}},
            'origin_records': [{} for _ in range(12)]}


def test_material_shape_and_original_tool_release_are_frozen(tmp_path):
    runtime_root = tmp_path/'var'/'db'/'mastermind-executive'/'control'/'db'
    backup_root = tmp_path/'var'/'db'/'mastermind-executive'/'control'/'backups'
    material = _material(runtime_root, backup_root)
    assert m._validate_v5_to_v7_material(material) == (runtime_root, backup_root)
    assert m._v5_to_v7_tool_release(material) == TOOL
    # The original migration tool sha is pinned in the chain, never the working
    # descriptor's proof successor.
    other = _material(runtime_root, backup_root, release_sha=SUCCESSOR)
    assert m._v5_to_v7_tool_release(other) == SUCCESSOR
    for fault, mutation in [
            ('no-runtime-root', {'runtime_root': None}),
            ('relative-root', {'runtime_root': 'rel/ative'}),
            ('traversing-root', {'runtime_root': str(runtime_root/'..')}),
            ('no-backup-root', {'backup_root': None}),
            ('uid-type', {'control_uid': '450'}),
            ('gid-negative', {'control_gid': -1}),
            ('no-chain', {'chain': None}),
            ('empty-chain', {'chain': {}}),
            ('tool-extra', {'chain': {'tool_release': dict(
                material['chain']['tool_release'], extra=True)}}),
            ('tool-short-sha', {'chain': {'tool_release': dict(
                material['chain']['tool_release'], sha='short')}}),
            ('tool-successor-is-not-forbidden-but-is-pinned', {
                'chain': {'tool_release': dict(material['chain']['tool_release'],
                                               tree_sha='nope')}}),
            ('tool-missing-manifest', {'chain': {'tool_release': {
                key: value for key, value in material['chain']['tool_release'].items()
                if key != 'manifest_sha256'}}})]:
        with pytest.raises(m.MaintenanceError):
            m._validate_v5_to_v7_material(dict(material, **mutation))
    for foreign in [None, 'material', 5, [], {}, {'runtime_root': str(runtime_root)}]:
        with pytest.raises(m.MaintenanceError):
            m._validate_v5_to_v7_material(foreign)


def test_origin_records_are_closed_permission_ints_with_original_addresses():
    record = {'path': '/private/var/db/backup/proof.sqlite3', 'device': 1, 'inode': 2,
              'uid': 450, 'gid': 450, 'mode': 0o400, 'nlink': 1, 'size': 8192,
              'mtime_ns': 3, 'ctime_ns': 4, 'sha256': 'a'*64}
    assert m._v5_to_v7_origin_record(record) == record
    for fault in [dict(record, mode=stat.S_IFREG | 0o400),      # file-type bits
                  dict(record, mode=-1), dict(record, mode=0o10000),
                  dict(record, inode=0), dict(record, inode=-2),
                  dict(record, nlink=2), dict(record, nlink=True),
                  dict(record, size=-1), dict(record, mtime_ns='3'),
                  dict(record, sha256='short'), dict(record, path='relative.sqlite3'),
                  dict(record, path='/a/../../b'), {key: value for key, value in record.items()
                                                    if key != 'ctime_ns'},
                  dict(record, unexpected=True)]:
        with pytest.raises(m.MaintenanceError):
            m._v5_to_v7_origin_record(fault)


# --- schema-specific carry history: gates run before any retained owner ------

def _v7_store_fixture(tmp_path, monkeypatch):
    """One real current v7 runtime store with its canonical offline lock."""
    state = tmp_path/'var'/'db'/'mastermind-executive'/'control'/'db'/'data'/'control_plane'
    state.mkdir(parents=True, mode=0o700)
    database = state/'executive.sqlite3'
    runtime_root = state.parent.parent
    runtime = rt.Runtime.at(runtime_root)
    assert Path(runtime.store.path) == database
    lock = state/m._SERVICE_LOCK
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    backup_root = tmp_path/'var'/'db'/'mastermind-executive'/'control'/'backups'
    backup_root.mkdir(parents=True, mode=0o700)
    return SimpleNamespace(runtime=runtime, database=database, lock=lock, state=state,
                           runtime_root=runtime_root, backup_root=backup_root)


def _restore_bundle_fixture(tmp_path, monkeypatch):
    """One sealed accepted v5-to-v7 bundle over real producer receipts.

    Everything here is the genuine owner output: a real current v7 store, a
    real online backup with its manifest, the real verification and drill, the
    real offline restore receipt, the real closed PASS summary validator input
    and the real Root-config preimage the descriptor pins.
    """
    from control_plane import executive_backup as backup
    store = _v7_store_fixture(tmp_path, monkeypatch)
    release_root = tmp_path/'releases'/TOOL
    release_root.mkdir(parents=True)
    receipt = backup.create_online_backup(store.runtime.store, store.backup_root)
    verification = backup.verify_backup(receipt.database_path, receipt.manifest_path)
    drill = backup.verify_restore_drill(receipt.database_path, receipt.manifest_path)
    applied = backup.restore_backup_offline(store.runtime_root, receipt.database_path,
                                            receipt.manifest_path)
    backup_name = Path(receipt.database_path).name
    origins = {}
    for key, path in (('database', Path(receipt.database_path)),
                      ('manifest', Path(receipt.manifest_path))):
        info = path.lstat()
        origins[key] = {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino,
                        'uid': info.st_uid, 'gid': info.st_gid,
                        'mode': stat.S_IMODE(info.st_mode), 'nlink': info.st_nlink,
                        'size': info.st_size, 'mtime_ns': info.st_mtime_ns,
                        'ctime_ns': info.st_ctime_ns,
                        'sha256': (receipt.database_sha256 if key == 'database'
                                   else receipt.manifest_sha256)}
    material = _material(store.runtime_root, store.backup_root)
    material['control_uid'] = origins['database']['uid']
    material['control_gid'] = origins['database']['gid']
    verification_dict = dataclasses.asdict(verification)
    drill_dict = dataclasses.asdict(drill)
    applied_dict = dataclasses.asdict(applied)
    summary_raw = json.dumps(
        _acceptance_summary(store, tmp_path/'system'), sort_keys=True, indent=2).encode()
    restore_evidence = {
        'schema_version': m._V5_TO_V7_RESTORE_EVIDENCE_SCHEMA,
        'proof_job_ids': ['JOB-proof-1', 'JOB-proof-2'],
        'acceptance_summary_sha256': hashlib.sha256(summary_raw).hexdigest(),
        'receipt_sha256': {
            'backup-created.json': hashlib.sha256(json.dumps(
                {'ok': True, 'result': dataclasses.asdict(receipt)},
                sort_keys=True, indent=2).encode()).hexdigest(),
            'backup-verified.json': hashlib.sha256(json.dumps(
                {'ok': True, 'result': verification_dict}, sort_keys=True, indent=2).encode()).hexdigest(),
            'restore-drill.json': hashlib.sha256(json.dumps(
                drill_dict, sort_keys=True, indent=2).encode()).hexdigest(),
            'restore-applied.json': hashlib.sha256(json.dumps(
                applied_dict, sort_keys=True, indent=2).encode()).hexdigest()},
        'backup': {'name': backup_name, 'database_sha256': receipt.database_sha256,
                   'manifest_sha256': receipt.manifest_sha256},
        'origins': origins,
        'verification': verification_dict,
        'restore_drill': drill_dict,
        'current_runtime_database': {'path': str(store.database),
                                     'device': store.database.stat().st_dev,
                                     'inode': store.database.stat().st_ino},
        'schema_upgrade_evidence_sha256': m.digest(material),
    }
    descriptor = _v5_to_v7_descriptor(
        _middle_descriptor(),
        evidence_sha=m.digest(material),
        source_control_sha=hashlib.sha256(b'old-config').hexdigest())
    return SimpleNamespace(
        store=store, receipt=receipt, verification=verification_dict, drill=drill_dict,
        applied=applied_dict, material=material, origins=origins,
        restore_evidence=restore_evidence, descriptor=descriptor,
        summary_raw=summary_raw, backup_name=backup_name)


def _acceptance_summary(store, system_root):
    """A real closed PASS summary the existing arming owner validates."""
    return {
        'schema_version': 'mastermind.executive_host_acceptance/v1',
        'passed': True,
        'observed_at': '2026-10-23T00:00:00+00:00',
        'exact_origin_master_sha': SUCCESSOR,
        'release_root': os.fspath(Path(system_root)/'releases'/SUCCESSOR),
        'control_uid': os.getuid() + 1, 'worker_uid': os.getuid() + 2,
        'success_job_id': 'JOB-proof-1',
        'interrupted_requeued_job_id': 'JOB-proof-2',
        'detached_session_cleanup': 'PASS', 'terminal_assignment_sealing': 'PASS',
        'lost_workspace_rotation_boundary': 'PASS', 'backup_restore': 'PASS',
        'no_public_listener': 'PASS', 'credential_leakage_scan': 'PASS',
        'financial_scheduler_activation': 'NOT_REQUESTED_OR_TOUCHED',
    }


def _middle_descriptor(store):
    keys = m._DESCRIPTOR_V2_KEYS
    middle = {key: 'f'*64 for key in keys}
    for key in keys:
        if key.endswith(('_job_id', '_attempt_id')) or key in {'worker_id', 'quota_class'}:
            middle[key] = 'fixture-' + key
        elif key.endswith('_event_id'):
            middle[key] = 1
    middle.update(schema_version=m.SCHEMA_PREPROOF, predecessor_sha=ACCEPTED,
                  successor_sha=MIDDLE, frozen_base_sha='d'*40,
                  interrupted_preproof_sha=DEEPER, preproof_evidence_sha256='3'*64,
                  superseded_descriptor_sha256='4'*64)
    return middle


def _seal_carry_bundle(f, tmp_path, monkeypatch, *, faults=None):
    """Seal the accepted newtype bundle with its carry receipt and receipts."""
    faults = faults or {}
    store = f.store
    monkeypatch.setattr(m, 'SYSTEM_ROOT', tmp_path/'system')
    (m.SYSTEM_ROOT/'config').mkdir(parents=True)
    (m.SYSTEM_ROOT/'releases'/SUCCESSOR).mkdir(parents=True)
    config = {'runtime_root': str(store.runtime_root),
              'backup_root': str(store.backup_root)}
    _write_private(m.SYSTEM_ROOT/'config'/'control.json',
                   json.dumps(config).encode(), 0o440)
    monkeypatch.setattr(m, '_TRUSTED_UID', os.getuid())
    monkeypatch.setattr(m, '_TRUSTED_GID', os.getgid())
    monkeypatch.setattr(m, '_sealed_ancestors', lambda path: [])
    monkeypatch.setattr(m, 'has_macos_acl', lambda *args, **kwargs: False)
    monkeypatch.setattr(ac, 'RUNTIME_ROOT', store.runtime_root.parent.parent)
    monkeypatch.setattr(ac, '_has_acl', lambda *args, **kwargs: False)
    import pwd
    import grp
    monkeypatch.setattr(pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(grp, 'getgrnam', lambda name: SimpleNamespace(gr_gid=os.getgid()))
    monkeypatch.setattr(ac, 'CONTROL_USER', 'fixture-control')
    monkeypatch.setattr(ac, 'CONTROL_GROUP', 'fixture-control')
    acceptance = store.runtime_root.parent.parent/'control'/'acceptance'/SUCCESSOR
    acceptance.mkdir(parents=True)
    documents = {
        'backup-created.json': {'ok': True, 'result': dataclasses.asdict(f.receipt)},
        'backup-verified.json': {'ok': True, 'result': f.verification},
        'restore-drill.json': f.drill,
        'restore-applied.json': f.applied,
    }
    documents.update(faults.get('documents', {}))
    for name, value in documents.items():
        _write_private(acceptance/name, json.dumps(value, sort_keys=True,
                                                   indent=2).encode() + b'\n', 0o400)
    _write_private(acceptance/'acceptance-summary.json', f.summary_raw, 0o400)
    material = faults.get('material', f.material)
    restore_evidence = faults.get('restore_evidence', f.restore_evidence)
    descriptor = f.descriptor
    if 'descriptor' in faults:
        descriptor = faults['descriptor']
    elif 'material' in faults or 'restore_evidence' in faults:
        descriptor = dict(f.descriptor,
                          schema_upgrade_evidence_sha256=m.digest(material))
    carry = dict(schema_version=m.SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7, passed=True,
                 baseline_preserved=True, descriptor_sha256=m.digest(descriptor),
                 acceptance_summary_sha256=hashlib.sha256(f.summary_raw).hexdigest(),
                 schema_upgrade_evidence_sha256=m.digest(material),
                 acceptance_restore_evidence_sha256=m.digest(restore_evidence))
    if 'carry' in faults:
        carry = faults['carry']
    bundle = m.bundle_path(SUCCESSOR)
    bundle.mkdir()
    m.write_sealed(bundle/'descriptor.json', descriptor, public=True)
    m.write_sealed(bundle/'run-started.json',
                   {'schema_version': descriptor['schema_version'],
                    'descriptor_sha256': m.digest(descriptor)}, public=True)
    m.write_sealed(bundle/m._V5_TO_V7_EVIDENCE_NAME, material)
    m.write_sealed(bundle/m._V5_TO_V7_RESTORE_EVIDENCE_NAME, restore_evidence)
    m.write_sealed_bytes(bundle/m._V5_TO_V7_SOURCE_CONTROL_NAME, b'old-config')
    m.write_sealed(bundle/'carry-forward.json', carry, public=True)
    m.write_sealed(bundle/'baseline.json', {'tables': {}, 'schema': []})
    return SimpleNamespace(bundle=bundle, descriptor=descriptor, carry=carry,
                           acceptance=acceptance, material=material,
                           restore_evidence=restore_evidence)


def _validate_carry(f, sealed, monkeypatch):
    """Run the real carry chain over the sealed accepted predecessor."""
    summaries = {SUCCESSOR: ({'success_job_id': 'JOB-proof-1'}, f.summary_raw)}
    monkeypatch.setattr(m, 'summary_document',
                        lambda sha: summaries[sha])
    real = m.descriptor_for
    monkeypatch.setattr(m, 'descriptor_for',
                        lambda sha: sealed.descriptor if sha == SUCCESSOR else real(sha))
    m.validate_carry_receipt(SUCCESSOR, hashlib.sha256(f.summary_raw).hexdigest())


def test_carry_without_original_run_refuses_before_retained_owner(tmp_path, monkeypatch):
    _f, descriptor, _material, restore_evidence, bundle = _sealed_newmode_bundle(
        tmp_path, monkeypatch)
    summary = b'accepted-summary'
    m.write_sealed(bundle/'carry-forward.json',
                   _carry_receipt(descriptor, summary, restore_evidence), public=True)
    reached = []
    def forbidden():
        reached.append(True)
        raise AssertionError('unaccepted hash bundle reached retained owner')
    monkeypatch.setattr(m, '_evidence_owner', forbidden)
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_carry_receipt(SUCCESSOR, hashlib.sha256(summary).hexdigest())
    assert not reached


@needs_bridge
@needs_source_fixtures
def test_carry_self_hashes_without_real_run_are_not_acceptance(tmp_path, monkeypatch):
    _f, descriptor, _material, restore_evidence, bundle = _sealed_newmode_bundle(
        tmp_path, monkeypatch)
    summary = b'accepted-summary'
    carry = _carry_receipt(descriptor, summary, restore_evidence)
    m.write_sealed(bundle/'carry-forward.json', carry, public=True)
    real = m.descriptor_for
    monkeypatch.setattr(m, 'descriptor_for',
                        lambda sha: descriptor if sha == SUCCESSOR else real(sha))
    monkeypatch.setattr(m, 'prior_carry_material',
                        lambda sha, **kwargs: (descriptor, {}, {}))
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_carry_receipt(SUCCESSOR, hashlib.sha256(summary).hexdigest())
    assert set(m.sealed_json(bundle/'carry-forward.json')) == {
        'schema_version', 'passed', 'baseline_preserved', 'descriptor_sha256',
        'acceptance_summary_sha256', 'schema_upgrade_evidence_sha256',
        'acceptance_restore_evidence_sha256'}
    for fault, receipt, remove in [
            ('schema-pin', dict(carry, schema_upgrade_evidence_sha256='3'*64), None),
            ('restore-pin', dict(carry, acceptance_restore_evidence_sha256='4'*64), None),
            ('old-shape', {key: carry[key] for key in
                           ('schema_version', 'passed', 'descriptor_sha256',
                            'acceptance_summary_sha256', 'baseline_preserved')}, None),
            ('missing-restore-evidence', carry, m._V5_TO_V7_RESTORE_EVIDENCE_NAME),
            ('missing-upgrade-evidence', carry, m._V5_TO_V7_EVIDENCE_NAME)]:
        if remove:
            (bundle/remove).chmod(0o600)
            (bundle/remove).unlink()
        else:
            (bundle/'carry-forward.json').chmod(0o600)
            (bundle/'carry-forward.json').unlink()
            m.write_sealed(bundle/'carry-forward.json', receipt, public=True)
        with pytest.raises((m.MaintenanceError, OSError)):
            m.validate_carry_receipt(SUCCESSOR, hashlib.sha256(summary).hexdigest())


def _sealed_newmode_bundle(tmp_path, monkeypatch):
    f = source_lineage_fixture(tmp_path, monkeypatch)
    bundle = m.bundle_path(SUCCESSOR)
    bundle.mkdir()
    material = {'runtime_root': str(f.runtime), 'backup_root': str(f.runtime),
                'control_uid': 450, 'control_gid': 450,
                'chain': {'tool_release': {'root': 'root', 'sha': TOOL, 'tree_sha': 'b'*40,
                                           'manifest_sha256': 'c'*64}}}
    restore_evidence = {'restore': 'fixture-evidence'}
    descriptor = _v5_to_v7_descriptor(f.middle,
                                      evidence_sha=m.digest(material),
                                      source_control_sha=hashlib.sha256(b'old-config').hexdigest())
    m.write_sealed(bundle/'descriptor.json', descriptor, public=True)
    m.write_sealed(bundle/m._V5_TO_V7_EVIDENCE_NAME, material)
    m.write_sealed(bundle/m._V5_TO_V7_RESTORE_EVIDENCE_NAME, restore_evidence)
    m.write_sealed_bytes(bundle/m._V5_TO_V7_SOURCE_CONTROL_NAME, b'old-config')
    return f, descriptor, material, restore_evidence, bundle


def _carry_receipt(descriptor, summary, restore_evidence):
    return dict(schema_version=descriptor['schema_version'], passed=True,
                baseline_preserved=True, descriptor_sha256=m.digest(descriptor),
                acceptance_summary_sha256=hashlib.sha256(summary).hexdigest(),
                schema_upgrade_evidence_sha256=descriptor['schema_upgrade_evidence_sha256'],
                acceptance_restore_evidence_sha256=m.digest(restore_evidence))


@needs_bridge
@needs_source_fixtures
def test_future_carry_refuses_synthetic_hashes_without_original_run(tmp_path, monkeypatch):
    f, descriptor, _material, restore_evidence, bundle = _sealed_newmode_bundle(
        tmp_path, monkeypatch)
    summary = b'accepted-summary'
    receipt = _carry_receipt(descriptor, summary, restore_evidence)
    m.write_sealed(bundle/'carry-forward.json', receipt, public=True)
    summaries = {ACCEPTED: ({'success_job_id': 'JOB-proof'}, b'ancestor-summary'),
                 SUCCESSOR: ({'success_job_id': 'JOB-proof'}, summary)}
    monkeypatch.setattr(m, 'summary_document', lambda sha: summaries[sha])
    future = {key: value for key, value in descriptor.items()
              if key not in {'superseded_unstarted_preproof_sha',
                             'superseded_descriptor_sha256',
                             'schema_upgrade_evidence_sha256',
                             'source_control_config_sha256'}}
    future_material = {
        'prior_descriptor_sha256': m.digest(descriptor),
        'prior_carry_sha256': m.digest(receipt),
        'prior_summary_sha256': hashlib.sha256(summary).hexdigest(),
        'frozen_base_sha': descriptor['frozen_base_sha'],
    }
    future.update(schema_version=m.SCHEMA_V2, predecessor_sha=SUCCESSOR,
                  successor_sha='1'*40, **future_material)
    future_bundle = m.bundle_path('1'*40)
    future_bundle.mkdir()
    m.write_sealed(future_bundle/'descriptor.json', future, public=True)
    # The future carry walk re-enters the real prior material reader for the
    # v5-to-v7 predecessor; the accepted ancestor stays a fixture seam.
    real_prior = m.prior_carry_material
    ancestor_root = {'root_job_id': descriptor['root_job_id'],
                     'root_identity_sha256': descriptor['root_identity_sha256'],
                     'root_event_id': descriptor['root_event_id'],
                     'root_event_sha256': descriptor['root_event_sha256']}

    def prior_seam(sha, **kwargs):
        if sha == SUCCESSOR:
            return real_prior(sha, **kwargs)
        return (ancestor_root, {'success_job_id': 'JOB-proof'}, {})

    monkeypatch.setattr(m, 'prior_carry_material', prior_seam)
    walks = []
    real = m.validate_superseded_binding

    def spy(walked, **kwargs):
        walks.append((walked['schema_version'], kwargs.get('historical', False)))
        return real(walked, **kwargs)

    monkeypatch.setattr(m, 'validate_superseded_binding', spy)
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_prior_carry_binding(future)
    # The incomplete synthetic run never becomes an accepted predecessor:
    # the newtype entered the historical walk
    # itself and the exact pinned restore evidence was required before any
    # continuation.
    assert walks == []
    _rewrite(bundle/m._V5_TO_V7_RESTORE_EVIDENCE_NAME,
             dict(restore_evidence, tampered=True))
    with pytest.raises(m.MaintenanceError,
                       match='no matching maintenance PASS receipt'):
        m.validate_prior_carry_binding(future)
    # No bare historical escape: without the schema-specific PASS receipt the
    # newtype predecessor refuses even on the historical walk.
    (bundle/'carry-forward.json').chmod(0o600)
    (bundle/'carry-forward.json').unlink()
    with pytest.raises((m.MaintenanceError, OSError)):
        m.validate_prior_carry_binding(future)


# --- working inventory merge and canonical JSON data -------------------------

def test_working_inventory_is_exact_source_plus_qualified_additions(tmp_path):
    root = tmp_path/'backup-root'
    (root/'pair').mkdir(parents=True)
    roots = [root]
    source_inventory = {str(root): {'uid': 0, 'gid': 0, 'mode': 0o755, 'directory': True,
                                    'device': 1, 'inode': 2}}
    addition = {'uid': 0, 'gid': 0, 'mode': 0o400, 'nlink': 1, 'sha256': 'a'*64}
    additions = {str(root/'pair'/f'v{n}.sqlite3'): addition for n in range(8)}
    working = m._v5_to_v7_working_inventory(source_inventory, additions, roots)
    assert set(working) == set(source_inventory) | set(additions)
    assert working[str(root/'pair'/'v0.sqlite3')] == addition
    for fault in [{f'p{n}': addition for n in range(7)},
                  {str(root/f'pair{n}'/'x.sqlite3'): addition for n in range(9)},
                  {str(tmp_path/'outside.sqlite3'): addition},
                  {str(root/'pair'/'v0.sqlite3'): dict(addition, nlink=None)},
                  {str(root/'pair'/'v0.sqlite3'): dict(addition, sha256='short')}]:
        with pytest.raises(m.MaintenanceError):
            m._v5_to_v7_working_inventory(source_inventory, fault, roots)


def test_json_data_refuses_unknown_types_instead_of_coercing():
    assert m._json_data({'tuple': (1, 2)}) == {'tuple': [1, 2]}
    assert m._json_data({'nested': {'b': 1, 'a': 2}}) == {'nested': {'a': 2, 'b': 1}}
    with pytest.raises(TypeError):
        m._json_data({'bytes': b'raw'})


# --- sealed raw preimage writer ----------------------------------------------

def test_write_sealed_bytes_keeps_the_exact_raw_preimage(tmp_path, monkeypatch):
    monkeypatch.setattr(m, '_TRUSTED_UID', os.getuid())
    monkeypatch.setattr(m, '_TRUSTED_GID', os.getgid())
    raw = b'{"indent":  "spelled   exactly",\n "trailing": "bytes"}\n'
    path = tmp_path/'source-control.json'
    m.write_sealed_bytes(path, raw)
    assert path.read_bytes() == raw
    assert _s_imode(path) == 0o400
    with pytest.raises(FileExistsError):
        m.write_sealed_bytes(path, raw)
    with pytest.raises(m.MaintenanceError):
        m.write_sealed_bytes(tmp_path/'inventory.json', b'x' * (m._MAX_INVENTORY_BYTES + 1))
    assert m.sealed_bytes(path, m._MAX_DOCUMENT_BYTES) == raw
    with pytest.raises(m.MaintenanceError):
        m.sealed_bytes(path, 4)


# --- qualified Root control config pin ---------------------------------------

def _config_pin_fixture(tmp_path, monkeypatch):
    system = tmp_path/'system'
    (system/'config').mkdir(parents=True)
    path = system/'config'/'control.json'
    _write_private(path, json.dumps({'runtime_root': str(tmp_path/'runtime')}).encode(),
                   0o440)
    monkeypatch.setattr(m, 'SYSTEM_ROOT', system)
    monkeypatch.setattr(m, '_TRUSTED_UID', os.getuid())
    monkeypatch.setattr(m, '_TRUSTED_GID', os.getgid())
    monkeypatch.setattr(m, '_sealed_ancestors', lambda p: [])
    monkeypatch.setattr(m, 'has_macos_acl', lambda *a, **k: False)
    monkeypatch.setattr(ac, '_has_acl', lambda *a, **k: False)
    import pwd
    import grp
    monkeypatch.setattr(pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(grp, 'getgrnam', lambda name: SimpleNamespace(gr_gid=os.getgid()))
    monkeypatch.setattr(ac, 'CONTROL_GROUP', 'fixture-control')
    return path


def test_root_config_pin_holds_and_rechecks_the_exact_preimage(tmp_path, monkeypatch):
    path = _config_pin_fixture(tmp_path, monkeypatch)
    with m._RootConfig() as holder:
        raw = path.read_bytes()
        assert holder.raw == raw
        assert holder.value == json.loads(raw)
        assert holder.check() == holder.value
        # Any content drift through the same name refuses at the edge.
        replacement = tmp_path/'new-config.json'
        _write_private(replacement, json.dumps({'runtime_root': 'drift'}).encode(), 0o440)
        os.replace(replacement, path)
        with pytest.raises(m.MaintenanceError):
            holder.check()
    # A config that is not the sealed Root-owned 0440 preimage refuses.
    path.chmod(0o600)
    with pytest.raises((m.MaintenanceError, OSError)):
        m._RootConfig()
    path.chmod(0o440)
    os.unlink(path)
    with pytest.raises((m.MaintenanceError, OSError)):
        m._RootConfig()


# --- canonical admission lock -------------------------------------------------

def _lock_fixture(tmp_path, monkeypatch):
    root = tmp_path/'var'/'db'/'mastermind-executive'/'control'/'db'
    state = root/'data'/'control_plane'
    state.mkdir(parents=True, mode=0o700)
    lock = state/m._SERVICE_LOCK
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    import fcntl
    import pwd
    import grp
    monkeypatch.setattr(m, '_TRUSTED_UID', os.getuid())
    monkeypatch.setattr(m, '_TRUSTED_GID', os.getgid())
    monkeypatch.setattr(m, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(m, 'has_macos_acl', lambda *args, **kwargs: False)
    monkeypatch.setattr(pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid(), pw_name=name))
    monkeypatch.setattr(grp, 'getgrnam', lambda name: SimpleNamespace(gr_gid=os.getgid(), gr_name=name))
    monkeypatch.setattr(ac, 'CONTROL_USER', 'fixture-control')
    monkeypatch.setattr(ac, 'CONTROL_GROUP', 'fixture-control')
    return SimpleNamespace(root=root, state=state, lock=lock, fcntl=fcntl)


def test_admission_lock_acquires_the_existing_canonical_lock_and_releases(tmp_path, monkeypatch):
    f = _lock_fixture(tmp_path, monkeypatch)
    config = {'runtime_root': str(f.root)}
    with _RealAdmissionLock(config) as held:
        held.check()
        outside = os.open(f.lock, os.O_RDWR)
        try:
            with pytest.raises(OSError):
                f.fcntl.flock(outside, f.fcntl.LOCK_EX | f.fcntl.LOCK_NB)
        finally:
            os.close(outside)
    # Releasing the admission lock is what makes normal Service startup possible.
    outside = os.open(f.lock, os.O_RDWR)
    f.fcntl.flock(outside, f.fcntl.LOCK_EX | f.fcntl.LOCK_NB)
    f.fcntl.flock(outside, f.fcntl.LOCK_UN)
    os.close(outside)


@pytest.mark.parametrize('fault', ['occupied', 'missing', 'group-readable', 'link',
                                   'fifo', 'foreign-lock', 'marker', 'barrier',
                                   'replaced', 'state-replaced'])
def test_admission_lock_refuses_occupied_replaced_or_unsafe_custody(tmp_path, monkeypatch, fault):
    f = _lock_fixture(tmp_path, monkeypatch)
    config = {'runtime_root': str(f.root)}
    if fault == 'occupied':
        outside = os.open(f.lock, os.O_RDWR)
        f.fcntl.flock(outside, f.fcntl.LOCK_EX | f.fcntl.LOCK_NB)
        with pytest.raises(m.MaintenanceError, match='occupied'):
            _RealAdmissionLock(config).__enter__()
        f.fcntl.flock(outside, f.fcntl.LOCK_UN)
        os.close(outside)
        return
    if fault == 'missing':
        f.lock.unlink()
        with pytest.raises((m.MaintenanceError, OSError)):
            _RealAdmissionLock(config).__enter__()
        # A missing canonical lock is never created as a decoy.
        assert not f.lock.exists()
        return
    if fault == 'group-readable':
        f.lock.chmod(0o640)
    elif fault == 'link':
        foreign = tmp_path/'foreign-lock'
        foreign.write_bytes(b'')
        foreign.chmod(0o600)
        f.lock.unlink()
        f.lock.symlink_to(foreign)
    elif fault == 'fifo':
        f.lock.unlink()
        os.mkfifo(f.lock)
    elif fault == 'foreign-lock':
        real = f.state/'real-lock'
        real.touch(mode=0o600)
        f.lock.unlink()
        f.lock.symlink_to(real)
    elif fault == 'marker':
        (f.state/m._SERVICE_MARKER).write_text('')
    elif fault == 'barrier':
        (f.state/m._SCHEMA_UPGRADE_BARRIER).write_text('{}')
    expected = ((m.MaintenanceError, OSError) if fault in {'link', 'fifo', 'foreign-lock'}
                else (m.MaintenanceError,))
    with pytest.raises(expected):
        with _RealAdmissionLock(config) as held:
            if fault == 'replaced':
                replacement = f.state/'fresh-lock'
                replacement.write_bytes(b'')
                replacement.chmod(0o600)
                os.replace(replacement, f.lock)
            elif fault == 'state-replaced':
                survivor = tmp_path/'survivor-state'
                survivor.mkdir(mode=0o700)
                (survivor/m._SERVICE_LOCK).touch(mode=0o600)
                f.state.rename(tmp_path/'old-state')
                survivor.rename(f.state)
            held.check()
    if fault in {'marker', 'barrier'}:
        assert f.lock.exists()


def test_admission_lock_pins_the_exact_configured_runtime_alias(tmp_path, monkeypatch):
    f = _lock_fixture(tmp_path, monkeypatch)
    physical = tmp_path/'physical-var'
    physical_state = physical/'db/mastermind-executive/control/db/data/control_plane'
    physical_state.mkdir(parents=True, mode=0o700)
    (physical_state/m._SERVICE_LOCK).touch(mode=0o600)
    alias = tmp_path/'logical-var'
    alias.symlink_to(physical, target_is_directory=True)
    monkeypatch.setattr(m, '_MACOS_VAR_ALIAS', alias)
    monkeypatch.setattr(m, '_MACOS_VAR_PHYSICAL', physical)
    monkeypatch.setattr(m, 'sys', SimpleNamespace(platform='darwin'))
    # The exact configured logical runtime root is the closed alias spelling.
    config = {'runtime_root': str(alias/'db/mastermind-executive/control/db')}
    with _RealAdmissionLock(config) as held:
        held.check()
        alias.unlink()
        alias.symlink_to(tmp_path/'foreign-var', target_is_directory=True)
        with pytest.raises(m.MaintenanceError, match='alias'):
            held.check()
    # Any other spelling is never mapped and never generically resolved.
    with _RealAdmissionLock({'runtime_root': str(f.root)}) as held:
        held.check()
    with pytest.raises((m.MaintenanceError, OSError)):
        _RealAdmissionLock({'runtime_root': str(alias/'db/mastermind-executive')}).__enter__()


# --- restore receipt shapes and their exact binding --------------------------

def _real_receipts(store):
    """Producer-shape receipts from the real backup/restore owners."""
    from control_plane import executive_backup as backup
    receipt = backup.create_online_backup(store.runtime.store, store.backup_root)
    verification = backup.verify_backup(receipt.database_path, receipt.manifest_path)
    drill = backup.verify_restore_drill(receipt.database_path, receipt.manifest_path)
    applied = backup.restore_backup_offline(store.runtime_root, receipt.database_path,
                                            receipt.manifest_path)
    return (dataclasses.asdict(receipt), dataclasses.asdict(verification),
            dataclasses.asdict(drill), dataclasses.asdict(applied))


def test_restore_receipts_bind_full_addresses_and_the_authoritative_database(
        tmp_path, monkeypatch):
    store = _v7_store_fixture(tmp_path, monkeypatch)
    created, verified, drill, applied = _real_receipts(store)
    backup_name = Path(created['database_path']).name
    assert (m._validate_v7_restore_receipts(
        created, verified, drill, applied,
        backup_root=store.backup_root, database=store.database) == backup_name)
    assert Path(created['database_path']).parent == store.backup_root
    assert Path(created['manifest_path']).parent == store.backup_root
    # The restore names the genuine configured authoritative store and never
    # invents an inode for it.
    assert applied['restored_database_path'] == os.fspath(store.database)
    assert not any('inode' in json.dumps(document)
                   for document in (created, verified, drill, applied))
    manifest_path = Path(created['manifest_path'])
    from ops.executive_os.autonomy_control import _root_json
    manifest, _raw = _root_json(manifest_path, modes=frozenset({0o600}),
                                uid=os.getuid(), gid=os.getgid())
    assert m._qualified_backup_manifest(created, store.backup_root,
                                        os.getuid(), os.getgid()) == manifest


@pytest.mark.parametrize('fault', ['created-keys', 'basename-only', 'foreign-directory',
                                   'verified-hash', 'verified-manifest-none',
                                   'drill-version', 'drill-integrity', 'applied-none',
                                   'restored-mismatch', 'foreign-source', 'manifest-pin',
                                   'restored-foreign-database', 'manifest-foreign-directory'])
def test_restore_receipts_refuse_wrong_or_downgraded_shapes(tmp_path, monkeypatch, fault):
    store = _v7_store_fixture(tmp_path, monkeypatch)
    created, verified, drill, applied = _real_receipts(store)
    foreign_backup = tmp_path/'elsewhere'
    foreign_backup.mkdir()
    shutil.copyfile(created['database_path'], foreign_backup/'copy.sqlite3')
    if fault == 'created-keys':
        created.pop('backup_id')
    elif fault == 'basename-only':
        created['database_path'] = Path(created['database_path']).name
    elif fault == 'foreign-directory':
        created['database_path'] = str(foreign_backup/'copy.sqlite3')
    elif fault == 'verified-hash':
        verified['database_sha256'] = '0'*64
    elif fault == 'verified-manifest-none':
        verified['manifest_path'] = None
    elif fault == 'drill-version':
        drill['runtime_schema_version'] = 5
    elif fault == 'drill-integrity':
        drill['integrity_check'] = 'degraded'
    elif fault == 'applied-none':
        applied['final_runtime_sha256'] = None
    elif fault == 'restored-mismatch':
        applied['restored_sha256'] = '1'*64
    elif fault == 'foreign-source':
        applied['source_backup_sha256'] = '2'*64
    elif fault == 'manifest-pin':
        applied['manifest_sha256'] = '3'*64
    elif fault == 'restored-foreign-database':
        applied['restored_database_path'] = os.fspath(foreign_backup/'copy.sqlite3')
    else:
        created['manifest_path'] = str(foreign_backup/'copy.manifest.json')
    with pytest.raises(m.MaintenanceError):
        m._validate_v7_restore_receipts(created, verified, drill, applied,
                                        backup_root=store.backup_root,
                                        database=store.database)


def test_restore_receipts_read_the_four_fixed_control_documents(tmp_path, monkeypatch):
    store = _v7_store_fixture(tmp_path, monkeypatch)
    created, verified, drill, applied = _real_receipts(store)
    receipts = {
        'backup-created.json': {'ok': True, 'result': created},
        'backup-verified.json': {'ok': True, 'result': verified},
        'restore-drill.json': drill,
        'restore-applied.json': applied,
    }
    owner = _receipts_fixture(store, tmp_path, monkeypatch, receipts)
    documents = owner._restore_receipts()
    assert set(documents) == ({name for name in m._V5_TO_V7_RESTORE_RECEIPTS}
                              | {name + ':sha256' for name in m._V5_TO_V7_RESTORE_RECEIPTS})
    for name in m._V5_TO_V7_RESTORE_RECEIPTS:
        assert documents[name + ':sha256'] == hashlib.sha256(json.dumps(
            receipts[name], sort_keys=True, indent=2).encode()).hexdigest()


def _receipts_fixture(store, tmp_path, monkeypatch, receipts):
    import pwd
    import grp
    acceptance = (store.runtime_root.parent.parent/'control'/'acceptance'/SUCCESSOR)
    acceptance.mkdir(parents=True)
    monkeypatch.setattr(ac, 'RUNTIME_ROOT', store.runtime_root.parent.parent)
    monkeypatch.setattr(pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(grp, 'getgrnam', lambda name: SimpleNamespace(gr_gid=os.getgid()))

    def fake_root_json(path, *, modes, uid, gid):
        return receipts[path.name], json.dumps(receipts[path.name], sort_keys=True,
                                               indent=2).encode()

    monkeypatch.setattr(ac, '_root_json', fake_root_json)
    owner = object.__new__(m.Maintenance)
    owner.descriptor = {'successor_sha': SUCCESSOR}
    return owner


@pytest.mark.parametrize('fault', ['envelope-flat', 'created-keys', 'verified-hash',
                                   'drill-version', 'drill-integrity', 'applied-none',
                                   'restored-mismatch', 'foreign-source', 'manifest-pin'])
def test_receipt_reader_refuses_wrong_or_downgraded_shapes(tmp_path, monkeypatch, fault):
    store = _v7_store_fixture(tmp_path, monkeypatch)
    created, verified, drill, applied = _real_receipts(store)
    if fault == 'created-keys':
        created.pop('backup_id')
    elif fault == 'verified-hash':
        verified['database_sha256'] = '0'*64
    elif fault == 'drill-version':
        drill['runtime_schema_version'] = 5
    elif fault == 'drill-integrity':
        drill['integrity_check'] = 'degraded'
    elif fault == 'applied-none':
        applied['final_runtime_sha256'] = None
    elif fault == 'restored-mismatch':
        applied['restored_sha256'] = '1'*64
    elif fault == 'foreign-source':
        applied['source_backup_sha256'] = '2'*64
    elif fault == 'manifest-pin':
        applied['manifest_sha256'] = '3'*64
    receipts = {
        'backup-created.json': ({'ok': True, 'result': created} if fault != 'envelope-flat'
                                else created),
        'backup-verified.json': {'ok': True, 'result': verified},
        'restore-drill.json': drill,
        'restore-applied.json': applied,
    }
    owner = _receipts_fixture(store, tmp_path, monkeypatch, receipts)
    if fault in {'envelope-flat', 'created-keys'}:
        # The reader refuses a wrong envelope or a downgraded receipt shape.
        with pytest.raises(m.MaintenanceError):
            owner._restore_receipts()
        return
    # Cross-document and producer-format faults refuse at the exact binding
    # check with the actual configured roots.
    with pytest.raises(m.MaintenanceError):
        documents = owner._restore_receipts()
        m._validate_v7_restore_receipts(
            documents['backup-created.json'], documents['backup-verified.json'],
            documents['restore-drill.json'], documents['restore-applied.json'],
            backup_root=store.backup_root, database=store.database)


# --- the real closed migration chain into the current v7 runtime -------------

def _v5_runtime_fixture(tmp_path, monkeypatch):
    """Construct actual historical v5 rows, restore current7 before any upgrade."""
    from control_plane.ceo_intent import submit_intent
    from tests.test_executive_os_phase1fc import _v3_execution_binding, _v2_intent
    captured = rt._MIGRATIONS, rt.SCHEMA_VERSION, rt._NORMALIZED_V7_SCHEMA_DIGEST
    try:
        rt._MIGRATIONS = captured[0][:5]
        rt.SCHEMA_VERSION = 5
        rt._NORMALIZED_V7_SCHEMA_DIGEST = rt._NORMALIZED_V5_SCHEMA_DIGEST
        runtime = rt.Runtime.at(tmp_path/'control'/'db')
        binding = _v3_execution_binding()
        binding.pop('work_placement_union')
        binding['host_execution_binding_version'] = rt.HOST_EXECUTION_BINDING_V2
        binding['eligible_quota_classes'] = ['default']
        binding['base_sha'] = ACCEPTED
        runtime.workers.register_worker('worker-1', provider='codex',
            account_label='fixture', worker_type='mock', capabilities=['read', 'research'],
            quota_classes={'default': {'provider': 'codex', 'capabilities': ['read','research'],
                'cost_class': 'small', 'model': binding['model'], 'effort': binding['effort'],
                'metadata': {key: binding[key] for key in
                ('model','effort','routing_policy_version','execution_profile_id',
                 'execution_profile_digest','capability_policy_version','capability_policy_digest')}}})
        proof = runtime.jobs.create_job('inert fixed proof', constraints={'base_sha': ACCEPTED},
                                         requested_authorities=['READ'], attempt_limit=2)
        lease = runtime.broker.claim(proof.job_id, lease_owner='fixture-template')
        assert lease is not None
        runtime.attempts.complete_attempt(lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
            payload=rt.JobPayload(summary='inert completed template'))
        root_id = submit_intent(runtime, _v2_intent(
            grounding={'mastermind_sha': ACCEPTED, 'macro_sha': 'b'*40},
            execution_contract={'requested_authorities': ['READ'], 'attempt_limit': 1,
                                'constraints': {'base_sha': ACCEPTED}}), execution_binding=binding)['job_id']
        planner = runtime.jobs.create_cycle_planner(root_id,
            command_id=f'coo-cycle:{root_id}:create-planner:0')
        command = f'coo-cycle:{root_id}:dispatch:{planner.job_id}:attempt:1'
        lease = runtime.attempts.dispatch_cycle_job(planner.job_id,
            command_id=command, lease_owner='fixture-terminal-owner')
        assert lease is not None
        runtime.attempts.fail_attempt(lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
            payload=rt.JobPayload(summary='inert prelaunch refusal'))
        runtime.jobs.record_cycle_dispatch_effect_unknown(root_id,
            selected_job_id=planner.job_id, dispatch_command_id=command)
        return runtime, runtime.jobs.get_job(root_id)
    finally:
        rt._MIGRATIONS, rt.SCHEMA_VERSION, rt._NORMALIZED_V7_SCHEMA_DIGEST = captured


def _stage_successor_release(tmp_path, monkeypatch):
    """Patch the staged successor release observer to an exact fixture root."""
    from control_plane import executive_backup as backup
    release_root = tmp_path/SUCCESSOR
    release_root.mkdir(mode=0o700, exist_ok=True)
    monkeypatch.setattr(backup, '_SCHEMA_UPGRADE_RELEASE_OBSERVER', lambda: {
        'release_root': str(release_root), 'release_sha': SUCCESSOR,
        'release_tree_sha': 'b'*40, 'release_manifest_sha256': 'c'*64})
    return SUCCESSOR


def _migrated_v7_fixture(tmp_path, monkeypatch):
    """Run the real closed v5->v6 and v6->v7 transitions over the v5 fixture.

    The v5 fixture is constructed with the captured historical migration set;
    the actual current values are restored before the real upgrades run, and
    the reopened store is the current authoritative v7 runtime. Every
    process-owned read connection is closed before the migrations start.
    """
    from control_plane import executive_backup as backup
    from tests.test_executive_backup import _upgrade_test_release_and_census
    fixture_root = tmp_path/'owner'
    fixture_root.mkdir()
    runtime, root = _v5_runtime_fixture(fixture_root, monkeypatch)
    database = Path(runtime.store.path)
    v5_before = m.snapshot(database)
    v5_backup = fixture_root/'source-v5.sqlite3'
    shutil.copyfile(database, v5_backup)
    v5_backup.chmod(0o400)
    # Snapshot read connections are process-owned; a read-only close cannot
    # unlink the WAL sidecars, so the fixture's explicit connection lifecycle
    # collects every closed handle before the real closed migration starts.
    # No sidecar is ever deleted and no guard is relaxed.
    gc.collect()
    # The canonical offline lock the closed upgrades require beside the store.
    lock = database.parent/m._SERVICE_LOCK
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    backup.upgrade_v5_to_v6(database, tmp_path/'upgrades-56', release_sha=release)
    backup.upgrade_v6_to_v7(database, tmp_path/'upgrades-67', release_sha=release)
    # The authoritative database lives at <runtime root>/data/control_plane,
    # so the reopened runtime root is three levels above the file.
    reopened = rt.Runtime.at(database.parent.parent.parent)
    assert Path(reopened.store.path) == database
    return SimpleNamespace(runtime=reopened, database=database, v5_before=v5_before,
                           v5_backup=v5_backup, release=release, lock=lock,
                           tool_release=release)


@needs_v7
@needs_source_fixtures
def test_real_closed_migrations_reach_the_current_v7_runtime(tmp_path, monkeypatch):
    from control_plane import executive_backup as backup
    f = _migrated_v7_fixture(tmp_path, monkeypatch)
    before = m.snapshot(f.database)
    with backup._readonly_database(f.database) as connection:
        versions = [row[0] for row in connection.execute(
            'SELECT version FROM schema_migrations ORDER BY version')]
        assert versions == [1, 2, 3, 4, 5, 6, 7]
        with backup._readonly_database(f.v5_backup) as source_connection:
            assert (backup.full_v5_content_digest(connection)
                    == backup.full_v5_content_digest(source_connection))
    assert not (f.database.parent/m._SCHEMA_UPGRADE_BARRIER).exists()
    # The working v7 prestate keeps the whole historical logical prestate.
    for table in ('jobs', 'attempts', 'events', 'workers', 'worker_quota_classes',
                  'harness_session_epochs', 'process_generations'):
        assert before['tables'][table] == f.v5_before['tables'][table]


@needs_v7
@needs_source_fixtures
def test_projection_digests_agree_across_the_real_closed_migration(tmp_path, monkeypatch):
    """Unit mechanics over real migration output: source, target and current
    share one full v5 content digest. The real evidence context arrives with
    the joined owner; only the digest comparison is exercised here."""
    from control_plane import executive_backup as backup
    f = _migrated_v7_fixture(tmp_path, monkeypatch)
    with backup._readonly_database(f.v5_backup) as connection:
        source_digest = backup.full_v5_content_digest(connection)
    evidence = SimpleNamespace(source_v5_database=f.v5_backup,
                               target_v7_database=f.database,
                               source_v5_content_digest=source_digest)
    m._v5_to_v7_projection_digests(evidence, f.database)
    drifted = SimpleNamespace(source_v5_database=f.v5_backup,
                              target_v7_database=f.database,
                              source_v5_content_digest='0'*64)
    with pytest.raises(m.MaintenanceError):
        m._v5_to_v7_projection_digests(drifted, f.database)


@needs_v7
@needs_source_fixtures
def test_v7_preserved_proof_delta_keeps_the_old_allowances(tmp_path, monkeypatch):
    f = _migrated_v7_fixture(tmp_path, monkeypatch)
    f.runtime_root = Path(f.runtime.store.path).parents[2]
    before = m.snapshot(f.database)
    template = next(row for row in before['tables']['jobs']
                    if row['objective'] == 'inert fixed proof')
    descriptor = dict(schema_version=m.SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7,
        template_proof_job_id=template['job_id'], successor_sha=SUCCESSOR,
        worker_id='worker-1', quota_class='default')
    proof_ids = _actual_proof_delta(f, descriptor)
    after = m.snapshot(f.database)
    m.verify_preserved(before, after, descriptor, proof_ids)
    heartbeat = copy.deepcopy(after)
    for row in heartbeat['tables']['workers']:
        row['version'] += 1
    m.verify_preserved(before, heartbeat, descriptor, proof_ids)
    drifted = copy.deepcopy(after)
    next(row for row in drifted['tables']['attempts'] if row['status'] == 'FAILED')['status'] = 'COMPLETED'
    with pytest.raises(m.MaintenanceError):
        m.verify_preserved(before, drifted, descriptor, proof_ids)


# --- issuance, admission, first finish and future carry ----------------------

def _migrate_source_fixture(f, tmp_path, monkeypatch):
    from control_plane import executive_backup as backup
    from tests.test_executive_backup import _upgrade_test_release_and_census
    database = Path(f.runtime.store.path)
    gc.collect()
    _upgrade_test_release_and_census(monkeypatch, tmp_path)
    release = _stage_successor_release(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence_owner, '_prove_current_release',
                        lambda sha: backup._prove_upgrade_release(sha))
    backup.upgrade_v5_to_v6(database, Path(f.config['backup_root']), release_sha=release)
    backup.upgrade_v6_to_v7(database, Path(f.config['backup_root']), release_sha=release)
    f.database = database
    f.v7_before = m.snapshot(database, immutable=True)
    f.tool_release = release
    _stage_successor_release(tmp_path, monkeypatch)
    return f


def _issuance_fixture(tmp_path, monkeypatch):
    return _migrate_source_fixture(_preflight_fixture(tmp_path, monkeypatch), tmp_path, monkeypatch)


def _write_receipt(path, value):
    _write_private(path, json.dumps(value, sort_keys=True, indent=2).encode() + b'\n', 0o400)


@needs_v7_bridge
@needs_source_fixtures
def test_issuance_publishes_the_working_v7_bundle_and_keeps_the_v5_source(
        tmp_path, monkeypatch):
    _issued(tmp_path, monkeypatch)


def _issued(tmp_path, monkeypatch, f=None):
    f = f or _issuance_fixture(tmp_path, monkeypatch)
    originals = {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()}
    deeper_originals = {p.name: p.read_bytes() for p in f.deeper_bundle.iterdir()}
    result = m.prepare(_v5_to_v7_args(f))
    descriptor = m.descriptor_for(SUCCESSOR)
    assert result == m.bundle_path(SUCCESSOR)
    assert descriptor['schema_version'] == m.SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7
    assert descriptor['superseded_unstarted_preproof_sha'] == MIDDLE
    assert descriptor['superseded_descriptor_sha256'] == m.digest(f.middle)
    assert descriptor['predecessor_sha'] == ACCEPTED
    assert descriptor['baseline_sha256'] == m.digest(f.v7_before)
    assert descriptor['prior_canary_sha256'] == m.digest(f.live_envelope)
    evidence_document = m.sealed_json(result/m._V5_TO_V7_EVIDENCE_NAME)
    assert m.digest(evidence_document) == descriptor['schema_upgrade_evidence_sha256']
    assert m._v5_to_v7_tool_release(evidence_document) == f.tool_release
    source_control = (result/m._V5_TO_V7_SOURCE_CONTROL_NAME).read_bytes()
    assert (hashlib.sha256(source_control).hexdigest()
            == descriptor['source_control_config_sha256'])
    assert {p.name for p in result.iterdir()} == set(m._V5_TO_V7_BUNDLE_NAMES)
    assert m.sealed_json(result/'preparing.json')['schema_version'] == (
        m.SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7)
    # The selected v5 lineage keeps its exact bytes and stays unstarted.
    assert {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()} == originals
    assert {p.name: p.read_bytes() for p in f.deeper_bundle.iterdir()} == deeper_originals
    assert not (f.middle_bundle/'run-started.json').exists()
    assert not (f.runtime_root/'control'/'acceptance'/MIDDLE).exists()
    assert not (result/'run-started.json').exists()
    # The working inventory is the exact source inventory plus the qualified
    # additions; the source inventory itself is unchanged.
    working = m.sealed_json(result/'inventory.json')
    source_inventory = m.sealed_json(f.middle_bundle/'inventory.json')
    added = set(working) - set(source_inventory)
    assert len(added) == 8
    assert all(set(working[name]) == {'uid', 'gid', 'mode', 'nlink', 'sha256'}
               for name in added)
    return f, descriptor, result


def _admitted(tmp_path, monkeypatch, issued=None):
    f, descriptor, bundle = issued or _issued(tmp_path, monkeypatch)
    originals = {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()}
    owner = m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    assert owner.predecessor_recovery_required is False
    assert m.recovery_permitted(None, 'old', SUCCESSOR, 'worker', 'proof') is False
    assert m.sealed_json(bundle/'run-started.json') == {
        'schema_version': m.SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7,
        'descriptor_sha256': m.digest(descriptor)}
    assert {p.name: p.read_bytes() for p in f.middle_bundle.iterdir()} == originals
    assert m.snapshot(f.database, immutable=True) == f.v7_before
    # The marker is exclusive: a second admission cannot rewrite it.
    with pytest.raises((m.MaintenanceError, FileExistsError)):
        m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    return f, descriptor, bundle, owner


@needs_v7_bridge
@needs_source_fixtures
def test_admission_writes_the_runmarker_and_revalidation_is_exclusive(
        tmp_path, monkeypatch):
    _admitted(tmp_path, monkeypatch)


def _proof_backup_chain(f, tmp_path):
    """The genuine proof backup with its four real producer receipts."""
    from control_plane import executive_backup as backup
    receipt = backup.create_online_backup(f.runtime.store, Path(f.config['backup_root']))
    verification = backup.verify_backup(receipt.database_path, receipt.manifest_path)
    drill = backup.verify_restore_drill(receipt.database_path, receipt.manifest_path)
    applied = backup.restore_backup_offline(f.runtime_root, receipt.database_path,
                                            receipt.manifest_path)
    return receipt.to_dict(), verification.to_dict(), drill, applied


def _write_proof_receipts(f, receipt, verification, drill, applied):
    acceptance_root = f.runtime_root.parent.parent/'control'/'acceptance'/SUCCESSOR
    acceptance_root.mkdir(parents=True, exist_ok=True)
    for name, value in {
            'backup-created.json': {'ok': True, 'result': receipt},
            'backup-verified.json': {'ok': True, 'result': verification},
            'restore-drill.json': dataclasses.asdict(drill),
            'restore-applied.json': dataclasses.asdict(applied)}.items():
        _write_receipt(acceptance_root/name, value)
    return acceptance_root


def _real_pass_summary(f, proof_ids):
    """The real closed PASS summary the existing arming owner validates.

    ``m.SYSTEM_ROOT`` is the patched fixture system root here, so the summary
    binds the same release root the real validator compares."""
    return {
        'schema_version': 'mastermind.executive_host_acceptance/v1',
        'passed': True,
        'observed_at': '2026-10-23T00:00:00+00:00',
        'exact_origin_master_sha': SUCCESSOR,
        'release_root': os.fspath(m.SYSTEM_ROOT/'releases'/SUCCESSOR),
        'control_uid': os.getuid() + 1, 'worker_uid': os.getuid() + 2,
        'success_job_id': proof_ids[0],
        'interrupted_requeued_job_id': proof_ids[1],
        'detached_session_cleanup': 'PASS', 'terminal_assignment_sealing': 'PASS',
        'lost_workspace_rotation_boundary': 'PASS', 'backup_restore': 'PASS',
        'no_public_listener': 'PASS', 'credential_leakage_scan': 'PASS',
        'financial_scheduler_activation': 'NOT_REQUESTED_OR_TOUCHED',
    }


def _complete_inert_proof(runtime, job):
    lease = runtime.broker.claim(job.job_id, lease_owner='inert-proof-fixture')
    assert lease is not None
    runtime.attempts.record_process(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        provider_session_id='inert-fixture-'+lease.attempt.attempt_id)
    runtime.attempts.mark_running(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
    runtime.attempts.complete_attempt(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        payload=rt.JobPayload(summary='inert proof complete'))


def _actual_proof_delta(f, descriptor):
    from datetime import datetime, timezone
    from tests.test_executive_service import _proof_absence
    runtime = rt.Runtime.at(f.runtime_root)
    template = runtime.jobs.get_job(descriptor['template_proof_job_id'])
    def create():
        return runtime.jobs.create_job(template.objective,
            department=template.department, priority=template.priority,
            authority_level=template.authority_level, attempt_limit=template.attempt_limit,
            requested_authorities=list(template.requested_authorities),
            allowed_write_paths=list(template.allowed_write_paths),
            validation_commands=list(template.validation_commands),
            constraints={**template.constraints, 'base_sha': SUCCESSOR})
    first = create()
    _complete_inert_proof(runtime, first)
    second = create()
    lease = runtime.broker.claim(second.job_id, lease_owner='inert-lost-fixture')
    assert lease is not None
    runtime.attempts.record_process(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        provider_session_id='inert-missing-fixture')
    runtime.attempts.mark_running(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
    runtime.attempts.mark_lost(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        reason='process identity absent during supervisor restart', verified_process_absent=True)
    runtime.jobs.requeue_job(second.job_id)
    lost = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    observed_before = datetime.now(timezone.utc)
    sweep = _proof_absence(lost)  # synthetic observation DATA, real closed receipt validator
    state = runtime.workers.proof_capacity_recovery_snapshot(second.job_id,
        lost.attempt_id, worker_id=descriptor['worker_id'], quota_class=descriptor['quota_class'])
    runtime.workers.recover_proof_capacity(second.job_id, lost.attempt_id,
        worker_id=descriptor['worker_id'], quota_class=descriptor['quota_class'],
        expected_snapshot=state, uid_sweep=sweep, expected_worker_uid=451,
        observation_started_at=observed_before, observation_finished_at=datetime.now(timezone.utc))
    _complete_inert_proof(runtime, second)
    f.runtime = runtime
    return [first.job_id, second.job_id]


@needs_v7_bridge
@needs_source_fixtures
@pytest.mark.parametrize('logical', [False, True], ids=['physical-owner', 'normal-logical-var'])
def test_joined_chain_from_preflight_to_future_carry(tmp_path, monkeypatch, logical):
    """The one substantive joined path: real preflight, real closed migrations,
    real issuance and admission under the canonical lock, the real preserved
    proof delta, a genuine online backup with its four real receipts, the real
    offline restore, the real closed PASS summary validator, the first finish
    and the future historical carry through the real handler."""
    from control_plane import executive_backup as backup
    # (1) The read-only preflight qualifies the real v5 source and writes nothing.
    f = _preflight_fixture(tmp_path, monkeypatch, logical=logical)
    paths = [*f.middle_bundle.iterdir(), *f.deeper_bundle.iterdir()]
    original = {str(p): p.read_bytes() for p in paths}
    result = m.prepare(_v5_to_v7_args(f, qualify_v5_source_only=True))
    assert result['action'] == 'qualify-v5-source-only'
    assert not m.bundle_path(SUCCESSOR).exists()
    assert original == {str(p): p.read_bytes() for p in paths}
    assert m.snapshot(f.runtime.store.path, immutable=True) == f.before
    # (2) The SAME preflighted source undergoes actual closed transitions.
    f = _migrate_source_fixture(f, tmp_path, monkeypatch)
    # (3-4) Normal prepare and admission retain the same DB/root/selected lineage.
    issued = _issued(tmp_path, monkeypatch, f=f)
    f3, descriptor, bundle, owner = _admitted(tmp_path, monkeypatch, issued=issued)
    proof_ids = _actual_proof_delta(f3, descriptor)
    m.verify_preserved(owner.before, m.snapshot(f3.database), descriptor, proof_ids)
    # (5) The real backup, verification, drill and offline restore producers.
    receipt, verification, drill, applied = _proof_backup_chain(f3, tmp_path)
    acceptance_root = _write_proof_receipts(f3, receipt, verification, drill, applied)
    summary_document = _real_pass_summary(f3, proof_ids)
    _write_receipt(acceptance_root/'acceptance-summary.json', summary_document)
    summary_path = acceptance_root/'acceptance-summary.json'
    def refusal(path, changed, match):
        raw = path.read_bytes()
        _rewrite(path, changed)
        try:
            with pytest.raises(m.MaintenanceError, match=match):
                owner.finish(proof_ids, summary_path)
            assert not (bundle/m._V5_TO_V7_RESTORE_EVIDENCE_NAME).exists()
            assert not (bundle/'carry-forward.json').exists()
        finally:
            path.chmod(0o600)
            path.write_bytes(raw)
            path.chmod(0o400)
    refusal(summary_path, dict(summary_document, success_job_id=proof_ids[1],
                               interrupted_requeued_job_id=proof_ids[0]), 'summary proof jobs')
    applied_path = acceptance_root/'restore-applied.json'
    applied_value = json.loads(applied_path.read_text())
    for mutation in ({'physical_history_digest': '0'*64},
                     {'ohf_invalidated_attempts': True},
                     {'ohf_invalidated_attempts': -1},
                     {'ohf_invalidated_attempts': 1}):
        refusal(applied_path, dict(applied_value, **mutation), 'physical history or TX-9')
    refusal(applied_path, dict(applied_value, restored_database_path=str(tmp_path/'foreign.sqlite3')),
            'qualified proof backup')
    # (6) The Service legitimately restarted during backup_restore: the
    # canonical lock is held by the running Service and the store carries
    # normal worker heartbeat activity. The finish path tolerates both.
    outside = os.open(f3.lock, os.O_RDWR)
    fcntl.flock(outside, fcntl.LOCK_EX | fcntl.LOCK_NB)
    live = sqlite3.connect(f3.database)
    live.execute('PRAGMA journal_mode=WAL')
    with live:
        live.execute('UPDATE workers SET last_seen_at_ms=last_seen_at_ms+1, '
                     'updated_at_ms=updated_at_ms+1,version=version+1')
    assert f3.database.with_name(f3.database.name+'-wal').exists()
    try:
        owner.finish(proof_ids, acceptance_root/'acceptance-summary.json')
    finally:
        live.close()
        fcntl.flock(outside, fcntl.LOCK_UN)
        os.close(outside)
    evidence_document = m.sealed_json(bundle/m._V5_TO_V7_RESTORE_EVIDENCE_NAME)
    assert set(evidence_document) == set(m._V5_TO_V7_RESTORE_EVIDENCE_KEYS)
    assert evidence_document['proof_job_ids'] == proof_ids
    assert evidence_document['backup']['database_sha256'] == receipt['database_sha256']
    observed = os.stat(f3.database)
    assert evidence_document['current_runtime_database'] == {
        'path': os.fspath(f3.database), 'device': observed.st_dev,
        'inode': observed.st_ino}
    carry = m.sealed_json(bundle/'carry-forward.json')
    assert carry['acceptance_restore_evidence_sha256'] == m.digest(evidence_document)
    # A second finish refuses instead of rewriting the sealed run.
    with pytest.raises((m.MaintenanceError, FileExistsError, OSError)):
        owner.finish(proof_ids, acceptance_root/'acceptance-summary.json')
    # (7) The future historical carry dispatches through the real handler and
    # re-derives the sealed history through the real retained owner.
    future = {key: value for key, value in descriptor.items()
              if key not in {'superseded_unstarted_preproof_sha',
                             'superseded_descriptor_sha256',
                             'schema_upgrade_evidence_sha256',
                             'source_control_config_sha256'}}
    future.update(schema_version=m.SCHEMA_V2, predecessor_sha=SUCCESSOR,
                  successor_sha='1'*40,
                  prior_descriptor_sha256=m.digest(descriptor),
                  prior_carry_sha256=m.digest(carry),
                  prior_summary_sha256=hashlib.sha256(json.dumps(
                      summary_document, sort_keys=True, indent=2).encode() + b'\n').hexdigest(),
                  frozen_base_sha=descriptor['frozen_base_sha'])
    future_bundle = m.bundle_path('1'*40)
    future_bundle.mkdir()
    m.write_sealed(future_bundle/'descriptor.json', future, public=True)
    # Later unrelated current rows do not retroactively require INITIAL state.
    rt.Runtime.at(f3.runtime_root).jobs.create_job('later unrelated inert job')
    m.validate_prior_carry_binding(future)
    # A Root-self-hash update cannot bless a wrong physical receipt.
    carry_path = bundle/'carry-forward.json'
    restore_path = bundle/m._V5_TO_V7_RESTORE_EVIDENCE_NAME
    original_carry, original_restore = carry_path.read_bytes(), restore_path.read_bytes()
    original_applied = applied_path.read_bytes()
    _rewrite(applied_path, dict(applied_value, physical_history_digest='0'*64))
    forged_restore = copy.deepcopy(evidence_document)
    forged_restore['receipt_sha256']['restore-applied.json'] = hashlib.sha256(applied_path.read_bytes()).hexdigest()
    _rewrite(restore_path, forged_restore)
    _rewrite(carry_path, dict(carry, acceptance_restore_evidence_sha256=m.digest(forged_restore)))
    with pytest.raises(m.MaintenanceError, match='physical history'):
        m.validate_prior_carry_binding(future)
    for path, raw in ((applied_path, original_applied), (carry_path, original_carry),
                      (restore_path, original_restore)):
        path.chmod(0o600); path.write_bytes(raw); path.chmod(0o400)
    # A mutated sealed restore evidence refuses the future carry.
    _rewrite(bundle/m._V5_TO_V7_RESTORE_EVIDENCE_NAME,
             dict(evidence_document, tampered=True))
    with pytest.raises(m.MaintenanceError):
        m.validate_prior_carry_binding(future)


@needs_v7_bridge
@needs_source_fixtures
@pytest.mark.parametrize('fault', ['missing-created', 'missing-drill', 'missing-applied',
                                   'foreign-hash', 'downgraded-drill', 'foreign-backup-path'])
def test_first_finish_refuses_wrong_or_missing_receipts(tmp_path, monkeypatch, fault):
    f, descriptor, bundle, owner = _admitted(tmp_path, monkeypatch)
    receipt, verification, drill, applied = _proof_backup_chain(f, tmp_path)
    drill_dict = dataclasses.asdict(drill)
    applied_dict = dataclasses.asdict(applied)
    if fault == 'foreign-hash':
        applied_dict['source_backup_sha256'] = '0'*64
    elif fault == 'downgraded-drill':
        drill_dict['runtime_schema_version'] = 5
    elif fault == 'foreign-backup-path':
        receipt = dict(receipt, database_path=str(
            Path(f.config['backup_root']).parent/'elsewhere.sqlite3'))
    acceptance_root = f.runtime_root.parent.parent/'control'/'acceptance'/SUCCESSOR
    acceptance_root.mkdir(parents=True, exist_ok=True)
    documents = {
        'backup-created.json': {'ok': True, 'result': receipt},
        'backup-verified.json': {'ok': True, 'result': verification},
        'restore-drill.json': drill_dict,
        'restore-applied.json': applied_dict,
    }
    for name, value in documents.items():
        if fault == 'missing-created' and name == 'backup-created.json':
            continue
        if fault == 'missing-drill' and name == 'restore-drill.json':
            continue
        if fault == 'missing-applied' and name == 'restore-applied.json':
            continue
        _write_receipt(acceptance_root/name, value)
    summary_document = _real_pass_summary(f, ['JOB-proof-1', 'JOB-proof-2'])
    _write_receipt(acceptance_root/'acceptance-summary.json', summary_document)
    with pytest.raises((m.MaintenanceError, OSError)):
        owner.finish(['JOB-proof-1', 'JOB-proof-2'],
                     acceptance_root/'acceptance-summary.json')
    assert not (bundle/m._V5_TO_V7_RESTORE_EVIDENCE_NAME).exists()
    assert not (bundle/'carry-forward.json').exists()


# --- read-only v5 source preflight -------------------------------------------

def _v5_host_fixture(tmp_path, monkeypatch, *, logical=False):
    """A real v5 runtime with the exact host seams the owner reads, inert."""
    fixture_root = tmp_path/'physical-var'/'db/mastermind-executive' if logical else tmp_path/'owner'
    fixture_root.mkdir(parents=True)
    runtime, root = _v5_runtime_fixture(fixture_root, monkeypatch)
    before = m.snapshot(runtime.store.path, immutable=True)
    admission = next(row for row in before['tables']['events']
                     if row['job_id'] == root.job_id and row['event_type'] == 'JOB_CREATED')
    quota_row = next(row for row in before['tables']['worker_quota_classes']
                     if row['status'] == 'AVAILABLE' and row['held_attempt_id'] is None)
    import pwd
    import grp
    monkeypatch.setattr(pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid(), pw_name=ac.CONTROL_USER))
    monkeypatch.setattr(grp, 'getgrnam', lambda name: SimpleNamespace(gr_gid=os.getgid(), gr_name=ac.CONTROL_GROUP))
    _stage_successor_release(tmp_path, monkeypatch)
    monkeypatch.setattr(m, 'SYSTEM_ROOT', tmp_path/'system')
    monkeypatch.setattr(ac, 'SYSTEM_ROOT', m.SYSTEM_ROOT)
    monkeypatch.setattr(m, '_TRUSTED_UID', os.getuid())
    monkeypatch.setattr(m, '_TRUSTED_GID', os.getgid())
    monkeypatch.setattr(m, '_sealed_ancestors', lambda path: [])
    monkeypatch.setattr(m, 'has_macos_acl', lambda *args, **kwargs: False)
    monkeypatch.setattr(ac, '_has_acl', lambda *args, **kwargs: False)
    monkeypatch.setattr(m, 'os', SimpleNamespace(**{name: getattr(os, name) for name in dir(os) if name != 'geteuid'}, geteuid=lambda: 0))
    monkeypatch.setattr(m, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(m, 'require_stopped', lambda: None)
    runtime_root = Path(runtime.store.path).parents[2]
    (runtime_root.parent.parent/'control'/'acceptance').mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ac, 'RUNTIME_ROOT', runtime_root.parent.parent)
    monkeypatch.setattr(ac, 'CONTROL_USER', 'fixture-control')
    monkeypatch.setattr(ac, 'CONTROL_GROUP', 'fixture-control')
    config = {'worker_id': quota_row['worker_id'], 'quota_class': quota_row['quota_class']}
    config.update(runtime_root=str(runtime_root), proof_base_sha=MIDDLE,
                  ceo_submit_armed=False, coo_autonomy_armed=False,
                  coo_operator_harness_armed=False)
    for key in ('proof_workspace_root', 'worker_runs_root', 'receipts_root', 'backup_root'):
        path = (runtime_root.parent/'backups' if key == 'backup_root' else tmp_path/'artifacts'/key)
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        config[key] = str(path)
    canary_fixtures = runtime_root.parent.parent/'canary-fixtures'
    canary_fixtures.mkdir(exist_ok=True)
    live_envelope = envelope()
    canary_path = runtime_root.parent/'canaries/secret-canary.json'
    canary_path.parent.mkdir(mode=0o700)
    canary_path.write_text(json.dumps(live_envelope))
    config['secret_canary_receipt_path'] = str(canary_path)
    if logical:
        alias, physical = tmp_path/'logical-var', tmp_path/'physical-var'
        alias.symlink_to(physical, target_is_directory=True)
        monkeypatch.setattr(m, '_MACOS_VAR_ALIAS', alias)
        monkeypatch.setattr(m, '_MACOS_VAR_PHYSICAL', physical)
        monkeypatch.setattr(evidence_owner, '_FIXED_SYSTEM_MAPPINGS', ((alias, physical),))
        for key in ('runtime_root', 'backup_root', 'secret_canary_receipt_path'):
            config[key] = str(alias/Path(config[key]).relative_to(physical))
        monkeypatch.setattr(ac, 'RUNTIME_ROOT', alias/'db/mastermind-executive')
    (m.SYSTEM_ROOT/'config').mkdir(parents=True, mode=0o700)
    # The fixed Root control config is a Root-owned 0440 preimage, read through
    # the guarded owner and pinned for the whole action.
    _write_private(m.SYSTEM_ROOT/'config'/'control.json',
                   json.dumps(config, sort_keys=True, indent=2).encode() + b'\n', 0o440)
    (m.SYSTEM_ROOT/'config'/'worker-codex.json').write_text('{"operator_harness_armed":false}')
    artifacts = m.inventory([Path(config[key]) for key in
                             ('proof_workspace_root', 'worker_runs_root', 'receipts_root',
                              'backup_root')] + [canary_fixtures])
    # Canonical admission lock beside the authoritative database.
    state = runtime_root/'data'/'control_plane'
    state.mkdir(parents=True, exist_ok=True)
    lock = state/m._SERVICE_LOCK
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    # Sealed accepted ancestor the terminal carry binds.
    ancestor = dict(schema_version=m.SCHEMA, predecessor_sha='a'*40, successor_sha=ACCEPTED,
                    root_job_id=root.job_id, root_identity_sha256=m.root_identity(root),
                    root_event_id=admission['event_id'],
                    root_event_sha256=m.digest(admission),
                    recovery_job_id='JOB-ancestor', recovery_attempt_id='ATT-ancestor',
                    recovery_job_sha256='6'*64, worker_id=config['worker_id'],
                    quota_class=config['quota_class'], baseline_sha256='3'*64,
                    backup_sha256='4'*64, inventory_sha256='5'*64,
                    prior_canary_sha256='6'*64)
    ancestor_summary = b'accepted-ancestor-summary'
    ancestor_bundle = m.bundle_path(ACCEPTED)
    ancestor_bundle.mkdir(parents=True)
    m.write_sealed(ancestor_bundle/'descriptor.json', ancestor, public=True)
    m.write_sealed(ancestor_bundle/'carry-forward.json', dict(
        schema_version=m.SCHEMA, passed=True, baseline_preserved=True,
        descriptor_sha256=m.digest(ancestor),
        acceptance_summary_sha256=hashlib.sha256(ancestor_summary).hexdigest()))
    ancestor_carry = dict(
        schema_version=m.SCHEMA, passed=True, baseline_preserved=True,
        descriptor_sha256=m.digest(ancestor),
        acceptance_summary_sha256=hashlib.sha256(ancestor_summary).hexdigest())
    ancestor_material = {
        'prior_descriptor_sha256': m.digest(ancestor),
        'prior_carry_sha256': m.digest(ancestor_carry),
        'prior_summary_sha256': hashlib.sha256(ancestor_summary).hexdigest(),
        'frozen_base_sha': ACCEPTED,
    }
    real_prior = m.prior_carry_material
    proof = next(job for job in runtime.jobs.list_jobs() if job.objective == 'inert fixed proof')
    def prior(sha, **kwargs):
        if sha != ACCEPTED:
            return real_prior(sha, **kwargs)
        return ({'root_job_id': root.job_id, 'root_identity_sha256': m.root_identity(root),
                 'root_event_id': admission['event_id'],
                 'root_event_sha256': m.digest(admission)},
                {'success_job_id': proof.job_id}, ancestor_material)
    monkeypatch.setattr(m, 'prior_carry_material', prior)
    monkeypatch.setattr(m, 'terminal_assignment',
                        lambda *args, **kwargs: {'assignment_seal_sha256': '7'*64})
    from tests.test_executive_schema_upgrade_evidence import _mock_root
    _mock_root(monkeypatch, runtime_root.parent.parent, runtime_root,
               Path(config['backup_root']), m.SYSTEM_ROOT/'config/control.json')
    for directory in (runtime_root.parent.parent, runtime_root.parent, runtime_root,
                      runtime_root/'data', state):
        directory.chmod(0o700)
    _proof, carry_fields = m.terminal_carry_fields(runtime, root, config, before, ACCEPTED)
    return SimpleNamespace(
        runtime=runtime, root=root, before=before, config=config, proof=proof,
        admission=admission, carry_fields=carry_fields, artifacts=artifacts,
        ancestor=ancestor, ancestor_material=ancestor_material,
        live_envelope=live_envelope, canary_path=canary_path,
        canary_fixtures=canary_fixtures, runtime_root=runtime_root,
        lock=lock, state=state, monkeypatch=monkeypatch, tool_release=None)


def _seal_source_chain(f):
    """Seal the deeper started prefix and the unstarted selected preparation."""
    deeper_bundle = m.bundle_path(DEEPER)
    deeper_bundle.mkdir(parents=True)
    source = sqlite3.connect(f.runtime.store.path)
    destination = sqlite3.connect(deeper_bundle/'prestate.sqlite3')
    try:
        source.backup(destination)
    finally:
        # Process-owned read connections are closed before any migration.
        destination.close()
        source.close()
    (deeper_bundle/'prestate.sqlite3').chmod(0o400)
    prior_canary = {'passed': True, 'generation': 'prior'}
    deeper = dict(schema_version=m.SCHEMA_V2, predecessor_sha=ACCEPTED, successor_sha=DEEPER,
                  root_job_id=f.root.job_id, root_identity_sha256=m.root_identity(f.root),
                  root_event_id=f.admission['event_id'],
                  root_event_sha256=m.digest(f.admission),
                  worker_id=f.config['worker_id'], quota_class=f.config['quota_class'],
                  baseline_sha256=m.digest(f.before), inventory_sha256=m.digest(f.artifacts),
                  prior_canary_sha256=m.digest(prior_canary),
                  backup_sha256=m._file_digest(deeper_bundle/'prestate.sqlite3'),
                  **f.carry_fields)
    for filename, value in [('descriptor.json', deeper),
                            ('preparing.json', {'schema_version': m.SCHEMA_V2}),
                            ('baseline.json', f.before), ('inventory.json', f.artifacts),
                            ('prior-secret-canary.json', prior_canary)]:
        m.write_sealed(deeper_bundle/filename, value, public=filename == 'descriptor.json')
    write_full_preproof_root(f.runtime_root.parent.parent, deeper, f.monkeypatch)
    import pwd, grp
    f.monkeypatch.setattr(pwd, 'getpwnam', lambda name: SimpleNamespace(
        pw_uid=os.getuid(), pw_gid=os.getgid(), pw_name=ac.CONTROL_USER))
    f.monkeypatch.setattr(grp, 'getgrnam', lambda name: SimpleNamespace(
        gr_gid=os.getgid(), gr_name=ac.CONTROL_GROUP))
    evidence, read_envelope = m.preproof_evidence(DEEPER)
    assert read_envelope == f.live_envelope
    middle_bundle = m.bundle_path(MIDDLE)
    middle_bundle.mkdir()
    # The unstarted preparation carries the exact selected backup bytes.
    shutil.copyfile(deeper_bundle/'prestate.sqlite3', middle_bundle/'prestate.sqlite3')
    (middle_bundle/'prestate.sqlite3').chmod(0o400)
    middle = dict(deeper, schema_version=m.SCHEMA_PREPROOF, successor_sha=MIDDLE,
                  interrupted_preproof_sha=DEEPER,
                  superseded_descriptor_sha256=m.digest(deeper),
                  preproof_evidence_sha256=evidence,
                  prior_canary_sha256=m.digest(f.live_envelope))
    for filename, value in [('descriptor.json', middle),
                            ('preparing.json', {'schema_version': m.SCHEMA_PREPROOF}),
                            ('baseline.json', f.before), ('inventory.json', f.artifacts),
                            ('prior-secret-canary.json', f.live_envelope)]:
        m.write_sealed(middle_bundle/filename, value, public=filename == 'descriptor.json')
    return SimpleNamespace(deeper=deeper, middle=middle, deeper_bundle=deeper_bundle,
                           middle_bundle=middle_bundle)


def _preflight_fixture(tmp_path, monkeypatch, **options):
    f = _v5_host_fixture(tmp_path, monkeypatch, **options)
    source = _seal_source_chain(f)
    f.middle = source.middle
    f.deeper = source.deeper
    f.middle_bundle = source.middle_bundle
    f.deeper_bundle = source.deeper_bundle
    return f


def _v5_to_v7_args(f, **overrides):
    values = dict(predecessor_sha=ACCEPTED, successor_sha=SUCCESSOR,
                  root_job_id=f.root.job_id, recovery_job_id=None,
                  recovery_attempt_id=None, carry_terminal_dispatch=True,
                  supersede_unstarted_sha=None, supersede_prejob_sha=None,
                  supersede_preproof_sha=None, supersede_unstarted_preproof_sha=None,
                  supersede_unstarted_preproof_v5_to_v7_sha=MIDDLE,
                  superseded_descriptor_sha256=m.digest(f.middle),
                  qualify_v5_source_only=False)
    values.update(overrides)
    return argparse.Namespace(**values)


@needs_source_fixtures
def test_preflight_qualifies_the_v5_source_without_any_write(tmp_path, monkeypatch):
    f = _preflight_fixture(tmp_path, monkeypatch)
    paths = [*f.middle_bundle.iterdir(), *f.deeper_bundle.iterdir()]
    original = {str(p): p.read_bytes() for p in paths}
    result = m.prepare(_v5_to_v7_args(f, qualify_v5_source_only=True))
    assert result['action'] == 'qualify-v5-source-only'
    assert result['schema_version'] == m.SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7
    assert result['selected_sha'] == MIDDLE
    assert result['superseded_descriptor_sha256'] == m.digest(f.middle)
    assert result['source_baseline_sha256'] == m.digest(f.before)
    assert result['source_canary_sha256'] == m.digest(f.live_envelope)
    assert result['staged_release_sha'] == SUCCESSOR
    # Bounded constraint data only: no preparation directory, backup,
    # descriptor, runmarker or acceptance leaf anywhere.
    assert not m.bundle_path(SUCCESSOR).exists()
    assert not list(m.bundle_path(SUCCESSOR).parent.glob('.preparing-*'))
    assert not (f.runtime_root/'control'/'acceptance'/SUCCESSOR).exists()
    assert not (f.middle_bundle/'run-started.json').exists()
    assert original == {str(p): p.read_bytes() for p in paths}
    assert m.snapshot(f.runtime.store.path, immutable=True) == f.before
    # The preflight lock was released before any migration could start.
    import fcntl
    descriptor = os.open(f.lock, os.O_RDWR)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(descriptor, fcntl.LOCK_UN)
    os.close(descriptor)


@pytest.mark.parametrize('fault', ['wrong-installed', 'mixed-old-selector', 'recovery',
                                   'no-carry', 'live-canary', 'live-inventory',
                                   'selected-drift', 'occupied-lock', 'missing-lock',
                                   'marker-present', 'config-drift'])
@needs_source_fixtures
def test_preflight_refuses_before_any_write(tmp_path, monkeypatch, fault):
    f = _preflight_fixture(tmp_path, monkeypatch)
    args = _v5_to_v7_args(f, qualify_v5_source_only=True)
    if fault == 'wrong-installed':
        f.config['proof_base_sha'] = '7'*40
        _rewrite(m.SYSTEM_ROOT/'config'/'control.json', f.config)
        def forbidden(*args, **kwargs):
            raise AssertionError('uninstalled selection reached the runtime read')
        monkeypatch.setattr(m, 'snapshot', forbidden)
    elif fault == 'mixed-old-selector':
        args.supersede_unstarted_preproof_sha = MIDDLE
    elif fault == 'recovery':
        args.recovery_job_id = 'JOB-old'
        args.recovery_attempt_id = 'ATT-old'
    elif fault == 'no-carry':
        args.carry_terminal_dispatch = False
    elif fault == 'live-canary':
        f.canary_path.write_text(json.dumps({'passed': True, 'drift': True}))
    elif fault == 'live-inventory':
        (f.canary_fixtures/'drift.bin').write_bytes(b'drift')
    elif fault == 'selected-drift':
        _rewrite(f.middle_bundle/'baseline.json', {'drift': True})
    elif fault == 'occupied-lock':
        import fcntl
        outside = os.open(f.lock, os.O_RDWR)
        fcntl.flock(outside, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif fault == 'missing-lock':
        f.lock.unlink()
    elif fault == 'config-drift':
        f.config['runtime_root'] = str(f.runtime_root.parent/'elsewhere')
        _rewrite(m.SYSTEM_ROOT/'config'/'control.json', f.config)
    else:
        (f.state/m._SERVICE_MARKER).write_text('')
    originals = {str(p): p.read_bytes() for p in f.middle_bundle.iterdir()}
    with pytest.raises((m.MaintenanceError, OSError)):
        m.prepare(args)
    assert not m.bundle_path(SUCCESSOR).exists()
    assert not list(m.bundle_path(SUCCESSOR).parent.glob('.preparing-*'))
    assert not (f.runtime_root/'control'/'acceptance'/SUCCESSOR).exists()
    assert originals == {str(p): p.read_bytes() for p in f.middle_bundle.iterdir()}

@pytest.mark.parametrize('fault', ['none', 'wal', 'shm', 'journal', 'sequence-only',
                                   'replace-db', 'replace-lock', 'replace-selected',
                                   'corrupt-temp'])
def test_quiescent_preflight_uses_only_a_qualified_private_copy(tmp_path, monkeypatch, fault):
    f = _preflight_fixture(tmp_path, monkeypatch)
    database = Path(f.runtime.store.path)
    original = database.read_bytes()
    initial = m._identity(database.lstat())
    before = m.snapshot(database, immutable=True)
    decoded = []
    real = m._verification_runtime
    def decode(path):
        assert path != database and path.name == 'verification.sqlite3'
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        decoded.append(path)
        runtime = real(path)
        if fault in {'replace-db', 'replace-lock', 'replace-selected'}:
            target = {'replace-db': database, 'replace-lock': f.lock,
                      'replace-selected': f.middle_bundle/'prestate.sqlite3'}[fault]
            replacement = target.with_name(target.name+'.replacement')
            shutil.copyfile(target, replacement)
            replacement.chmod(stat.S_IMODE(target.stat().st_mode))
            os.replace(replacement, target)
        elif fault == 'corrupt-temp':
            with path.open('ab') as stream:
                stream.write(b'changed-private-verification-copy')
        return runtime
    monkeypatch.setattr(m, '_verification_runtime', decode)
    if fault in {'wal', 'shm', 'journal'}:
        sidecar = database.with_name(database.name+'-'+fault)
        sidecar.write_bytes(b'inert retained sidecar')
    elif fault == 'sequence-only':
        connection = sqlite3.connect(database)
        try:
            with connection:
                connection.execute("UPDATE sqlite_sequence SET seq=seq+1 WHERE name='events'")
        finally:
            connection.close()
        assert m.snapshot(database, immutable=True) == before
        assert m._full_v5_digest(database) != m._full_v5_digest(f.middle_bundle/'prestate.sqlite3')
    args = _v5_to_v7_args(f, qualify_v5_source_only=True)
    if fault == 'none':
        assert m.prepare(args)['action'] == 'qualify-v5-source-only'
        assert decoded
        assert database.read_bytes() == original and m._identity(database.lstat()) == initial
    else:
        with pytest.raises((m.MaintenanceError, OSError)):
            m.prepare(args)
        if fault in {'wal', 'shm', 'journal', 'sequence-only'}:
            assert not decoded
    assert all(not path.exists() for path in decoded)
    if fault not in {'wal', 'shm', 'journal'}:
        assert all(not database.with_name(database.name+suffix).exists()
                   for suffix in ('-wal', '-shm', '-journal'))
    assert not m.bundle_path(SUCCESSOR).exists()
    assert not (f.middle_bundle/'run-started.json').exists()

@pytest.mark.parametrize('phase,target', [('prepare','lock'), ('prepare','database'),
    ('prepare','deeper'), ('admission','lock'), ('admission','selected'), ('admission','canary')])
def test_last_terminal_read_rechecks_held_names_before_publication(tmp_path, monkeypatch, phase, target):
    f = _issuance_fixture(tmp_path, monkeypatch)
    descriptor = None
    if phase == 'admission':
        f, descriptor, _bundle = _issued(tmp_path, monkeypatch, f=f)
    files = {path: path.read_bytes() for path in
             [*f.middle_bundle.iterdir(), *f.deeper_bundle.iterdir()]}
    real = m.terminal_carry_fields
    fired = []
    def mutate(*args, **kwargs):
        result = real(*args, **kwargs)
        # Preparation's first terminal read precedes candidate creation. The
        # second is the genuine final semantic requalification after sealing.
        if not fired and (phase == 'admission' or list(m.bundle_path(SUCCESSOR).parent.glob('.preparing-*'))):
            path = {'lock': f.lock, 'database': f.database,
                    'deeper': next((f.runtime_root.parent.parent/'control/acceptance'/DEEPER).glob('*.json')),
                    'selected': f.middle_bundle/'inventory.json',
                    'canary': f.canary_path}[target]
            replacement = path.with_name(path.name+'.adversarial-replacement')
            shutil.copyfile(path, replacement)
            replacement.chmod(stat.S_IMODE(path.stat().st_mode))
            os.replace(replacement, path)
            fired.append(path)
        return result
    monkeypatch.setattr(m, 'terminal_carry_fields', mutate)
    with pytest.raises((m.MaintenanceError, evidence_owner.SchemaUpgradeEvidenceError, OSError)):
        if phase == 'prepare':
            m.prepare(_v5_to_v7_args(f))
        else:
            m.Maintenance(SUCCESSOR, m.digest(descriptor), f.config)
    assert fired
    if phase == 'prepare':
        assert not m.bundle_path(SUCCESSOR).exists()
        assert list(m.bundle_path(SUCCESSOR).parent.glob('.preparing-*'))
    else:
        assert not (m.bundle_path(SUCCESSOR)/'run-started.json').exists()
    assert {path: path.read_bytes() for path in files} == files


def test_v7_source_join_refuses_resealed_selected_sequence_only_drift(tmp_path, monkeypatch):
    f = _issuance_fixture(tmp_path, monkeypatch)
    selected_backup = f.middle_bundle/'prestate.sqlite3'
    before = m.snapshot(selected_backup, immutable=True)
    old_digest = m._full_v5_digest(selected_backup)
    selected_backup.chmod(0o600)
    connection = sqlite3.connect(selected_backup)
    try:
        with connection:
            connection.execute("UPDATE sqlite_sequence SET seq=seq+1 WHERE name='events'")
    finally:
        connection.close()
    selected_backup.chmod(0o400)
    assert m.snapshot(selected_backup, immutable=True) == before
    assert m._full_v5_digest(selected_backup) != old_digest
    # A changed raw backup pin/selected descriptor does not alter the genuine
    # immutable migration-source digest, despite equal ordinary snapshots.
    f.middle = dict(f.middle, backup_sha256=hashlib.sha256(selected_backup.read_bytes()).hexdigest())
    _rewrite(f.middle_bundle/'descriptor.json', f.middle)
    with pytest.raises(m.MaintenanceError, match='full content differs from migration source'):
        m.prepare(_v5_to_v7_args(f))
    assert not m.bundle_path(SUCCESSOR).exists()
    assert not list(m.bundle_path(SUCCESSOR).parent.glob('.preparing-*'))
