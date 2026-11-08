"""Real installed App-peer/Runtime ingress; native history bytes are a named peer fixture.

The separate native-process test qualifies actual Gateway and JSONL history.
These tests use the original isolated Linux/root transport fixture, not installed
Executive state, a provider, or a caller-supplied production descriptor.
"""
import asyncio
import dataclasses
import os
from pathlib import Path
import sys

import pytest

from common.session_bridge_private_contract import BridgeError
from integrations.session_bridge.installed import InstalledSessionBridgeClient
from tests.test_deepseek_native_read import composition, respond, assert_no_frame
from tests.test_executive_mcp_installed_fabric_composition import (
    _listening, _patch_composition, _raw_for_factory, short_socket_root,
)
from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE

pytestmark = pytest.mark.skipif(sys.platform != "linux" or os.geteuid() != 0,
    reason="incumbent isolated Linux/root App-peer transport qualification")


@pytest.mark.parametrize("rotation", ["app-binding", "native-source"])
def test_actual_app_peer_reads_native_history_then_refuses_retired_original_owner(
        tmp_path, short_socket_root, monkeypatch, rotation):
    h = composition(tmp_path)
    raw = _raw_for_factory(tmp_path, short_socket_root, profile=WEB_CEO_SESSIONS_PROFILE)
    sockets = {
        "Operator": _listening(Path(raw["control_socket_path"])),
        "CeoIngress": _listening(Path(raw["ceo_ingress_socket_path"])),
    }
    module = _patch_composition(monkeypatch, sockets)

    async def run():
        service = module._service_from_config(raw, deepseek_native_read_source=h.source)
        try:
            await service.start()
            runtime = service._require_runtime()
            service._namespace_custody.bound_runtime(runtime)
            assert service._require_runtime() is runtime
            factory = service._ceo_ingress_app_binding.session_bridge_provider_factory
            original = factory(runtime)
            client = InstalledSessionBridgeClient(raw["ceo_ingress_socket_path"])
            native = asyncio.create_task(respond(h.peer, data={
                "projections": None, "page": {"records": [], "private_edge_fixture": True}}))
            result = await client.native_read(h.principal, h.args)
            frame, _ = await native
            assert result["selection"] == h.args["selection"]
            assert result["native"]["page"]["private_edge_fixture"] is True
            assert result["native_session_id"] == h.association.native_session_id
            assert frame["principal"]["principal_scope"] == h.association.owner_principal_scope
            assert result["can_send"] is False and result["parent_consumed"] is False
            foreign = dataclasses.replace(h.principal, client_ref="9"*64)
            with pytest.raises(BridgeError):
                await client.native_read(foreign, h.args)
            assert_no_frame(h)
            if rotation == "app-binding":
                service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding)
            else:
                h.live["source"] = False
            # Hold the exact old request-local factory result through rotation.
            # It may not borrow the new App binding or a replacement source.
            refused = await original.handle_frame(h.frame())
            assert refused["ok"] is False and refused["data"] is None
            assert_no_frame(h)
        finally:
            await service.close()

    try:
        asyncio.run(run())
    finally:
        h.port.retire();h.peer.close()
        for endpoint in sockets.values():
            endpoint.close()


def test_config_cannot_mint_the_trusted_native_port_from_a_json_projection():
    from scripts.executive_os_phase1c import _service_from_config
    from control_plane.executive_service import ServiceError
    with pytest.raises(ServiceError, match="trusted live composition"):
        _service_from_config({}, deepseek_native_read_source={
            "fd": 3, "association": {"native_session_id": "caller-selected"}})
