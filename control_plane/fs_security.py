"""Fail-closed filesystem security observations shared by control-plane code."""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


ACL_TYPE_EXTENDED = 0x100
ACL_FIRST_ENTRY = 0


class FilesystemSecurityError(RuntimeError):
    """A filesystem security observation could not be completed."""


def has_macos_acl(path: Path | str) -> bool:
    """Return whether a Darwin path has at least one extended ACL entry."""

    if sys.platform != "darwin":
        return False

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

    acl = acl_get_file(os.fsencode(path), ACL_TYPE_EXTENDED)
    if not acl:
        return False

    entry = ctypes.c_void_p()
    try:
        result = acl_get_entry(acl, ACL_FIRST_ENTRY, ctypes.byref(entry))
    finally:
        acl_free(acl)

    if result == 0:
        return bool(entry)
    if result == 1:
        return False
    raise FilesystemSecurityError(
        f"macOS ACL enumeration failed: errno={ctypes.get_errno()}"
    )


__all__ = ["FilesystemSecurityError", "has_macos_acl"]
