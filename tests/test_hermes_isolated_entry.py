"""Held Hermes source recipe; filesystem identity facts are explicitly synthetic.

The archive probe executes the real CLI's harmless help path. It does not
install a unit, open provider credentials or attest a live interpreter.
"""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "ops/executive_os/release_manifest.py"
YAML_ROOT = "ops/native_fabric/quota_continuity/candidate"


def owner_module():
    spec = importlib.util.spec_from_file_location("_held_hermes_entry_test", ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Proxy:
    def __init__(self, target, **overrides):
        self.target, self.overrides = target, overrides

    def __getattr__(self, name):
        return self.overrides.get(name, getattr(self.target, name))


def root_info(info, ancestors):
    fields = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
    fields.update(st_uid=0, st_gid=0)
    if (info.st_dev, info.st_ino) in ancestors:
        fields["st_mode"] &= ~0o022
    return SimpleNamespace(**fields)


def manifest(root):
    entries = []
    for path in sorted(root.rglob("*")):
        if path.name == ".executive-release-manifest.json":
            continue
        info = path.lstat()
        item = dict(path=path.relative_to(root).as_posix(), uid=0, gid=0,
                    mode=stat.S_IMODE(info.st_mode))
        if path.is_symlink():
            item.update(type="symlink", target=os.readlink(path))
        elif path.is_dir():
            item["type"] = "directory"
        else:
            raw = path.read_bytes()
            item.update(type="file", size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        entries.append(item)
    (root / ".executive-release-manifest.json").write_text(json.dumps(dict(
        schema_version="mastermind.executive_release_manifest/v1",
        commit_sha=root.name, tree_sha="b" * 40, entries=entries,
    )))


@pytest.fixture
def sources(tmp_path):
    m = owner_module()
    root = tmp_path.resolve() / "releases" / ("a" * 40)
    (root / "common").mkdir(parents=True)
    (root / "common/__init__.py").write_text("VALUE = 'held source'\n")
    manifest(root)
    # Keep actual descriptors, bytes, modes, links and replacement races.
    # Only root ownership, outside-fixture ancestor modes and Linux ACL absence
    # are synthetic on the Mac/unprivileged CI filesystem.
    ancestors = {(p.stat().st_dev, p.stat().st_ino) for p in root.parents}
    m.os = Proxy(os,
        stat=lambda *a, **k: root_info(os.stat(*a, **k), ancestors),
        fstat=lambda fd: root_info(os.fstat(fd), ancestors))
    m.sys = Proxy(sys, platform="linux")
    m._LINUX_RELEASES = root.parent
    m._linux_source_acl = lambda fd, directory: None
    return m, root


def test_held_bytes_execute_without_a_path_loader(sources):
    m, root = sources
    owner = m._HeldReleaseSources(root)
    modules, finders = {}, []
    m.sys = Proxy(m.sys, modules=modules, meta_path=finders)
    finder = m._ReleaseSourceFinder(owner)
    finders.insert(0, finder)
    try:
        spec = finder.find_spec("common")
        module = importlib.util.module_from_spec(spec)
        modules["common"] = module
        finder.exec_module(module)
        assert module.VALUE == "held source"
        assert module.__file__ == str(root / "common/__init__.py")
        assert module.__path__ == []
        modules["common"] = object()
        with pytest.raises(m.ReleaseManifestError, match="module ownership"):
            finder.check()
        modules["common"] = module
        modules["common.injected"] = object()
        with pytest.raises(m.ReleaseManifestError, match="module ownership"):
            finder.check()
        del modules["common.injected"]
        m.sys.overrides["path"] = list(sys.path) + ["/unqualified-import-root"]
        with pytest.raises(m.ReleaseManifestError, match="import path"):
            finder.check()
        del m.sys.overrides["path"]
        with pytest.raises(m.ReleaseManifestError, match="not listed"):
            finder.find_spec("common.unlisted")
        descriptors = [value[0] for value in owner.held.values()]
    finally:
        finders.remove(finder)
        owner.close()
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)
    with pytest.raises(m.ReleaseManifestError, match="closed"):
        owner.check()


@pytest.mark.parametrize("change", ["bytes", "replace", "symlink", "hardlink", "writable"])
def test_source_drift_and_unsafe_leaves_refuse(sources, change):
    m, root = sources
    leaf = root / "common/__init__.py"
    owner = m._HeldReleaseSources(root)
    try:
        if change == "replace":
            owner.source("common/__init__.py")
            replacement = leaf.with_name("replacement")
            replacement.write_bytes(leaf.read_bytes())
            replacement.replace(leaf)
        elif change == "bytes":
            leaf.write_text("VALUE = 'foreign bytes'\n")
        elif change == "symlink":
            target = leaf.with_name("target")
            leaf.rename(target)
            leaf.symlink_to(target.name)
        elif change == "hardlink":
            os.link(leaf, leaf.with_name("second-name"))
        else:
            leaf.chmod(0o666)
        with pytest.raises(m.ReleaseManifestError):
            owner.source("common/__init__.py")
    finally:
        owner.close()


def test_replaced_ancestor_and_manifest_are_not_reopened(sources):
    m, root = sources
    owner = m._HeldReleaseSources(root)
    try:
        owner.source("common/__init__.py")
        (root / "common").rename(root / "held-common")
        (root / "common").mkdir()
        (root / "common/__init__.py").write_text("VALUE = 'held source'\n")
        with pytest.raises(m.ReleaseManifestError, match="changed"):
            owner.check()
    finally:
        owner.close()
    owner = m._HeldReleaseSources(root)
    try:
        path = root / m.MANIFEST_NAME
        raw = path.read_bytes()
        path.unlink()
        path.write_bytes(raw)
        with pytest.raises(m.ReleaseManifestError, match="changed"):
            owner.check()
    finally:
        owner.close()


@pytest.mark.parametrize("raw", [
    b'{"schema_version":"x","schema_version":"y"}',
    b'{"entries":NaN}', b'\xff', b'[]',
])
def test_non_closed_manifest_refuses(sources, raw):
    m, root = sources
    (root / m.MANIFEST_NAME).write_bytes(raw)
    with pytest.raises(m.ReleaseManifestError):
        m._HeldReleaseSources(root)


@pytest.mark.parametrize("error", [errno.EACCES, errno.EBADF, errno.EIO, errno.ENOTSUP])
def test_descriptor_acl_errors_never_mean_absence(error):
    m = owner_module()
    with mock.patch.object(os, "getxattr", create=True, side_effect=OSError(error, "fixture")) as read:
        with pytest.raises(m.ReleaseManifestError):
            m._linux_source_acl(73, True)
    assert read.call_args.args == (73, "system.posix_acl_access")


def test_descriptor_acl_checks_default_and_refuses_even_empty_value():
    m = owner_module()
    with mock.patch.object(os, "getxattr", create=True, side_effect=OSError(errno.ENODATA, "absent")) as read:
        m._linux_source_acl(73, True)
    assert read.call_args_list == [
        mock.call(73, "system.posix_acl_access"), mock.call(73, "system.posix_acl_default")]
    for value in (b"", b"malformed", b"\x02\x00\x00\x00"):
        with mock.patch.object(os, "getxattr", create=True, return_value=value):
            with pytest.raises(m.ReleaseManifestError, match="has an ACL"):
                m._linux_source_acl(73, False)


def test_ambient_first_party_and_changed_finder_order_refuse(sources):
    m, root = sources
    owner = m._HeldReleaseSources(root)
    try:
        with mock.patch.dict(sys.modules, {"common.unqualified": object()}):
            with pytest.raises(m.ReleaseManifestError, match="ambient"):
                with m._held_release_imports(owner):
                    pytest.fail("ambient module adopted")
        finder = m._ReleaseSourceFinder(owner)
        sys.meta_path.insert(0, finder)
        marker = object()
        sys.meta_path.insert(0, marker)
        try:
            with pytest.raises(m.ReleaseManifestError, match="finder order"):
                finder.find_spec("common")
        finally:
            sys.meta_path.remove(marker)
            sys.meta_path.remove(finder)
    finally:
        owner.close()


def test_wrong_entry_refuses_before_repository_import(tmp_path):
    poison = tmp_path / "poison"
    (poison / "control_plane").mkdir(parents=True)
    (poison / "control_plane/__init__.py").write_text("raise AssertionError('ambient imported')\n")
    (poison / "sitecustomize.py").write_text("raise AssertionError('site loaded')\n")
    probe = """import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('_entry_probe',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert not any(n.split('.')[0] in m._FIRST_PARTY for n in sys.modules)
sys.argv=[sys.argv[1],'hermes-runtime','supervise','--help']
assert m.main()==78
print('REFUSED_BEFORE_FIRST_PARTY_IMPORT')
"""
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", probe, str(ENTRY)],
        cwd=poison, env={**os.environ, "PYTHONPATH": str(poison)},
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "REFUSED_BEFORE_FIRST_PARTY_IMPORT"
    assert result.stderr.strip() == "HERMES_RELEASE_SOURCE_UNQUALIFIED"


@pytest.mark.parametrize("command, argument", [
    ("supervise", "--help"), ("isolation-probe", "--list-cases"),
])
def test_actual_archive_runs_closed_hermes_modes_with_held_yaml(tmp_path, command, argument):
    """Actual CLI/import closure; synthetic root identity is stated in the driver."""
    spec = importlib.util.spec_from_file_location("_enrollment_entry_probe", ROOT / "scripts/enroll_linux_secondary_worker.py")
    enrollment = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = enrollment
    spec.loader.exec_module(enrollment)
    raw = enrollment._git(ROOT, "archive", "HEAD", "--", *enrollment.RELEASE_PATHS).stdout
    root = tmp_path.resolve() / "releases" / ("a" * 40)
    root.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        enrollment._safe_archive_members(archive)
        archive.extractall(root, filter="data")
    # HEAD is the source base while this change is being qualified. Overlay only
    # the three candidate owners, never a workspace-wide path or dependency.
    for relative in ("ops/executive_os/release_manifest.py",
                     "integrations/hermes_runtime/system_service.py",
                     "scripts/enroll_linux_secondary_worker.py"):
        (root / relative).write_bytes((ROOT / relative).read_bytes())
    manifest(root)
    poison = tmp_path / "poison"
    poison.mkdir()
    (poison / "yaml.py").write_text("raise AssertionError('ambient yaml')\n")
    (poison / "sitecustomize.py").write_text("raise AssertionError('ambient site')\n")
    (poison / "integrations").mkdir()
    (poison / "integrations/__init__.py").write_text("raise AssertionError('ambient source')\n")
    driver = r"""
import importlib.util,os,pathlib,sys,types
root=pathlib.Path(sys.argv[1])
entry=root/'ops/executive_os/release_manifest.py'
spec=importlib.util.spec_from_file_location('_held_entry_probe',entry)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
real_os=os
ancestors={(p.stat().st_dev,p.stat().st_ino) for p in root.parents}
def root_info(raw):
 data={k:getattr(raw,k) for k in dir(raw) if k.startswith('st_')}
 data.update(st_uid=0,st_gid=0)
 if (raw.st_dev,raw.st_ino) in ancestors:data['st_mode'] &= ~0o022
 return types.SimpleNamespace(**data)
class Proxy:
 def __init__(self,target,**overrides):self.target=target;self.overrides=overrides
 def __getattr__(self,name):return self.overrides.get(name,getattr(self.target,name))
m.os=Proxy(os,stat=lambda *a,**k:root_info(real_os.stat(*a,**k)),
           fstat=lambda fd:root_info(real_os.fstat(fd)))
m.sys=Proxy(sys,platform='linux',argv=[str(entry),'hermes-runtime',sys.argv[2],sys.argv[3]])
m._LINUX_RELEASES=root.parent
m._linux_source_acl=lambda fd,directory:None
try:result=m.main()
except SystemExit as exc:result=exc.code
assert result==0,result
assert not any(n.split('.')[0] in m._FIRST_PARTY or n=='yaml' or n.startswith('yaml.') for n in sys.modules)
assert str(root) not in sys.path
print('ARCHIVED_HELD_HERMES_ENTRY_OK')
"""
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", driver, str(root), command, argument],
        cwd=poison, env={**os.environ, "PYTHONPATH": str(poison)},
        capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, (result.stdout[-2000:], result.stderr[-4000:])
    assert result.stdout.rstrip().endswith("ARCHIVED_HELD_HERMES_ENTRY_OK")
