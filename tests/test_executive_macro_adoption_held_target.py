"""Held-target guard tests with real temp FDs and explicit synthetic OS facts.

Only uid and ACL observations are supplied as fixture facts so an unprivileged
source test can reach the guard's held-read bracket. No custody predicate or
helper is replaced; real paths, modes, inodes, timestamps, bytes and FD lifetimes
remain in use. These tests do not qualify a Root-owned or installed generation.
"""
import ctypes
import errno
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from control_plane import fs_security
from ops.executive_os import acceptance_maintenance as maintenance
from ops.executive_os import autonomy_control as control
from ops.executive_os import macro_adoption as adoption


@pytest.fixture
def held_target(tmp_path, monkeypatch):
    system = tmp_path.resolve() / "synthetic-system"
    root = system / "macro-sources" / ("b" * 40)
    artifact = root / "data/governance/agent_os_state.json"
    artifact.parent.mkdir(parents=True)
    original = b'{"schema":"fixture-only","generated_at":"2026-10-31T05:28:23Z"}\n'
    artifact.write_bytes(original)
    artifact.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    real_lstat, real_fstat, real_open = Path.lstat, os.fstat, os.open
    facts = SimpleNamespace(root=root, artifact=artifact, original=original,
                            bad_uid_inodes=set(), acl_inodes=set(), acl_calls=[],
                            artifact_fd=None, real_lstat=real_lstat)

    def root_uid_fact(info):
        # Preserve every real metadata field except the explicit synthetic uid.
        values = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
        values["st_uid"] = 1 if info.st_ino in facts.bad_uid_inodes else 0
        return SimpleNamespace(**values)

    def lstat_fact(path, *args, **kwargs):
        return root_uid_fact(real_lstat(path, *args, **kwargs))

    class FixtureOS:
        def __getattr__(self, name):
            return getattr(os, name)

        def fstat(self, descriptor):
            return root_uid_fact(real_fstat(descriptor))

        def open(self, path, flags, *args, **kwargs):
            descriptor = real_open(path, flags, *args, **kwargs)
            if str(path) == str(artifact):
                facts.artifact_fd = descriptor
            return descriptor

    def acl_handle_fact(descriptor):
        inode = real_fstat(descriptor).st_ino
        facts.acl_calls.append(inode)
        if inode in facts.acl_inodes:
            ctypes.set_errno(0)
            return 1
        ctypes.set_errno(errno.ENOENT)
        return None

    def acl_entry_fact(_acl, _entry_id, pointer):
        pointer._obj.value = 1
        ctypes.set_errno(0)
        return 0

    monkeypatch.setattr(control, "SYSTEM_ROOT", system)
    monkeypatch.setattr(Path, "lstat", lstat_fact)
    monkeypatch.setattr(adoption, "os", FixtureOS())
    # Exercise the real Darwin ACL predicate on every platform. Only its raw
    # syscall observations are supplied; no global sys/platform is changed.
    monkeypatch.setattr(fs_security, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(fs_security, "_acl_get_fd", acl_handle_fact)
    monkeypatch.setattr(fs_security, "_acl_get_entry", acl_entry_fact)
    monkeypatch.setattr(fs_security, "_acl_free", lambda _acl: 0)
    return facts


def test_real_held_read_bracket_preserves_exact_bytes_under_synthetic_uid_acl_facts(held_target):
    facts = held_target
    with adoption._held_macro_artifact(str(facts.root)) as (raw, check):
        assert raw == facts.original
        check()
        assert facts.artifact_fd is not None
    assert facts.acl_calls
    assert facts.real_lstat(facts.artifact).st_uid == os.getuid()
    assert facts.artifact.read_bytes() == facts.original


@pytest.mark.parametrize("redirect", ["root", "ancestor", "artifact"])
def test_lexical_symlink_is_refused_without_normalizing_into_admission(held_target, redirect):
    facts = held_target
    path = {"root": facts.root, "ancestor": facts.root / "data", "artifact": facts.artifact}[redirect]
    retained = path.with_name(path.name + "-retained")
    path.rename(retained)
    path.symlink_to(retained, target_is_directory=redirect != "artifact")
    with pytest.raises(adoption.AdoptionError, match="target_not_direct_canonical_root"):
        with adoption._held_macro_artifact(str(facts.root)):
            pytest.fail("symlink must not enter the held bracket")


@pytest.mark.parametrize("defect", ["ancestor_owner", "artifact_owner", "ancestor_writable", "artifact_writable", "ancestor_acl", "artifact_acl"])
def test_actual_custody_predicates_refuse_bad_os_facts(held_target, defect):
    facts = held_target
    target = facts.artifact.parent if defect.startswith("ancestor_") else facts.artifact
    inode = facts.real_lstat(target).st_ino
    if defect.endswith("owner"):
        facts.bad_uid_inodes.add(inode)
    elif defect.endswith("writable"):
        target.chmod(stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH
                     if target.is_dir() else stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    else:
        facts.acl_inodes.add(inode)
    error = maintenance.MaintenanceError if defect.startswith("ancestor_") else adoption.AdoptionError
    with pytest.raises(error):
        with adoption._held_macro_artifact(str(facts.root)):
            pytest.fail("bad custody facts must not enter the held bracket")
    if defect.endswith("acl"):
        assert inode in facts.acl_calls


@pytest.mark.parametrize("drift", ["named_artifact", "held_fd", "ancestor", "bytes"])
def test_guard_rechecks_real_identity_and_bytes_after_yield(held_target, drift):
    facts = held_target
    other = facts.root.parent / "other-user-owned-file"
    other.write_bytes(facts.original)
    other.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    with pytest.raises(adoption.AdoptionError, match="target_changed_during_generation_proof"):
        with adoption._held_macro_artifact(str(facts.root)):
            if drift == "named_artifact":
                os.replace(other, facts.artifact)  # Same bytes, different named inode.
            elif drift == "held_fd":
                with other.open("rb") as stream:
                    os.dup2(stream.fileno(), facts.artifact_fd)
            elif drift == "ancestor":
                facts.artifact.parent.chmod(stat.S_IRWXU)
            else:
                facts.artifact.chmod(stat.S_IRUSR | stat.S_IWUSR)
                facts.artifact.write_bytes(facts.original.replace(b"fixture-only", b"changed-data"))
                facts.artifact.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
