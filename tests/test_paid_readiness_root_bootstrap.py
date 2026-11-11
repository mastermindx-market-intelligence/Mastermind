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

_READINESS_IDENTITY_FIELDS = (
    'dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns',
)


def _observe_bootstrap_identity(m, frame, info, comparison, root, definition,
                                fixture_root, seen):
    """Describe the first real comparison without reading another stat or path."""
    if seen or frame.f_code is not m._RootSourceBootstrap.check.__code__:
        return
    before = frame.f_locals.get('before')
    if type(before) is not tuple or len(before) != len(_READINESS_IDENTITY_FIELDS):
        return
    current = m._identity(info)
    if current == before:
        return
    owner = frame.f_locals['self']
    held_fd = frame.f_locals['fd']
    path = next((path for path, item in owner.held.items() if item[0] == held_fd), None)
    if path is None:
        return
    if path.is_relative_to(root):
        scope = 'release'
    elif path.is_relative_to(definition):
        scope = 'definition'
    elif path.is_relative_to(fixture_root):
        scope = 'fixture_ancestor'
    else:
        scope = 'external_ancestor'
    report = {
        'comparison': comparison,
        'scope': scope,
        'kind': 'directory' if stat.S_ISDIR(before[2]) else 'file',
        'changed_fields': [
            field for field, old, new in zip(_READINESS_IDENTITY_FIELDS, before, current)
            if old != new
        ],
    }
    seen.append(report)
    # Never emit paths, source, raw stat values or exception text. Pytest retains
    # this captured line on a failure; the original check still decides refusal.
    print('READINESS_IDENTITY_DIAGNOSTIC ' + json.dumps(report, sort_keys=True),
          file=sys.stderr)


