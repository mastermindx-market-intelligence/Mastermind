"""Inert fixed-leaf and same-operation recovery discriminators.

Host principals/metadata are explicit fixture seams. All payload IO is through
real held descriptors under the disposable fixture; no live host path is read.
"""
from pathlib import Path
from types import SimpleNamespace
import json
import os
import stat

import pytest

from control_plane import executive_backup as b
from control_plane import fs_security


@pytest.fixture
def fixed_leaf(tmp_path, monkeypatch):
    top = tmp_path / 'top'
    database = top / 'control/db/data/control_plane/executive.sqlite3'
    database.parent.mkdir(parents=True)
    leaf = database.parent / b._UPGRADE_BARRIER_NAME
    releases = tmp_path / 'releases'
    value = {'schema_version': b.UPGRADE_BARRIER_SCHEMA,
             'operation_id': 'a' * 32, 'database_path': str(database),
             'tool_release_root': str(releases / ('1' * 40)),
             'tool_release_tree_sha': '2' * 40,
             'tool_release_manifest_sha256': '3' * 64,
             'release_sha': '1' * 40, 'control_uid': 450,
             'created_at': '2026-10-23T23:00:00Z'}
    leaf.write_bytes(b._upgrade_receipt_bytes(value));leaf.chmod(0o600)
    state = SimpleNamespace(leaf=leaf, database=database, payload=value,
                            uid=450, gid=450, euid=450, egid=450,
                            mode=0o600, links=1, acl=False, mutation=None,
                            opens=[], reads=0, closes=[], open_fds={},
                            before_read=None, named_change=False)
    original = os
    proxy = SimpleNamespace(**{name:getattr(os,name) for name in dir(os)})
    def metadata(path, fd=None):
        real = original.fstat(fd) if fd is not None else original.lstat(path)
        result = SimpleNamespace(**{name:getattr(real,name) for name in dir(real) if name.startswith('st_')})
        if Path(path) == leaf:
            result.st_uid=state.uid;result.st_gid=state.gid
            result.st_mode=stat.S_IFREG | state.mode;result.st_nlink=state.links
            if state.named_change and fd is None:result.st_ino += 1
        else:
            result.st_uid=0;result.st_gid=0;result.st_mode=stat.S_IFDIR | 0o755
            if Path(path)==top:result.st_mode=stat.S_IFDIR | 0o711
            elif top in Path(path).parents:
                result.st_uid=450;result.st_gid=450;result.st_mode=stat.S_IFDIR | 0o700
        return result
    def opened(path, flags, *args, **kwargs):
        assert Path(path) == leaf, 'ancestor-directory READ or foreign payload open'
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        assert flags & os.O_NOFOLLOW
        state.opens.append((str(path),flags))
        fd=original.open(path,flags,*args,**kwargs);state.open_fds[fd]=Path(path);return fd
    def read(fd, size):
        if state.before_read:state.before_read();state.before_read=None
        state.reads+=1
        return original.read(fd,size)
    def close(fd):
        state.closes.append(fd);state.open_fds.pop(fd,None);return original.close(fd)
    proxy.lstat=lambda path:metadata(path)
    proxy.fstat=lambda fd:metadata(state.open_fds[fd],fd)
    proxy.open=opened;proxy.read=read;proxy.close=close
    proxy.geteuid=lambda:state.euid;proxy.getegid=lambda:state.egid
    proxy.listdir=lambda *a:pytest.fail('directory enumeration')
    proxy.scandir=lambda *a:pytest.fail('directory enumeration')
    monkeypatch.setattr(b,'os',proxy)
    monkeypatch.setattr(b,'_PRE_CENSUS_DATABASE',database)
    monkeypatch.setattr(b,'_PRE_CENSUS_RELEASES',releases)
    monkeypatch.setattr(b,'_pre_census_control_identity',lambda:(450,450))
    monkeypatch.setattr(fs_security,'has_macos_acl',lambda path,**kw:state.acl)
    for name in ('_upgrade_census','_checkpoint_quiesced_wal','create_offline_backup',
                 '_offline_restore_lock','_readonly_database','_write_private_json'):
        monkeypatch.setattr(b,name,lambda *a,_name=name,**kw:pytest.fail('inspection effect '+_name))
    return state


