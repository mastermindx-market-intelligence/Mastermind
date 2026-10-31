"""Finite no-site profile: closed-code normal imports, never a Python sandbox."""
import base64
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest
from ops.native_fabric.quota_continuity.candidate import paid_initializer as m
from tests.test_paid_initializer import commitment, selectors, _preserving_stat_view



def _stat_view(info,*,uid=0,mode=None):
    return _preserving_stat_view(info,uid=uid,mode=mode)


def nested_commitment():
    value=commitment();value.update(initialization_contract=m.NESTED_CONTRACT,
        nested_helper=dict(path='/home/worker/lanes/ext/.host_glm_token.sh',sha256='c'*64,size=57,uid=1000,gid=1000,mode=0o600))
    value['host_env'].update(sha256=m.NESTED_OUTER_SHA256,size=m.NESTED_OUTER_SIZE)
    value['startup']['profile']=m.NO_SITE_PROFILE
    return value


def test_profile_is_explicit_nested_only_and_decode_has_no_policy_side_effect():
    before={key:sys.modules.get(key,'ABSENT') for key in ('site','sitecustomize','usercustomize')}
    value=nested_commitment();assert m.validate_commitment(value,**selectors())==value
    old=commitment();old['startup']['profile']=m.NO_SITE_PROFILE
    with pytest.raises(m.InitializerCommitmentRefused):m.validate_commitment(old,**selectors())
    assert before=={key:sys.modules.get(key,'ABSENT') for key in before}
    value['startup']['profile']='cpython-3.12-linux-root-prefix.v1'
    assert m.validate_commitment(value,**selectors())==value


def child(code,flags=('-I','-S','-B')):
    return subprocess.run([sys.executable,*flags,'-c',code],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)


@pytest.mark.parametrize('flags',[('-I','-S'),('-I','-B'),('-S','-B')])
def test_preamble_missing_real_flags_refuses_before_marker(flags):
    result=child(m.NO_SITE_PREAMBLE+'print("MARKER")',flags)
    assert result.returncode==78 and not result.stdout


@pytest.mark.parametrize('name',['site','sitecustomize','usercustomize'])
def test_preloaded_module_and_replaced_policy_refuse_without_repair(name):
    result=child('import sys\nsys.modules['+repr(name)+']=None\n'+m.NO_SITE_PREAMBLE+'print("MARKER")')
    assert result.returncode==78 and not result.stdout
    source=Path(m.__file__).read_text()
    code=m.NO_SITE_PREAMBLE+'import types\nm=types.ModuleType("inert_owner")\nexec('+repr(source)+',m.__dict__)\nm.require_no_site_policy()\nsys.modules['+repr(name)+']=object()\nm.require_no_site_policy()\nprint("MARKER")'
    result=child(code)
    assert result.returncode!=0 and not result.stdout


def test_normal_imports_and_importlib_cannot_execute_marker(tmp_path):
    marker=tmp_path/'not-executed';module=tmp_path/'sitecustomize.py'
    module.write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_bytes(b"effect")\n')
    code=m.NO_SITE_PREAMBLE+'import importlib\nsys.path.insert(0,'+repr(str(tmp_path))+')\n'
    code+='for name in ("site","sitecustomize","usercustomize"):\n try:importlib.import_module(name)\n except ModuleNotFoundError:pass\n else:raise AssertionError()\n_paid_no_site_check()\n'
    result=child(code);assert result.returncode==0 and not result.stdout and not marker.exists()
    # Deliberate counterexample: arbitrary alias loaders are NOT sandboxed.
    result=child(m.NO_SITE_PREAMBLE+'from importlib.machinery import SourceFileLoader\nSourceFileLoader("inert_alias",'+repr(str(module))+').load_module()')
    assert result.returncode==0 and marker.read_bytes()==b'effect'


def test_new_profile_mutated_probe_hash_refuses_canonical_admission(monkeypatch):
    from tests import test_paid_host_qualification as q
    value=q.request();value['initializer_commitment']=nested_commitment()
    value['initializer_commitment_sha256']=hashlib.sha256(m.canonical(value['initializer_commitment'])).hexdigest()
    value['probe_sha256']=hashlib.sha256(b'from importlib.machinery import SourceFileLoader').hexdigest()
    with pytest.raises(q.m.QualificationRefused):q.m._request(value)


