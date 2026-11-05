"""Recovery wire folding over real four-step receipts and four verified pairs.

The Root qualification here is a constructed protocol fixture; it is NOT
counted as the real Root issuer or Control continuation test. Host principal,
release seals and process census are the original fixture's explicit seams.
Original backup verification/drills/full projections and all retained readers
run unchanged. The final integrated owner test exercises actual issuance.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from control_plane import executive_backup as backup
from ops.executive_os import schema_upgrade_evidence as evidence
from tests.test_executive_schema_upgrade_evidence import (
    _build_chain, _receipt_path, _write_private,
)

CENSUS = 'mastermind.executive_schema_upgrade_quiesce/pre_census_recovery_v1'
OLD = '9'*40


def _ref(path, payload):
    info = path.stat(); raw = path.read_bytes()
    return dict(path=str(path), device=info.st_dev, inode=info.st_ino,
                size=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                payload_digest=backup._upgrade_digest(payload))


def _write(path, payload, mode=0o600):
    if path.exists(): path.chmod(0o600)
    _write_private(path, backup._upgrade_receipt_bytes(payload)); path.chmod(mode)


def _recovered(tmp_path, monkeypatch):
    runtime, backups, config, release = _build_chain(tmp_path, monkeypatch)
    state = runtime/'data/control_plane'; database = state/'executive.sqlite3'
    pre = json.loads(_receipt_path(runtime, 'P56').read_bytes())
    top = Path(pre['tool_release_root']).parent
    new_config = top.parent/'config/control.json'; new_config.parent.mkdir(mode=0o700)
    _write_private(new_config, config.read_bytes()); new_config.chmod(0o440)
    monkeypatch.setattr(evidence, '_control_config_path', lambda: new_config)
    monkeypatch.setattr(backup, '_PRE_CENSUS_DATABASE', database)
    monkeypatch.setattr(backup, '_PRE_CENSUS_RELEASES', top)
    monkeypatch.setattr(backup, 'PRE_CENSUS_CENSUS_SCHEMA', CENSUS, raising=False)
    old_barrier = dict(schema_version=backup.UPGRADE_BARRIER_SCHEMA,
        operation_id=pre['operation_id'], database_path=str(database),
        tool_release_root=str(top/OLD), release_sha=OLD,
        tool_release_tree_sha='b'*40, tool_release_manifest_sha256='c'*64,
        control_uid=os.getuid(), created_at=pre['created_at'])
    raw = backup._upgrade_receipt_bytes(old_barrier)
    barrier_identity = dict(pre['barrier_identity'], size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(), payload_digest=backup._upgrade_digest(old_barrier))
    info = database.stat()
    source = dict(pre['database'], uid=os.getuid(), gid=os.getgid(), mode=0o600,
                  nlink=1, mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)
    v5_database = Path(pre['v5_backup']['database_path'])
    with backup._readonly_database(v5_database) as connection:
        content = backup.full_v5_content_digest(connection)
        _, _, vector = backup._verify_connection(connection, expected_schema_version=5)
    tool = dict(root=pre['tool_release_root'], sha=release,
                tree_sha=pre['tool_release_tree_sha'], manifest_sha256=pre['tool_release_manifest_sha256'])
    qualification = dict(schema_version=backup.PRE_CENSUS_QUALIFICATION_SCHEMA,
        operation_id=pre['operation_id'], original_barrier=dict(payload=old_barrier,identity=barrier_identity),
        original_tool=dict(root=str(top/OLD), sha=OLD, tree_sha='b'*40, manifest_sha256='c'*64),
        recovery_tool=tool, database=source, normalized_schema_digest=pre['normalized_schema_digest'],
        full_v5_content_digest=content, migration_vector=[row.to_dict() for row in vector],
        selected_source=dict(sha='8'*40, **{key:'7'*64 for key in (
            'descriptor_raw_sha256','descriptor_sha256','source_backup_sha256',
            'baseline_sha256','inventory_sha256','prior_canary_sha256')}),
        source_control_config=dict(path=str(new_config),sha256=hashlib.sha256(new_config.read_bytes()).hexdigest()),
        host=dict(runtime_root=str(runtime),backup_root=str(backups),control_uid=os.getuid(),control_gid=os.getgid()),
        backup_inventory_sha256='6'*64, created_at='2026-10-23T19:00:00+00:00')
    qpath = state/backup.PRE_CENSUS_QUALIFICATION_NAME
    _write(qpath,qualification,0o440)
    intent = dict(schema_version=backup.PRE_CENSUS_CONTINUATION_SCHEMA,
        operation_id=pre['operation_id'],original_barrier_identity=barrier_identity,
        qualification_identity=_ref(qpath,qualification),recovery_tool=tool,
        created_at='2026-10-23T19:01:00+00:00')
    ipath=state/backup.PRE_CENSUS_CONTINUATION_NAME; _write(ipath,intent)
    pre.update(schema_version=evidence._RECOVERED_PREFLIGHT_SCHEMA,
        barrier_identity=barrier_identity,pre_census_reconciliation=dict(
            qualification_identity=_ref(qpath,qualification),continuation_identity=_ref(ipath,intent)))
    census = pre['quiesce_writer_census']; census['schema_version']=CENSUS
    own = census['open_files'][0]
    census['open_files'] = [dict(own,fd=str(fd),path=str(path)) for fd,path in enumerate((
        state/backup.DEFAULT_SERVICE_LOCK_NAME,state/backup._UPGRADE_BARRIER_NAME,database),start=100)]
    pre['quiesce_writer_census_digest']=backup._upgrade_digest(census)
    _write(_receipt_path(runtime,'P56'),pre)
    cpath=_receipt_path(runtime,'C56'); completion=json.loads(cpath.read_bytes())
    completion['preflight_receipt_digest']=backup._upgrade_digest(pre)
    completion['quiesce_writer_census_digest']=pre['quiesce_writer_census_digest']; _write(cpath,completion)
    return runtime,release,qpath,ipath,qualification


def test_explicit_recovery_retains_fourteen_origins_and_historical_provenance(tmp_path,monkeypatch):
    runtime,release,qpath,ipath,qualification=_recovered(tmp_path,monkeypatch)
    with evidence.open_v5_to_v7_evidence(runtime,release) as opened:
        material=copy.deepcopy(opened.material)
        assert material['schema_version']==evidence.RECOVERED_MATERIAL_SCHEMA_VERSION
        assert len(material['origin_records'])==14
        assert opened.pre_census_qualification==qualification
        assert material['chain']['tool_release']['sha']==release
        assert material['chain']['pre_census_reconciliation']['original_tool']['sha']==OLD
        assert len(opened.inventory_additions)==8
    # Historical verification must not require the original current physical
    # identity or backup-root digest after legitimate proof-time additions.
    (runtime/'data/control_plane/executive.sqlite3').write_bytes(b'later database')
    with evidence.open_retained_v5_to_v7_evidence(runtime,release,material) as historical:
        assert historical.material==material
        assert historical.pre_census_qualification==qualification


@pytest.mark.parametrize('fault',['root-mode','intent-ref','source-full','source-sequence',
                                  'executor','old-tool','extra-key','census-foreign','census-duplicate'])
def test_recovery_immutable_join_refuses_mutated_origin(tmp_path,monkeypatch,fault):
    runtime,release,qpath,ipath,qualification=_recovered(tmp_path,monkeypatch)
    if fault=='root-mode': qpath.chmod(0o600)
    elif fault=='intent-ref':
        value=json.loads(ipath.read_bytes()); value['qualification_identity']['inode']+=1; _write(ipath,value)
    elif fault in {'census-foreign','census-duplicate'}:
        path=_receipt_path(runtime,'P56'); value=json.loads(path.read_bytes())
        rows=value['quiesce_writer_census']['open_files']
        if fault=='census-foreign': rows[-1]['path']=str(runtime/'foreign')
        else: rows[-1]['fd']=rows[0]['fd']
        value['quiesce_writer_census_digest']=backup._upgrade_digest(value['quiesce_writer_census']);_write(path,value)
        cpath=_receipt_path(runtime,'C56'); c=json.loads(cpath.read_bytes());c['preflight_receipt_digest']=backup._upgrade_digest(value);c['quiesce_writer_census_digest']=value['quiesce_writer_census_digest'];_write(cpath,c)
    else:
        if fault=='source-full': qualification['full_v5_content_digest']='0'*64
        elif fault=='source-sequence': qualification['migration_vector'][-1]['checksum']='0'*64
        elif fault=='executor': qualification['recovery_tool']['sha']='1'*40
        elif fault=='old-tool': qualification['original_tool']['manifest_sha256']='0'*64
        else: qualification['unexpected']=True
        _write(qpath,qualification,0o440)
        # Rebind all hash refs to test substantive DATA joins, not merely a
        # stale byte hash. No fixture is treated as real Root issuance.
        intent=json.loads(ipath.read_bytes());intent['qualification_identity']=_ref(qpath,qualification);_write(ipath,intent)
        path=_receipt_path(runtime,'P56'); pre=json.loads(path.read_bytes())
        pre['pre_census_reconciliation']=dict(qualification_identity=_ref(qpath,qualification),continuation_identity=_ref(ipath,intent));_write(path,pre)
        cpath=_receipt_path(runtime,'C56'); c=json.loads(cpath.read_bytes());c['preflight_receipt_digest']=backup._upgrade_digest(pre);_write(cpath,c)
    with pytest.raises((evidence.SchemaUpgradeEvidenceError,backup.ExecutiveSchemaUpgradeError)):
        with evidence.open_v5_to_v7_evidence(runtime,release): pass


def test_normal_twelve_origins_do_not_accept_recovery_kind(tmp_path,monkeypatch):
    runtime,backups,config,release=_build_chain(tmp_path,monkeypatch)
    with evidence.open_v5_to_v7_evidence(runtime,release) as opened:
        pinned=copy.deepcopy(opened.material)
        assert len(pinned['origin_records'])==12
        assert opened.pre_census_qualification is None
    pinned['origin_records'].append(copy.deepcopy(pinned['origin_records'][0]))
    with pytest.raises(evidence.RetainedChainInvalid):
        with evidence.open_retained_v5_to_v7_evidence(runtime,release,pinned): pass
