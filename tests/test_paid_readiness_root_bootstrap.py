"""Actual import ordering with disposable Root/ACL premises, no installed reads."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

import pytest

SOURCE=Path(__file__).resolve().parents[1]/'ops/native_fabric/quota_continuity/candidate/paid_host_readiness.py'

@pytest.fixture
def bootstrap(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('inert_readiness_bootstrap',SOURCE)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    root=tmp_path/'releases'/('a'*40);definition=tmp_path/'definition'
    root.mkdir(parents=True);definition.mkdir()
    files={
        'control_plane/__init__.py':b'',
        'control_plane/codex_provider_realm.py':b'_native_open = None\n',
        'control_plane/paid_fabric_backend.py':b'_root_source = None\n',
        'ops/executive_os/canonical_paid_qualification.py':b'from scripts.fixed_owner import ANSWER\n',
        'scripts/__init__.py':b'',
        'scripts/fixed_owner.py':b'ANSWER = 42\n',
        'ops/executive_os/release_manifest.py':b'ANSWER = 43\n',
    }
    for name,raw in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);path.chmod(0o644)
    def seal():
        entries=[]
        for path in sorted(root.rglob('*')):
            if path.name=='.executive-release-manifest.json':continue
            row=dict(path=path.relative_to(root).as_posix(),uid=0,gid=0,mode=stat.S_IMODE(path.stat().st_mode))
            if path.is_dir():row['type']='directory'
            else:row.update(type='file',size=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            entries.append(row)
        raw=m.canonical(dict(schema_version='mastermind.executive_release_manifest/v1',commit_sha=root.name,tree_sha='b'*40,entries=entries))
        (root/'.executive-release-manifest.json').write_bytes(raw)
        (definition/'profile.json').write_bytes(m.canonical(dict(release_commit=root.name,release_tree='b'*40,release_manifest_sha256=hashlib.sha256(raw).hexdigest())))
    seal()
    # Only the native Root ownership/ancestor mode/ACL premise is simulated.
    # The actual opened FD, named identities, bytes, import finder and compile run.
    raw_fstat=os.fstat;raw_stat=os.stat
    class RootInfo:
        def __init__(self,value):self.value=value
        st_uid=0;st_gid=0
        @property
        def st_mode(self):return self.value.st_mode&~0o022 if stat.S_ISDIR(self.value.st_mode) else self.value.st_mode
        def __getattr__(self,key):return getattr(self.value,key)
    monkeypatch.setattr(os,'fstat',lambda fd:RootInfo(raw_fstat(fd)))
    monkeypatch.setattr(os,'stat',lambda *a,**kw:RootInfo(raw_stat(*a,**kw)))
    monkeypatch.setattr(m,'_bootstrap_acl',lambda fd:None)
    monkeypatch.setattr(m,'_RELEASES',root.parent);monkeypatch.setattr(m,'_DEFINITION',definition)
    names=lambda name:any(name==p or name.startswith(p+'.') for p in ('ops','control_plane','scripts','common'))
    saved={name:value for name,value in sys.modules.items() if names(name)}
    for name in saved:sys.modules.pop(name)
    try:yield m,root,definition,seal
    finally:
        for name in list(sys.modules):
            if names(name):sys.modules.pop(name)
        sys.modules.update(saved)


def test_actual_bootstrap_compiles_qualified_root_snapshot(bootstrap):
    m,root,_,_=bootstrap
    with m._qualified_root_interfaces() as (actual,owner,manifest,_,__):
        assert actual==root and owner.ANSWER==42 and manifest.ANSWER==43
        assert Path(owner.__file__)==root/'ops/executive_os/canonical_paid_qualification.py'

@pytest.mark.parametrize('kind',['hash','mode','acl','profile_digest','foreign_alias'])
def test_unqualified_source_never_executes_secret_sentinel(bootstrap,monkeypatch,kind):
    m,root,definition,seal=bootstrap
    target=root/'ops/executive_os/canonical_paid_qualification.py'
    sentinel=root.parent/'executed'
    target.write_text(f"open({str(sentinel)!r}, 'w').write('SECRET_SENTINEL')\nANSWER=42\n")
    seal()
    if kind=='hash':target.write_text(target.read_text()+'# altered\n')
    elif kind=='mode':target.chmod(0o666)
    elif kind=='acl':
        actual_open=os.open
        def acl(fd):
            info=os.fstat(fd)
            if info.st_ino==target.stat().st_ino:m._refuse()
        monkeypatch.setattr(m,'_bootstrap_acl',acl)
    elif kind=='profile_digest':
        doc=json.loads((definition/'profile.json').read_bytes());doc['release_manifest_sha256']='f'*64
        (definition/'profile.json').write_bytes(m.canonical(doc))
    else:
        raw=target.read_bytes();target.unlink();other=root.parent/'foreign.py';other.write_bytes(raw);target.symlink_to(other)
    with pytest.raises((ValueError,OSError)):
        with m._qualified_root_interfaces():pytest.fail('unqualified import yielded')
    assert not sentinel.exists()


def test_unknown_root_module_has_no_path_loader_fallback(bootstrap):
    m,root,_,seal=bootstrap
    target=root/'ops/executive_os/canonical_paid_qualification.py'
    target.write_text('from control_plane import unlisted\n')
    seal()
    (root/'control_plane/unlisted.py').write_text("raise AssertionError('SECRET_SENTINEL')\n")
    with pytest.raises(ValueError):
        with m._qualified_root_interfaces():pytest.fail('unlisted source imported')


def test_source_replacement_during_context_is_detected(bootstrap):
    m,root,_,_=bootstrap
    with pytest.raises(ValueError):
        with m._qualified_root_interfaces() as interfaces:
            target=root/'ops/executive_os/canonical_paid_qualification.py'
            target.write_text('ANSWER=99\n')
            interfaces.check()


@pytest.mark.parametrize('pointer,error,accepted',[(None,2,True),(None,0,False),(None,13,False),(123,0,False)])
def test_bootstrap_acl_has_only_native_enoent_absence(monkeypatch,pointer,error,accepted):
    import ctypes
    spec=importlib.util.spec_from_file_location('inert_bootstrap_acl',SOURCE)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    calls=[]
    class Function:
        def __init__(self,kind):self.kind=kind
        def __call__(self,value):
            calls.append((self.kind,value))
            if self.kind=='get':ctypes.set_errno(error);return pointer
            return 0
    class Library:
        acl_get_fd=Function('get');acl_free=Function('free')
    monkeypatch.setattr(m.sys,'platform','darwin')
    monkeypatch.setattr(ctypes,'CDLL',lambda *a,**k:Library())
    if accepted:m._bootstrap_acl(42)
    else:
        with pytest.raises(ValueError):m._bootstrap_acl(42)
    assert calls==([('get',42),('free',123)] if pointer else [('get',42)])
