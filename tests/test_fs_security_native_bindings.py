"""Native-binding reuse never reuses a filesystem ACL observation.

Real temporary descriptors and identity checks are combined with explicit libc
facts so fresh ACL changes and native errors remain observable on hosted CI.
"""
from __future__ import annotations

import ctypes
import errno
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from control_plane import fs_security


@pytest.fixture
def native(monkeypatch):
    binder = fs_security._bind_macos_acl_functions
    clear = getattr(binder, "cache_clear", lambda: None)
    clear()
    state = SimpleNamespace(mode="absent", observed=[], enumeration_error=False)

    def read_acl(fd):
        state.observed.append((fd, os.fstat(fd).st_ino))
        ctypes.set_errno({"absent": errno.ENOENT, "present": 0, "error": errno.EIO}[state.mode])
        return 1001 if state.mode == "present" else None

    def read_entry(_acl, _entry_id, pointer):
        ctypes.set_errno(errno.EIO if state.enumeration_error else 0)
        if state.enumeration_error:
            return -1
        pointer._obj.value = 2001
        return 0

    def free_acl(_acl):
        # Cleanup must not replace the preceding observation's failure errno.
        ctypes.set_errno(errno.EACCES)
        return 0

    state.library = SimpleNamespace(
        acl_get_fd=Mock(side_effect=read_acl),
        acl_get_entry=Mock(side_effect=read_entry),
        acl_free=Mock(side_effect=free_acl),
    )
    state.loader = Mock(return_value=state.library)
    monkeypatch.setattr(fs_security, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(fs_security.ctypes, "CDLL", state.loader)
    try:
        yield state
    finally:
        clear()


def test_binding_reuse_observes_each_acl_change_and_native_failure(tmp_path, native):
    path = tmp_path / "fresh-acl"
    path.touch()
    assert fs_security.has_macos_acl(path) is False
    native.mode = "present"
    assert fs_security.has_macos_acl(path) is True
    native.mode = "absent"
    assert fs_security.has_macos_acl(path) is False
    native.mode = "error"
    with pytest.raises(fs_security.FilesystemSecurityError, match="observation failed: errno=5"):
        fs_security.has_macos_acl(path)
    assert len(native.observed) == 4
    assert all(inode == path.stat().st_ino for _fd, inode in native.observed)
    native.library.acl_get_entry.assert_called_once()
    native.library.acl_free.assert_called_once_with(1001)
    native.loader.assert_called_once_with(None, use_errno=True)


def test_warm_bindings_preserve_descriptor_identity_refusal(tmp_path, native):
    original, other = tmp_path / "original", tmp_path / "other"
    original.touch()
    other.touch()
    assert fs_security.has_macos_acl(original) is False
    with pytest.raises(fs_security.FilesystemSecurityError, match="identity changed"):
        fs_security.has_macos_acl(other, expected_identity=original.stat())
    assert len(native.observed) == 1
    native.loader.assert_called_once()


def test_warm_bindings_preserve_enumeration_failure_and_cleanup(tmp_path, native):
    path = tmp_path / "enumeration-error"
    path.touch()
    assert fs_security.has_macos_acl(path) is False
    native.mode = "present"
    native.enumeration_error = True
    with pytest.raises(fs_security.FilesystemSecurityError, match="enumeration failed: errno=5"):
        fs_security.has_macos_acl(path)
    assert len(native.observed) == 2
    native.library.acl_free.assert_called_once_with(1001)
    native.loader.assert_called_once()


def test_unavailable_native_bindings_refuse_without_caching_failure(tmp_path, native):
    path = tmp_path / "unavailable"
    path.touch()
    native.loader.side_effect = [SimpleNamespace(), native.library]
    with pytest.raises(fs_security.FilesystemSecurityError, match="observer is unavailable"):
        fs_security.has_macos_acl(path)
    assert not native.observed
    assert fs_security.has_macos_acl(path) is False
    assert len(native.observed) == 1
    assert native.loader.call_count == 2


def test_non_darwin_never_loads_native_bindings(tmp_path, native, monkeypatch):
    monkeypatch.setattr(fs_security, "sys", SimpleNamespace(platform="linux"))
    assert fs_security.has_macos_acl(tmp_path / "not-acquired") is False
    native.loader.assert_not_called()
