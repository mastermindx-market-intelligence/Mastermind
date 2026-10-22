"""Trusted factory wiring over one live cache; the only listener is the
fixture's own short-lived AF_UNIX socket (no installed grant)."""
import asyncio
import copy
import os
import socket
import stat

import pytest

from common.workspace_control_room_read_contract import FRAME_SCHEMA
import control_plane.workspace_control_room_lifecycle as lifecycle_mod
from control_plane.workspace_control_room_lifecycle import HostedControlRoom
from control_plane.workspace_read_service import workspace_provider_factory
from scripts import chairman_control_room as ccr
from scripts.chairman_control_room import UNIX_CONTROL_ROOM_ORIGIN
from tests.executive_installed_control_fixture import unix_listener
from tests.test_workspace_control_room_presenter import owner, principal
from tests.test_workspace_read_service import cache_fixture


@pytest.fixture
def room_socket():
    listener, path = unix_listener()
    try:
        yield listener, path
    finally:
        listener.close()
        try:
            os.unlink(path)
        except OSError:
            pass
        try:
            os.rmdir(os.path.dirname(path))
        except OSError:
            pass


@pytest.fixture
def hosted(tmp_path, monkeypatch, room_socket):
    listener, path = room_socket
    owners, clock, _ = cache_fixture(tmp_path)
    baseline = copy.deepcopy(owners[0].state_cache["doc"])
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *_a, **_k: copy.deepcopy(baseline))
    monkeypatch.setattr(ccr.capability, "census", lambda **_k: {})
    # Fixture-only custody seam: the trusted socket-parent uid accepts this
    # test's short AF_UNIX listener, exactly as the lifecycle tests do. The
    # protected constructor refuses TCP and loopback configurations itself,
    # so the removed ControlRoomServer presenter guard is not re-created here.
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
    cfg = ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
                           token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0,
                           state_ttl=60)
    cfg.validity_sample_fn = lambda: tuple(clock)
    host = HostedControlRoom(cfg, listener=listener, socket_path=path,
                             allowed_peer_uids=(os.geteuid(),))
    try:
        yield host, baseline
    finally:
        # The tests close the started owner themselves; a host whose start
        # never happened has no server to drain.
        if host._server is not None:
            asyncio.run(host.close())


def provider(host, **kwargs):
    return workspace_provider_factory(
        control_room=host, authorize=owner({"fixture-web"}),
        armed={}, runtime_identity={}, **kwargs,
    )


def frame(operation):
    return {"schema": FRAME_SCHEMA, "operation": operation, "principal": principal()}


def test_factory_keeps_discovery_dark_and_state_bound_to_live_owner(hosted, monkeypatch):
    host, baseline = hosted
    monkeypatch.setattr(ccr, "_discover_document", lambda *_: pytest.fail("discovery denied"))
    service = provider(host)(object())

    async def exercise():
        assert (await service.handle_frame(frame("state")))["status"] == 503
        await host.start()
        try:
            result = await service.handle_frame(frame("state"))
            assert result["ok"] and result["result"]["control_room"] == baseline
            assert (await service.handle_frame(frame("discover")))["status"] == 403
            assert host.config.state_published_seq == 1
        finally:
            await host.close()
        assert (await service.handle_frame(frame("state")))["status"] == 503

    asyncio.run(exercise())


def test_factory_threads_distinct_discovery_owner_to_same_cache(hosted, room_socket, monkeypatch):
    host, _ = hosted
    listener, path = room_socket
    calls = []
    monkeypatch.setattr(
        ccr, "_discover_document", lambda cfg: calls.append(cfg) or {"candidates": []},
    )
    provide = provider(host, authorize_discovery=owner({"fixture-web"}))
    first, second = provide(object()), provide(object())

    async def exercise():
        await host.start()
        try:
            for service in (first, second):
                assert await service.handle_frame(frame("discover")) == {
                    "ok": True, "result": {"candidates": []},
                }
            assert calls == [host.config, host.config]
            assert host.config.state_published_seq == 1
            # Moved assertion: a cache_only room kept _server None; the hosted
            # room now runs its real presenter on this fixture's AF_UNIX
            # listener — same config, same cache, never TCP. The TCP-presenter
            # refusal itself moved into the protected constructor and is owned
            # by the lifecycle tests.
            assert host._server is not None and host._server.config is host.config
            assert host.config.port == 0
            assert host._server_thread is not None and host._server_thread.is_alive()
            assert listener.family == socket.AF_UNIX and listener.getsockname() == path
            assert stat.S_ISSOCK(os.stat(path).st_mode)
        finally:
            await host.close()
        assert (await first.handle_frame(frame("discover")))["status"] == 503

    asyncio.run(exercise())


def test_factory_rejects_noncallable_discovery_owner(hosted):
    host, _ = hosted
    with pytest.raises(ValueError, match="discovery authority must be a callback"):
        provider(host, authorize_discovery=True)


def test_factory_never_promotes_unstamped_discovery_permission(hosted, monkeypatch):
    host, _ = hosted
    monkeypatch.setattr(ccr, "_discover_document", lambda *_: pytest.fail("discovery denied"))
    service = provider(host, authorize_discovery=lambda _p: True)(object())

    async def exercise():
        await host.start()
        try:
            assert (await service.handle_frame(frame("discover")))["status"] == 403
        finally:
            await host.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("change,status", [("revoked", 403), ("stamp_changed", 503)])
def test_factory_rechecks_discovery_owner_after_source_work(hosted, monkeypatch, change, status):
    host, _ = hosted
    allowed = {"fixture-web"}
    discovery = owner(allowed)
    stamp = ["d" * 64]
    discovery.binding_digest = lambda p: stamp[0] if discovery(p) else None
    calls = []

    def discover(cfg):
        calls.append(cfg)
        if change == "revoked":
            allowed.clear()
        else:
            stamp[0] = "e" * 64
        return {"candidates": [{"private": "must not be released"}]}

    monkeypatch.setattr(ccr, "_discover_document", discover)
    service = provider(host, authorize_discovery=discovery)(object())

    async def exercise():
        await host.start()
        try:
            result = await service.handle_frame(frame("discover"))
            assert result["status"] == status
            assert "private" not in str(result)
            assert calls == [host.config]
        finally:
            await host.close()

    asyncio.run(exercise())
