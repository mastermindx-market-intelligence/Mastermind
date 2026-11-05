"""Actual fresh Root -> new Control -> ordinary67 -> retained16 -> maintenance.

Offline disposable SQLite only. Inherited host identities/ACL/ancestors,
sealed-source and sensor-return seams are explicit; no accepting path replaces
qualification, continuation, census parsing, DDL, backup/drill, projection,
helper, selected binding, restoration or carry validators.
The injected ctime event is not proof of the live failure's cause.
"""
import copy
import fcntl
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest
from control_plane import executive_backup as b
from ops.executive_os import acceptance_maintenance as m
from ops.executive_os import schema_upgrade_evidence as evidence
from tests.test_executive_persistent_origin import filesystem
from tests.test_executive_spent_ctime_qualification import _spent_fixture, _no_external_effects
from tests.test_executive_precensus_joined_acceptance import _control_boundary
from tests.test_executive_acceptance_v5_to_v7 import (
    SUCCESSOR, MIDDLE, _issued, _admitted, _actual_proof_delta,
    _proof_backup_chain, _write_proof_receipts, _real_pass_summary, _write_receipt,
)


@pytest.fixture(autouse=True)
def _current_data_anchor_fixture(filesystem):
    """Explicit raw Root/Darwin facts; real held anchor predicates execute."""
    yield filesystem


