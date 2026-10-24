"""Fail-closed filesystem security observations shared by control-plane code."""
from __future__ import annotations

import ctypes
import errno
import grp
import hmac
import os
import stat
import sys
from pathlib import Path
from typing import Any, NamedTuple


ACL_TYPE_EXTENDED = 0x100
ACL_FIRST_ENTRY = 0

# Native sys/acl.h constants for the single-entry deny-delete classifier.
ACL_EXTENDED_DENY = 2
ACL_DELETE_PERM = 16


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

    The opt-in is also strict about its inputs on every platform. It never accepts
    a caller-supplied ``descriptor``: the symlink observation must own the
    ``O_SYMLINK`` open itself, so the trusted flags are part of the observation
    rather than something a caller can assert by handing over a descriptor.
    ``expected_identity`` must be the caller's real ``os.stat_result``; any other
    object refuses before any open instead of leaking an ``AttributeError``.
    ``O_SYMLINK`` must be a native, nonzero ``int`` (``bool`` is rejected); a
    missing, zero, or non-integer attribute refuses before any open.
    """

    if allow_symlink:
        # The opt-in's input contract is unconditional and is validated before the
        # Darwin gate, so a portable caller can never receive a silent ACL-free
        # answer from a malformed opt-in. Only the ACL observation itself is
        # Darwin-scoped, which is what keeps the manifest path working off Darwin.
        if descriptor is not None:
            raise FilesystemSecurityError(
                "macOS ACL symlink observation must own its descriptor"
            )
        if expected_identity is None:
            raise FilesystemSecurityError(
                "macOS ACL symlink observation requires the caller's pre-open lstat"
            )
        if not isinstance(expected_identity, os.stat_result):
            raise FilesystemSecurityError(
                "macOS ACL symlink observation requires an os.stat_result "
                "pre-open identity"
            )
        if not stat.S_ISLNK(expected_identity.st_mode):
            raise FilesystemSecurityError(
                "macOS ACL symlink observation requires a symlink pre-open identity"
            )

    if sys.platform != "darwin":
        return False

    if expected_identity is None:
        try:
            before = os.lstat(path)
        except OSError as exc:
            raise FilesystemSecurityError(
                f"macOS ACL observation target is unavailable: errno={exc.errno}"
            ) from exc
    else:
        before = expected_identity

    if allow_symlink:
        o_symlink = getattr(os, "O_SYMLINK", None)
        if type(o_symlink) is not int:
            raise FilesystemSecurityError(
                "macOS ACL symlink observation is unavailable: O_SYMLINK is not native"
            )
        if o_symlink <= 0:
            raise FilesystemSecurityError(
                "macOS ACL symlink observation is unavailable: "
                "O_SYMLINK is not a nonzero integer"
            )
        flags = (
            os.O_RDONLY
            | o_symlink
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
        if allow_symlink:
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


class _AclClassifierBindings(NamedTuple):
    """Exactly bound libc ACL entry points, with ownership spelled out.

    ``acl_t`` handles are caller-owned ``c_void_p`` values released through
    ``acl_free``; entry handles are owned by their ``acl_t`` and are never
    freed separately; qualifier and external-representation buffers are
    caller-owned memory handed to libc as ``c_void_p``.
    """

    acl_get_fd: Any
    acl_free: Any
    acl_init: Any
    acl_create_entry: Any
    acl_set_tag_type: Any
    acl_set_qualifier: Any
    acl_set_permset_mask_np: Any
    acl_size: Any
    acl_copy_ext_native: Any
    mbr_gid_to_uuid: Any


def _bind_acl_classifier_functions() -> _AclClassifierBindings:
    """Bind the libc ACL family the exact-shape classifier needs.

    Every signature is declared explicitly before first use. A missing native
    entry point fails closed instead of degrading the classification.
    """

    libc = ctypes.CDLL(None, use_errno=True)
    try:
        bindings = _AclClassifierBindings(
            acl_get_fd=libc.acl_get_fd,
            acl_free=libc.acl_free,
            acl_init=libc.acl_init,
            acl_create_entry=libc.acl_create_entry,
            acl_set_tag_type=libc.acl_set_tag_type,
            acl_set_qualifier=libc.acl_set_qualifier,
            acl_set_permset_mask_np=libc.acl_set_permset_mask_np,
            acl_size=libc.acl_size,
            acl_copy_ext_native=libc.acl_copy_ext_native,
            mbr_gid_to_uuid=libc.mbr_gid_to_uuid,
        )
    except AttributeError as exc:
        raise FilesystemSecurityError(
            "macOS everyone-deny-delete ACL classifier is unavailable"
        ) from exc
    bindings.acl_get_fd.argtypes = [ctypes.c_int]
    bindings.acl_get_fd.restype = ctypes.c_void_p
    bindings.acl_free.argtypes = [ctypes.c_void_p]
    bindings.acl_free.restype = ctypes.c_int
    bindings.acl_init.argtypes = [ctypes.c_int]
    bindings.acl_init.restype = ctypes.c_void_p
    bindings.acl_create_entry.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    bindings.acl_create_entry.restype = ctypes.c_int
    bindings.acl_set_tag_type.argtypes = [ctypes.c_void_p, ctypes.c_int]
    bindings.acl_set_tag_type.restype = ctypes.c_int
    bindings.acl_set_qualifier.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    bindings.acl_set_qualifier.restype = ctypes.c_int
    bindings.acl_set_permset_mask_np.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    bindings.acl_set_permset_mask_np.restype = ctypes.c_int
    bindings.acl_size.argtypes = [ctypes.c_void_p]
    bindings.acl_size.restype = ctypes.c_ssize_t
    bindings.acl_copy_ext_native.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ssize_t,
    ]
    bindings.acl_copy_ext_native.restype = ctypes.c_ssize_t
    bindings.mbr_gid_to_uuid.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_ubyte)]
    bindings.mbr_gid_to_uuid.restype = ctypes.c_int
    return bindings


def _checked_acl_free(bindings: _AclClassifierBindings, acl: int) -> None:
    """Release one owned ``acl_t``; a failed release fails closed."""

    if bindings.acl_free(acl) != 0:
        raise FilesystemSecurityError("macOS ACL release failed")


_ACL_EVERYONE_GROUP = "everyone"
_ACL_ENTRY_RESERVE = 1
_ACL_EXT_SIZE_LIMIT = 4096
_UUID_BYTES = 16
_CLASSIFIER_STABLE_FIELDS = (
    "st_mode",
    "st_ino",
    "st_dev",
    "st_uid",
    "st_gid",
    "st_nlink",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)


def _classifier_stable_identity(info: os.stat_result) -> tuple:
    return tuple(getattr(info, field) for field in _CLASSIFIER_STABLE_FIELDS)


def _everyone_group_gid() -> int:
    """Resolve the fixed ``everyone`` group's gid from the group database."""

    try:
        record = grp.getgrnam(_ACL_EVERYONE_GROUP)
    except (KeyError, OSError, ValueError) as exc:
        raise FilesystemSecurityError(
            "macOS ACL classifier could not resolve the fixed everyone group"
        ) from exc
    gid = record.gr_gid
    if (type(gid) is not int or not 0 <= gid <= 0xFFFFFFFF
            or getattr(record, "gr_name", None) != _ACL_EVERYONE_GROUP):
        raise FilesystemSecurityError(
            "macOS ACL classifier resolved a malformed everyone group"
        )
    return gid