def test_no_follow_scanner_never_classifies_target_or_descends_symlinks(tmp_path,monkeypatch):
    library=tmp_path/'library';library.mkdir();outside=tmp_path/'outside';outside.mkdir()
    (outside/'not-read').write_bytes(b'inert')
    (library/'sitecustomize.py').symlink_to(outside,target_is_directory=True)
    (library/'nested').mkdir();(library/'nested/sitecustomize.py').symlink_to(outside)
    values=list(m._no_site_startup_entries(str(library)))
    assert {Path(name).relative_to(library).as_posix() for name,_ in values}=={'sitecustomize.py','nested','nested/sitecustomize.py'}
    assert all(stat.S_ISLNK(info.st_mode) for name,info in values if name.endswith('sitecustomize.py'))


@pytest.mark.parametrize('outcome',[[],['system.posix_acl_access'],['user.inert'],(),None,
    errno.EOPNOTSUPP,errno.EBADF,errno.EACCES,errno.EIO])
def test_ignored_node_visible_metadata_is_closed_data_not_errno_absence(tmp_path,monkeypatch,outcome):
    # Pure method discriminator: sentinel FDs are not native custody proof.
    parent=tmp_path/'library';parent.mkdir();link=parent/'sitecustomize.py'
    link.symlink_to(tmp_path/'unopened-target')
    parent_info=_stat_view(parent.stat());link_info=_stat_view(link.lstat(),mode=stat.S_IFLNK|0o777)
    node=object.__new__(m._IgnoredNoSiteNode);node.directory=object();node.fd=object()
    node.directory_before=node._identity(parent_info);node.before=node._identity(link_info)
    raw_fstat=os.fstat;raw_stat=os.stat;raw_list=getattr(os,'listxattr',None)
    def fstat(fd):
        if fd is node.directory:return parent_info
        if fd is node.fd:return link_info
        return raw_fstat(fd)
    def named(name,*args,**kwargs):
        if name=='sitecustomize.py' and kwargs.get('dir_fd') is node.directory:
            assert kwargs=={'dir_fd':node.directory,'follow_symlinks':False}
            return link_info
        return raw_stat(name,*args,**kwargs)
    def listed(name,**kwargs):
        if name=='/proc/self/fd/'+str(node.directory)+'/sitecustomize.py':
            assert kwargs=={'follow_symlinks':False}
            if type(outcome)is int:raise OSError(outcome,'inert metadata refusal')
            return outcome
        assert raw_list is not None
        return raw_list(name,**kwargs)
    with monkeypatch.context() as model:
        model.setattr(os,'fstat',fstat);model.setattr(os,'stat',named);model.setattr(os,'listxattr',listed,raising=False)
        if type(outcome)is list and not outcome:node.check()
        else:
            with pytest.raises(m.InitializerCommitmentRefused):node.check()