@pytest.fixture
def bootstrap(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('inert_readiness_bootstrap',SOURCE)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    fixture_root=tmp_path/'namespace'
    root=fixture_root/'releases'/('a'*40);definition=fixture_root/'definition'
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
    # Simulate native Root ownership/mode/ACL and stable child-list metadata on
    # the exact external directory ancestors of this disposable namespace.
    # Sibling activity can change nlink, size, mtime and ctime without changing
    # these copied sources. Only those four observed fields are projected.
    # Device/inode stay real, ownership/mode keep their existing premises, and
    # every field inside the namespace stays outside this new projection.
    # Actual FDs, descriptor/named device and inode, bytes, finder and compile run.
    raw_fstat=os.fstat;raw_stat=os.stat
    external_ancestors = frozenset(fixture_root.parents)
    external_contents = {}
    content_fields = ('st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    class RootInfo:
        def __init__(self,value,contents=None):
            self.value=value
            self.contents=contents
        st_uid=0;st_gid=0
        @property
        def st_mode(self):return self.value.st_mode&~0o022 if stat.S_ISDIR(self.value.st_mode) else self.value.st_mode
        def __getattr__(self,key):
            if self.contents is not None and key in self.contents:
                return self.contents[key]
            return getattr(self.value,key)
    def root_info(value, frame):
        path = None
        if frame.f_code is m._RootSourceBootstrap.hold.__code__:
            path = frame.f_locals.get('path')
        elif frame.f_code is m._RootSourceBootstrap.check.__code__:
            owner, fd = frame.f_locals['self'], frame.f_locals['fd']
            path = next((p for p, item in owner.held.items() if item[0] == fd), None)
        contents = None
        if stat.S_ISDIR(value.st_mode) and path in external_ancestors:
            contents = external_contents.setdefault(
                path, {field: getattr(value, field) for field in content_fields},
            )
        return RootInfo(value, contents)
    seen_identity_drift = []
    def observed_fstat(fd):
        info = root_info(raw_fstat(fd), sys._getframe(1))
        try:
            _observe_bootstrap_identity(
                m, sys._getframe(1), info, 'fd', root, definition, fixture_root,
                seen_identity_drift,
            )
        except Exception:
            pass  # Diagnostic failure cannot replace the original guard outcome.
        return info
    def observed_stat(*args, **kwargs):
        info = root_info(raw_stat(*args, **kwargs), sys._getframe(1))
        try:
            _observe_bootstrap_identity(
                m, sys._getframe(1), info, 'named', root, definition, fixture_root,
                seen_identity_drift,
            )
        except Exception:
            pass
        return info
    monkeypatch.setattr(os,'fstat',observed_fstat)
    monkeypatch.setattr(os,'stat',observed_stat)
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


def test_source_replacement_during_context_is_detected(bootstrap, capsys):
    m,root,_,_=bootstrap
    with pytest.raises(m.ReadinessRefused):
        with m._qualified_root_interfaces() as interfaces:
            target=root/'ops/executive_os/canonical_paid_qualification.py'
            target.write_text('ANSWER=99\n# PRIVATE_SOURCE_SENTINEL\n')
            interfaces.check()
    stderr = capsys.readouterr().err
    rows = [line.removeprefix('READINESS_IDENTITY_DIAGNOSTIC ')
            for line in stderr.splitlines()
            if line.startswith('READINESS_IDENTITY_DIAGNOSTIC ')]
    assert len(rows) == 1
    report = json.loads(rows[0])
    assert set(report) == {'comparison', 'scope', 'kind', 'changed_fields'}
    assert report['comparison'] == 'fd'
    assert report['scope'] == 'release' and report['kind'] == 'file'
    assert 'size' in report['changed_fields']
    assert set(report['changed_fields']) <= set(_READINESS_IDENTITY_FIELDS)
    assert str(root) not in stderr and 'PRIVATE_SOURCE_SENTINEL' not in stderr


def test_identity_diagnostic_failure_preserves_the_original_refusal(
    bootstrap, monkeypatch, capsys,
):
    m,root,_,_=bootstrap
    def broken_observer(*args, **kwargs):
        raise RuntimeError('PRIVATE_DIAGNOSTIC_SENTINEL')
    monkeypatch.setattr(sys.modules[__name__], '_observe_bootstrap_identity',
                        broken_observer)
    with pytest.raises(m.ReadinessRefused):
        with m._qualified_root_interfaces() as interfaces:
            target=root/'ops/executive_os/canonical_paid_qualification.py'
            target.write_text('ANSWER=99\n')
            interfaces.check()
    assert 'PRIVATE_DIAGNOSTIC_SENTINEL' not in capsys.readouterr().err


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



def test_actual_root_owner_import_graph_from_disposable_git_sources(bootstrap,record_property):
    m,root,_,seal=bootstrap
    source=SOURCE.parents[4]
    # Source only, four existing package owners; no installed files or data.
    count=0
    for package in ('control_plane','ops/executive_os','scripts','common'):
        for path in (source/package).rglob('*.py'):
            relative=path.relative_to(source)
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(path.read_bytes());target.chmod(0o644);count+=1
    seal()
    before=list(sys.path)
    with m._qualified_root_interfaces() as interfaces:
        actual,qualification,manifest,native_open,root_read=interfaces
        assert actual==root
        assert callable(qualification.verify_qualified_artifacts)
        assert callable(manifest.verify) and callable(native_open) and callable(root_read)
        backend=sys.modules['control_plane.paid_fabric_backend']
        assert callable(backend.CanonicalPaidBackend)
        assert Path(backend.__file__).is_relative_to(root)
        interfaces.check()
    assert sys.path==before
    record_property('actual_root_python_snapshots',count)



def test_external_ancestor_timestamp_noise_does_not_change_fixture_sources(bootstrap):
    m,root,_,_=bootstrap
    # This private outer directory belongs to this test, but is strictly above
    # the disposable Root namespace. Never mutate a shared host ancestor.
    external = root.parents[2]
    with m._qualified_root_interfaces() as interfaces:
        before = external.stat()
        os.utime(external, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
        after = external.stat()
        changed = {
            field for field, old, new in zip(
                _READINESS_IDENTITY_FIELDS, m._identity(before), m._identity(after),
            ) if old != new
        }
        assert 'mtime_ns' in changed
        assert changed <= {'mtime_ns', 'ctime_ns'}
        interfaces.check()


@pytest.mark.parametrize('scope', ['fixture_ancestor', 'release', 'definition'])
def test_owned_namespace_timestamp_drift_is_still_refused(bootstrap, capsys, scope):
    m,root,definition,_=bootstrap
    target = {
        'fixture_ancestor': root.parent.parent,
        'release': root,
        'definition': definition,
    }[scope]
    with pytest.raises(m.ReadinessRefused):
        with m._qualified_root_interfaces() as interfaces:
            before = target.stat()
            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
            after = target.stat()
            changed = {
                field for field, old, new in zip(
                    _READINESS_IDENTITY_FIELDS, m._identity(before), m._identity(after),
                ) if old != new
            }
            assert 'mtime_ns' in changed
            assert changed <= {'mtime_ns', 'ctime_ns'}
            interfaces.check()
    stderr = capsys.readouterr().err
    rows = [json.loads(line.removeprefix('READINESS_IDENTITY_DIAGNOSTIC '))
            for line in stderr.splitlines()
            if line.startswith('READINESS_IDENTITY_DIAGNOSTIC ')]
    assert len(rows) == 1
    assert rows[0]['scope'] == scope and rows[0]['kind'] == 'directory'
    assert rows[0]['comparison'] == 'fd'
    assert 'mtime_ns' in rows[0]['changed_fields']
    assert set(rows[0]['changed_fields']) <= {'mtime_ns', 'ctime_ns'}
    assert str(target) not in stderr


@pytest.mark.parametrize('field', ['nlink', 'size', 'mtime_ns', 'ctime_ns'])
@pytest.mark.parametrize('comparison', ['fd', 'named'])
def test_original_guard_refuses_each_content_field_without_fixture_projection(
    monkeypatch, field, comparison,
):
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('inert_timestamp_guard',SOURCE)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    values = (1, 2, stat.S_IFDIR | 0o755, 0, 0, 1, 4096, 100, 200)
    original = dict(zip(('st_' + name for name in _READINESS_IDENTITY_FIELDS), values))
    changed = dict(original)
    changed['st_' + field] += 1
    before, after = SimpleNamespace(**original), SimpleNamespace(**changed)
    assert [name for name in original if original[name] != changed[name]] == ['st_' + field]
    guard = object.__new__(m._RootSourceBootstrap)
    guard.held = {Path('/uninstalled-test-namespace'): (41, m._identity(before), None, 'synthetic')}
    # The original production check runs with controlled returned metadata only.
    # No real external ancestor is opened or mutated by this control.
    with pytest.raises(m.ReadinessRefused):
        with monkeypatch.context() as patch:
            patch.setattr(os, 'fstat', lambda fd: after if comparison == 'fd' else before)
            patch.setattr(os, 'stat', lambda *args, **kwargs: after if comparison == 'named' else before)
            patch.setattr(m, '_bootstrap_acl', lambda fd: pytest.fail('drift reached ACL check'))
            guard.check()


def test_external_ancestor_child_entry_does_not_change_fixture_sources(bootstrap):
    m,root,_,_=bootstrap
    external = root.parents[2]
    with m._qualified_root_interfaces() as interfaces:
        before = external.stat()
        (external / 'unrelated-owned-sibling').mkdir()
        after = external.stat()
        changed = {
            field for field, old, new in zip(
                _READINESS_IDENTITY_FIELDS, m._identity(before), m._identity(after),
            ) if old != new
        }
        assert changed & {'nlink', 'size'}
        assert changed <= {'nlink', 'size', 'mtime_ns', 'ctime_ns'}
        interfaces.check()


@pytest.mark.parametrize('scope', ['fixture_ancestor', 'release', 'definition'])
def test_owned_namespace_child_entry_is_still_refused(bootstrap, capsys, scope):
    m,root,definition,_=bootstrap
    target = {
        'fixture_ancestor': root.parent.parent,
        'release': root,
        'definition': definition,
    }[scope]
    with pytest.raises(m.ReadinessRefused):
        with m._qualified_root_interfaces() as interfaces:
            before = target.stat()
            (target / 'new-owned-entry').mkdir()
            after = target.stat()
            changed = {
                field for field, old, new in zip(
                    _READINESS_IDENTITY_FIELDS, m._identity(before), m._identity(after),
                ) if old != new
            }
            assert changed & {'nlink', 'size'}
            assert changed <= {'nlink', 'size', 'mtime_ns', 'ctime_ns'}
            interfaces.check()
    stderr = capsys.readouterr().err
    rows = [json.loads(line.removeprefix('READINESS_IDENTITY_DIAGNOSTIC '))
            for line in stderr.splitlines()
            if line.startswith('READINESS_IDENTITY_DIAGNOSTIC ')]
    assert len(rows) == 1
    assert rows[0]['scope'] == scope and rows[0]['kind'] == 'directory'
    assert rows[0]['comparison'] == 'fd'
    assert set(rows[0]['changed_fields']) & {'nlink', 'size'}
    assert set(rows[0]['changed_fields']) <= {'nlink', 'size', 'mtime_ns', 'ctime_ns'}
    assert str(target) not in stderr


def test_external_ancestor_replacement_is_still_refused(bootstrap, capsys):
    m,root,_,_=bootstrap
    external = root.parents[2]
    moved = external.with_name(external.name + '-held-original')
    assert not moved.exists()
    try:
        with pytest.raises(m.ReadinessRefused):
            with m._qualified_root_interfaces() as interfaces:
                mode = stat.S_IMODE(external.stat().st_mode)
                external.rename(moved)
                external.mkdir(mode=mode)
                interfaces.check()
    finally:
        # Restore only this test's private directory after the guard closes FDs.
        if moved.exists():
            external.rmdir()
            moved.rename(external)
    stderr = capsys.readouterr().err
    rows = [json.loads(line.removeprefix('READINESS_IDENTITY_DIAGNOSTIC '))
            for line in stderr.splitlines()
            if line.startswith('READINESS_IDENTITY_DIAGNOSTIC ')]
    assert len(rows) == 1
    assert rows[0]['scope'] == 'external_ancestor'
    assert rows[0]['comparison'] == 'named' and rows[0]['kind'] == 'directory'
    assert rows[0]['changed_fields'] == ['ino']
    assert str(external) not in stderr
