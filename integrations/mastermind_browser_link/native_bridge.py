"""Chrome-owned, profile-bound forwarding process for Browser Link.

No listener, lease, retry, action store, command execution, or browser launch is
owned here. The incumbent Workbench relay is the server. Every new native port
must qualify its exact installed enrollment and extension origin.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import select
import socket
import stat
import struct
import sys
import time
from typing import Any

from integrations.chairman_surfaces.web_sol_native_host import _raw_binary_stream
from .native_channel import (
    Deadline, LinkEnrollment, LinkProtocolError, NativeHostError, READY_SCHEMA,
    read_frame, write_frame, validate_hello, validate_owner_message,
    validate_extension_message,
)


def require_peer_uid(connection: socket.socket, uid: int) -> None:
    """Kernel peer identity, never a peer-supplied JSON identity."""
    try:
        if sys.platform == "darwin":
            # Same libc getpeereid ABI used by the incumbent worker broker.
            getpeereid = ctypes.CDLL(None, use_errno=True).getpeereid
            getpeereid.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
            getpeereid.restype = ctypes.c_int
            peer_uid_value, peer_gid_value = ctypes.c_uint(), ctypes.c_uint()
            if getpeereid(connection.fileno(), ctypes.byref(peer_uid_value), ctypes.byref(peer_gid_value)) != 0:
                raise LinkProtocolError("LINK_PEER_UNAVAILABLE")
            peer_uid = int(peer_uid_value.value)
        elif sys.platform.startswith("linux"):
            _pid, peer_uid, _gid = struct.unpack(
                "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
        else:
            raise LinkProtocolError("LINK_PEER_UNAVAILABLE")
        if peer_uid != uid:
            raise LinkProtocolError("LINK_PEER_CHANGED")
    except OSError as exc:
        raise LinkProtocolError("LINK_PEER_UNAVAILABLE") from exc


def private_parent(path: Path, uid: int) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise LinkProtocolError("LINK_PARENT_UNAVAILABLE") from exc
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) & 0o077:
        raise LinkProtocolError("LINK_PARENT_UNSAFE")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise LinkProtocolError("LINK_ENROLLMENT_INVALID")
        result[key] = value
    return result


def _constant(_value):
    raise LinkProtocolError("LINK_ENROLLMENT_INVALID")


def load_enrollment(path: Path, *, owner_uid: int | None = None) -> LinkEnrollment:
    uid = os.geteuid() if owner_uid is None else owner_uid
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise LinkProtocolError("LINK_ENROLLMENT_INVALID")
    private_parent(path.parent, uid)
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 16384):
            raise LinkProtocolError("LINK_ENROLLMENT_UNSAFE")
        raw = os.read(fd, 16385)
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino) or len(raw) > 16384:
            raise LinkProtocolError("LINK_ENROLLMENT_CHANGED")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        return LinkEnrollment.from_document(value)
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        raise LinkProtocolError("LINK_ENROLLMENT_INVALID") from exc
    finally:
        if fd is not None:
            os.close(fd)


def connect_owner(enrollment: LinkEnrollment, *, timeout: float = 5.0) -> socket.socket:
    enrollment.__post_init__()
    path, uid = enrollment.socket_path, os.geteuid()
    private_parent(path.parent, uid)
    try:
        before = path.lstat()
    except OSError as exc:
        raise LinkProtocolError("LINK_OWNER_UNAVAILABLE") from exc
    if not stat.S_ISSOCK(before.st_mode) or before.st_uid != uid or stat.S_IMODE(before.st_mode) != 0o600:
        raise LinkProtocolError("LINK_OWNER_UNSAFE")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout)
        connection.connect(str(path))
        require_peer_uid(connection, uid)
        after = path.lstat()
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            raise LinkProtocolError("LINK_OWNER_CHANGED")
        return connection
    except BaseException:
        connection.close()
        raise


def run_bridge(
    source, destination, *, enrollment: LinkEnrollment, caller_origin: str,
    connect=connect_owner, monotonic=time.monotonic,
) -> None:
    if type(enrollment) is not LinkEnrollment:
        raise LinkProtocolError("LINK_ENROLLMENT_INVALID")
    enrollment.__post_init__()
    if caller_origin != f"chrome-extension://{enrollment.extension_id}/":
        raise LinkProtocolError("LINK_ORIGIN_REFUSED")
    hello = validate_hello(
        read_frame(source, deadline=Deadline(monotonic() + 5.0)), enrollment
    )
    generation = hello["connection_generation"]
    connection = connect(enrollment)
    try:
        with connection.makefile("rwb", buffering=0) as channel:
            deadline = Deadline(monotonic() + 5.0)
            write_frame(channel, hello, deadline=deadline)
            ready = validate_owner_message(read_frame(channel, deadline=deadline), generation)
            if ready["schema"] != READY_SCHEMA:
                raise LinkProtocolError("LINK_HANDSHAKE_REFUSED")
            write_frame(destination, ready, deadline=deadline)
            while True:
                ready_streams, _, _ = select.select([source, channel], [], [], 1.0)
                for stream in ready_streams:
                    deadline = Deadline(monotonic() + 5.0)
                    value = read_frame(stream, deadline=deadline)
                    if stream is source:
                        message = validate_extension_message(value, generation)
                        write_frame(channel, message, deadline=deadline)
                    else:
                        message = validate_owner_message(value, generation)
                        if message["schema"] == READY_SCHEMA:
                            raise LinkProtocolError("LINK_HANDSHAKE_REPLAY")
                        write_frame(destination, message, deadline=deadline)
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", required=True)
    parser.add_argument("origin")
    args = parser.parse_args(argv)
    try:
        enrollment = load_enrollment(Path(args.config))
        run_bridge(
            _raw_binary_stream(sys.stdin), _raw_binary_stream(sys.stdout),
            enrollment=enrollment, caller_origin=args.origin,
        )
    except (LinkProtocolError, NativeHostError, OSError, ValueError):
        return 65
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
