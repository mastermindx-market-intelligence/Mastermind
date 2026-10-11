"""Shared Darwin process-instance observation; no role or effect authority."""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import sys

from control_plane.executive_peer_identity import PeerIdentityError

class _ProcUniqueIdentifierInfo(ctypes.Structure):
    """Darwin PROC_PIDUNIQIDENTIFIERINFO ABI, fixed at 56 bytes.

    Apple XNU f6217f891ac0bb64f3d375211650a4c1ff8ca1ea,
    bsd/sys/proc_info_private.h. Kernel lineage is observation only; callers
    independently bind their service or OHF authority.
    """

    _fields_ = [
        ("p_uuid", ctypes.c_ubyte * 16),
        ("p_uniqueid", ctypes.c_uint64),
        ("p_puniqueid", ctypes.c_uint64),
        ("p_idversion", ctypes.c_int32),
        ("p_orig_ppidversion", ctypes.c_int32),
        ("p_reserve2", ctypes.c_uint64),
        ("p_reserve3", ctypes.c_uint64),
    ]


@dataclass(frozen=True, slots=True)
class _ProcessInstanceObservation:
    """Kernel process/exec identity only; neither peer nor effect authority."""

    unique_id: int
    pidversion: int
    parent_unique_id: int | None = None
    parent_pidversion: int | None = None


def _observe_process_instance(pid: int) -> _ProcessInstanceObservation:
    """Read one internally supplied PID; production role wiring is separate.

    This private primitive does not qualify a service or replace the existing
    socket audit-token observer. Each call reads a fresh kernel result.
    """
    if type(pid) is not int or not 0 < pid <= (1 << 31) - 1:
        raise PeerIdentityError("SERVICE_PROCESS_PID_INVALID")
    if sys.platform != "darwin":
        raise PeerIdentityError("PEER_PLATFORM_UNSUPPORTED")
    try:
        if ctypes.sizeof(_ProcUniqueIdentifierInfo) != 56 or ctypes.sizeof(ctypes.c_int) != 4:
            raise PeerIdentityError("SERVICE_PROCESS_ABI_UNSUPPORTED")
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        query = library.proc_pidinfo
        query.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
            ctypes.c_void_p, ctypes.c_int,
        ]
        query.restype = ctypes.c_int
        observed = _ProcUniqueIdentifierInfo()
        ctypes.set_errno(0)
        size = query(pid, 17, 0, ctypes.byref(observed), 56)
    except PeerIdentityError:
        raise
    except Exception:
        raise PeerIdentityError("SERVICE_PROCESS_OBSERVATION_UNAVAILABLE") from None
    if type(size) is not int or size != 56:
        raise PeerIdentityError("SERVICE_PROCESS_OBSERVATION_SIZE_INVALID")
    if observed.p_uniqueid <= 0 or observed.p_idversion <= 0:
        raise PeerIdentityError("SERVICE_PROCESS_IDENTITY_INVALID")
    return _ProcessInstanceObservation(
        observed.p_uniqueid, observed.p_idversion, observed.p_puniqueid or None,
        observed.p_orig_ppidversion if observed.p_orig_ppidversion > 0 else None,
    )


