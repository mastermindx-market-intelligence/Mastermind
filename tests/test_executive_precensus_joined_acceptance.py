"""Real Root issuer -> Control continuation -> v7 -> retained acceptance join.

No live owner is contacted. Account/host ancestry/native ACL/release seals and
process observations map to disposable fixtures, as in the existing accepted
maintenance suite. Inherited accepted-ancestor/assignment inputs stay synthetic.
No accepting path substitutes qualification, migration/census parsing, receipt,
backup/drill, full content, helper or maintenance binding validators.
"""
import copy
import fcntl
import sqlite3
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from control_plane import executive_backup as b
from ops.executive_os import acceptance_maintenance as m
from ops.executive_os import schema_upgrade_evidence as evidence
from tests.test_executive_acceptance_pre_census_qualification import (
    _fixture, _no_external_effects,
)
from tests.test_executive_acceptance_v5_to_v7 import (
    SUCCESSOR, MIDDLE, _issued, _admitted, _actual_proof_delta,
    _proof_backup_chain, _write_proof_receipts, _real_pass_summary, _write_receipt,
)


def _control_boundary(f, monkeypatch):
    """Fake only principal/Root profile, seal and OS command return DATA.

    FD rows derive the actual owner opens, not fixture-provided census DTOs.
    Both ps/lsof parsers and all owner comparisons remain production code.
    """
    uid, gid = os.getuid(), os.getgid()
    real_leaf = b._pre_census_leaf
    monkeypatch.setattr(b, '_pre_census_leaf', lambda path, fd, *, uid, gid, mode:
        real_leaf(path, fd, uid=os.getuid() if uid == 0 else uid, gid=gid, mode=mode))
    monkeypatch.setattr(b, '_pre_census_prove_original_tool', lambda tool:
        evidence._verify_pinned_release(Path(tool['root']),tool['sha'],tool['tree_sha']))
    opened, commands = {}, []
    proxy = SimpleNamespace(**{name:getattr(os,name) for name in dir(os)})
    def open_fd(path, flags, *args, **kwargs):
        fd = os.open(path,flags,*args,**kwargs);opened[fd]=Path(path);return fd
    def close_fd(fd):
        opened.pop(fd,None);return os.close(fd)
    proxy.open,proxy.close = open_fd,close_fd
    monkeypatch.setattr(b,'os',proxy)
    database = Path(f.runtime.store.path)
    lock=database.parent/b.DEFAULT_SERVICE_LOCK_NAME
    barrier=database.parent/b._UPGRADE_BARRIER_NAME
    def sensor(command):
        commands.append(command)
        if command[0]=='/bin/ps':
            return (0,f'{os.getpid()} {uid} {uid} {uid} own\n999999 {uid} {uid} {uid} sensor\n','',999999)
        assert command[0]=='/usr/sbin/lsof'
        rows=[f'p{os.getpid()}',f'u{uid}']
        for fd,path in sorted(opened.items()):
            if path in (database,lock,barrier):rows.extend([f'f{fd}',f'n{path}'])
        return (0,'\n'.join(rows)+'\n','',999998)
    monkeypatch.setattr(b,'_run_census_command',sensor)
    # Ordinary67 uses the genuine default one-FD census, not the historical
    # fixture observer installed by unrelated v5 fixture construction.
    monkeypatch.setattr(b,'_SCHEMA_UPGRADE_CENSUS_OBSERVER',None)
    return opened, commands


