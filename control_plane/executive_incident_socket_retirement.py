"""Private stopped-broker socket preservation, never recovery admission.

The maintenance owner brackets this primitive with the existing complete source,
disabled/unloaded and old-owner observations. Held directory FDs are observations,
not a lock against another trusted root. A concurrent replacement fails closed.
The fixed retained name is never overwritten, removed, adopted or replayed here.
Its presence blocks another maintenance attempt, including after uncertain rename.
"""
import errno
import ctypes
import os
import stat
from dataclasses import dataclass

from control_plane import executive_recovery_namespace as namespace
from ops.executive_os.capacity_host_artifacts import _rename_exclusive

__all__ = ()
_RETAINED = '.privileged-retired.sock'


class SocketRetirementError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _refuse(code):
    raise SocketRetirementError(code)


def _parent(handles):
    namespace._recheck_namespace(handles)
    return next(row for row in handles.held if row.path == namespace._DIRECTORIES[-1])


def _retained_state(handles):
    parent = _parent(handles)
    try:
        return handles.budget.call(os.stat, _RETAINED,
                                   dir_fd=parent.descriptor, follow_symlinks=False)
    except FileNotFoundError as error:
        if error.errno != errno.ENOENT:
            raise
        handles.budget.check(force=True)
        return None


def _require_retained_absent(handles):
    if _retained_state(handles) is not None:
        _refuse('BROKER_MAINTENANCE_RETAINED_SOCKET_OCCUPIED')
    namespace._recheck_namespace(handles)


@dataclass(frozen=True, slots=True)
class _RetirementCandidate:
    node: object
    identity: tuple


def _candidate(handles):
    """Qualify only the incumbent socket profile; never infer listener ownership."""
    _require_retained_absent(handles)
    states = namespace._leaf_states(handles)
    if all(value is None for value in states):
        namespace._require_socket_absent(handles)
        return None
    node = namespace._observe_socket_node(handles)
    states = namespace._leaf_states(handles)
    if any(value is None or getattr(value, 'st_flags', None) != 0
           or namespace.peer._object_identity(value) != node.identity for value in states):
        _refuse('BROKER_MAINTENANCE_SOCKET_GENERATION_DRIFT')
    namespace._require_same_socket(handles, node)
    return _RetirementCandidate(node, node.identity + (0,))


def _preserved_identity(info):
    # Darwin rename may advance ctime. Every other qualified property must be
    # identical; the new ctime is then pinned through the final readback.
    return namespace.peer._object_identity(info)[:8] + (info.st_flags,)


def _require_no_retained_acl(handles):
    """Same native no-follow socket ACL contract, only the fixed retained leaf."""
    _parent(handles)
    budget = handles.budget
    acl = None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        acquire, free = libc.acl_get_link_np, libc.acl_free
        acquire.argtypes = [ctypes.c_char_p, ctypes.c_int]
        acquire.restype = ctypes.c_void_p
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_int
        budget.check(force=True)
        ctypes.set_errno(0)
        acl = acquire((namespace._DIRECTORIES[-1] + '/' + _RETAINED).encode('ascii'),
                      namespace.ACL_TYPE_EXTENDED)
        observed_errno = ctypes.get_errno()
        budget.check(force=True)
        if acl or observed_errno != errno.ENOENT:
            _refuse('BROKER_MAINTENANCE_RETAINED_ACL_UNPROVEN')
    finally:
        if acl:
            if free(acl) != 0:
                _refuse('BROKER_MAINTENANCE_RETAINED_ACL_CLEANUP_UNPROVEN')
    budget.check(force=True)


def _retire(handles, candidate):
    """One native no-replace rename; caller marks uncertainty BEFORE invoking.

    No exception authorizes rollback, unlink or a second rename. A retained node
    or uncertain result must be reconciled on the original operation by its owner.
    """
    if type(candidate) is not _RetirementCandidate:
        _refuse('BROKER_MAINTENANCE_SOCKET_CANDIDATE_REFUSED')
    parent = _parent(handles)
    _require_retained_absent(handles)
    current = _candidate(handles)
    if current != candidate:
        _refuse('BROKER_MAINTENANCE_SOCKET_GENERATION_DRIFT')
    handles.budget.check(force=True)
    # Existing native descriptor-relative RENAME_EXCL; no replace/copy/delete
    # fallback, and no caller-provided paths or destination are accepted.
    _rename_exclusive(parent.descriptor, namespace._LEAF, parent.descriptor, _RETAINED)
    handles.budget.check(force=True)
    handles.budget.call(os.fsync, parent.descriptor)
    namespace._require_socket_absent(handles)
    retained = _retained_state(handles)
    expected = candidate.identity[:8] + (candidate.identity[-1],)
    if (retained is None or not stat.S_ISSOCK(retained.st_mode)
            or _preserved_identity(retained) != expected):
        _refuse('BROKER_MAINTENANCE_RETAINED_SOCKET_MISMATCH')
    identity = namespace._metadata_identity(retained)
    _require_no_retained_acl(handles)
    namespace._recheck_namespace(handles)
    final = _retained_state(handles)
    if final is None or namespace._metadata_identity(final) != identity:
        _refuse('BROKER_MAINTENANCE_RETAINED_SOCKET_CHANGED')
    namespace._require_socket_absent(handles)
    return identity


def _recheck_retained(handles, identity):
    current = _retained_state(handles)
    if current is None or namespace._metadata_identity(current) != identity:
        _refuse('BROKER_MAINTENANCE_RETAINED_SOCKET_CHANGED')
    _require_no_retained_acl(handles)
    final = _retained_state(handles)
    if final is None or namespace._metadata_identity(final) != identity:
        _refuse('BROKER_MAINTENANCE_RETAINED_SOCKET_CHANGED')
    namespace._require_socket_absent(handles)