@pytest.mark.skipif(sys.platform!='linux',reason='actual Linux O_PATH/no-follow named link ACL')
def test_actual_nofollow_link_metadata_recheck_and_unsupported_acl_refusal(tmp_path,monkeypatch):
    library=tmp_path/'library';library.mkdir(mode=0o700)
    target=tmp_path/'NEVER_OPEN_TARGET';target.write_bytes(b'inert-not-code')
    link=library/'sitecustomize.py';link.symlink_to(target)
    rawfstat=os.fstat;rawstat=os.stat;rawopen=os.open;rawlist=os.listxattr
    # Model only exact owned objects, restore before pytest renders a failure,
    # and preserve the complete stat_result interface and actual timestamps.
    directory=rawopen(library,os.O_RDONLY|os.O_DIRECTORY)
    try:
        with monkeypatch.context() as model:
            watched={directory:(rawfstat(directory).st_dev,rawfstat(directory).st_ino)}
            def root_fstat(fd):
                info=rawfstat(fd)
                return _stat_view(info) if watched.get(fd)==(info.st_dev,info.st_ino) else info
            def root_stat(name,*args,**kwargs):
                info=rawstat(name,*args,**kwargs)
                return _stat_view(info) if name=='sitecustomize.py' and kwargs.get('dir_fd')==directory and kwargs.get('follow_symlinks') is False else info
            model.setattr(os,'fstat',root_fstat);model.setattr(os,'stat',root_stat)
            def guarded_open(name,flags,*args,**kwargs):
                assert str(name)!=str(target)
                owned=name=='sitecustomize.py' and kwargs.get('dir_fd')==directory
                if owned:assert flags&os.O_PATH and flags&os.O_NOFOLLOW
                fd=rawopen(name,flags,*args,**kwargs)
                if owned:
                    info=rawfstat(fd);watched[fd]=(info.st_dev,info.st_ino)
                return fd
            model.setattr(os,'open',guarded_open)
            alias='/proc/self/fd/'+str(directory)+'/sitecustomize.py'
            def native_list(name,**kwargs):
                if str(name)==alias:assert kwargs=={'follow_symlinks':False}
                return rawlist(name,**kwargs)
            model.setattr(os,'listxattr',native_list)
            # Actual Linux llistxattr/O_PATH results; only owned UID is modeled.
            with m._IgnoredNoSiteNode(directory) as node:node.check()
            assert rawlist(alias,follow_symlinks=False)==[]
            for value in (['system.posix_acl_access'],['user.inert'],(),None):
                def named_or_invalid(name,**kwargs):
                    if str(name)==alias:
                        assert kwargs=={'follow_symlinks':False}
                        return value
                    return rawlist(name,**kwargs)
                model.setattr(os,'listxattr',named_or_invalid)
                with pytest.raises(m.InitializerCommitmentRefused):m._IgnoredNoSiteNode(directory)
            for code in (errno.EOPNOTSUPP,errno.EBADF,errno.EACCES,errno.EIO):
                def unsupported(name,**kwargs):
                    if str(name)==alias:
                        assert kwargs=={'follow_symlinks':False}
                        raise OSError(code,'synthetic metadata refusal')
                    return rawlist(name,**kwargs)
                model.setattr(os,'listxattr',unsupported)
                with pytest.raises(m.InitializerCommitmentRefused):m._IgnoredNoSiteNode(directory)
            model.setattr(os,'listxattr',native_list)
            with pytest.raises(m.InitializerCommitmentRefused):
                with m._IgnoredNoSiteNode(directory) as node:
                    link.unlink();link.symlink_to(target)
                    with pytest.raises(m.InitializerCommitmentRefused):node.check()
    finally:os.close(directory)
    assert target.read_bytes()==b'inert-not-code'


def test_real_new_profile_compiler_early_policy_and_final_utf8_ceiling(monkeypatch,record_property):
    import shlex
    from tests import test_paid_initializer_nested_join as joined
    from tests import test_paid_host_qualification as fixture
    q=fixture.m;source=Path(m.__file__).read_bytes()
    monkeypatch.setattr(q,'_initializer_module',lambda expected:(m,source) if expected==hashlib.sha256(source).hexdigest() else q._refuse())
    req=joined._compiled_fixture(q,monkeypatch)
    req['initializer_commitment']['startup']['profile']=m.NO_SITE_PROFILE
    req['initializer_commitment_sha256']=q._digest(req['initializer_commitment'])
    alias,command=q.build_paid_probe(req);parts=shlex.split(command)
    assert alias==req['transport_alias'] and len(parts)==8
    assert parts[5].startswith(m.NO_SITE_PREAMBLE)
    assert parts[5].index('import sys')<parts[5].index('def _load_qualified_package')<parts[5].index('import base64,json,sys')
    size=len(command.encode('utf-8'))+1
    record_property('final_remote_command_bytes_with_nul',size)
    assert size<=q.MAX_REMOTE_COMMAND_BYTES==100000


