"""Configured-only hosting of the canonical ControlRoomServer in control service.

Uses the existing ServerConfig/cache/publisher/HTTP server. No new acquisition,
permission, namespace, or publication authority is introduced. Requires the
accompanying narrow CCR refresh-handle patch; installation belongs to the host.

S3 (CRROOM-CORE lane): the hosted room runs on an adopted AF_UNIX launchd
listener. No TCP construct remains in this file. The owning launchd listener
is verified for AF_UNIX/SOCK_STREAM, listening, path match, owner/mode,
and a non-restricted parent before the lifecycle ever starts, and again at
start() in case anyone tampered with the filesystem between construction
and serve.
"""
from __future__ import annotations

import asyncio
from control_plane.workspace_owned_task import await_owned
import math
import os
import socket
import stat
import threading
import time


# Test seam: production parent is root-owned and immutable. The constant is
# read at call time so a test can rebind control_plane.workspace_control_room_
# lifecycle._TRUSTED_SOCKET_PARENT_UID to os.geteuid() while it owns a tmp dir.
_TRUSTED_SOCKET_PARENT_UID = 0


class ControlRoomDrainUnavailable(RuntimeError):
    pass


class ControlRoomSocketRefused(ValueError):
    """Closed refusal codes for a malformed adopted launchd listener."""

    REASONS = (
        "not-unix-stream",
        "not-listening",
        "path-mismatch",
        "not-socket",
        "symlink",
        "owner",
        "group",
        "mode",
        "parent-not-dir",
        "parent-owner",
        "parent-writable",
    )

    def __init__(self, reason: str) -> None:
        if reason not in self.REASONS:
            raise ValueError("control room socket custody refused: unknown reason")
        super().__init__(f"control room socket custody refused: {reason}")


def _verify_socket_custody(listener, *, socket_path, expected_owner_uid, expected_gid,
                           trusted_parent_uid):
    """Verify the adopted AF_UNIX listener against a closed set of invariants.

    Raises ``ControlRoomSocketRefused`` with a stable reason code on any
    failure. The listener, its socket file, and its parent directory are
    checked; nothing is bound, listened on, or unlinked here.
    """
    if listener.family != socket.AF_UNIX or listener.type != socket.SOCK_STREAM:
        raise ControlRoomSocketRefused("not-unix-stream")
    from control_plane.executive_service import _require_listening_if_queryable
    try:
        _require_listening_if_queryable(listener)
    except Exception:
        raise ControlRoomSocketRefused("not-listening") from None
    listener_name = listener.getsockname()
    if isinstance(listener_name, bytes):
        listener_name = os.fsdecode(listener_name)
    listener_real_dir = os.path.realpath(os.path.dirname(listener_name))
    listener_real_path = os.path.join(listener_real_dir, os.path.basename(listener_name))
    expected_real_dir = os.path.realpath(os.path.dirname(socket_path))
    expected_real_path = os.path.join(expected_real_dir, os.path.basename(socket_path))
    if listener_real_path != expected_real_path:
        raise ControlRoomSocketRefused("path-mismatch")
    st = os.lstat(socket_path)
    if stat.S_ISLNK(st.st_mode):
        raise ControlRoomSocketRefused("symlink")
    if not stat.S_ISSOCK(st.st_mode):
        raise ControlRoomSocketRefused("not-socket")
    if st.st_uid != expected_owner_uid:
        raise ControlRoomSocketRefused("owner")
    if st.st_gid != expected_gid:
        raise ControlRoomSocketRefused("group")
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise ControlRoomSocketRefused("mode")
    parent_st = os.lstat(os.path.dirname(socket_path))
    if stat.S_ISLNK(parent_st.st_mode) or not stat.S_ISDIR(parent_st.st_mode):
        raise ControlRoomSocketRefused("parent-not-dir")
    if parent_st.st_uid != trusted_parent_uid:
        raise ControlRoomSocketRefused("parent-owner")
    if parent_st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ControlRoomSocketRefused("parent-writable")


