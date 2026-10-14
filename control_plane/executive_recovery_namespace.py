"""Dormant fixed-namespace observations; held descriptors are NOT a lock.

No listener creation, unlink, bootstrap, connect, issuer or core API is here.
The sole trusted installer must independently own the uninterrupted interval.
These handles cannot be serialized or transferred as permission to a broker.
"""
from dataclasses import dataclass
import errno
import ctypes
import os
import stat
import sys

from control_plane import executive_installed_peer as peer
from control_plane import executive_release_observation as release
from control_plane.executive_recovery_host_observation import _instance
from control_plane.fs_security import ACL_TYPE_EXTENDED

__all__ = ()
_DIRECTORIES = ('/', '/private', '/private/var', '/private/var/run',
                '/private/var/run/mastermind-executive')
_ALIAS = '/var'
_ALIAS_TARGET = 'private/var'
_LEAF = 'privileged.sock'
_CANONICAL = _DIRECTORIES[-1] + '/' + _LEAF
_LEXICAL = '/var/run/mastermind-executive/' + _LEAF


class NamespaceObservationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _refuse(code):
    raise NamespaceObservationError(code) from None


def _structural(info):
    # Directory timestamps/size change on legitimate child creation. Pin the
    # directory itself and its security metadata, not a claimed child history.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_nlink)


@dataclass(frozen=True, slots=True)
class _Held:
    path: str
    descriptor: int
    identity: tuple
    alias: bool


class _NamespaceHandles:
    """Private observation resources only; never exclusion/activation authority."""
    def __init__(self, budget):
        self.budget = budget
        self.held = []
        self.owner = None
        self.boot = None
        self.closed = False
        self.failed = False


