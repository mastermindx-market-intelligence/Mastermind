"""Inert release-manifest DATA; no installed reads or Root authority proof.

Actual temporary files/descriptors exercise the byte and identity bounds. Only
their UID/GID metadata is mapped to the declared Root fixture; native FD ACL
observation remains real except in explicit refusal tests.
"""
import json
import os
import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import autonomy_control as control

SHA, TREE = "a" * 40, "b" * 40


@pytest.fixture
def manifest(monkeypatch, tmp_path):
    path = tmp_path / "releases" / SHA / control.release_manifest.MANIFEST_NAME
    path.parent.mkdir(parents=True)
    document = {
        "schema_version": control.release_manifest.SCHEMA_VERSION,
        "commit_sha": SHA, "tree_sha": TREE,
        "entries": [{"path": f"source/file-{i:05d}.py", "mode": 292,
                     "uid": 0, "gid": 0, "type": "file", "size": 0,
                     "sha256": "c" * 64} for i in range(8000)],
    }
    raw = (json.dumps(document, sort_keys=True) + "\n").encode()
    assert control._MAX_JSON_BYTES < len(raw) < control._GATEWAY_ROOT_FILE_MAX_BYTES
    path.write_bytes(raw)
    path.chmod(0o444)
    real_open, real_fstat, real_read = os.open, os.fstat, os.read
    real_close, real_lstat = os.close, Path.lstat
    fds, reads = set(), []
    before_changes, after_changes, named_changes = {}, {}, {}

    def mapped(info, changes):
        names = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid",
                 "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        value = {key: getattr(info, key) for key in names}
        value.update(st_uid=0, st_gid=0)
        value.update(changes)
        return SimpleNamespace(**value)

    def owned_open(target, flags, *args, **kwargs):
        fd = real_open(target, flags, *args, **kwargs)
        if Path(target) == path:
            assert flags & os.O_NOFOLLOW
            fds.add(fd)
        return fd

    def owned_fstat(fd):
        observed = real_fstat(fd)
        return mapped(observed, after_changes if reads else before_changes) if fd in fds else observed

    def owned_read(fd, count):
        if fd in fds:
            reads.append(count)
        return real_read(fd, count)

    def owned_close(fd):
        fds.discard(fd)
        return real_close(fd)

    def owned_lstat(target, *args, **kwargs):
        observed = real_lstat(target, *args, **kwargs)
        return mapped(observed, named_changes) if target == path else observed

    monkeypatch.setattr(control, "SYSTEM_ROOT", tmp_path)
    monkeypatch.setattr(os, "open", owned_open)
    monkeypatch.setattr(os, "fstat", owned_fstat)
    monkeypatch.setattr(os, "read", owned_read)
    monkeypatch.setattr(os, "close", owned_close)
    monkeypatch.setattr(Path, "lstat", owned_lstat)
    return SimpleNamespace(path=path, root=tmp_path, document=document, raw=raw,
                           reads=reads, before=before_changes, after=after_changes,
                           named=named_changes, fds=fds)


def test_real_inventory_document_larger_than_config_budget_is_bounded(manifest):
    assert control._release_manifest_json(SHA) == manifest.document
    assert manifest.reads and max(manifest.reads) <= 65536
    assert not manifest.fds


def test_fixed_manifest_raw_companion_preserves_original_bytes(manifest):
    assert control._release_manifest_bytes(SHA) == manifest.raw
    assert manifest.reads and not manifest.fds


def test_same_document_still_refuses_generic_config_reader(manifest):
    with pytest.raises(control.HostControlError, match="config_identity_unavailable"):
        control._root_json(manifest.path, modes=frozenset({0o444}), gid=0)
    assert control._MAX_JSON_BYTES == 1024 * 1024


def test_manifest_over_existing_gateway_bound_refuses_before_payload(manifest):
    manifest.path.chmod(0o644)
    manifest.path.write_bytes(b"x" * (control._GATEWAY_ROOT_FILE_MAX_BYTES + 1))
    manifest.path.chmod(0o444)
    with pytest.raises(control.HostControlError, match="config_identity_unavailable"):
        control._release_manifest_json(SHA)
    assert manifest.reads == [] and not manifest.fds


