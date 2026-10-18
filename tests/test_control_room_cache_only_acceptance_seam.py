"""Source-only cache/listener separation; never grants installed Control authority."""
import asyncio
import copy
import socket
import pytest

from control_plane.workspace_control_room_lifecycle import HostedControlRoom
from control_plane.workspace_read_service import ExistingControlRoomCache
from tests.test_workspace_control_room_lifecycle import config, doc
from tests.test_workspace_read_service import cache_fixture, frame, service
from scripts import chairman_control_room as ccr


def test_cache_only_preserves_same_live_owner_without_creating_tcp(tmp_path, monkeypatch):
    compositions = []
    monkeypatch.setattr(ccr, '_compose_state_doc', lambda *_a, **_k: compositions.append(1) or doc())
    monkeypatch.setattr(ccr.capability, 'census', lambda **kwargs: {})
    # A reserved TCP port proves the cache-only path does not require bind.
    with socket.socket() as incumbent:
        incumbent.bind(('127.0.0.1', 0))
        incumbent.listen()
        occupied = incumbent.getsockname()[1]
        async def run():
            host = HostedControlRoom(config(tmp_path, port=occupied, ttl=10), cache_only=True)
            assert host.current_owner() is None
            await host.start()
            try:
                assert host.current_owner() is host.config
                assert host._server is None and host._server_thread is None
                assert host.config.state_published_seq == 1
                assert len(compositions) == 1
                assert host.config.workspace_refresh_on_read is False
            finally:
                await host.close()
            assert host.current_owner() is None
            assert not host._cache_active and not host.config.state_refresh_threads
        asyncio.run(run())


def test_cache_only_uses_existing_workspace_read_snapshot_owner(tmp_path, monkeypatch):
    owners, clock, cache = cache_fixture(tmp_path)
    baseline = copy.deepcopy(owners[0].state_cache['doc'])
    monkeypatch.setattr(ccr, '_compose_state_doc', lambda *_a, **_k: copy.deepcopy(baseline))
    monkeypatch.setattr(ccr.capability, 'census', lambda **k: {})
    config_ = config(tmp_path, ttl=60)
    config_.validity_sample_fn = lambda: tuple(clock)
    async def run():
        host = HostedControlRoom(config_, cache_only=True)
        await host.start()
        try:
            mirror = ExistingControlRoomCache(
                host.current_owner, monotonic=lambda: host.config.state_cache['composed_monotonic'] + .01)
            result = await service(mirror, acquire=lambda *_a, **_k: pytest.fail('runtime read')).handle_frame(frame('programs'))
            assert result['result']['availability'] == 'AVAILABLE'
            assert result['result']['control_room'] == baseline
        finally:
            await host.close()
        with pytest.raises(ValueError, match='source_unavailable'):
            mirror.snapshot()
    asyncio.run(run())


@pytest.mark.parametrize('value', ['false', 0, 1, None])
def test_cache_only_mode_requires_exact_boolean(tmp_path, value):
    with pytest.raises(ValueError, match='hosting configuration refused'):
        HostedControlRoom(config(tmp_path), cache_only=value)


def test_default_http_mode_keeps_existing_owner_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(ccr, '_compose_state_doc', lambda *_a, **_k: doc())
    monkeypatch.setattr(ccr.capability, 'census', lambda **k: {})
    async def run():
        host = HostedControlRoom(config(tmp_path, ttl=10))
        await host.start()
        try:
            assert host.cache_only is False
            assert host._server is not None
            assert host.current_owner() is host._server.config
        finally:
            await host.close()
    asyncio.run(run())

def test_cache_only_drain_refuses_to_retire_live_owner_until_refresh_joins(tmp_path, monkeypatch):
    import threading
    import time
    from control_plane.workspace_control_room_lifecycle import ControlRoomDrainUnavailable
    started, release = threading.Event(), threading.Event()
    calls = [0]
    def compose(*_a, **_k):
        calls[0] += 1
        if calls[0] > 1:
            started.set()
            assert release.wait(5)
        return doc()
    monkeypatch.setattr(ccr, '_compose_state_doc', compose)
    monkeypatch.setattr(ccr.capability, 'census', lambda **k: {})
    async def run():
        host = HostedControlRoom(config(tmp_path, ttl=.1), shutdown_timeout=.1, cache_only=True)
        await host.start()
        assert await asyncio.to_thread(started.wait, 3)
        try:
            with pytest.raises(ControlRoomDrainUnavailable):
                await host.close()
            assert host.current_owner() is None
            assert host._cache_active is True
        finally:
            release.set()
            await host.close()
        assert host._cache_active is False
        assert not host.config.state_refresh_threads
    asyncio.run(run())


