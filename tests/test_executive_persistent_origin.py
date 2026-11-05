"""Real temporary filesystem/FD tests with explicit raw privilege observations.

Only this module's fixture anchor, Darwin/euid/stat-owner facts and low-level ACL
syscalls are synthetic. The Root/Darwin/custody predicates themselves execute.
No installed path, history, service or actual Root custody is qualified here.
"""
import ctypes
import errno
import hashlib
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace

import pytest

from control_plane import fs_security
from ops.executive_os import persistent_origin as origin


@pytest.fixture
def filesystem(monkeypatch):
    with tempfile.TemporaryDirectory(prefix=".mmos-data-anchor-", dir=Path.home().resolve()) as name:
        base = Path(name)
        anchor = base / "data-volume"
        anchor.mkdir(mode=stat.S_IRWXU)
        state = SimpleNamespace(anchor=anchor, base=base, euid=0, owner={}, device={},
                                fd_device={}, acl=set(), opened=set(), fail_open=None,
                                fail_fstat=False)
        # Only the fixture anchor/prefixes model Root custody. Other real
        # source-fixture files retain their actual owner/group observations.
        anchor_inodes = {path.lstat().st_ino for path in [*anchor.parents, anchor]}
        state.owner.update({inode: 0 for inode in anchor_inodes})

        def facts(info):
            values = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
            values.update(st_uid=state.owner.get(info.st_ino, info.st_uid),
                          st_gid=0 if info.st_ino in anchor_inodes else info.st_gid,
                          st_dev=state.device.get(info.st_ino, info.st_dev))
            return SimpleNamespace(**values)

        class ObservedOS:
            def __getattr__(self, key):
                return getattr(os, key)

            def geteuid(self):
                return state.euid

            def open(self, path, flags, **kwargs):
                assert flags & os.O_NOFOLLOW
                if path == state.fail_open:
                    raise PermissionError(errno.EACCES, "fixture open refused")
                fd = os.open(path, flags, **kwargs)
                state.opened.add(fd)
                return fd

            def close(self, fd):
                os.close(fd)
                state.opened.remove(fd)

            def fstat(self, fd):
                if state.fail_fstat:
                    state.fail_fstat = False
                    raise OSError(errno.EIO, "fixture fstat failed")
                value = facts(os.fstat(fd))
                if fd in state.fd_device:
                    value.st_dev = state.fd_device[fd]
                return value

            def stat(self, path, **kwargs):
                return facts(os.stat(path, **kwargs))

            def lstat(self, path):
                return facts(os.lstat(path))

        def acl_get_fd(fd):
            ctypes.set_errno(0 if os.fstat(fd).st_ino in state.acl else errno.ENOENT)
            return 1 if os.fstat(fd).st_ino in state.acl else None

        def acl_get_entry(_acl, _entry, pointer):
            pointer._obj.value = 1
            ctypes.set_errno(0)
            return 0

        monkeypatch.setattr(origin, "DATA_VOLUME_ANCHOR", anchor)
        monkeypatch.setattr(origin, "os", ObservedOS())
        monkeypatch.setattr(origin, "sys", SimpleNamespace(platform="darwin"))
        monkeypatch.setattr(fs_security, "sys", SimpleNamespace(platform="darwin"))
        monkeypatch.setattr(fs_security, "_acl_get_fd", acl_get_fd)
        monkeypatch.setattr(fs_security, "_acl_get_entry", acl_get_entry)
        monkeypatch.setattr(fs_security, "_acl_free", lambda _acl: 0)
        yield state
        # Every test must leave no live helper-owned descriptor, including failures.
        assert not state.opened


def records(volume):
    current = volume.current_device
    old = current + 1
    expected = {"path": "/fixed/original", "device": old, "inode": 73,
                "size": 8, "sha256": "a" * 64, "payload_digest": "b" * 64}
    return old, expected, dict(expected, device=current)


@pytest.mark.parametrize("same_device", [False, True])
def test_record_qualifies_only_current_custody_and_preserves_original(filesystem, same_device):
    with origin.CurrentDataVolumeGuard() as volume:
        old, expected, observed = records(volume)
        if same_device:
            old = expected["device"] = volume.current_device
        before_expected, before_observed = dict(expected), dict(observed)
        assert origin.persistent_record_matches(expected, observed, volume=volume,
                                                historical_device=old)
        assert expected == before_expected and observed == before_observed


@pytest.mark.parametrize("field", ["path", "inode", "size", "sha256", "payload_digest",
                                   "uid", "gid", "mode", "nlink", "mtime_ns", "ctime_ns"])
def test_every_nondevice_field_stays_exact(filesystem, field):
    with origin.CurrentDataVolumeGuard() as volume:
        old, expected, observed = records(volume)
        expected.setdefault(field, 17)
        observed.setdefault(field, 17)
        observed[field] = "changed" if type(expected[field]) is str else expected[field] + 1
        assert not origin.persistent_record_matches(expected, observed, volume=volume,
                                                    historical_device=old)


@pytest.mark.parametrize("fault", ["foreign", "wrong_old", "missing", "extra", "bool_device",
                                   "bool_old", "negative", "bool_equals_int", "nested_device",
                                   "list_type", "object"])
def test_record_closure_types_and_nested_history_are_not_normalized(filesystem, fault):
    with origin.CurrentDataVolumeGuard() as volume:
        old, expected, observed = records(volume)
        if fault == "foreign": observed["device"] += 2
        elif fault == "wrong_old": old += 2
        elif fault == "missing": observed.pop("device")
        elif fault == "extra": observed["unknown"] = 1
        elif fault == "bool_device": observed["device"] = True
        elif fault == "bool_old": old = True
        elif fault == "negative": old = -1
        elif fault == "bool_equals_int": expected["inode"], observed["inode"] = True, 1
        elif fault == "nested_device": expected["nested"], observed["nested"] = {"device": 1}, {"device": 2}
        elif fault == "list_type": expected["nested"], observed["nested"] = [True], [1]
        else: expected["nested"] = observed["nested"] = object()
        assert not origin.persistent_record_matches(expected, observed, volume=volume,
                                                    historical_device=old)