def test_fixed_leaf_inspection_never_reads_ancestor_or_database(fixed_leaf):
    s=fixed_leaf;before=s.leaf.read_bytes()
    result=b.inspect_v5_to_v6_pre_census_barrier()
    assert result['schema_version']==b.PRE_CENSUS_INSPECTION_SCHEMA
    assert result['original_barrier']['payload']==s.payload
    assert result['original_barrier']['identity']['inode']==s.leaf.stat().st_ino
    assert s.leaf.read_bytes()==before
    assert s.opens and not s.open_fds
    assert set(result)=={'schema_version','original_barrier','custody'}


@pytest.mark.parametrize('field,value', [('uid',451),('gid',451),('mode',0o644),('links',2),('acl',True),('euid',0),('egid',451)])
def test_fixed_leaf_custody_refuses_before_payload(fixed_leaf,field,value):
    s=fixed_leaf;setattr(s,field,value)
    with pytest.raises(b.ExecutiveSchemaUpgradeError):b.inspect_v5_to_v6_pre_census_barrier()
    assert s.reads==0 and not s.open_fds


@pytest.mark.parametrize('change', ['extra','missing','duplicate','noncanonical','badop','badtool','baddb','badtime','oversized'])
def test_fixed_leaf_closed_canonical_wire(fixed_leaf,change):
    s=fixed_leaf;value=dict(s.payload)
    if change=='extra':value['phase']='not-recorded'
    if change=='missing':value.pop('created_at')
    if change=='badop':value['operation_id']='8632'
    if change=='badtool':value['tool_release_root']='/foreign/tool'
    if change=='baddb':value['database_path']='/foreign/db'
    if change=='badtime':value['created_at']='2026-10-23'
    raw=b._upgrade_receipt_bytes(value)
    if change=='duplicate':raw=raw[:-2]+b', "control_uid":450}\n'
    if change=='noncanonical':raw=json.dumps(value).encode()
    if change=='oversized':raw=b' '*(b._PRE_CENSUS_LIMIT+1)
    s.leaf.write_bytes(raw)
    with pytest.raises((b.ExecutiveSchemaUpgradeError, b.BackupVerificationError)):b.inspect_v5_to_v6_pre_census_barrier()
    assert not s.open_fds


def test_leaf_permission_denial_is_not_rerouted(fixed_leaf):
    s=fixed_leaf
    def denied(*a,**kw):raise PermissionError('inert exact-leaf denial')
    b.os.open=denied
    with pytest.raises(PermissionError):b.inspect_v5_to_v6_pre_census_barrier()
    assert s.reads==0


def test_named_leaf_swap_during_read_refuses(fixed_leaf):
    s=fixed_leaf;s.before_read=lambda:setattr(s,'named_change',True)
    with pytest.raises(b.ExecutiveSchemaUpgradeError):b.inspect_v5_to_v6_pre_census_barrier()
    assert not s.open_fds


def test_inspection_cli_needs_no_arbitrary_paths(fixed_leaf, capsys):
    from scripts import executive_os_migrate as cli
    assert cli.main(['--inspect-v5-to-v6-pre-census-barrier']) == 0
    result=json.loads(capsys.readouterr().out)
    assert result['original_barrier']['payload']['operation_id'] == fixed_leaf.payload['operation_id']


@pytest.mark.parametrize('extra', [
    ['--database','/foreign/db'], ['--backup-directory','/foreign/backups'],
    ['--release-sha','1'*40], ['--expected-operation-id','a'*32],
    ['--transition','v5-to-v6'], ['--resume-v5-to-v6-pre-census'],
])
def test_inspection_cli_rejects_other_effect_selectors(fixed_leaf,extra):
    from scripts import executive_os_migrate as cli
    with pytest.raises(SystemExit) as error:
        cli.main(['--inspect-v5-to-v6-pre-census-barrier',*extra])
    assert error.value.code == 2 and not fixed_leaf.opens