def test_cache_only_start_cancellation_cannot_detach_composition(tmp_path, monkeypatch):
    import threading
    started, release, completed = threading.Event(), threading.Event(), threading.Event()
    def compose(*_a, **_k):
        started.set()
        assert release.wait(5)
        completed.set()
        return doc()
    monkeypatch.setattr(ccr, '_compose_state_doc', compose)
    monkeypatch.setattr(ccr.capability, 'census', lambda **k: {})
    async def run():
        host = HostedControlRoom(config(tmp_path, ttl=10), cache_only=True)
        task = asyncio.create_task(host.start())
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(.02)
        assert not task.done(), 'the cache producer was still active'
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert completed.is_set()
        assert host.current_owner() is None
        assert host._cache_active is False
        assert host._server is None and host._server_thread is None
        assert not host.config.state_refresh_threads
    asyncio.run(run())


def test_cache_only_precompose_error_never_yields_approved_workspace_read(tmp_path, monkeypatch):
    monkeypatch.setattr(ccr, '_compose_state_doc', lambda *_a, **_k: (_ for _ in ()).throw(ValueError('unavailable')))
    monkeypatch.setattr(ccr.capability, 'census', lambda **k: {})
    async def run():
        host = HostedControlRoom(config(tmp_path, ttl=60), cache_only=True)
        await host.start()
        try:
            mirror = ExistingControlRoomCache(host.current_owner)
            result = await service(mirror, acquire=lambda *_a, **_k: pytest.fail('runtime read')).handle_frame(frame('programs'))
            assert result['result']['availability'] == 'UNAVAILABLE'
            assert result['result']['control_room'] is None
        finally:
            await host.close()
        assert host.current_owner() is None
    asyncio.run(run())


def test_actual_executive_service_workspace_socket_reuses_cache_only_owner(
        tmp_path, short_socket_root, monkeypatch):
    """Real service/ingress route, no Control-owned HTTP and no duplicate cache."""
    from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from tests.test_executive_ceo_ingress import _FakeGrounding, _FakeSupervisor, _config
    from tests.test_workspace_read_service import cache_fixture, frame, service as workspace_service

    owners, clock, _ = cache_fixture(tmp_path)
    baseline = copy.deepcopy(owners[0].state_cache['doc'])
    monkeypatch.setattr(ccr, '_compose_state_doc', lambda *_a, **_k: copy.deepcopy(baseline))
    monkeypatch.setattr(ccr.capability, 'census', lambda **k: {})
    host_config = config(tmp_path, ttl=30)
    host_config.validity_sample_fn = lambda: tuple(clock)
    host = HostedControlRoom(host_config, cache_only=True)
    reads = []

    def provider(runtime):
        # Runtime remains the service's existing exact owner; the only cache
        # is the source-owned ServerConfig visible through current_owner().
        cache = ExistingControlRoomCache(
            host.current_owner,
            monotonic=lambda: host.config.state_cache['composed_monotonic'] + .01,
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
            ceo_ingress_peer_uid=1000 + __import__('os').geteuid(),
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=__import__('os').geteuid(), armed=False,
                grounding_provider=_FakeGrounding(),
                workspace_read_provider_factory=provider,
            ),
            workspace_control_room=host,
        )
        await svc.start()
        try:
            assert host.current_owner() is host.config
            assert host._server is None and host._server_thread is None
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            answer = await client.request(frame('programs'))
            assert answer['result']['availability'] == 'AVAILABLE'
            assert answer['result']['control_room'] == baseline
            assert reads == [svc.runtime]
        finally:
            await svc.close()
        assert host.current_owner() is None
        assert host._cache_active is False
    asyncio.run(run())


def test_actual_executive_app_socket_serves_one_signed_member_state_without_tcp(
        tmp_path, short_socket_root, monkeypatch):
    """The real private App-peer dispatcher reaches the same cache exactly once.

    The fixture principal is host-verified in the existing socket law; JWT
    verification itself is exercised separately at the signed A1 HTTP edge.
    Discovery and all effectful routes remain refused without a new action
    grant. No real Control HTTP listener, accounts, Macro or provider used.
    """
    import os
    from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
    from control_plane.workspace_read_service import workspace_provider_factory
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from common.workspace_control_room_read_contract import FRAME_SCHEMA
    from tests.test_executive_ceo_ingress import _FakeGrounding, _FakeSupervisor, _config
    from tests.test_workspace_read_service import cache_fixture, frame

    owners, clock, _ = cache_fixture(tmp_path)
    baseline = copy.deepcopy(owners[0].state_cache["doc"])
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *_a, **_k: copy.deepcopy(baseline))
    monkeypatch.setattr(ccr.capability, "census", lambda **kw: {"test-only": True})
    cfg = config(tmp_path, ttl=30)
    cfg.validity_sample_fn = lambda: tuple(clock)
    host = HostedControlRoom(cfg, cache_only=True)

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
            assert host._server is None and host._server_thread is None
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
        assert host._cache_active is False
    asyncio.run(run())
