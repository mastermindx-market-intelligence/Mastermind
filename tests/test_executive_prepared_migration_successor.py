"""A real completed sixteen-origin preparation, then a different reader release.

Disposable SQLite and real issuers/DDL/census parsing/backups/helper/maintenance
validators. Principal/ACL/ancestor/seal/sensor and inherited ancestor/assignment
inputs are explicit existing fixture seams; no live host/provider is touched.
"""
import copy
import fcntl
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest
from tests.test_executive_persistent_origin import filesystem


@pytest.fixture(autouse=True)
def _current_data_anchor_fixture(filesystem):
    """Explicit raw Root/Darwin facts; real held anchor predicates execute."""
    yield filesystem

from control_plane import executive_backup as b
from ops.executive_os import acceptance_maintenance as m
from ops.executive_os import schema_upgrade_evidence as e
from tests import test_executive_acceptance_v5_to_v7 as fixtures
from tests.test_executive_spent_ctime_qualification import _spent_fixture, _no_external_effects
from tests.test_executive_precensus_joined_acceptance import _control_boundary

P='c'*40
R='2'*40


def _completed_preparation(tmp_path,monkeypatch):
    f=_spent_fixture(tmp_path,monkeypatch)
    database=Path(f.runtime.store.path)
    m.prepare(f.args)
    root_r=json.loads(f.reconciliation.read_bytes())
    monkeypatch.setattr(b.os,'geteuid',os.getuid)
    opened,_commands=_control_boundary(f,monkeypatch)
    b.continue_spent_v5_to_v6_pre_census_ctime(database,database.parents[3]/'backups',release_sha=P,
        expected_operation_id=f.q['operation_id'],
        expected_barrier_sha256=f.q['original_barrier']['identity']['sha256'],
        expected_spent_continuation_sha256=root_r['spent_continuation_identity']['sha256'],
        expected_reconciliation_sha256=hashlib.sha256(f.reconciliation.read_bytes()).hexdigest())
    b.upgrade_v6_to_v7(database,database.parents[3]/'backups',release_sha=P)
    assert not opened
    monkeypatch.setattr(e,'_prove_current_release',lambda sha:b._prove_upgrade_release(sha))
    f.database=database;f.tool_release=P;f.v7_before=m.snapshot(database,immutable=True)
    _,f.parent,f.parent_bundle=fixtures._issued(tmp_path,monkeypatch,f=f)
    f.material=m.sealed_json(f.parent_bundle/m._V5_TO_V7_EVIDENCE_NAME)
    assert len(f.material['origin_records'])==16
    assert f.parent['successor_sha']==P
    f.old_files={path:(path.read_bytes(),path.stat().st_ino) for path in f.parent_bundle.iterdir()}
    f.old_receipts={Path(row['path']):Path(row['path']).read_bytes()
                    for row in f.material['origin_records']}
    (m.SYSTEM_ROOT/'releases'/R).mkdir(mode=0o700)
    monkeypatch.setattr(b,'_SCHEMA_UPGRADE_RELEASE_OBSERVER',lambda:dict(
        release_root=str(m.SYSTEM_ROOT/'releases'/R),release_sha=R,
        release_tree_sha='b'*40,release_manifest_sha256='c'*64))
    f.new_args=fixtures._v5_to_v7_args(f,successor_sha=R,
        supersede_unstarted_preproof_v5_to_v7_sha=None,superseded_descriptor_sha256=None,
        supersede_unstarted_migration_preparation_sha=P,
        superseded_migration_preparation_descriptor_sha256=m.digest(f.parent))
    return f


def _assert_parent_unchanged(f):
    assert f.old_files=={path:(path.read_bytes(),path.stat().st_ino) for path in f.old_files}
    assert f.old_receipts=={path:path.read_bytes() for path in f.old_receipts}
    assert not (f.parent_bundle/'run-started.json').exists()
    assert not (f.runtime_root.parent/'acceptance'/P).exists()


def test_distinct_reader_initial_is_current_and_preserves_original_material(tmp_path,monkeypatch):
    f=_completed_preparation(tmp_path,monkeypatch)
    # Both incumbent INITIAL entry forms must still refuse the two-source case.
    for sha in (P,R):
        with pytest.raises((b.ExecutiveSchemaUpgradeError,e.SchemaUpgradeEvidenceError)):
            with e.open_v5_to_v7_evidence(f.runtime_root,sha): pytest.fail('old INITIAL widened')
    with e.open_prepared_successor_v5_to_v7_evidence(f.runtime_root,R,f.material) as evidence:
        assert evidence.phase==e.EVIDENCE_PHASE_INITIAL
        assert evidence.material==f.material
        assert evidence.material['chain']['tool_release']['sha']==P
        assert len(evidence.material['origin_records'])==16
        completion=json.loads((f.database.parent/b._UPGRADE_V6_TO_V7_COMPLETION_NAME).read_bytes())
        assert evidence.target_v7_database_identity==completion['authoritative_v7_database']
        evidence.check()
    _assert_parent_unchanged(f)