def _shape(info, alias):
    expected_type = stat.S_ISLNK if alias else stat.S_ISDIR
    if (not expected_type(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o755
            or (info.st_nlink != 1 if alias else info.st_nlink < 1)):
        _refuse('RECOVERY_NAMESPACE_PROFILE_DRIFT')


def _check_handle(held, budget):
    first = budget.call(os.fstat, held.descriptor)
    named = budget.call(peer._lstat, held.path)
    _shape(first, held.alias)
    if peer._object_identity(first) != peer._object_identity(named):
        _refuse('RECOVERY_NAMESPACE_REPLACED')
    identity = peer._object_identity(first) if held.alias else _structural(first)
    if identity != held.identity:
        _refuse('RECOVERY_NAMESPACE_REPLACED')
    if held.alias and budget.call(peer._readlink, held.path) != _ALIAS_TARGET:
        _refuse('RECOVERY_NAMESPACE_ALIAS_DRIFT')
    if budget.call(peer._require_no_acl, held.path, first,
                   descriptor=None if held.alias else held.descriptor,
                   code='RECOVERY_NAMESPACE_ACL_UNAVAILABLE', allow_symlink=held.alias):
        _refuse('RECOVERY_NAMESPACE_ACL_PRESENT')
    # All properties must stay stable during THIS read. Across bootstrap the
    # directory's stable structural identity is retained; its child timestamps
    # are deliberately not treated as an exclusive filesystem lock.
    final = budget.call(os.fstat, held.descriptor)
    current = budget.call(peer._lstat, held.path)
    if (peer._object_identity(final) != peer._object_identity(first)
            or peer._object_identity(current) != peer._object_identity(first)
            or (held.alias and budget.call(peer._readlink, held.path) != _ALIAS_TARGET)):
        _refuse('RECOVERY_NAMESPACE_CHANGED_DURING_READ')


def _recheck_namespace(handles):
    try:
        if type(handles) is not _NamespaceHandles or handles.closed or handles.failed:
            _refuse('RECOVERY_NAMESPACE_CONTEXT_UNAVAILABLE')
        budget = handles.budget
        budget.check(force=True)
        if sys.platform != 'darwin' or os.geteuid() != 0:
            _refuse('RECOVERY_NAMESPACE_OWNER_CHANGED')
        if _instance(os.getpid(), budget) != handles.owner or budget.call(release._boot, budget) != handles.boot:
            _refuse('RECOVERY_NAMESPACE_OWNER_CHANGED')
        if tuple(h.path for h in handles.held) != _DIRECTORIES + (_ALIAS,):
            _refuse('RECOVERY_NAMESPACE_CONTEXT_UNAVAILABLE')
        for held in handles.held:
            _check_handle(held, budget)
        budget.check(force=True)
    except BaseException:
        if type(handles) is _NamespaceHandles:
            handles.failed = True
        raise


def _release_namespace(handles):
    if type(handles) is not _NamespaceHandles or handles.closed:
        _refuse('RECOVERY_NAMESPACE_CONTEXT_UNAVAILABLE')
    # Invalidate first. A failed close cannot authorize a retry on a potentially
    # reused descriptor. Attempt every owned descriptor even after one failure.
    handles.closed = True
    pending, handles.held = tuple(reversed(handles.held)), []
    failed = False
    for held in pending:
        try:
            peer._close(held.descriptor)
        except BaseException:
            failed = True
    if failed:
        handles.failed = True
        _refuse('RECOVERY_NAMESPACE_CLEANUP_UNPROVEN')
    handles.budget.check(force=True)


def _acquire_namespace(*, deadline_monotonic_ns):
    budget = release._Budget(deadline_monotonic_ns)
    handles = _NamespaceHandles(budget)
    try:
        if sys.platform != 'darwin' or os.geteuid() != 0:
            _refuse('RECOVERY_NAMESPACE_OWNER_UNQUALIFIED')
        for flag in ('O_NOFOLLOW', 'O_CLOEXEC', 'O_SYMLINK'):
            value = getattr(os, flag, None)
            if type(value) is not int or value <= 0:
                _refuse('RECOVERY_NAMESPACE_NATIVE_FLAGS_UNAVAILABLE')
        handles.owner = _instance(os.getpid(), budget)
        handles.boot = budget.call(release._boot, budget)
        for path in _DIRECTORIES + (_ALIAS,):
            alias = path == _ALIAS
            # Do not wrap acquisition in budget.call: _open_trusted owns its
            # fences/cleanup. Register its returned FD before any later fence
            # can fail so acquisition cannot leak an unowned returned handle.
            descriptor, info, _ = peer._open_trusted(
                path, budget=budget, allow_symlink=_ALIAS if alias else None)
            handles.held.append(_Held(path, descriptor, (), alias))
            identity = peer._object_identity(info) if alias else _structural(info)
            handles.held[-1] = _Held(path, descriptor, identity, alias)
            budget.check(force=True)
            _shape(info, alias)
        _recheck_namespace(handles)
        return handles
    except BaseException:
        handles.failed = True
        _release_namespace(handles)
        raise


def _leaf_states(handles):
    parent = next(h for h in handles.held if h.path == _DIRECTORIES[-1])
    budget = handles.budget
    values = []
    for function, args, kwargs in (
        (os.stat, (_LEAF,), {'dir_fd': parent.descriptor, 'follow_symlinks': False}),
        (peer._lstat, (_CANONICAL,), {}),
        (peer._lstat, (_LEXICAL,), {}),
    ):
        try:
            values.append(budget.call(function, *args, **kwargs))
        except FileNotFoundError as error:
            if error.errno != errno.ENOENT:
                raise
            # The command budget may have an existing refusal; absence does
            # not swallow it or avoid the return-side absolute deadline fence.
            budget.check(force=True)
            values.append(None)
    return tuple(values)


def _require_socket_absent(handles):
    try:
        _recheck_namespace(handles)
        if any(info is not None for info in _leaf_states(handles)):
            _refuse('RECOVERY_NAMESPACE_SOCKET_PREEXISTS')
        _recheck_namespace(handles)
    except BaseException:
        if type(handles) is _NamespaceHandles:
            handles.failed = True
        raise


@dataclass(frozen=True, slots=True)
class _SocketNode:
    identity: tuple


def _require_no_socket_acl(budget):
    """Fixed no-follow native ACL acquisition; no text-marker inference.

    The caller brackets this path query with three-view inode/namespace reads.
    NULL+ENOENT may mean no ACL property or a missing path; only the caller's
    independently present, stable socket can distinguish those for admission.
    Any allocated ACL, including an empty one, conservatively refuses.
    """
    budget.check(force=True)
    if sys.platform != 'darwin' or os.geteuid() != 0:
        _refuse('RECOVERY_NAMESPACE_SOCKET_ACL_UNPROVEN')
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        acquire = libc.acl_get_link_np
        free = libc.acl_free
        acquire.argtypes = [ctypes.c_char_p, ctypes.c_int]
        acquire.restype = ctypes.c_void_p
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_int
    except (AttributeError, OSError):
        _refuse('RECOVERY_NAMESPACE_SOCKET_ACL_API_UNAVAILABLE')
    acl = None
    try:
        ctypes.set_errno(0)
        # Do not use budget.call around this allocating call: a return-side
        # deadline failure must not lose the allocation before it is registered.
        acl = acquire(_CANONICAL.encode('ascii'), ACL_TYPE_EXTENDED)
        observed_errno = ctypes.get_errno()
        budget.check(force=True)
        if acl:
            _refuse('RECOVERY_NAMESPACE_SOCKET_ACL_PRESENT')
        if observed_errno != errno.ENOENT:
            _refuse('RECOVERY_NAMESPACE_SOCKET_ACL_UNPROVEN')
    finally:
        if acl:
            try:
                result = free(acl)
            except BaseException:
                _refuse('RECOVERY_NAMESPACE_SOCKET_ACL_CLEANUP_UNPROVEN')
            if type(result) is not int or result != 0:
                _refuse('RECOVERY_NAMESPACE_SOCKET_ACL_CLEANUP_UNPROVEN')
    budget.check(force=True)


def _observe_socket_node(handles):
    """Observe shape/native ACL absence, not creation or accepting process."""
    try:
        _recheck_namespace(handles)
        first = _leaf_states(handles)
        if any(info is None for info in first):
            _refuse('RECOVERY_NAMESPACE_SOCKET_MISSING')
        for info in first:
            if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != 450 or info.st_gid != 453
                    or stat.S_IMODE(info.st_mode) != 0o660 or info.st_nlink != 1):
                _refuse('RECOVERY_NAMESPACE_SOCKET_PROFILE_DRIFT')
        identity = peer._object_identity(first[0])
        if any(peer._object_identity(info) != identity for info in first):
            _refuse('RECOVERY_NAMESPACE_SOCKET_REPLACED')
        _require_no_socket_acl(handles.budget)
        after = _leaf_states(handles)
        if any(info is None or peer._object_identity(info) != identity for info in after):
            _refuse('RECOVERY_NAMESPACE_SOCKET_REPLACED')
        _recheck_namespace(handles)
        return _SocketNode(identity)
    except BaseException:
        if type(handles) is _NamespaceHandles:
            handles.failed = True
        raise


def _require_same_socket(handles, previous):
    try:
        if type(previous) is not _SocketNode or _observe_socket_node(handles) != previous:
            _refuse('RECOVERY_NAMESPACE_SOCKET_REPLACED')
    except BaseException:
        if type(handles) is _NamespaceHandles:
            handles.failed = True
        raise
