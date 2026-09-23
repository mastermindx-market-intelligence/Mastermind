"""Requires the companion isolated CCR lifecycle integration patch."""
import asyncio
import socket
import threading
import time
from urllib.request import Request, urlopen

import pytest

from control_plane.workspace_control_room_lifecycle import HostedControlRoom, ControlRoomDrainUnavailable
from scripts import chairman_control_room as ccr


def config(tmp_path, *, port=0, ttl=.1):
    return ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
        token="fixture", origin="http://127.0.0.1:0", port=port, state_ttl=ttl)


def doc():
    return {"schema": "mastermind.chairman_control_room.v1", "generated_at": "2026-09-21T00:00:00Z",
            "work": [], "autonomy": {"generated_at": "2026-09-21T00:00:00Z", "responsibilities": []}}


def test_occupied_bind_refuses_without_composition(tmp_path, monkeypatch):
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *a, **k: pytest.fail("composition"))
    with socket.socket() as incumbent:
        incumbent.bind(("127.0.0.1", 0)); incumbent.listen()
        owner = config(tmp_path, port=incumbent.getsockname()[1])
        host = HostedControlRoom(owner)
        with pytest.raises(OSError): asyncio.run(host.start())
        assert host.current_owner() is None and owner.state_cache == {} and owner.state_published_seq == 0


def test_shared_owner_refresh_off_request_and_shutdown(tmp_path, monkeypatch):
    compositions = []
    def compose(*args, **kwargs):
        compositions.append(True)
        return doc()
    monkeypatch.setattr(ccr, "_compose_state_doc", compose)
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    async def run():
        host = HostedControlRoom(config(tmp_path, ttl=1))
        await host.start()
        try:
            assert host.current_owner() is host.config is host._server.config
            assert host.config.state_published_seq == 1 and len(compositions) == 1
            # Both the UI and workspace reference the same existing server cache.
            await asyncio.to_thread(lambda: urlopen(Request(host.config.origin + "/api/state", headers={"Origin": host.config.origin, "X-CCR-Token": host.config.token})).read())
            assert len(compositions) == 1
            assert host.config.workspace_refresh_on_read is False
        finally:
            await host.close()
        assert host.current_owner() is None
        assert not host.config.state_refresh_threads
        assert not host._refresh_thread.is_alive()
    asyncio.run(run())


def test_refresh_error_retains_publication_then_next_refresh_recovers(tmp_path, monkeypatch):
    calls = []
    def compose(*a, **k):
        calls.append(True)
        if len(calls) == 2: raise ValueError("fixture refresh failure")
        return doc()
    monkeypatch.setattr(ccr, "_compose_state_doc", compose)
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    async def run():
        host = HostedControlRoom(config(tmp_path))
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
        finally: await host.close()
    asyncio.run(run())


def test_shutdown_drain_deadline_retains_owner_until_actual_completion(tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()
    count = [0]
    def compose(*args, **kwargs):
        count[0] += 1
        if count[0] > 1:
            started.set()
            assert release.wait(5)
        return doc()
    monkeypatch.setattr(ccr, "_compose_state_doc", compose)
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    async def run():
        host = HostedControlRoom(config(tmp_path), shutdown_timeout=.1)
        await host.start()
        assert await asyncio.to_thread(started.wait, 3)
        start = time.monotonic()
        try:
            with pytest.raises(ControlRoomDrainUnavailable): await host.close()
            assert time.monotonic() - start < 1
            assert host._server is not None and host.config.state_stopping
            assert host.current_owner() is None
        finally:
            release.set()
            await host.close()
        assert not host.config.state_refresh_threads and host._server is None
    asyncio.run(run())