def test_genuine_three_executor_chain_reaches_finish_and_future_carry(tmp_path,monkeypatch):
    f=_spent_fixture(tmp_path,monkeypatch)
    database=Path(f.runtime.store.path)
    old={p:(p.read_bytes(),p.stat().st_ino) for p in (f.barrier,f.destination,f.spent_path)}
    selected={p:p.read_bytes() for bundle in (f.middle_bundle,f.deeper_bundle) for p in bundle.iterdir()}
    m.prepare(f.args)
    root_r=json.loads(f.reconciliation.read_bytes())
    # Restore the Control principal seam after the actual Root action returns.
    monkeypatch.setattr(b.os,'geteuid',os.getuid)
    opened,commands=_control_boundary(f,monkeypatch)
    checkpoint=b._checkpoint_quiesced_wal; seen=[]
    def postcommit_only(path):
        with b._readonly_database(Path(path)) as connection:
            version=connection.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
        assert version>=6, 'spent v5 checkpoint was replayed'
        seen.append(version); return checkpoint(path)
    monkeypatch.setattr(b,'_checkpoint_quiesced_wal',postcommit_only)
    q=f.q
    kwargs=dict(release_sha=SUCCESSOR,expected_operation_id=q['operation_id'],
        expected_barrier_sha256=q['original_barrier']['identity']['sha256'],
        expected_spent_continuation_sha256=root_r['spent_continuation_identity']['sha256'],
        expected_reconciliation_sha256=hashlib.sha256(f.reconciliation.read_bytes()).hexdigest())
    b.continue_spent_v5_to_v6_pre_census_ctime(database,database.parents[3]/'backups',**kwargs)
    assert seen and min(seen)>=6
    assert not opened
    assert not f.barrier.exists()
    for path in (f.destination,f.spent_path):
        assert (path.read_bytes(),path.stat().st_ino)==old[path]
    with pytest.raises(b.ExecutiveSchemaUpgradeError):
        b.continue_spent_v5_to_v6_pre_census_ctime(database,database.parents[3]/'backups',**kwargs)
    with pytest.raises(b.ExecutiveSchemaUpgradeError):
        b.resume_v5_to_v6_pre_census(database,database.parents[3]/'backups',
            release_sha=SUCCESSOR,expected_operation_id=q['operation_id'],
            expected_barrier_sha256=q['original_barrier']['identity']['sha256'])
    pre=json.loads((database.parent/b._UPGRADE_V5_TO_V6_PREFLIGHT_NAME).read_bytes())
    assert pre['schema_version']==b.SPENT_PRE_CENSUS_CTIME_PREFLIGHT_SCHEMA
    assert pre['release_sha']==SUCCESSOR and pre['operation_id']==q['operation_id']
    assert len(pre['pre_census_reconciliation'])==4
    assert len(pre['quiesce_writer_census']['open_files'])==3
    assert pre['database']['sha256']==q['database']['sha256']
    b.upgrade_v6_to_v7(database,database.parents[3]/'backups',release_sha=SUCCESSOR)
    assert not opened
    assert {command[0] for command in commands}=={'/bin/ps','/usr/sbin/lsof'}
    pre67=json.loads((database.parent/b._UPGRADE_V6_TO_V7_PREFLIGHT_NAME).read_bytes())
    assert pre67['quiesce_writer_census']['schema_version']==b.UPGRADE_CENSUS_SCHEMA
    assert len(pre67['quiesce_writer_census']['open_files'])==1
    monkeypatch.setattr(evidence,'_prove_current_release',lambda sha:b._prove_upgrade_release(sha))
    with evidence.open_v5_to_v7_evidence(f.runtime_root,SUCCESSOR) as retained:
        material=copy.deepcopy(retained.material)
        assert material['schema_version']==evidence.SPENT_CTIME_MATERIAL_SCHEMA_VERSION
        assert len(material['origin_records'])==16 and len(retained.inventory_additions)==8
        assert retained.pre_census_qualification==q
        m._bind_pre_census_selected(retained,MIDDLE,f.middle,
            (m.SYSTEM_ROOT/'config/control.json').read_bytes())
    # Real normal descriptor issuance and INITIAL maintenance admission.
    f.database=database; f.tool_release=SUCCESSOR
    f.v7_before=m.snapshot(database,immutable=True)
    issued=_issued(tmp_path,monkeypatch,f=f)
    _,descriptor,bundle,owner=_admitted(tmp_path,monkeypatch,issued=issued)
    assert len(m.sealed_json(bundle/m._V5_TO_V7_EVIDENCE_NAME)['origin_records'])==16
    assert descriptor['schema_upgrade_evidence_sha256']==m.digest(material)
    assert selected=={p:p.read_bytes() for p in selected}
    assert owner.before==f.v7_before
    # Genuine proof Jobs/attempts, offline restore, PASS/first-finish/history.
    proof_ids=_actual_proof_delta(f,descriptor)
    receipt,verification,drill,applied=_proof_backup_chain(f,tmp_path)
    acceptance_root=_write_proof_receipts(f,receipt,verification,drill,applied)
    summary_path=acceptance_root/'acceptance-summary.json'
    _write_receipt(summary_path,_real_pass_summary(f,proof_ids))
    service_fd=os.open(f.lock,os.O_RDWR)
    fcntl.flock(service_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    live=sqlite3.connect(database);live.execute('PRAGMA journal_mode=WAL')
    with live:
        live.execute('UPDATE workers SET last_seen_at_ms=last_seen_at_ms+1, '
                     'updated_at_ms=updated_at_ms+1,version=version+1')
    try:
        owner.finish(proof_ids,summary_path)
    finally:
        live.close();fcntl.flock(service_fd,fcntl.LOCK_UN);os.close(service_fd)
    carry=m.sealed_json(bundle/'carry-forward.json');assert carry['passed'] is True
    future={key:value for key,value in descriptor.items() if key not in {
        'superseded_unstarted_preproof_sha','superseded_descriptor_sha256',
        'schema_upgrade_evidence_sha256','source_control_config_sha256'}}
    future.update(schema_version=m.SCHEMA_V2,predecessor_sha=SUCCESSOR,successor_sha='1'*40,
        prior_descriptor_sha256=m.digest(descriptor),prior_carry_sha256=m.digest(carry),
        prior_summary_sha256=hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        frozen_base_sha=descriptor['frozen_base_sha'])
    future_bundle=m.bundle_path('1'*40);future_bundle.mkdir()
    m.write_sealed(future_bundle/'descriptor.json',future,public=True)
    from control_plane.executive_runtime import Runtime
    Runtime.at(f.runtime_root).jobs.create_job('later unrelated inert ctime-fixture job')
    m.validate_prior_carry_binding(future)
    assert selected=={p:p.read_bytes() for p in selected}
