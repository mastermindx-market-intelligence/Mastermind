"""Real namespace/hash/no-replace checks with explicit ownership/ACL doubles.

Fixture metadata maps the test user to root; this is not host custody proof.
"""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import native_gateway_sources as source


@pytest.fixture
def tree(monkeypatch, tmp_path):
    vendor = tmp_path / "vendor"
    vendor.mkdir(mode=0o755)
    (vendor / "package").mkdir(mode=0o755)
    vendor.chmod(0o755)
    (vendor / "package").chmod(0o755)
    (vendor / "package/a.py").write_text("value = 1\n")
    (vendor / "package/a.py").chmod(0o644)
    real_os = os
    fds = []
    ancestors = {str(p) for p in vendor.parents}
    ancestor_ids = {(p.stat().st_dev, p.stat().st_ino) for p in vendor.parents}
    def mapped(info):
        fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
        fields.update(st_uid=0, st_gid=0)
        if (info.st_dev, info.st_ino) in ancestor_ids:
            fields["st_mode"] |= 0o005
        return SimpleNamespace(**fields)
    class Proxy:
        def __getattr__(self, name):
            return getattr(real_os, name)
        def fstat(self, fd):
            return mapped(real_os.fstat(fd))
        def stat(self, *args, **kwargs):
            return mapped(real_os.stat(*args, **kwargs))
        def getuid(self):
            return 0
        def geteuid(self):
            return 0
        def fchown(self, fd, uid, gid):
            assert uid == gid == 0  # simulated metadata boundary only
    monkeypatch.setattr(source, "os", Proxy())
    class Owner:
        root = tmp_path / "release"
        def hold(self, path, *, directory=False):
            fd = real_os.open(path, os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0))
            fds.append(fd)
            return fd
        def read(self, path, maximum):
            return real_os.read(self.hold(path), maximum + 1)
        def check(self):
            pass
    owner = Owner()
    acl = lambda *a: None
    raw = source.candidate_inventory(owner, [str(vendor)], acl)
    path = tmp_path / "inventory.json"
    recipe = dict(import_roots=[str(vendor)], dependency_inventory=dict(
        path=str(path), sha256=hashlib.sha256(raw).hexdigest(), size=len(raw)))
    yield SimpleNamespace(owner=owner, recipe=recipe, vendor=vendor, path=path, raw=raw, acl=acl)
    for fd in fds:
        real_os.close(fd)


def test_exact_frozen_inventory_publishes_then_adopts_without_rewrite(tree):
    source.prepare_inventory(tree.owner, tree.recipe, tree.acl)
    before = tree.path.stat()
    assert tree.path.read_bytes() == tree.raw and before.st_nlink == 1
    source.prepare_inventory(tree.owner, tree.recipe, tree.acl)
    after = tree.path.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def test_wrong_frozen_commitment_cannot_create_artifact(tree):
    tree.recipe["dependency_inventory"]["sha256"] = "0" * 64
    with pytest.raises(source.NativeSourceRefusal):
        source.prepare_inventory(tree.owner, tree.recipe, tree.acl)
    assert not tree.path.exists()


def test_existing_different_artifact_is_never_replaced(tree):
    tree.path.write_bytes(b"previous input\n")
    before = tree.path.stat().st_ino
    with pytest.raises(source.NativeSourceRefusal):
        source.prepare_inventory(tree.owner, tree.recipe, tree.acl)
    assert tree.path.read_bytes() == b"previous input\n" and tree.path.stat().st_ino == before


@pytest.mark.parametrize("mutation", ["bytes", "extra", "symlink", "hardlink", "unreadable"])
def test_native_namespace_drift_refuses(tree, mutation):
    source.prepare_inventory(tree.owner, tree.recipe, tree.acl)
    closure = source.NativeSourceClosure(tree.owner, tree.recipe, tree.acl)
    item = tree.vendor / "package/a.py"
    if mutation == "bytes":
        item.write_text("value = 2\n")
    elif mutation == "extra":
        (tree.vendor / "extra.py").write_text("x=1\n")
    elif mutation == "symlink":
        (tree.vendor / "link").symlink_to(item)
    elif mutation == "hardlink":
        os.link(item, tree.vendor / "alias.py")
    else:
        item.chmod(0o600)
    with pytest.raises((source.NativeSourceRefusal, OSError)):
        closure.check()
    closure.close()


def test_inventory_cannot_be_added_inside_immutable_release(tree):
    tree.recipe["dependency_inventory"]["path"] = str(tree.owner.root / "inventory.json")
    with pytest.raises(source.NativeSourceRefusal):
        source.prepare_inventory(tree.owner, tree.recipe, tree.acl)