def test_normalized_request_system_selector_uses_current_commitment(monkeypatch,record_property):
    from tests import test_paid_initializer_nested_join as joined
    from tests import test_paid_host_qualification as fixture
    q=fixture.m;source=Path(m.__file__).read_bytes()
    monkeypatch.setattr(q,'_initializer_module',lambda expected:(m,source) if expected==hashlib.sha256(source).hexdigest() else q._refuse())
    req=joined._compiled_fixture(q,monkeypatch)
    original=req['initializer_commitment'];req=q._request(req)
    assert req['initializer_commitment'] is not original
    # Reproduce the Linux fixture's stale construction-object update. The
    # canonical compiler must continue refusing that mismatched request.
    original['startup']['profile']=m.NO_SITE_PROFILE
    original['launch_python'].update(path='/usr/bin/python3',real_path='/usr/bin/python3.12')
    req['python_path']='/usr/bin/python3'
    req['initializer_commitment_sha256']=q._digest(original)
    with pytest.raises(ValueError):q.build_paid_probe(req)
    current=req['initializer_commitment']
    current['startup']['profile']=m.NO_SITE_PROFILE
    current['launch_python'].update(path='/usr/bin/python3',real_path='/usr/bin/python3.12')
    req['initializer_commitment_sha256']=q._digest(current)
    alias,command=q.build_paid_probe(req)
    size=len(command.encode('utf-8'))+1
    record_property('normalized_request_command_bytes_with_nul',size)
    assert alias==req['transport_alias'] and size<=q.MAX_REMOTE_COMMAND_BYTES==100000


@pytest.mark.parametrize('uid,mode,count',[
    (1,stat.S_IFREG|0o644,1),(0,stat.S_IFREG|0o664,1),
    (0,stat.S_IFDIR|0o777,1),(0,stat.S_IFLNK|0o777,1),
    (0,stat.S_IFIFO|0o600,1),(0,stat.S_IFREG|0o644,20001),
])
def test_shared_actual_startup_predicate_rejects_foreign_writable_links_types_count(uid,mode,count):
    with pytest.raises(m.InitializerCommitmentRefused):m._require_startup_entry(SimpleNamespace(st_uid=uid,st_mode=mode),count)
    m._require_startup_entry(SimpleNamespace(st_uid=0,st_mode=stat.S_IFREG|0o644),20000)


@pytest.mark.parametrize('uid,mode',[(1,stat.S_IFDIR|0o700),(0,stat.S_IFDIR|0o777),(0,stat.S_IFREG|0o600)])
def test_ignored_node_rejects_unqualified_parent_before_open(monkeypatch,tmp_path,uid,mode):
    raw_fstat=os.fstat;raw_open=os.open;directory=raw_open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    def fstat(fd):
        info=raw_fstat(fd)
        return _stat_view(info,uid=uid,mode=mode) if fd==directory else info
    def opened(name,*args,**kwargs):
        if name=='sitecustomize.py' and kwargs.get('dir_fd')==directory:pytest.fail('unqualified namespace opened')
        return raw_open(name,*args,**kwargs)
    monkeypatch.setattr(os,'fstat',fstat);monkeypatch.setattr(os,'open',opened)
    try:
        with pytest.raises(m.InitializerCommitmentRefused):m._IgnoredNoSiteNode(directory)
    finally:os.close(directory)


def test_stat_uid_model_preserves_complete_interface_and_linecache(tmp_path,monkeypatch):
    import linecache
    file=tmp_path/'source.py';file.write_text('public inert source\n');raw=file.stat();view=_stat_view(raw)
    assert type(view)is os.stat_result and len(view)==len(raw)
    assert view.st_uid==0 and view[4]==0
    assert all(getattr(view,key)==getattr(raw,key)for key in dir(raw)if key.startswith('st_')and key!='st_uid')
    actual_stat=os.stat
    monkeypatch.setattr(os,'stat',lambda name,*args,**kwargs:_stat_view(actual_stat(name,*args,**kwargs)) if str(name)==str(file) else actual_stat(name,*args,**kwargs))
    assert linecache.getline(str(file),1)=='public inert source\n'
    other=tmp_path/'unmodeled';other.write_bytes(b'public')
    assert other.stat()==actual_stat(other)