@pytest.fixture
def control_recovery(tmp_path, monkeypatch):
    """Real SQLite/FD/wire IO; fixed account, seal and Root config are host seams."""
    import hashlib
    from test_executive_upgrade_v6 import _exact_v5
    from ops.executive_os import acceptance_maintenance as maintenance
    top=tmp_path/'top'
    db=top/'control/db/data/control_plane/executive.sqlite3'
    db.parent.mkdir(parents=True)
    _exact_v5(db);db.chmod(0o600)
    backups=top/'control/backups';backups.mkdir(mode=0o700)
    releases=tmp_path/'releases';releases.mkdir()
    oldsha,newsha='1'*40,'e'*40
    for sha in (oldsha,newsha):(releases/sha).mkdir()
    uid,gid=os.geteuid(),os.getegid()
    lock=db.parent/b.DEFAULT_SERVICE_LOCK_NAME;lock.touch(mode=0o600)
    monkeypatch.setattr(b,'_PRE_CENSUS_DATABASE',db)
    monkeypatch.setattr(b,'_PRE_CENSUS_RELEASES',releases)
    monkeypatch.setattr(b,'_pre_census_control_identity',lambda:(uid,gid))
    monkeypatch.setattr(b,'_SCHEMA_UPGRADE_RELEASE_OBSERVER',lambda:{'release_root':str(releases/newsha),'release_sha':newsha,'release_tree_sha':'b'*40,'release_manifest_sha256':'c'*64})
    monkeypatch.setattr(b,'_pre_census_prove_original_tool',lambda tool:None)
    monkeypatch.setattr(fs_security,'has_macos_acl',lambda *a,**k:False)
    # Identity profiles are already discriminated by fixed_leaf tests; this
    # host seam permits local UID-owned fixtures, without changing byte/FD IO.
    monkeypatch.setattr(b,'_pre_census_ancestors',lambda path,*a:tuple((str(p),p.lstat().st_dev,p.lstat().st_ino) for p in path.parents))
    leaf_reader=b._pre_census_leaf
    monkeypatch.setattr(b,'_pre_census_leaf',lambda path,fd,*,uid,gid,mode:leaf_reader(path,fd,uid=os.geteuid() if uid==0 else uid,gid=gid,mode=mode))
    configpath=releases.parent/'config/control.json';configpath.parent.mkdir()
    cfg={'proof_base_sha':'8'*40,'runtime_root':str(db.parents[2]),'backup_root':str(backups)}
    configraw=b._upgrade_receipt_bytes(cfg);configpath.write_bytes(configraw)
    class RootConfig:
        def __init__(self):self.path=configpath;self.raw=configraw;self.value=cfg
        def check(self):assert configpath.read_bytes()==self.raw
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(maintenance,'_RootConfig',RootConfig)
    monkeypatch.setattr(maintenance,'require_disarmed',lambda config:None)
    barrier=db.parent/b._UPGRADE_BARRIER_NAME
    original={'schema_version':b.UPGRADE_BARRIER_SCHEMA,'operation_id':'a'*32,'database_path':str(db),'tool_release_root':str(releases/oldsha),'tool_release_tree_sha':'2'*40,'tool_release_manifest_sha256':'3'*64,'release_sha':oldsha,'control_uid':uid,'created_at':'2026-10-23T23:00:00Z'}
    barrier.write_bytes(b._upgrade_receipt_bytes(original));barrier.chmod(0o600)
    identity=b._artifact_identity(barrier,expected_payload=original)
    fd=os.open(db,os.O_RDONLY)
    try:origin=b._pre_census_database_origin(db,fd,uid,gid)
    finally:os.close(fd)
    state=b._upgrade_v5_retained_state(db,version=5)
    qualification={'schema_version':b.PRE_CENSUS_QUALIFICATION_SCHEMA,'operation_id':original['operation_id'],'original_barrier':{'payload':original,'identity':identity},'original_tool':{'root':str(releases/oldsha),'sha':oldsha,'tree_sha':'2'*40,'manifest_sha256':'3'*64},'recovery_tool':{'root':str(releases/newsha),'sha':newsha,'tree_sha':'b'*40,'manifest_sha256':'c'*64},'database':origin,'normalized_schema_digest':state['normalized_schema_digest'],'full_v5_content_digest':state['full_v5_content_digest'],'migration_vector':state['migration_vector'],'selected_source':{'sha':'8'*40,**{name:'9'*64 for name in ('descriptor_raw_sha256','descriptor_sha256','source_backup_sha256','baseline_sha256','inventory_sha256','prior_canary_sha256')}},'source_control_config':{'path':str(configpath),'sha256':hashlib.sha256(configraw).hexdigest()},'host':{'runtime_root':str(db.parents[2]),'backup_root':str(backups),'control_uid':uid,'control_gid':gid},'created_at':'2026-10-24T00:00:00Z','backup_inventory_sha256':maintenance.digest(b._pre_census_backup_inventory(backups))}
    qpath=db.parent/b.PRE_CENSUS_QUALIFICATION_NAME
    qpath.write_bytes(b._upgrade_receipt_bytes(qualification));qpath.chmod(0o440)
    fixture=SimpleNamespace(database=db,backups=backups,barrier=barrier,original=original,identity=identity,qualification=qualification,qpath=qpath,release=newsha,wire_change=None,commands=[],fd_paths={})
    proxy=SimpleNamespace(**{name:getattr(os,name) for name in dir(os)})
    def opened(path,flags,*a,**kw):
        fd=os.open(path,flags,*a,**kw);fixture.fd_paths[fd]=Path(path);return fd
    def closed(fd):fixture.fd_paths.pop(fd,None);return os.close(fd)
    proxy.open=opened;proxy.close=closed
    monkeypatch.setattr(b,'os',proxy)
    def sensor(command):
        fixture.commands.append(command)
        if command[0]=='/bin/ps':return (0,f'{os.getpid()} {uid} {uid} {uid} own\n999999 {uid} {uid} {uid} sensor\n','',999999)
        assert command[0]=='/usr/sbin/lsof'
        rows=[f'p{os.getpid()}',f'u{uid}']
        for fd,path in sorted(fixture.fd_paths.items()):
            if path in (db,lock,barrier):rows.extend([f'f{fd}',f'n{path}'])
        if fixture.wire_change:rows=fixture.wire_change(rows)
        return (0,'\n'.join(rows)+'\n','',999998)
    monkeypatch.setattr(b,'_run_census_command',sensor)
    return fixture


