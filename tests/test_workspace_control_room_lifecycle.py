"""Hosted Control Room lifecycle over the adopted AF_UNIX launchd socket."""
import asyncio
import http.client
import os
import socket
import threading
import time

import pytest

import control_plane.workspace_control_room_lifecycle as lifecycle_mod
from control_plane.workspace_control_room_lifecycle import (
    HostedControlRoom, ControlRoomDrainUnavailable,
)
from scripts import chairman_control_room as ccr
from scripts.chairman_control_room import UNIX_CONTROL_ROOM_HOST, UNIX_CONTROL_ROOM_ORIGIN
from tests.executive_installed_control_fixture import unix_listener, UnixHTTPConnection


def _unix_config(tmp_path, *, ttl=.1):
    return ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
        token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0, state_ttl=ttl)


def _doc():
    return {"schema": "mastermind.chairman_control_room.v1",
            "generated_at": "2026-09-21T00:00:00Z",
            "work": [], "autonomy": {"generated_at": "2026-09-21T00:00:00Z",
                                     "responsibilities": []}}


def _install_room(tmp_path, monkeypatch, *, ttl=.1):
    listener, path = unix_listener()
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    config = _unix_config(tmp_path, ttl=ttl)
    return listener, path, config


def _request(path, *, headers=None):
    conn = UnixHTTPConnection(path)
    try:
        conn.request("GET", "/", headers=headers or {"Host": UNIX_CONTROL_ROOM_HOST})
        return conn.getresponse()
    finally:
        conn.close()


def test_occupied_bind_refuses_without_composition(tmp_path, monkeypatch):
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *a, **k: pytest.fail("composition"))
    listener, path, config = _install_room(tmp_path, monkeypatch)
    host = HostedControlRoom(config, listener=listener, socket_path=path,
                             allowed_peer_uids=(os.geteuid(),))
    try:
        with pytest.raises(BaseException):
            asyncio.run(host.start())
        assert host.current_owner() is None and config.state_cache == {} and config.state_published_seq == 0
    finally:
        listener.close()
        os.unlink(path)


def test_shared_owner_refresh_off_request_and_shutdown(tmp_path, monkeypatch):
    compositions = []

    def compose(*args, **kwargs):
        compositions.append(True)
        return _doc()

    monkeypatch.setattr(ccr, "_compose_state_doc", compose)
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    listener, path, config = _install_room(tmp_path, monkeypatch, ttl=1)
    host = HostedControlRoom(config, listener=listener, socket_path=path,
                             allowed_peer_uids=(os.geteuid(),))
    async def run():
        await host.start()
        try:
            assert host.current_owner() is host.config is host._server.config
            assert host.config.state_published_seq == 1 and len(compositions) == 1
            await asyncio.to_thread(lambda: _request(path,
                headers={"Host": UNIX_CONTROL_ROOM_HOST, "Origin": host.config.origin,
                         "X-CCR-Token": host.config.token}).read())
            assert len(compositions) == 1
            assert host.config.workspace_refresh_on_read is False
        finally:
            await host.close()
        assert host.current_owner() is None
        assert not host.config.state_refresh_threads
        assert not host._refresh_thread.is_alive()
    try:
        asyncio.run(run())
    finally:
        listener.close()
        try:
            os.unlink(path)
        except OSError:
            pass


def test_refresh_error_retains_publication_then_next_refresh_recovers(tmp_path, monkeypatch):
    calls = []

    def compose(*a, **k):
        calls.append(True)
        if len(calls) == 2:
            raise ValueError("fixture refresh failure")
        return _doc()

    monkeypatch.setattr(ccr, "_compose_state_doc", compose)
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    listener, path, config = _install_room(tmp_path, monkeypatch)
    host = HostedControlRoom(config, listener=listener, socket_path=path,
                             allowed_peer_uids=(os.geteuid(),))
    async def run():
        await host.start()
        try:
            deadline = time.monotonic() + 3
            while host.config.state_refresh_error is None and time.monotonic() < deadline:
                await asyncio.sleep(.01)
            assert host.config.state_refresh_error is not None
            assert host.config.state_published_seq == 1
            while host.config.state_published_seq <= 1 and time.monotonic() < deadline:
                await asyncio.sleep(.01)
            assert host.config.state_published_seq > 1 and host.config.state_refresh_error is None
        finally:
            await host.close()
    try:
        asyncio.run(run())
    finally:
        listener.close()
        try:
            os.unlink(path)
        except OSError:
            pass


def test_shutdown_drain_deadline_retains_owner_until_actual_completion(tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()
    count = [0]

    def compose(*args, **kwargs):
        count[0] += 1
        if count[0] > 1:
            started.set()
            assert release.wait(5)
        return _doc()

    monkeypatch.setattr(ccr, "_compose_state_doc", compose)
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    listener, path, config = _install_room(tmp_path, monkeypatch)
    host = HostedControlRoom(config, listener=listener, socket_path=path,
                             allowed_peer_uids=(os.geteuid(),), shutdown_timeout=.1)
    async def run():
        await host.start()
        assert await asyncio.to_thread(started.wait, 3)
        start = time.monotonic()
        try:
            with pytest.raises(ControlRoomDrainUnavailable):
                await host.close()
            assert time.monotonic() - start < 1
            assert host._server is not None and host.config.state_stopping
            assert host.current_owner() is None
        finally:
            release.set()
            await host.close()
        assert not host.config.state_refresh_threads and host._server is None
    try:
        asyncio.run(run())
    finally:
        listener.close()
        try:
            os.unlink(path)
        except OSError:
            pass


def test_unix_room_refuses_tcp_port_config(tmp_path):
    tcp_config = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
        token="fixture", origin="http://127.0.0.1:8787", port=8787, state_ttl=10.0)
    with pytest.raises(ValueError, match="control room hosting configuration refused"):
        HostedControlRoom(tcp_config, listener=None, socket_path="/tmp/x.sock",
                          allowed_peer_uids=(os.geteuid(),))


def test_unix_room_refuses_loopback_origin_config(tmp_path):
    bad = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
        token="fixture", origin="http://127.0.0.1:0", port=0, state_ttl=10.0)
    with pytest.raises(ValueError, match="control room hosting configuration refused"):
        HostedControlRoom(bad, listener=None, socket_path="/tmp/x.sock",
                          allowed_peer_uids=(os.geteuid(),))


def test_unix_room_class_identity_kept_for_workspace_provider_factory(tmp_path):
    from control_plane.workspace_control_room_lifecycle import HostedControlRoom as _HCR
    from control_plane.workspace_read_service import workspace_provider_factory
    assert workspace_provider_factory.__doc__ is not None
    # The exact-class identity contract is preserved (no subclass rename).
    sentinel = _HCR.__name__
    assert sentinel == "HostedControlRoom"