def test_genuine_root_to_control_to_v7_to_selected_maintenance(tmp_path,monkeypatch):
    f=_fixture(tmp_path,monkeypatch)
    database=Path(f.runtime.store.path)
    original={p:p.read_bytes() for bundle in (f.middle_bundle,f.deeper_bundle) for p in bundle.iterdir()}
    original_barrier=(f.barrier.read_bytes(),f.barrier.stat().st_ino)
    # Actual Root issuer retains the genuine v5/selected/deeper source and
    # writes its real fourteen-field qualification under the canonical lock.
    qualification_result=m.prepare(f.args)
    qualification=json.loads(f.destination.read_bytes())
    assert qualification['original_barrier']['payload']==f.barrier_payload
    assert len(qualification)==14
    opened,commands=_control_boundary(f,monkeypatch)
    seen=[]
    def before_remove(phase):
        if phase=='before_barrier_unlink':
            assert (f.barrier.read_bytes(),f.barrier.stat().st_ino)==original_barrier
            seen.append(phase)
    monkeypatch.setattr(b,'_SCHEMA_UPGRADE_TEST_HOOK',before_remove)
    # Actual one-use Control owner, real exclusive SQLite DDL, source/target
    # backup/drill and completion; neither reservation nor P56 is fabricated.
    b.resume_v5_to_v6_pre_census(database,Path(f.config['backup_root']),release_sha=SUCCESSOR,
        expected_operation_id=f.barrier_payload['operation_id'],
        expected_barrier_sha256=qualification['original_barrier']['identity']['sha256'])
    assert seen==['before_barrier_unlink']
    monkeypatch.setattr(b,'_SCHEMA_UPGRADE_TEST_HOOK',None)
    assert not opened
    pre56=json.loads((database.parent/b._UPGRADE_V5_TO_V6_PREFLIGHT_NAME).read_bytes())
    assert pre56['schema_version']==b.PRE_CENSUS_PREFLIGHT_SCHEMA
    assert pre56['operation_id']==f.barrier_payload['operation_id']
    assert pre56['barrier_identity']==qualification['original_barrier']['identity']
    assert pre56['quiesce_writer_census']['schema_version']==b.PRE_CENSUS_CENSUS_SCHEMA
    assert len(pre56['quiesce_writer_census']['open_files'])==3
    assert f.destination.read_bytes()==b._upgrade_receipt_bytes(qualification)
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='intent already exists'):
        b.resume_v5_to_v6_pre_census(database,Path(f.config['backup_root']),release_sha=SUCCESSOR,
            expected_operation_id=f.barrier_payload['operation_id'],
            expected_barrier_sha256=qualification['original_barrier']['identity']['sha256'])
    # Existing ordinary67 gate must admit exactly the completed recovery chain.
    b.upgrade_v6_to_v7(database,Path(f.config['backup_root']),release_sha=SUCCESSOR)
    assert not opened
    assert {command[0] for command in commands}=={'/bin/ps','/usr/sbin/lsof'}
    pre67=json.loads((database.parent/b._UPGRADE_V6_TO_V7_PREFLIGHT_NAME).read_bytes())
    assert pre67['quiesce_writer_census']['schema_version']==b.UPGRADE_CENSUS_SCHEMA
    assert len(pre67['quiesce_writer_census']['open_files'])==1
    monkeypatch.setattr(evidence,'_prove_current_release',lambda sha:b._prove_upgrade_release(sha))
    with evidence.open_v5_to_v7_evidence(f.runtime_root,SUCCESSOR) as retained:
        material=copy.deepcopy(retained.material)
        assert material['schema_version']==evidence.RECOVERED_MATERIAL_SCHEMA_VERSION
        assert len(material['origin_records'])==14
        assert retained.pre_census_qualification==qualification
        assert len(retained.inventory_additions)==8
        m._bind_pre_census_selected(retained,MIDDLE,f.middle,
            (m.SYSTEM_ROOT/'config/control.json').read_bytes())
    # Real normal maintenance producer then INITIAL admission consume the
    # recovered helper and publish the working v7 baseline, not an old v5 view.
    f.database=database;f.tool_release=SUCCESSOR
    f.v7_before=m.snapshot(database,immutable=True)
    issued=_issued(tmp_path,monkeypatch,f=f)
    _,descriptor,bundle,owner=_admitted(tmp_path,monkeypatch,issued=issued)
    assert len(m.sealed_json(bundle/m._V5_TO_V7_EVIDENCE_NAME)['origin_records'])==14
    assert descriptor['schema_upgrade_evidence_sha256']==m.digest(material)
    assert original=={p:p.read_bytes() for p in original}
    assert owner.before==f.v7_before

    # The recovery variant also reaches the real first-finish/historical
    # consumer after ordinary proof-time backups and a physical restoration.
    # Existing synthetic lost-process observation DATA is explicit; no process
    # or provider is launched. All Runtime/receipt/preservation checks are real.
    proof_ids = _actual_proof_delta(f, descriptor)
    receipt, verification, drill, applied = _proof_backup_chain(f, tmp_path)
    acceptance_root = _write_proof_receipts(f, receipt, verification, drill, applied)
    summary = _real_pass_summary(f, proof_ids)
    summary_path = acceptance_root/'acceptance-summary.json'
    _write_receipt(summary_path, summary)
    service_fd = os.open(f.lock, os.O_RDWR)
    fcntl.flock(service_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    live = sqlite3.connect(database)
    live.execute('PRAGMA journal_mode=WAL')
    with live:
        live.execute('UPDATE workers SET last_seen_at_ms=last_seen_at_ms+1, '
                     'updated_at_ms=updated_at_ms+1,version=version+1')
    try:
        owner.finish(proof_ids, summary_path)
    finally:
        live.close()
        fcntl.flock(service_fd, fcntl.LOCK_UN)
        os.close(service_fd)
    carry = m.sealed_json(bundle/'carry-forward.json')
    assert carry['passed'] is True
    future = {key:value for key,value in descriptor.items() if key not in {
        'superseded_unstarted_preproof_sha','superseded_descriptor_sha256',
        'schema_upgrade_evidence_sha256','source_control_config_sha256'}}
    future.update(schema_version=m.SCHEMA_V2, predecessor_sha=SUCCESSOR,
        successor_sha='1'*40, prior_descriptor_sha256=m.digest(descriptor),
        prior_carry_sha256=m.digest(carry),
        prior_summary_sha256=hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        frozen_base_sha=descriptor['frozen_base_sha'])
    future_bundle = m.bundle_path('1'*40);future_bundle.mkdir()
    m.write_sealed(future_bundle/'descriptor.json',future,public=True)
    from control_plane.executive_runtime import Runtime
    Runtime.at(f.runtime_root).jobs.create_job('later unrelated inert recovery-fixture job')
    m.validate_prior_carry_binding(future)
    assert original == {p:p.read_bytes() for p in original}