def _resume(s):
    return b.resume_v5_to_v6_pre_census(s.database,s.backups,release_sha=s.release,expected_operation_id=s.original['operation_id'],expected_barrier_sha256=s.identity['sha256'])


def test_actual_same_operation_continuation_preserves_old_identity_and_new_executor(control_recovery,monkeypatch):
    s=control_recovery;seen=[]
    def hook(phase):
        if phase=='before_barrier_unlink':
            assert s.barrier.read_bytes()==b._upgrade_receipt_bytes(s.original)
            assert s.barrier.stat().st_ino==s.identity['inode'];seen.append(phase)
    monkeypatch.setattr(b,'_SCHEMA_UPGRADE_TEST_HOOK',hook)
    receipt=_resume(s)
    assert receipt.release_sha==s.release
    assert seen==['before_barrier_unlink'] and not s.barrier.exists()
    p=json.loads((s.database.parent/b._UPGRADE_V5_TO_V6_PREFLIGHT_NAME).read_bytes())
    assert p['schema_version']==b.PRE_CENSUS_PREFLIGHT_SCHEMA
    assert p['created_at']==s.original['created_at'] and p['release_sha']!=s.original['release_sha']
    assert p['barrier_identity']==s.identity
    assert p['quiesce_writer_census']['schema_version']==b.PRE_CENSUS_CENSUS_SCHEMA
    assert len(p['quiesce_writer_census']['open_files'])==3
    assert len({row['fd'] for row in p['quiesce_writer_census']['open_files']})==3
    assert b.verify_backup(s.database,expected_schema_version=6)
    assert not s.fd_paths
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='intent already exists'):_resume(s)

