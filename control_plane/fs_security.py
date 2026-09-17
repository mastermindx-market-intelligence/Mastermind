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


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def has_macos_acl(
    path: Path | str,
    *,
    expected_identity: os.stat_result | None = None,
    descriptor: int | None = None,
    allow_symlink: bool = False,
) -> bool:
    """Return whether a Darwin object has ACL_TYPE_EXTENDED entries.

    The ACL is observed on the opened descriptor after checking its identity
    against the caller's pre-open lstat. Callers may instead pass a descriptor
    and its matching pre-open lstat so metadata and ACL observation share one
    object. An open file descriptor remains valid after unlink, but this
    function still fails closed when the pre-open and opened identities differ.

    ``allow_symlink`` is a narrow, manifest-only opt-in for observing a release
    symlink's *own* ACL. It is never inferred and never re-baselined: it requires
    the caller to supply the pre-open ``expected_identity`` it already validated,
    and that lstat must itself be a symlink. The descriptor is then opened with
    the native ``O_SYMLINK`` flag and without ``O_NOFOLLOW``, and the ACL is read
    through the same descriptor-bound acquisition regular files use, so only an
    observed symlink of exactly that identity is accepted. A missing opt-in, a
    missing ``expected_identity``, a non-symlink identity, or a missing native
    ``O_SYMLINK`` all fail closed instead of falling back to a fresh ``lstat`` or
    to the ordinary file/directory path, so every path-only caller keeps refusing
    symlinks exactly as before.
    """

    if sys.platform != "darwin":
        return False

    if expected_identity is None:
        if allow_symlink:
            raise FilesystemSecurityError(
                "macOS ACL symlink observation requires the caller's pre-open lstat"
            )
        try:
            before = os.lstat(path)
        except OSError as exc:
            raise FilesystemSecurityError(
                f"macOS ACL observation target is unavailable: errno={exc.errno}"
            ) from exc
    else:
        before = expected_identity

    observe_symlink = False
    if allow_symlink:
        if not stat.S_ISLNK(before.st_mode):
            raise FilesystemSecurityError(
                "macOS ACL symlink observation requires a symlink pre-open identity"
            )
        observe_symlink = True

    if observe_symlink:
        if not hasattr(os, "O_SYMLINK"):
            raise FilesystemSecurityError(
                "macOS ACL symlink observation is unavailable: O_SYMLINK is not native"
            )
        flags = (
            os.O_RDONLY
            | os.O_SYMLINK
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
    else:
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
        if observe_symlink:
            if not stat.S_ISLNK(observed.st_mode):
                raise FilesystemSecurityError("macOS ACL object is not a symlink")
        elif not stat.S_ISREG(observed.st_mode) and not stat.S_ISDIR(observed.st_mode):
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


__all__ = ["FilesystemSecurityError", "has_macos_acl"]