class HostedControlRoom:
    def __init__(self, config, *, listener, socket_path, allowed_peer_uids,
                 shutdown_timeout=10.0, expected_owner_uid=None, expected_gid=None,
                 peer_uid_fn=None):
        from scripts.chairman_control_room import (
            ServerConfig, UnixControlRoomServer, UNIX_CONTROL_ROOM_ORIGIN,
        )
        if (type(config) is not ServerConfig
                or config.port != 0
                or config.origin != UNIX_CONTROL_ROOM_ORIGIN
                or type(shutdown_timeout) not in (int, float) or not 0.1 <= shutdown_timeout <= 30
                or type(config.state_ttl) not in (int, float) or not math.isfinite(config.state_ttl)
                or not 0.1 <= config.state_ttl <= 3600):
            raise ValueError("control room hosting configuration refused")
        if listener is None or socket_path is None or allowed_peer_uids is None:
            raise ValueError("control room hosting configuration refused")
        if (not isinstance(allowed_peer_uids, (tuple, list))
                or len(allowed_peer_uids) == 0
                or any((type(item) is not int or item is True or item is False)
                       for item in allowed_peer_uids)
                or len(set(allowed_peer_uids)) != len(allowed_peer_uids)):
            raise ValueError("control room hosting configuration refused")
        if expected_owner_uid is None:
            expected_owner_uid = os.geteuid()
        if expected_gid is None:
            expected_gid = os.getegid()
        if peer_uid_fn is None:
            from control_plane.executive_service import _peer_uid
            peer_uid_fn = _peer_uid
        _verify_socket_custody(
            listener, socket_path=socket_path,
            expected_owner_uid=expected_owner_uid, expected_gid=expected_gid,
            trusted_parent_uid=_TRUSTED_SOCKET_PARENT_UID)
        self.config = config
        self._listener = listener
        self.socket_path = str(socket_path)
        self.allowed_peer_uids = tuple(int(uid) for uid in allowed_peer_uids)
        self._peer_uid_fn = peer_uid_fn
        self.shutdown_timeout = shutdown_timeout
        self._server = None
        self._server_thread = None
        self._refresh_thread = None
        self._stop = threading.Event()

    def current_owner(self):
        if self._server is None or self._stop.is_set():
            return None
        return self._server.config

    def _start(self):
        from scripts.chairman_control_room import (
            ChairmanControlRoomHandler, UnixControlRoomServer,
        )
        if self._server is not None or self._stop.is_set():
            raise ValueError("control room owner cannot be reused")
        # Bind-before-precompose is the existing server constructor's ordering.
        # Occupancy refuses here without minting a published dummy cache.
        if self.config.state_published_seq or self.config.state_cache:
            raise ValueError("control room hosting requires a fresh owner")
        # Fail closed: re-check the adopted socket between construction and
        # any serve_forever() loop, in case anyone mutated the filesystem.
        _verify_socket_custody(
            self._listener, socket_path=self.socket_path,
            expected_owner_uid=os.geteuid(), expected_gid=os.getegid(),
            trusted_parent_uid=_TRUSTED_SOCKET_PARENT_UID)
        self.config.workspace_refresh_on_read = False
        self._server = UnixControlRoomServer(
            self._listener, ChairmanControlRoomHandler, self.config,
            allowed_peer_uids=self.allowed_peer_uids,
            peer_uid_fn=self._peer_uid_fn)
        self._server_thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.05),
            name="workspace-canonical-control-room", daemon=True)
        self._server_thread.start()
        self._refresh_thread = threading.Thread(target=self._refresh, name="workspace-control-room-refresh", daemon=True)
        self._refresh_thread.start()

    def _refresh(self):
        from scripts.chairman_control_room import _maybe_start_background_refresh
        while not self._stop.wait(min(self.config.state_ttl, 30.0)):
            _maybe_start_background_refresh(self.config)

    async def start(self):
        task = asyncio.create_task(asyncio.to_thread(self._start))
        try:
            await await_owned(task)
        except asyncio.CancelledError:
            # await_owned only releases cancellation after startup is terminal.
            # Cleanup cannot race unfinished server construction.
            await self.close()
            raise

    def _close(self):
        self._stop.set()
        with self.config.state_lock:
            self.config.state_stopping = True
        deadline = time.monotonic() + self.shutdown_timeout
        if self._server_thread is not None and self._server_thread.is_alive():
            self._server.shutdown()
        threads = [self._server_thread, self._refresh_thread]
        with self.config.state_lock:
            threads.extend(self.config.state_refresh_threads)
        for thread in threads:
            if thread is not None and thread is not threading.current_thread():
                thread.join(max(0, deadline - time.monotonic()))
        with self.config.state_lock:
            pending = any(thread.is_alive() for thread in self.config.state_refresh_threads)
        if pending or any(thread is not None and thread.is_alive() for thread in threads):
            # Retain owner and control-service Runtime custody on uncertainty.
            # Caller must not retire Runtime merely because listeners closed.
            raise ControlRoomDrainUnavailable("control room refresh drain unavailable")
        if self._server is not None:
            self._server.server_close()
            self._server = None

    async def close(self):
        task = asyncio.create_task(asyncio.to_thread(self._close))
        await await_owned(task)