def test_wrong_volume_object_and_closed_guard_cannot_supply_authority(filesystem):
    with pytest.raises(origin.PersistentOriginError, match="actual current"):
        origin.persistent_record_matches({}, {}, volume=SimpleNamespace(current_device=1), historical_device=1)
    volume = origin.CurrentDataVolumeGuard()
    old, expected, observed = records(volume)
    volume.close()
    with pytest.raises(origin.PersistentOriginError, match="closed"):
        origin.persistent_record_matches(expected, observed, volume=volume, historical_device=old)
    volume.close()


@pytest.mark.parametrize("fault", ["nonroot", "nondarwin", "owner", "writable", "acl", "symlink"])
def test_qualification_requires_literal_root_darwin_and_real_directory_custody(filesystem, monkeypatch, fault):
    f = filesystem
    if fault == "nonroot":
        f.euid = os.geteuid() or 501
        # Even an anchor owned by that same unprivileged actor is not Root.
        f.owner[f.anchor.stat().st_ino] = f.euid
    elif fault == "nondarwin": monkeypatch.setattr(origin, "sys", SimpleNamespace(platform="linux"))
    elif fault == "owner": f.owner[f.anchor.stat().st_ino] = os.geteuid() or 501
    elif fault == "writable": f.anchor.chmod(stat.S_IRWXU | stat.S_IRWXG)
    elif fault == "acl": f.acl.add(f.anchor.stat().st_ino)
    else:
        retained = f.anchor.with_name("original")
        f.anchor.rename(retained)
        f.anchor.symlink_to(retained, target_is_directory=True)
    with pytest.raises(origin.PersistentOriginError):
        origin.CurrentDataVolumeGuard()


@pytest.mark.parametrize("fault", ["named_inode", "held_device", "prefix_mode", "acl", "principal", "constant"])
def test_lifetime_device_inode_prefix_acl_and_principal_stay_exact(filesystem, monkeypatch, fault):
    f = filesystem
    with origin.CurrentDataVolumeGuard() as volume:
        if fault == "named_inode":
            f.anchor.rename(f.anchor.with_name("retained"))
            f.anchor.mkdir(mode=stat.S_IRWXU)
        elif fault == "held_device": f.fd_device[volume._nodes[-1].fd] = volume.current_device + 1
        elif fault == "prefix_mode": f.base.chmod(stat.S_IRWXU | stat.S_IRWXG)
        elif fault == "acl": f.acl.add(f.anchor.stat().st_ino)
        elif fault == "principal": f.euid = os.geteuid() or 501
        else: monkeypatch.setattr(origin, "DATA_VOLUME_ANCHOR", f.anchor.with_name("foreign"))
        with pytest.raises(origin.PersistentOriginError): volume.check()


def test_unrelated_directory_children_do_not_rebaseline_anchor(filesystem):
    with origin.CurrentDataVolumeGuard() as volume:
        original = volume.current_device
        (filesystem.anchor / "unrelated-child").mkdir()
        assert volume.current_device == original


@pytest.mark.parametrize("fault", ["open", "first_fstat", "interrupt"])
def test_all_fds_are_released_on_qualification_failure(filesystem, monkeypatch, fault):
    if fault == "open": filesystem.fail_open = filesystem.anchor.name
    elif fault == "first_fstat": filesystem.fail_fstat = True
    else:
        def interrupted(_fd): raise KeyboardInterrupt()
        monkeypatch.setattr(fs_security, "_acl_get_fd", interrupted)
    with pytest.raises(KeyboardInterrupt if fault == "interrupt" else origin.PersistentOriginError):
        origin.CurrentDataVolumeGuard()


def test_named_file_info_must_be_current_and_anchor_member(filesystem):
    path = filesystem.anchor / "original"
    path.write_bytes(b"unchanged")
    with origin.CurrentDataVolumeGuard() as volume:
        before = origin.os.lstat(path)
        volume.require_path_device(path, before)
        path.rename(path.with_name("retained"))
        path.write_bytes(b"unchanged")
        with pytest.raises(origin.PersistentOriginError, match="identity changed"):
            volume.require_path_device(path, before)


def test_real_foreign_filesystem_is_refused_even_with_exact_nondevice_record(filesystem):
    with origin.CurrentDataVolumeGuard() as volume:
        candidates = (Path("/dev/shm"), Path(__file__).resolve().parents[1])
        parent = next((p for p in candidates if p.is_dir() and os.access(p, os.W_OK)
                       and p.stat().st_dev != volume.current_device), None)
        if parent is None:
            pytest.skip("unprivileged second filesystem unavailable; synthetic foreign-device case remains mandatory")
        with tempfile.TemporaryDirectory(prefix="mmos-foreign-origin-", dir=parent) as name:
            path = Path(name) / "same-bytes"
            raw = b"immutable original bytes"
            path.write_bytes(raw)
            actual = os.lstat(path)
            with pytest.raises(origin.PersistentOriginError, match="outside"):
                volume.require_path_device(path)
            observed = {"path": str(path), "device": actual.st_dev, "inode": actual.st_ino,
                        "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            old = volume.current_device + 1
            expected = dict(observed, device=old)
            assert not origin.persistent_record_matches(expected, observed, volume=volume,
                                                        historical_device=old)
