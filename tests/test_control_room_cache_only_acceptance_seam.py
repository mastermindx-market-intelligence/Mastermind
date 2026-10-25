"""Hosted Control Room acceptance seam over the adopted AF_UNIX listener.

Migrated from the retired cache/listener split: the ``cache_only`` hosting
mode no longer exists, so every test now drives the protected
``HostedControlRoom`` lifecycle exactly as production does — an adopted
AF_UNIX launchd listener, the canonical UNIX origin, ``port == 0``,
``allowed_peer_uids`` custody, and the explicit
``_TRUSTED_SOCKET_PARENT_UID`` test seam. No TCP construct, no duplicate
cache, and no retired hosting-mode state remains. Nothing here grants
installed Control authority beyond the retired module's contract.
"""
import asyncio
import copy
import os
import shutil
import socket
import stat
import threading
import time
from pathlib import Path

import pytest

import control_plane.workspace_control_room_lifecycle as lifecycle_mod
from control_plane.workspace_control_room_lifecycle import (
    ControlRoomDrainUnavailable,
    HostedControlRoom,
)
from control_plane.workspace_read_service import ExistingControlRoomCache
from scripts import chairman_control_room as ccr
from scripts.chairman_control_room import UNIX_CONTROL_ROOM_ORIGIN
from tests.executive_installed_control_fixture import egid_socket_dir, unix_listener
from tests.test_workspace_read_service import cache_fixture, frame, service


def config(tmp_path, *, ttl=.1):
    """Protected hosting configuration: canonical UNIX origin, port 0."""
    return ccr.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
                            token="fixture", origin=UNIX_CONTROL_ROOM_ORIGIN, port=0,
                            state_ttl=ttl)


def doc():
    return {"schema": "mastermind.chairman_control_room.v1",
            "generated_at": "2026-09-21T00:00:00Z",
            "work": [], "autonomy": {"generated_at": "2026-09-21T00:00:00Z",
                                     "responsibilities": []}}


@pytest.fixture
def room_socket(monkeypatch):
    """A test-owned adopted AF_UNIX listener plus the custody seam patch.

    The trusted socket-parent uid is rebound for this process only through
    the explicit ``_TRUSTED_SOCKET_PARENT_UID`` seam; the custody checker and
    every other piece of production behavior stay untouched. Cleanup closes
    the listener, unlinks the socket file, and removes the short owned
    directory even when a test fails.
    """
    listener, path = unix_listener()
    monkeypatch.setattr(lifecycle_mod, "_TRUSTED_SOCKET_PARENT_UID", os.geteuid())
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
def short_socket_root():
    """A distinct short owned directory for the existing Executive ingress
    sockets, so no AF_UNIX path in this module can exceed the sun_path limit
    (the room's own listener lives in its own short directory)."""
    base = Path(egid_socket_dir("seam-ceo"))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_hosted_room_needs_no_tcp_bind_even_with_occupied_port(
        tmp_path, room_socket, monkeypatch):
    """An occupied TCP port stays irrelevant: the hosted room serves the
    already adopted AF_UNIX listener on the canonical UNIX origin with
    port 0 and never opens or binds a TCP construct of its own."""
    compositions = []
    monkeypatch.setattr(ccr, "_compose_state_doc",
                        lambda *_a, **_k: compositions.append(1) or doc())
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    listener, path = room_socket
    host = HostedControlRoom(config(tmp_path, ttl=10), listener=listener,
                             socket_path=path, allowed_peer_uids=(os.geteuid(),))
    assert host.current_owner() is None
    with socket.socket() as incumbent:
        incumbent.bind(("127.0.0.1", 0))
        incumbent.listen()
        occupied = incumbent.getsockname()[1]

        async def run():
            await host.start()
            try:
                assert host.current_owner() is host.config is host._server.config
                assert host.config.port == 0
                assert host.config.origin == UNIX_CONTROL_ROOM_ORIGIN
                assert listener.family == socket.AF_UNIX
                assert host.config.state_published_seq == 1 and len(compositions) == 1
                assert host.config.workspace_refresh_on_read is False
            finally:
                await host.close()
            assert host.current_owner() is None
            assert not host.config.state_refresh_threads
            # The reserved TCP port was never touched by the hosted room.
            assert incumbent.getsockname() == ("127.0.0.1", occupied)

        asyncio.run(run())


