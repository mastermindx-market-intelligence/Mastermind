"""Fail-closed filesystem security observations shared by control-plane code."""
from __future__ import annotations

import ctypes
import errno
import os
import stat
import sys
from pathlib import Path
from typing import Any


ACL_TYPE_EXTENDED = 0x100
ACL_FIRST_ENTRY = 0


class FilesystemSecurityError(RuntimeError):
    """A filesystem security observation could not be completed."""


def _bind_macos_acl_functions() -> tuple[Any, Any, Any, Any]:
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        acl_get_fd = libc.acl_get_fd
        acl_get_entry = libc.acl_get_entry
        acl_free = libc.acl_free
    except AttributeError as exc:
        raise FilesystemSecurityError("macOS ACL observer is unavailable") from exc
    acl_get_fd.argtypes = [ctypes.c_int]
    acl_get_fd.restype = ctypes.c_void_p
    acl_get_entry.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    acl_get_entry.restype = ctypes.c_int
    acl_free.argtypes = [ctypes.c_void_p]
    acl_free.restype = ctypes.c_int
    return acl_get_fd, acl_get_entry, acl_free


def _acl_get_fd(descriptor: int) -> int | None:
    acl_get_fd, _, _ = _bind_macos_acl_functions()
    ctypes.set_errno(0)
    return acl_get_fd(descriptor)


def _acl_get_entry(acl: int, entry_id: int, entry: Any) -> int:
    _, acl_get_entry, _ = _bind_macos_acl_functions()
    ctypes.set_errno(0)
    return acl_get_entry(acl, entry_id, entry)


def _acl_free(acl: int) -> int:
    _, _, acl_free = _bind_macos_acl_functions()
    return acl_free(acl)


def _bind_macos_link_acl_function() -> Any:
    # Bound separately from the descriptor observers so a platform without the
    # non-portable link accessor degrades only the symbolic-link observation
    # instead of failing every existing file and directory caller.
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        acl_get_link_np = libc.acl_get_link_np
    except AttributeError as exc:
        raise FilesystemSecurityError("macOS link ACL observer is unavailable") from exc
    acl_get_link_np.argtypes = [ctypes.c_char_p, ctypes.c_int]
    acl_get_link_np.restype = ctypes.c_void_p
    return acl_get_link_np


def _acl_get_link(path: bytes) -> int | None:
    acl_get_link_np = _bind_macos_link_acl_function()
    ctypes.set_errno(0)
    return acl_get_link_np(path, ACL_TYPE_EXTENDED)


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def has_macos_acl(
    path: Path | str,
    *,
    expected_identity: os.stat_result | None = None,
    descriptor: int | None = None,
) -> bool:
    """Return whether a Darwin object has ACL_TYPE_EXTENDED entries.

    The ACL is observed on the opened descriptor after checking its identity
    against the caller's pre-open lstat. Callers may instead pass a descriptor
    and its matching pre-open lstat so metadata and ACL observation share one
    object. An open file descriptor remains valid after unlink, but this
    function still fails closed when the pre-open and opened identities differ.
    """

    if sys.platform != "darwin":
        return False

    try:
        before = os.lstat(path) if expected_identity is None else expected_identity
    except OSError as exc:
        raise FilesystemSecurityError(
            f"macOS ACL observation target is unavailable: errno={exc.errno}"
        ) from exc

    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    close_descriptor = False
    if descriptor is None:
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise FilesystemSecurityError("macOS ACL open failed") from exc
        close_descriptor = True
    opened_descriptor = descriptor
    try:
        try:
            observed = os.fstat(opened_descriptor)
        except OSError as exc:
            raise FilesystemSecurityError("macOS ACL object is unavailable") from exc
        if _identity(observed) != _identity(before):
            raise FilesystemSecurityError("macOS ACL observation identity changed")
        if not stat.S_ISREG(observed.st_mode) and not stat.S_ISDIR(observed.st_mode):
            raise FilesystemSecurityError("macOS ACL object is not a file or directory")

        acl = _acl_get_fd(opened_descriptor)
        acl_error_number = ctypes.get_errno()
        if not acl:
            if acl_error_number == errno.ENOENT:
                return False
            raise FilesystemSecurityError(
                f"macOS ACL observation failed: errno={acl_error_number}"
            )

        entry = ctypes.c_void_p()
        try:
            result = _acl_get_entry(acl, ACL_FIRST_ENTRY, ctypes.byref(entry))
        except BaseException:
            _acl_free(acl)
            raise
        enumeration_error_number = ctypes.get_errno()
        try:
            if result != 0:
                raise FilesystemSecurityError(
                    f"macOS ACL enumeration failed: errno={enumeration_error_number}"
                )
            if not getattr(entry, "_obj", entry):
                raise FilesystemSecurityError(
                    "macOS ACL object has no enumerable entries"
                )
            return True
        finally:
            _acl_free(acl)
    finally:
        if close_descriptor:
            try:
                os.close(opened_descriptor)
            except OSError as exc:
                raise FilesystemSecurityError("macOS ACL descriptor close failed") from exc


def has_macos_link_acl(
    path: Path | str,
    *,
    expected_identity: os.stat_result | None = None,
) -> bool:
    """Return whether a Darwin symbolic link has ACL_TYPE_EXTENDED entries.

    ``has_macos_acl`` opens its target with ``O_NOFOLLOW``, which by definition
    cannot open a symbolic link, so it can only ever fail closed on one. macOS
    nevertheless allows an ACL to be attached to the link itself (``chmod -h
    +a``), and refusing to look is not the same as proving none is present.
    This observes the link with ``acl_get_link_np``, which never follows, and
    brackets the observation with ``lstat`` so a path swapped underneath the
    call fails closed instead of reporting another object's ACL.
    """

    if sys.platform != "darwin":
        return False

    try:
        before = os.lstat(path) if expected_identity is None else expected_identity
    except OSError as exc:
        raise FilesystemSecurityError(
            f"macOS link ACL observation target is unavailable: errno={exc.errno}"
        ) from exc
    if not stat.S_ISLNK(before.st_mode):
        raise FilesystemSecurityError("macOS link ACL object is not a symbolic link")

    acl = _acl_get_link(os.fsencode(path))
    acl_error_number = ctypes.get_errno()

    try:
        after = os.lstat(path)
    except OSError as exc:
        if acl:
            _acl_free(acl)
        raise FilesystemSecurityError(
            f"macOS link ACL observation target is unavailable: errno={exc.errno}"
        ) from exc
    if not stat.S_ISLNK(after.st_mode) or _identity(after) != _identity(before):
        if acl:
            _acl_free(acl)
        raise FilesystemSecurityError("macOS link ACL observation identity changed")

    if not acl:
        if acl_error_number == errno.ENOENT:
            return False
        raise FilesystemSecurityError(
            f"macOS link ACL observation failed: errno={acl_error_number}"
        )

    entry = ctypes.c_void_p()
    try:
        result = _acl_get_entry(acl, ACL_FIRST_ENTRY, ctypes.byref(entry))
    except BaseException:
        _acl_free(acl)
        raise
    enumeration_error_number = ctypes.get_errno()
    try:
        if result != 0:
            raise FilesystemSecurityError(
                f"macOS link ACL enumeration failed: errno={enumeration_error_number}"
            )
        if not getattr(entry, "_obj", entry):
            raise FilesystemSecurityError(
                "macOS link ACL object has no enumerable entries"
            )
        return True
    finally:
        _acl_free(acl)


__all__ = ["FilesystemSecurityError", "has_macos_acl", "has_macos_link_acl"]