def test_exact_manifest_budget_is_accepted(manifest):
    raw = manifest.raw + b" " * (control._GATEWAY_ROOT_FILE_MAX_BYTES - len(manifest.raw))
    manifest.path.chmod(0o644)
    manifest.path.write_bytes(raw)
    manifest.path.chmod(0o444)
    assert control._release_manifest_json(SHA) == manifest.document
    assert manifest.reads and not manifest.fds


def test_actual_symlink_refuses_without_reading_its_target(manifest):
    target = manifest.path.with_name("inert-target.json")
    manifest.path.rename(target)
    manifest.path.symlink_to(target.name)
    with pytest.raises(control.HostControlError, match="config_identity_unavailable"):
        control._release_manifest_json(SHA)
    assert manifest.reads == [] and not manifest.fds


@pytest.mark.parametrize("changes", [
    {"st_uid": 1}, {"st_gid": 1}, {"st_mode": 0o100644},
    {"st_mode": 0o120444}, {"st_nlink": 2}, {"st_size": 0},
])
def test_custody_refuses_before_payload(manifest, changes):
    manifest.before.update(changes)
    with pytest.raises(control.HostControlError, match="config_identity_unavailable"):
        control._release_manifest_json(SHA)
    assert manifest.reads == [] and not manifest.fds


@pytest.mark.parametrize("unknown", [False, True])
def test_descriptor_acl_refuses_before_payload(monkeypatch, manifest, unknown):
    def acl(path, *, expected_identity, descriptor):
        assert path == manifest.path and descriptor in manifest.fds
        if unknown:
            raise control.FilesystemSecurityError("fixture unknown")
        return True
    monkeypatch.setattr(control, "has_macos_acl", acl)
    with pytest.raises(control.HostControlError, match="config_identity_unavailable"):
        control._release_manifest_json(SHA)
    assert manifest.reads == [] and not manifest.fds


@pytest.mark.parametrize("field", ["st_dev", "st_ino", "st_uid", "st_gid",
                                   "st_mtime_ns", "st_ctime_ns", "st_size"])
def test_held_identity_change_refuses(manifest, field):
    actual = os.stat(manifest.path)
    value = 1 if field in {"st_uid", "st_gid"} else getattr(actual, field) + 1
    manifest.after[field] = value
    with pytest.raises(control.HostControlError, match="config_identity_unavailable"):
        control._release_manifest_json(SHA)
    assert manifest.reads and not manifest.fds


def test_named_replacement_refuses_held_descriptor_data(manifest):
    manifest.named["st_ino"] = os.stat(manifest.path).st_ino + 1
    with pytest.raises(control.HostControlError, match="config_identity_unavailable"):
        control._release_manifest_json(SHA)
    assert manifest.reads and not manifest.fds


def test_invalid_release_selector_never_opens_manifest(manifest):
    with pytest.raises(control.HostControlError, match="installed_identity_mismatch"):
        control._release_manifest_json("../" + SHA)
    assert manifest.reads == [] and not manifest.fds


def test_gateway_and_installed_identity_share_manifest_bound_and_full_seal(monkeypatch, manifest):
    host = control.ProductionGatewayPublicationHost()
    assert host._gateway_release_tree(SHA) == TREE
    verified = []
    def verify(root, sha, tree):
        verified.append((root, sha, tree))
        return manifest.document
    monkeypatch.setattr(control.release_manifest, "verify", verify)
    def plist(path, **kwargs):
        script = ("scripts/executive_os_phase1c_control_wrapper.py" if path == control.CONTROL_PLIST
                  else "scripts/executive_os_phase1c_worker.py")
        root = manifest.path.parent
        return plistlib.dumps({"WorkingDirectory": str(root), "ProgramArguments":
                               [str(control.PINNED_PYTHON), str(root / script)]}), None
    monkeypatch.setattr(control, "_read_root_file", plist)
    assert host._release_identity(SHA) == SHA
    assert verified == [(manifest.path.parent, SHA, TREE)]
    def invalid_seal(*args):
        raise control.release_manifest.ReleaseManifestError("fixture mismatch")
    monkeypatch.setattr(control.release_manifest, "verify", invalid_seal)
    with pytest.raises(control.HostControlError, match="installed_identity_unavailable"):
        host._release_identity(SHA)