def test_hosted_room_shares_actual_server_config_owner_with_existing_cache(
        tmp_path, room_socket, monkeypatch):
    """The one cache is the source-owned ServerConfig identity shared with
    the serving owner; the read path snapshots it via
    ``ExistingControlRoomCache`` and never acquires the runtime. After close
    the same mirror refuses as ``source_unavailable``."""
    owners, clock, _ = cache_fixture(tmp_path)
    baseline = copy.deepcopy(owners[0].state_cache["doc"])
    monkeypatch.setattr(ccr, "_compose_state_doc",
                        lambda *_a, **_k: copy.deepcopy(baseline))
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    host_config = config(tmp_path, ttl=60)
    host_config.validity_sample_fn = lambda: tuple(clock)
    listener, path = room_socket
    host = HostedControlRoom(host_config, listener=listener, socket_path=path,
                             allowed_peer_uids=(os.geteuid(),))
    async def run():
        await host.start()
        try:
            assert host.current_owner() is host.config is host._server.config
            mirror = ExistingControlRoomCache(
                host.current_owner,
                monotonic=lambda: host.config.state_cache["composed_monotonic"] + .01)
            result = await service(
                mirror, acquire=lambda *_a, **_k: pytest.fail("runtime read"),
            ).handle_frame(frame("programs"))
            assert result["result"]["availability"] == "AVAILABLE"
            assert result["result"]["control_room"] == baseline
            assert host.config.state_published_seq == 1
        finally:
            await host.close()
        with pytest.raises(ValueError, match="source_unavailable"):
            mirror.snapshot()
        assert host.current_owner() is None
        assert not host.config.state_refresh_threads
    asyncio.run(run())


@pytest.mark.parametrize("value", ["false", 0, 1, None, True])
def test_retired_cache_only_kwarg_is_closed_for_every_value(
        tmp_path, room_socket, value):
    """The removed hosting mode is closed at the signature: every legacy
    ``cache_only`` value — including the previously accepted ``True`` — is
    refused before any custody or composition work happens."""
    listener, path = room_socket
    with pytest.raises(TypeError, match="cache_only"):
        HostedControlRoom(config(tmp_path, ttl=10), listener=listener,
                          socket_path=path, allowed_peer_uids=(os.geteuid(),),
                          cache_only=value)
    # The adopted listener was never consumed by the refused construction.
    assert listener.family == socket.AF_UNIX
    assert stat.S_ISSOCK(os.stat(path).st_mode)


def test_default_hosting_serves_the_real_af_unix_listener_owner(
        tmp_path, room_socket, monkeypatch):
    """Default construction (no retired mode kwarg) hosts the canonical
    server on the adopted AF_UNIX listener: a real server thread, the exact
    ServerConfig owner, port 0, canonical origin, and a 0600 socket file."""
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *_a, **_k: doc())
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    listener, path = room_socket
    host = HostedControlRoom(config(tmp_path, ttl=10), listener=listener,
                             socket_path=path, allowed_peer_uids=(os.geteuid(),))
    async def run():
        await host.start()
        try:
            assert host._server is not None and host._server_thread.is_alive()
            assert host.current_owner() is host._server.config
            assert host.config.port == 0
            assert host.config.origin == UNIX_CONTROL_ROOM_ORIGIN
            assert listener.family == socket.AF_UNIX
            assert listener.type == socket.SOCK_STREAM
            assert stat.S_ISSOCK(os.stat(path).st_mode)
            assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        finally:
            await host.close()
        assert host.current_owner() is None and host._server is None
        assert not host._server_thread.is_alive()
    asyncio.run(run())


def test_drain_keeps_owner_resources_until_refresh_joins(
        tmp_path, room_socket, monkeypatch):
    """A refresh producer still composing holds the protected owner
    resources (``_server``/``_server_thread`` and ``state_stopping``) across
    the refused drain, while ``current_owner()`` is already unavailable;
    once the producer joins, the second drain retires everything."""
    started, release = threading.Event(), threading.Event()
    calls = [0]

    def compose(*_a, **_k):
        calls[0] += 1
        if calls[0] > 1:
            started.set()
            assert release.wait(5)
        return doc()

    monkeypatch.setattr(ccr, "_compose_state_doc", compose)
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    listener, path = room_socket
    host = HostedControlRoom(config(tmp_path, ttl=.1), listener=listener,
                             socket_path=path, allowed_peer_uids=(os.geteuid(),),
                             shutdown_timeout=.1)
    async def run():
        await host.start()
        assert await asyncio.to_thread(started.wait, 3)
        try:
            with pytest.raises(ControlRoomDrainUnavailable):
                await host.close()
            assert host._server is not None and host._server_thread is not None
            assert host.config.state_stopping is True
            assert host.current_owner() is None
        finally:
            release.set()
            await host.close()
        assert host._server is None
        assert not host.config.state_refresh_threads
    asyncio.run(run())


