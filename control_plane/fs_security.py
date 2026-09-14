"""Fail-closed filesystem security observations shared by control-plane code."""
from __future__ import annotations

import ctypes
import errno
import os
import sys
from pathlib import Path


ACL_TYPE_EXTENDED = 0x100
ACL_FIRST_ENTRY = 0


class FilesystemSecurityError(RuntimeError):
    """A filesystem security observation could not be completed."""


def _bind_macos_acl_functions() -> tuple[Any, Any, Any]:
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        acl_get_file = libc.acl_get_file
        acl_get_entry = libc.acl_get_entry
        acl_free = libc.acl_free
    except AttributeError as exc:
        raise FilesystemSecurityError("macOS ACL observer is unavailable") from exc
    acl_get_file.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    acl_get_file.restype = ctypes.c_void_p
    acl_get_entry.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    acl_get_entry.restype = ctypes.c_int
    acl_free.argtypes = [ctypes.c_void_p]
    acl_free.restype = ctypes.c_int
    return acl_get_file, acl_get_entry, acl_free


def _acl_get_file(path: bytes, acl_type: int) -> int | None:
    acl_get_file, _, _ = _bind_macos_acl_functions()
    ctypes.set_errno(0)
    return acl_get_file(path, acl_type)


def _acl_get_entry(acl: int, entry_id: int, entry: Any) -> int:
    _, acl_get_entry, _ = _bind_macos_acl_functions()
    ctypes.set_errno(0)
    return acl_get_entry(acl, entry_id, entry)


def _acl_free(acl: int) -> int:
    _, _, acl_free = _bind_macos_acl_functions()
    return acl_free(acl)


def has_macos_acl(path: Path | str) -> bool:
    """Return whether a Darwin path has at least one extended ACL entry."""

    if sys.platform != "darwin":
        return False

    try:
        os.lstat(path)
    except OSError as exc:
        raise FilesystemSecurityError("macOS ACL observation target is unavailable") from exc

    acl = _acl_get_file(os.fsencode(path), ACL_TYPE_EXTENDED)
    if not acl:
        error_number = ctypes.get_errno()
        if error_number == errno.ENOENT:
            return False
        raise FilesystemSecurityError(
            f"macOS ACL observation failed: errno={error_number}"
        )

    entry = ctypes.c_void_p()
    try:
        result = _acl_get_entry(acl, ACL_FIRST_ENTRY, ctypes.byref(entry))
    finally:
        _acl_free(acl)

    if result == 0:
        return bool(entry)
    if result == -1:
        return False
    raise FilesystemSecurityError(
        f"macOS ACL enumeration failed: errno={ctypes.get_errno()}"
    )


__all__ = ["FilesystemSecurityError", "has_macos_acl"]
