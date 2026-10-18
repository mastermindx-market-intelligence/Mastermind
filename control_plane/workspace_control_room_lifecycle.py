"""Configured-only hosting of the canonical ControlRoomServer in control service.

Uses the existing ServerConfig/cache/publisher/HTTP server. No new acquisition,
permission, namespace, or publication authority is introduced. Requires the
accompanying narrow CCR refresh-handle patch; installation belongs to the host.
"""
from __future__ import annotations

import asyncio
from control_plane.workspace_owned_task import await_owned
import math
import secrets
import threading
import time


def _workspace_instance_locked(owner):
    """Reuse the actual ServerConfig identity; caller holds its state_lock."""
    instance = getattr(owner, "_workspace_read_instance", None)
    if instance is None:
        instance = secrets.token_hex(32)
        setattr(owner, "_workspace_read_instance", instance)
    return instance


class ControlRoomDrainUnavailable(RuntimeError):
    pass


class HostedControlRoom:
    def __init__(self, config, *, shutdown_timeout=10.0, cache_only=False):
        from scripts.chairman_control_room import ServerConfig
        if (type(config) is not ServerConfig or config.port < 0 or config.port > 65535
                or type(shutdown_timeout) not in (int, float) or not 0.1 <= shutdown_timeout <= 30
                or type(config.state_ttl) not in (int, float) or not math.isfinite(config.state_ttl)
                or not 0.1 <= config.state_ttl <= 3600
                or type(cache_only) is not bool):
            raise ValueError("control room hosting configuration refused")
        self.config = config
        # Source-only prerequisite for separating the existing canonical cache
        # from its user-facing HTTP presentation. The privileged Control caller
        # is NOT switched to this mode by this candidate.
        self.cache_only = cache_only
        self._cache_active = False
        self.shutdown_timeout = shutdown_timeout
        self._server = None
        self._server_thread = None
        self._refresh_thread = None
        self._stop = threading.Event()

    def current_owner(self):
        if self._stop.is_set():
            return None
        if self.cache_only:
            return self.config if self._cache_active else None
        return self._server.config if self._server is not None else None

    def _start(self):
        from scripts.chairman_control_room import ControlRoomServer, ChairmanControlRoomHandler, HOST
        if self._server is not None or self._cache_active or self._stop.is_set():
            raise ValueError("control room owner cannot be reused")
        # Bind-before-precompose is the existing server constructor's ordering.
        # Occupancy refuses here without minting a published dummy cache.
        if self.config.state_published_seq or self.config.state_cache:
            raise ValueError("control room hosting requires a fresh owner")
        self.config.workspace_refresh_on_read = False
        if self.cache_only:
            # Exact existing compose/publish/cache owner, without creating a
            # Control-owned AF_INET listener. No second cache or read identity.
            from scripts.chairman_control_room import _precompose_initial_state
            _precompose_initial_state(self.config)
            self._cache_active = True
        else:
            self._server = ControlRoomServer((HOST, self.config.port), ChairmanControlRoomHandler, self.config)
            self.config.port = self._server.server_address[1]
            self.config.origin = f"http://{HOST}:{self.config.port}"
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
        self._cache_active = False

    async def close(self):
        task = asyncio.create_task(asyncio.to_thread(self._close))
        await await_owned(task)