@pytest.mark.parametrize('phase',['barrier_persisted','preflight_persisted','after_m6_statement:01','after_v6_commit_before_checkpoint','completion_persisted'])
def test_consumed_failure_stays_quarantined_and_cannot_be_replayed(control_recovery,monkeypatch,phase):
    s=control_recovery;original=s.barrier.read_bytes();inode=s.barrier.stat().st_ino
    def fail(observed):
        if observed==phase:raise RuntimeError('inert post-intent failure')
    monkeypatch.setattr(b,'_SCHEMA_UPGRADE_TEST_HOOK',fail)
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='intent retained'):_resume(s)
    assert s.barrier.read_bytes()==original and s.barrier.stat().st_ino==inode
    assert (s.database.parent/b.PRE_CENSUS_CONTINUATION_NAME).is_file()
    assert not s.fd_paths
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='intent already exists'):_resume(s)
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='residue'):
        b.upgrade_v5_to_v6(s.database,s.backups,release_sha=s.release)


@pytest.mark.parametrize('action',['missing','swapped'])
def test_lost_original_barrier_never_regenerated_after_intent(control_recovery,monkeypatch,action):
    s=control_recovery
    def mutate(phase):
        if phase=='barrier_persisted':
            s.barrier.unlink()
            if action=='swapped':
                s.barrier.write_bytes(b._upgrade_receipt_bytes(s.original));s.barrier.chmod(0o600)
    monkeypatch.setattr(b,'_SCHEMA_UPGRADE_TEST_HOOK',mutate)
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='intent retained'):_resume(s)
    if action=='missing':assert not s.barrier.exists()
    else:assert s.barrier.stat().st_ino!=s.identity['inode']
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='intent already exists'):_resume(s)
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='residue'):
        b.upgrade_v5_to_v6(s.database,s.backups,release_sha=s.release)
    assert not s.fd_paths


@pytest.mark.parametrize('adverse',['foreign','duplicate','missing','wrongfd'])
def test_recovered_census_uses_actual_lsof_wire_not_declared_allowance(control_recovery,adverse):
    s=control_recovery
    def change(rows):
        if adverse=='foreign':return rows+['p999991','u'+str(os.geteuid()),'f88','n'+str(s.database)]
        if adverse=='duplicate':return rows+rows[-2:]
        if adverse=='missing':return rows[:-2]
        rows=list(rows);rows[-2]='f999';return rows
    s.wire_change=change
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='intent retained'):_resume(s)
    assert s.barrier.exists() and not (s.database.parent/b._UPGRADE_V5_TO_V6_PREFLIGHT_NAME).exists()
    assert not s.fd_paths


def test_complete_recovered56_allows_ordinary67_with_original_census(control_recovery):
    s=control_recovery
    _resume(s)
    # The recovered owner closed its DB/barrier descriptors. The actual next
    # ordinary sensor now sees only its own real canonical flock descriptor.
    result=b.upgrade_v6_to_v7(s.database,s.backups,release_sha=s.release)
    assert result.target_schema_version==7
    preflight=json.loads((s.database.parent/b._UPGRADE_V6_TO_V7_PREFLIGHT_NAME).read_bytes())
    assert preflight['schema_version']==b.UPGRADE_PREFLIGHT_SCHEMA
    assert preflight['quiesce_writer_census']['schema_version']==b.UPGRADE_CENSUS_SCHEMA
    assert len(preflight['quiesce_writer_census']['open_files'])==1
    assert not s.fd_paths


