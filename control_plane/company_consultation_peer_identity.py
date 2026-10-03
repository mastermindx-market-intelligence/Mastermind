"""Request-local MCP child lineage checks; no dispatch or installed-service grant.

A numeric parent PID is only a lookup hint. Admission also requires the child
kernel parent unique ID to match the unchanged current OHF writer instance.
An exec completed before child creation is outside this lineage proof; the host
must separately qualify admission-time OHF executable/capability continuity.
"""
from __future__ import annotations

from control_plane.codex_worker import ProcessInspector
from control_plane.executive_process_identity import _observe_process_instance
from control_plane.executive_peer_identity import (
    PeerIdentity,
    PeerIdentityError,
    _current_capture,
)


def _child_observation(peer: PeerIdentity, inspector: ProcessInspector):
    _current_capture(peer)
    child = inspector.inspect(peer.pid)
    instance = _observe_process_instance(peer.pid)
    if (
        type(child.parent_pid) is not int
        or child.parent_pid <= 0
        or child.effective_uid != peer.euid
        or child.real_uid != peer.euid
        or instance.pidversion != peer.pidversion
        or type(instance.parent_unique_id) is not int
        or instance.parent_unique_id <= 0
        or type(instance.parent_pidversion) is not int
        or instance.parent_pidversion <= 0
    ):
        raise PeerIdentityError("CONSULT_CHILD_IDENTITY_UNAVAILABLE")
    _current_capture(peer)
    return child, instance


def immediate_parent_pid(peer: PeerIdentity, *, inspector: ProcessInspector) -> int:
    """Return a fresh lookup hint, never identity or effect authority."""
    try:
        first = _child_observation(peer, inspector)
        if _child_observation(peer, inspector) != first:
            raise PeerIdentityError("CONSULT_CHILD_IDENTITY_CHANGED")
        return first[0].parent_pid
    except PeerIdentityError:
        raise
    except Exception:
        raise PeerIdentityError("CONSULT_PROCESS_OBSERVATION_UNAVAILABLE") from None


def require_current_writer_parent(
    peer: PeerIdentity,
    *,
    writer_pid: int,
    writer_pgid: int,
    writer_start_identity: str,
    writer_boot_id: str,
    inspector: ProcessInspector,
) -> None:
    """Check a Runtime-selected writer against this connected direct child.

    The caller must obtain writer facts from the current Runtime snapshot and
    repeat both that projection and this check at the dispatch boundary. This
    function issues no reusable credential or context and performs no effect.
    """
    if (
        type(writer_pid) is not int or writer_pid <= 0
        or type(writer_pgid) is not int or writer_pgid <= 0
        or type(writer_start_identity) is not str or not writer_start_identity
        or type(writer_boot_id) is not str or not writer_boot_id
    ):
        raise PeerIdentityError("CONSULT_WRITER_IDENTITY_REQUIRED")
    try:
        child = _child_observation(peer, inspector)
        writer = inspector.inspect(writer_pid)
        instance = _observe_process_instance(writer_pid)
        boot = inspector.boot_session_id()
        if (
            child[0].parent_pid != writer_pid
            or child[1].parent_unique_id != instance.unique_id
            or child[1].parent_pidversion != instance.pidversion
            or writer.start_identity != writer_start_identity
            or writer.pgid != writer_pgid
            or writer.effective_uid != peer.euid
            or writer.real_uid != peer.euid
            or boot != writer_boot_id
        ):
            raise PeerIdentityError("CONSULT_PARENT_WRITER_MISMATCH")
        if (
            _child_observation(peer, inspector) != child
            or inspector.inspect(writer_pid) != writer
            or _observe_process_instance(writer_pid) != instance
            or inspector.boot_session_id() != boot
        ):
            raise PeerIdentityError("CONSULT_PARENT_WRITER_CHANGED")
        _current_capture(peer)
    except PeerIdentityError:
        raise
    except Exception:
        raise PeerIdentityError("CONSULT_PROCESS_OBSERVATION_UNAVAILABLE") from None