def test_cancelled_startup_never_detaches_composition_and_drains_threads(
        tmp_path, room_socket, monkeypatch):
    """Cancelling ``start()`` while the first composition is still running
    cannot detach that composition: it runs to completion, then the
    cancellation surfaces and the lifecycle drains every thread it started."""
    started, release, completed = threading.Event(), threading.Event(), threading.Event()

    def compose(*_a, **_k):
        started.set()
        assert release.wait(5)
        completed.set()
        return doc()

    monkeypatch.setattr(ccr, "_compose_state_doc", compose)
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    listener, path = room_socket
    host = HostedControlRoom(config(tmp_path, ttl=10), listener=listener,
                             socket_path=path, allowed_peer_uids=(os.geteuid(),))
    async def run():
        task = asyncio.create_task(host.start())
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(.02)
        assert not task.done(), "the composition was still active"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert completed.is_set()
        assert host.current_owner() is None
        assert host._server is None
        assert host._server_thread is not None and not host._server_thread.is_alive()
        assert host._refresh_thread is not None and not host._refresh_thread.is_alive()
        assert not host.config.state_refresh_threads
    asyncio.run(run())


def test_failed_composition_never_yields_approved_workspace_read(
        tmp_path, room_socket, monkeypatch):
    """A composition failure leaves the hosted cache unqualified, so the
    snapshot-only read path refuses with the UNAVAILABLE envelope and a null
    control room — never an approved read, never a runtime acquisition, and
    never the private error text."""
    def compose(*_a, **_k):
        raise ValueError("private composition failure")

    monkeypatch.setattr(ccr, "_compose_state_doc", compose)
    monkeypatch.setattr(ccr.capability, "census", lambda **kwargs: {})
    listener, path = room_socket
    host = HostedControlRoom(config(tmp_path, ttl=60), listener=listener,
                             socket_path=path, allowed_peer_uids=(os.geteuid(),))
    async def run():
        await host.start()
        try:
            assert host.config.state_refresh_error is not None
            assert host.config.state_published_seq == 0
            assert host.config.state_cache == {}
            mirror = ExistingControlRoomCache(host.current_owner)
            result = await service(
                mirror, acquire=lambda *_a, **_k: pytest.fail("runtime read"),
            ).handle_frame(frame("programs"))
            assert result["result"]["availability"] == "UNAVAILABLE"
            assert result["result"]["control_room"] is None
            assert "private composition failure" not in str(result)
        finally:
            await host.close()
        assert host.current_owner() is None
    asyncio.run(run())


def test_actual_executive_service_workspace_socket_reuses_hosted_owner(
        tmp_path, short_socket_root, room_socket, monkeypatch):
    """Real service/ingress route over the hosted room: no Control-owned
    HTTP, no TCP construct, and no duplicate cache — the service's own
    runtime feeds the single source-owned ServerConfig cache."""
    from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from tests.test_executive_ceo_ingress import _FakeGrounding, _FakeSupervisor, _config
    from tests.test_workspace_read_service import service as workspace_service

    owners, clock, _ = cache_fixture(tmp_path)
    baseline = copy.deepcopy(owners[0].state_cache["doc"])
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *_a, **_k: copy.deepcopy(baseline))
    monkeypatch.setattr(ccr.capability, "census", lambda **k: {})
    host_config = config(tmp_path, ttl=30)
    host_config.validity_sample_fn = lambda: tuple(clock)
    listener, path = room_socket
    host = HostedControlRoom(host_config, listener=listener, socket_path=path,
                             allowed_peer_uids=(os.geteuid(),))
    reads = []

    def provider(runtime):
        # Runtime remains the service's existing exact owner; the only cache
        # is the source-owned ServerConfig visible through current_owner().
        cache = ExistingControlRoomCache(
            host.current_owner,
            monotonic=lambda: host.config.state_cache["composed_monotonic"] + .01,
        )
        value = workspace_service(cache)
        value.runtime = runtime
        reads.append(runtime)
        return value

    async def run():
        svc = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / 'ceo.sock',
            ceo_ingress_peer_uid=1000 + os.geteuid(),
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=False,
                grounding_provider=_FakeGrounding(),
                workspace_read_provider_factory=provider,
            ),
            workspace_control_room=host,
        )
        await svc.start()
        try:
            assert host.current_owner() is host.config
            assert host._server is not None and host._server.config is host.config
            assert host._server_thread is not None and host._server_thread.is_alive()
            assert host.config.port == 0
            assert host.config.origin == UNIX_CONTROL_ROOM_ORIGIN
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            answer = await client.request(frame('programs'))
            assert answer['result']['availability'] == 'AVAILABLE'
            assert answer['result']['control_room'] == baseline
            assert reads == [svc.runtime]
            assert host.config.state_published_seq == 1
        finally:
            await svc.close()
        assert host.current_owner() is None
        assert host._server is None
        assert host._server_thread is not None and not host._server_thread.is_alive()
        assert host._refresh_thread is not None and not host._refresh_thread.is_alive()
        assert not host.config.state_refresh_threads
    asyncio.run(run())


