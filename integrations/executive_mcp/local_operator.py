"""Local operator mode (L4): a Unix-socket door admitted by kernel peer uid.

Off unless the installed Executive config carries a ``local_operator`` block.
The public tunnel reaches the Executive only over loopback TCP, so loopback
source or request headers can never carry admission here: the only admission
fact is the connected socket's kernel peer uid (getpeereid(2)).
"""
from __future__ import annotations

import ctypes
import dataclasses
from pathlib import Path


class LocalOperatorConfigError(ValueError):
    """Malformed local-operator block; no socket may be created."""


@dataclasses.dataclass(frozen=True)
class LocalOperatorConfig:
    socket_path: Path
    allowed_uids: tuple[int, ...]
    operator_subject: str


def parse_local_operator_config(block: object) -> LocalOperatorConfig | None:
    """Parse the config block; absent stays off, malformed fails closed."""
    if block is None:
        return None
    keys = {"socket_path", "allowed_uids", "operator_subject"}
    if type(block) is not dict or set(block) != keys:
        raise LocalOperatorConfigError("local_operator block keys differ")
    path = block["socket_path"]
    if type(path) is not str or not path or "\x00" in path or not path.startswith("/"):
        raise LocalOperatorConfigError("local_operator socket_path must be absolute")
    uids = block["allowed_uids"]
    if (type(uids) is not list or not uids
            or any(type(uid) is not int or isinstance(uid, bool) or uid < 0 for uid in uids)
            or len(set(uids)) != len(uids)):
        raise LocalOperatorConfigError("local_operator allowed_uids must be a non-empty int list")
    subject = block["operator_subject"]
    if (type(subject) is not str or not subject or len(subject) > 128
            or subject != subject.strip() or any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in subject)):
        raise LocalOperatorConfigError("local_operator operator_subject is invalid")
    return LocalOperatorConfig(Path(path), tuple(uids), subject)


def peer_uid(sock: object) -> int:
    """Kernel credential of the connected peer via getpeereid(2)."""
    direct = getattr(sock, "getpeereid", None)
    if callable(direct):
        uid, _gid = direct()
        return int(uid)
    libc = ctypes.CDLL(None, use_errno=True)
    uid, gid = ctypes.c_uint32(0), ctypes.c_uint32(0)
    if libc.getpeereid(ctypes.c_int(sock.fileno()), ctypes.byref(uid), ctypes.byref(gid)) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, f"getpeereid failed: {errno}")
    return int(uid.value)