def test_actual_completed_parent_to_reader_descriptor_admission_restore_finish_and_carry(tmp_path,monkeypatch):
    f=_completed_preparation(tmp_path,monkeypatch)
    result=m.prepare(f.new_args);descriptor=m.descriptor_for(R)
    assert result==m.bundle_path(R)
    assert descriptor['schema_version']==m.SCHEMA_PREPARED_MIGRATION_SUCCESSOR
    assert descriptor['superseded_unstarted_migration_preparation_sha']==P
    assert descriptor['superseded_migration_preparation_descriptor_sha256']==m.digest(f.parent)
    assert all(descriptor[key]==f.parent[key] for key in m._DESCRIPTOR_UNSTARTED_PREPROOF_V5_TO_V7_KEYS
               -{'schema_version','successor_sha'})
    for name in m._V5_TO_V7_BUNDLE_NAMES-{'descriptor.json','preparing.json'}:
        assert (result/name).read_bytes()==(f.parent_bundle/name).read_bytes()
    assert m.sealed_json(result/m._V5_TO_V7_EVIDENCE_NAME)==f.material
    _assert_parent_unchanged(f)
    # Model the existing normal selected-config transition using only its
    # existing release fields; no new config key/authority is introduced.
    f.config['proof_base_sha']=R
    f.config['proof_source_repository']=str(f.runtime_root.parent/'admin-checkout'/R)
    config_path=m.SYSTEM_ROOT/'config/control.json'
    config_path.chmod(0o600);config_path.write_text(json.dumps(f.config,sort_keys=True,indent=2)+'\n');config_path.chmod(0o440)
    owner=m.Maintenance(R,m.digest(descriptor),f.config)
    assert m.sealed_json(result/'run-started.json')['schema_version']==m.SCHEMA_PREPARED_MIGRATION_SUCCESSOR
    assert owner.predecessor_recovery_required is False
    with pytest.raises(m.MaintenanceError): m.Maintenance(R,m.digest(descriptor),f.config)
    # Reuse real proof/restore producers with a DIFFERENT fixture release ID.
    monkeypatch.setattr(fixtures,'SUCCESSOR',R)
    proof_ids=fixtures._actual_proof_delta(f,descriptor)
    receipt,verification,drill,applied=fixtures._proof_backup_chain(f,tmp_path)
    acceptance=fixtures._write_proof_receipts(f,receipt,verification,drill,applied)
    summary=acceptance/'acceptance-summary.json'
    fixtures._write_receipt(summary,fixtures._real_pass_summary(f,proof_ids))
    fd=os.open(f.lock,os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    live=sqlite3.connect(f.database);live.execute('PRAGMA journal_mode=WAL')
    with live: live.execute('UPDATE workers SET last_seen_at_ms=last_seen_at_ms+1,updated_at_ms=updated_at_ms+1,version=version+1')
    try: owner.finish(proof_ids,summary)
    finally: live.close();fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
    carry=m.sealed_json(result/'carry-forward.json')
    assert carry['passed'] is True and carry['schema_version']==m.SCHEMA_PREPARED_MIGRATION_SUCCESSOR
    assert not (f.parent_bundle/'carry-forward.json').exists()
    future={key:value for key,value in descriptor.items() if key in m._DESCRIPTOR_V2_KEYS}
    future.update(schema_version=m.SCHEMA_V2,predecessor_sha=R,successor_sha='1'*40,
        prior_descriptor_sha256=m.digest(descriptor),prior_carry_sha256=m.digest(carry),
        prior_summary_sha256=hashlib.sha256(summary.read_bytes()).hexdigest())
    bundle=m.bundle_path('1'*40);bundle.mkdir();m.write_sealed(bundle/'descriptor.json',future,public=True)
    from control_plane.executive_runtime import Runtime
    Runtime.at(f.runtime_root).jobs.create_job('later unrelated prepared-successor fixture job')
    m.validate_prior_carry_binding(future)
    _assert_parent_unchanged(f)


@pytest.mark.parametrize('fault',['parent-digest','parent-started','parent-partial','acceptance',
    'occupied-target','partial-target','config','canary','inventory','database','sequence','reader-seal','tool-seal','mixed-selector'])
def test_unqualified_preparation_or_current_state_never_publishes_new_target(tmp_path,monkeypatch,fault):
    f=_completed_preparation(tmp_path,monkeypatch)
    if fault=='parent-digest': f.new_args.superseded_migration_preparation_descriptor_sha256='0'*64
    elif fault=='parent-started': m.write_sealed(f.parent_bundle/'run-started.json',{'schema_version':f.parent['schema_version']})
    elif fault=='parent-partial': (f.parent_bundle/'foreign').write_text('partial')
    elif fault=='acceptance': (f.runtime_root.parent/'acceptance'/P).mkdir()
    elif fault=='occupied-target': m.bundle_path(R).mkdir()
    elif fault=='partial-target': (m.bundle_path(R).parent/('.preparing-'+R+'-foreign')).mkdir()
    elif fault=='config':
        path=m.SYSTEM_ROOT/'config/control.json';path.chmod(0o600);path.write_bytes(path.read_bytes()+b' ');path.chmod(0o440)
    elif fault=='canary': Path(f.config['secret_canary_receipt_path']).write_text('{}')
    elif fault=='inventory': (Path(f.config['backup_root'])/'foreign').write_text('foreign')
    elif fault in ('database','sequence'):
        connection=sqlite3.connect(f.database)
        with connection:
            connection.execute('UPDATE sqlite_sequence SET seq=seq+1' if fault=='sequence'
                else 'UPDATE workers SET last_seen_at_ms=last_seen_at_ms+1')
        connection.close()
    elif fault=='reader-seal': monkeypatch.setattr(b,'_SCHEMA_UPGRADE_RELEASE_OBSERVER',lambda:{})
    elif fault=='tool-seal':
        real=e._verify_pinned_release
        monkeypatch.setattr(e,'_verify_pinned_release',lambda root,sha,tree: {} if sha==P else real(root,sha,tree))
    else: f.new_args.supersede_unstarted_preproof_v5_to_v7_sha=fixtures.MIDDLE
    with pytest.raises((m.MaintenanceError,b.ExecutiveSchemaUpgradeError,e.SchemaUpgradeEvidenceError,OSError,ValueError)):
        m.prepare(f.new_args)
    if fault!='occupied-target': assert not m.bundle_path(R).exists()
    assert not (f.parent_bundle/'carry-forward.json').exists()


@pytest.mark.parametrize('fault',['parent-leaf','acceptance','config','reader-seal','tool-seal'])
def test_late_mutation_leaves_only_private_candidate_never_published_R(tmp_path,monkeypatch,fault):
    f=_completed_preparation(tmp_path,monkeypatch)
    real=m._requalify_unstarted_preproof_v5_to_v7
    def late(*args,**kwargs):
        result=real(*args,**kwargs)
        if fault=='parent-leaf':
            path=f.parent_bundle/'baseline.json';path.chmod(0o600);path.write_bytes(path.read_bytes()+b' ');path.chmod(0o400)
        elif fault=='acceptance': (f.runtime_root.parent/'acceptance'/P).mkdir()
        elif fault=='reader-seal': monkeypatch.setattr(b,'_SCHEMA_UPGRADE_RELEASE_OBSERVER',lambda:{})
        elif fault=='tool-seal':
            real_seal=e._verify_pinned_release
            monkeypatch.setattr(e,'_verify_pinned_release',lambda root,sha,tree: {} if sha==P else real_seal(root,sha,tree))
        else:
            path=m.SYSTEM_ROOT/'config/control.json';path.chmod(0o600);path.write_bytes(path.read_bytes()+b' ');path.chmod(0o440)
        return result
    monkeypatch.setattr(m,'_requalify_unstarted_preproof_v5_to_v7',late)
    with pytest.raises((m.MaintenanceError,b.ExecutiveSchemaUpgradeError,e.SchemaUpgradeEvidenceError,OSError,ValueError)):
        m.prepare(f.new_args)
    assert not m.bundle_path(R).exists()
    assert list(m.bundle_path(R).parent.glob('.preparing-'+R+'-*'))


@pytest.mark.parametrize('fault',['parent-started','acceptance','reader-seal'])
def test_late_admission_refuses_before_runmarker(tmp_path,monkeypatch,fault):
    f=_completed_preparation(tmp_path,monkeypatch)
    result=m.prepare(f.new_args);descriptor=m.descriptor_for(R)
    f.config['proof_base_sha']=R
    f.config['proof_source_repository']=str(f.runtime_root.parent/'admin-checkout'/R)
    path=m.SYSTEM_ROOT/'config/control.json'
    path.chmod(0o600);path.write_text(json.dumps(f.config,sort_keys=True,indent=2)+'\n');path.chmod(0o440)
    real=m._requalify_unstarted_preproof_v5_to_v7
    def late(*args,**kwargs):
        value=real(*args,**kwargs)
        if fault=='parent-started': m.write_sealed(f.parent_bundle/'run-started.json',{'schema_version':f.parent['schema_version']})
        elif fault=='acceptance': (f.runtime_root.parent/'acceptance'/P).mkdir()
        else: monkeypatch.setattr(b,'_SCHEMA_UPGRADE_RELEASE_OBSERVER',lambda:{})
        return value
    monkeypatch.setattr(m,'_requalify_unstarted_preproof_v5_to_v7',late)
    with pytest.raises((m.MaintenanceError,b.ExecutiveSchemaUpgradeError,e.SchemaUpgradeEvidenceError,OSError,ValueError)):
        m.Maintenance(R,m.digest(descriptor),f.config)
    assert not (result/'run-started.json').exists()
