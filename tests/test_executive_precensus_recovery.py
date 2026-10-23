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
