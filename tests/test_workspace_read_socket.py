"""Actual ExecutiveControlService/CeoIngress socket against the integration patch."""
import asyncio
import os

import pytest

from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from integrations.mastermind_workspace_app.contract import MAX_RESPONSE_BYTES, canonical, error
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_executive_ceo_ingress import (
    _FakeGrounding, _FakeSupervisor, _config, short_socket_root,
)
from tests.test_workspace_read_service import cache_fixture, service as provider, frame


def control(tmp_path, short_socket_root, factory, *, app_uid=None):
    return ExecutiveControlService(_config(tmp_path, socket_root=short_socket_root),
        supervisor_factory=lambda runtime: _FakeSupervisor(),
        ceo_ingress_socket_path=short_socket_root / "ceo.sock",
        ceo_ingress_peer_uid=os.geteuid() + 1000,
        ceo_ingress_grounding_provider=_FakeGrounding(),
        ceo_ingress_app_binding=CeoIngressAppBinding(
            peer_uid=os.geteuid() if app_uid is None else app_uid, armed=False,
            grounding_provider=_FakeGrounding(), workspace_read_provider_factory=factory))


def test_actual_service_programs_reads_exact_cache_and_runtime_is_injected(tmp_path, short_socket_root):
    owners, clock, cache = cache_fixture(tmp_path)
    seen = []
    def factory(runtime):
        seen.append(runtime)
        value = provider(cache)
        value.runtime = runtime
        return value
    async def run():
        svc = control(tmp_path, short_socket_root, factory)
        await svc.start()
        try:
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            result = await client.request(frame("programs"))
            assert result["result"]["availability"] == "AVAILABLE"
            assert result["result"]["control_room"] == owners[0].state_cache["doc"]
            assert seen == [svc.runtime]
        finally: await svc.close()
    asyncio.run(run())


def test_non_app_peer_refused_before_workspace_provider(tmp_path, short_socket_root):
    def factory(runtime): pytest.fail("workspace provider reached")
    async def run():
        svc = control(tmp_path, short_socket_root, factory, app_uid=os.geteuid() + 2000)
        await svc.start()
        try:
            with pytest.raises(ValueError, match="source_unavailable"):
                await CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(frame())
        finally: await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize("count,available", [(100000, True), (2_000_000, False)])
def test_workspace_only_reply_ceiling_exact_and_no_partial_json(tmp_path, short_socket_root, count, available):
    class Provider:
        async def handle_frame(self, request):
            return {"ok": True, "result": {"fixture": "x" * count}}
    async def run():
        svc = control(tmp_path, short_socket_root, lambda runtime: Provider())
        await svc.start()
        try:
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            if available:
                assert len((await client.request(frame()))["result"]["fixture"]) == count
            else:
                result = await client.request(frame())
                assert result == error("source_unavailable", 503)
        finally: await svc.close()
    asyncio.run(run())


def test_missing_workspace_factory_typed_unavailable(tmp_path, short_socket_root):
    async def run():
        svc = control(tmp_path, short_socket_root, None)
        await svc.start()
        try:
            result = await CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(frame())
            assert result == error("source_unavailable", 503)
        finally: await svc.close()
    asyncio.run(run())


def test_actual_service_hosts_one_cache_before_readiness_and_drains_it(tmp_path, short_socket_root, monkeypatch):
    from control_plane.workspace_control_room_lifecycle import HostedControlRoom
    from tests.test_workspace_control_room_lifecycle import config, doc
    from scripts import chairman_control_room as ccr
    monkeypatch.setattr(ccr, "_compose_state_doc", lambda *a, **k: doc())
    monkeypatch.setattr(ccr.capability, "census", lambda **k: {})
    async def run():
        host = HostedControlRoom(config(tmp_path, ttl=10))
        svc = ExecutiveControlService(_config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
                grounding_provider=_FakeGrounding()), workspace_control_room=host)
        await svc.start()
        assert host.current_owner() is host.config is host._server.config
        assert host.config.state_published_seq == 1 and svc._ceo_ingress_ready
        await svc.close()
        assert host.current_owner() is None and host._server is None
        assert not host.config.state_refresh_threads
    asyncio.run(run())