def test_actual_executive_app_socket_serves_one_signed_member_state_without_tcp(
        tmp_path, short_socket_root, room_socket, monkeypatch):
    """The real private App-peer dispatcher reaches the same hosted cache
    exactly once over the adopted AF_UNIX listener.

    The fixture principal is host-verified in the existing socket law; JWT
    verification itself is exercised separately at the signed A1 HTTP edge.
    Discovery and all effectful routes remain refused without a new action
    grant. No real Control HTTP listener, accounts, Macro or provider used.
    """
    from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
    from control_plane.workspace_read_service import workspace_provider_factory
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from common.workspace_control_room_read_contract import FRAME_SCHEMA
    from tests.test_executive_ceo_ingress import _FakeGrounding, _FakeSupervisor, _config

    owners, clock, _ = cache_fixture(tmp_path)
    baseline = copy.deepcopy(owners[0].state_cache["doc"])
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *_a, **_k: copy.deepcopy(baseline))
    monkeypatch.setattr(ccr.capability, "census", lambda **kw: {"test-only": True})
    cfg = config(tmp_path, ttl=30)
    cfg.validity_sample_fn = lambda: tuple(clock)
    listener, path = room_socket
    host = HostedControlRoom(cfg, listener=listener, socket_path=path,
                             allowed_peer_uids=(os.geteuid(),))

    def authorize(p):
        return (type(p) is dict and p.get("client_ref") == "fixture-web"
                and p.get("scopes") == ["mastermind.workspace.read"])
    authorize.binding_digest = lambda p: ("d" * 64 if authorize(p) else None)
    provider = workspace_provider_factory(
        control_room=host, authorize=authorize, armed={}, runtime_identity={},
    )

    async def run():
        svc = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo-ccr.sock",
            ceo_ingress_peer_uid=1000 + os.geteuid(),
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=False,
                grounding_provider=_FakeGrounding(),
                workspace_read_provider_factory=provider,
            ),
            workspace_control_room=host,
        )
        await svc.start()
        try:
            assert host.current_owner() is host.config
            assert host._server is not None and host._server.config is host.config
            assert host.config.port == 0
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            principal = frame("programs")["principal"]
            state = await client.request({
                "schema": FRAME_SCHEMA, "operation": "state",
                "principal": dict(principal),
            })
            assert state["ok"] is True
            assert state["result"]["control_room"] == baseline
            assert state["result"]["capabilities"] == {"test-only": True}
            discovery = await client.request({
                "schema": FRAME_SCHEMA, "operation": "discover",
                "principal": dict(principal),
            })
            assert discovery["status"] == 403
            assert "result" not in discovery
            # No effectful action is a valid CCR READ request on this socket.
            with pytest.raises(ValueError, match="invalid_input"):
                await client.request({"schema": FRAME_SCHEMA, "operation": "bind",
                                      "principal": dict(principal)})
            assert host.config.state_published_seq == 1
        finally:
            await svc.close()
        assert host.current_owner() is None
        assert host._server is None
        assert host._server_thread is not None and not host._server_thread.is_alive()
        assert host._refresh_thread is not None and not host._refresh_thread.is_alive()
        assert not host.config.state_refresh_threads
    asyncio.run(run())