def _everyone_uuid(bindings: _AclClassifierBindings) -> bytes:
    """Map the fixed everyone gid to its membership UUID via libc."""

    gid = _everyone_group_gid()
    buffer = (ctypes.c_ubyte * _UUID_BYTES)()
    if bindings.mbr_gid_to_uuid(gid, buffer) != 0:
        raise FilesystemSecurityError("macOS everyone UUID conversion failed")
    uuid_bytes = bytes(buffer)
    if len(uuid_bytes) != _UUID_BYTES or uuid_bytes == bytes(_UUID_BYTES):
        raise FilesystemSecurityError(
            "macOS ACL classifier resolved a malformed everyone UUID"
        )
    return uuid_bytes


def _copy_external_acl(
    bindings: _AclClassifierBindings, acl: int, size: int
) -> bytes:
    """Copy the bounded native external representation of one ``acl_t``."""

    if size <= 0 or size > _ACL_EXT_SIZE_LIMIT:
        raise FilesystemSecurityError("macOS ACL external size is unbounded")
    buffer = ctypes.create_string_buffer(size)
    ctypes.set_errno(0)
    written = bindings.acl_copy_ext_native(buffer, acl, size)
    if written != size:
        raise FilesystemSecurityError("macOS ACL external copy failed")
    return buffer.raw[:size]