@pytest.mark.parametrize('drift',['intent','p56','c56','pair'])
def test_ordinary67_refuses_incomplete_or_drifted_recovered_completion(control_recovery,drift):
    s=control_recovery;result=_resume(s)
    names={'intent':b.PRE_CENSUS_CONTINUATION_NAME,'p56':b._UPGRADE_V5_TO_V6_PREFLIGHT_NAME,'c56':b._UPGRADE_V5_TO_V6_COMPLETION_NAME}
    if drift=='pair':Path(result.v5_backup_path).unlink()
    else:(s.database.parent/names[drift]).unlink()
    with pytest.raises((b.ExecutiveSchemaUpgradeError,OSError)):
        b.upgrade_v6_to_v7(s.database,s.backups,release_sha=s.release)
    assert not (s.database.parent/b._UPGRADE_BARRIER_NAME).exists()
    assert not (s.database.parent/b._UPGRADE_V6_TO_V7_PREFLIGHT_NAME).exists()
    assert not s.fd_paths

@pytest.mark.parametrize('adverse',['writable_fd','foreign_sidecar','replaced_journal'])
def test_transaction_owned_scope_never_admits_foreign_or_writable_artifacts(control_recovery,monkeypatch,adverse):
    s=control_recovery
    if adverse=='writable_fd':
        import fcntl
        proxy=SimpleNamespace(**{name:getattr(fcntl,name) for name in dir(fcntl)})
        original=fcntl.fcntl
        def flags(fd,op,*args):
            if op==fcntl.F_GETFL and s.fd_paths.get(fd)==s.barrier:return os.O_RDWR
            return original(fd,op,*args)
        proxy.fcntl=flags;monkeypatch.setattr(b,'fcntl',proxy)
    else:
        def mutate(phase):
            if phase=='after_m6_statement:01':
                if adverse=='foreign_sidecar':
                    path=Path(str(s.database)+'-shm');path.write_bytes(b'inert foreign');path.chmod(0o600)
                else:
                    path=Path(str(s.database)+'-journal')
                    assert path.exists(), 'real DELETE transaction must own a journal'
                    replacement=path.with_name('replacement')
                    replacement.write_bytes(path.read_bytes());replacement.chmod(0o600)
                    replacement.replace(path)
        monkeypatch.setattr(b,'_SCHEMA_UPGRADE_TEST_HOOK',mutate)
    with pytest.raises(b.ExecutiveSchemaUpgradeError,match='intent retained'):_resume(s)
    assert s.barrier.exists() and (s.database.parent/b.PRE_CENSUS_CONTINUATION_NAME).exists()
    assert not s.fd_paths


def test_original_tool_is_verified_at_retained_root_not_as_executing_release(tmp_path,monkeypatch):
    import hashlib
    from ops.executive_os import autonomy_control,release_manifest
    releases=tmp_path/'releases';monkeypatch.setattr(b,'_PRE_CENSUS_RELEASES',releases)
    raw=b'qualified retained manifest';sha='1'*40;tree='2'*40
    tool={'root':str(releases/sha),'sha':sha,'tree_sha':tree,'manifest_sha256':hashlib.sha256(raw).hexdigest()}
    calls=[]
    monkeypatch.setattr(release_manifest,'verify',lambda root,expected,expected_tree:calls.append((root,expected,expected_tree)) or {'commit_sha':expected,'tree_sha':expected_tree})
    monkeypatch.setattr(autonomy_control,'_release_manifest_bytes',lambda expected:raw if expected==sha else b'other')
    monkeypatch.setattr(b,'_prove_upgrade_release',lambda *a:pytest.fail('old tool is not current executing origin'))
    b._pre_census_prove_original_tool(tool)
    assert calls==[(releases/sha,sha,tree)]
    with pytest.raises(b.ExecutiveSchemaUpgradeError):
        b._pre_census_prove_original_tool({**tool,'sha':'e'*40,'root':str(releases/('e'*40))})