def _build_expected_deny_delete_acl(bindings: _AclClassifierBindings) -> tuple[int, bytes]:
    """Construct the expected single-entry ACL through libc alone.

    The expected ACL is built with ``acl_init``/``acl_create_entry`` and the
    native setters only — one noninherited ``group:everyone`` deny entry whose
    permission mask is exactly ``ACL_DELETE`` — then serialized with
    ``acl_copy_ext_native`` so the comparison never assumes a binary layout
    and never drops unknown flags.
    """

    expected = ctypes.c_void_p(bindings.acl_init(_ACL_ENTRY_RESERVE))
    if not expected:
        raise FilesystemSecurityError("macOS ACL expectation construction failed")
    try:
        entry = ctypes.c_void_p()
        if bindings.acl_create_entry(ctypes.byref(expected), ctypes.byref(entry)) != 0:
            raise FilesystemSecurityError("macOS ACL expectation entry failed")
        if not entry.value:
            raise FilesystemSecurityError("macOS ACL expectation entry is null")
        if bindings.acl_set_tag_type(entry, ACL_EXTENDED_DENY) != 0:
            raise FilesystemSecurityError("macOS ACL expectation tag failed")
        uuid_buffer = ctypes.create_string_buffer(_everyone_uuid(bindings))
        if bindings.acl_set_qualifier(entry, uuid_buffer) != 0:
            raise FilesystemSecurityError("macOS ACL expectation qualifier failed")
        if bindings.acl_set_permset_mask_np(entry, ACL_DELETE_PERM) != 0:
            raise FilesystemSecurityError("macOS ACL expectation permset failed")
        expected_size = int(bindings.acl_size(expected))
        return expected, _copy_external_acl(bindings, expected, expected_size)
    except BaseException:
        _checked_acl_free(bindings, expected)
        raise


def has_macos_everyone_deny_delete_only_acl(
    *,
    descriptor: int,
    expected_identity: os.stat_result,
) -> bool:
    """Classify one open directory as carrying exactly one deny-delete ACL.

    The only accepted shape is a single noninherited ``group:everyone`` deny
    entry whose permission mask is exactly ``ACL_DELETE``, with no other
    entries, rights, or flags. The observation is descriptor-bound: the
    descriptor is fstat'd before and after the ACL read and its full stable
    identity must match the caller's pre-open ``os.stat_result`` unchanged,
    and the object must be a directory. The expected ACL is generated through
    the native API and compared as bounded external bytes, so no caller ACL
    bytes are accepted and no semantic text or binary layout is parsed.

    Returns ``True`` only for the exact accepted shape and ``False`` for any
    well-formed ACL that is not it (including no ACL at all, reported by the
    kernel as ``ENOENT``). A missing native API, a failed or null observation,
    malformed input, or identity drift raises
    :class:`FilesystemSecurityError` — off Darwin this classifier refuses
    rather than silently passing.
    """

    if isinstance(descriptor, bool) or not isinstance(descriptor, int):
        raise FilesystemSecurityError(
            "macOS everyone-deny-delete ACL classification requires an "
            "integer descriptor"
        )
    if descriptor < 0:
        raise FilesystemSecurityError(
            "macOS everyone-deny-delete ACL classification requires a "
            "nonnegative descriptor"
        )
    if not isinstance(expected_identity, os.stat_result):
        raise FilesystemSecurityError(
            "macOS everyone-deny-delete ACL classification requires an "
            "os.stat_result identity"
        )

    if sys.platform != "darwin":
        raise FilesystemSecurityError(
            "macOS everyone-deny-delete ACL classification is unavailable "
            "off Darwin"
        )

    bindings = _bind_acl_classifier_functions()

    try:
        before = os.fstat(descriptor)
    except OSError as exc:
        raise FilesystemSecurityError(
            "macOS ACL classification object is unavailable"
        ) from exc
    if _classifier_stable_identity(before) != _classifier_stable_identity(
        expected_identity
    ):
        raise FilesystemSecurityError("macOS ACL classification identity changed")
    if not stat.S_ISDIR(before.st_mode):
        raise FilesystemSecurityError(
            "macOS everyone-deny-delete ACL classification requires a directory"
        )

    observed = 0
    expected = 0
    try:
        ctypes.set_errno(0)
        observed = bindings.acl_get_fd(descriptor)
        observed_errno = ctypes.get_errno()
        if not observed:
            if observed_errno == errno.ENOENT:
                return False
            raise FilesystemSecurityError(
                f"macOS ACL observation failed: errno={observed_errno}"
            )
        observed_size = int(bindings.acl_size(observed))
        observed_bytes = _copy_external_acl(bindings, observed, observed_size)
        expected, expected_bytes = _build_expected_deny_delete_acl(bindings)
        if observed_size != len(expected_bytes):
            return False
        return hmac.compare_digest(observed_bytes, expected_bytes)
    finally:
        try:
            if expected:
                _checked_acl_free(bindings, expected)
        finally:
            if observed:
                _checked_acl_free(bindings, observed)
        try:
            after = os.fstat(descriptor)
        except OSError as exc:
            raise FilesystemSecurityError(
                "macOS ACL classification object is unavailable"
            ) from exc
        if _classifier_stable_identity(after) != _classifier_stable_identity(before):
            raise FilesystemSecurityError("macOS ACL classification identity changed")


__all__ = [
    "FilesystemSecurityError",
    "has_macos_acl",
    "has_macos_everyone_deny_delete_only_acl",
]
