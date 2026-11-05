"""Real one-frame Unix handler and kernel peer; provider execution is an inert fixture."""
import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from common.session_bridge_private_contract import FOREGROUND_PRIVATE_SCHEMA
from control_plane import foreground_operation as scope
from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from integrations.session_bridge.installed import InstalledSessionBridgeProvider, private_ingress_owner
from tests.test_executive_mcp_installed_fabric_composition import factory_service
from tests.test_foreground_operation import frame
from tests.test_foreground_duplex_client import _transport_source


@pytest.mark.parametrize("edge", ["duplex", "legacy", "disconnect", "binding", "readonly"])
def test_actual_private_handler_lifetime_and_legacy_queue(tmp_path, short_socket_root, monkeypatch, edge):
    async def run():
        held, readers = [], []
        entered, proceed = asyncio.Event(), asyncio.Event()
        async with factory_service(tmp_path, short_socket_root, monkeypatch,
                profile=WEB_CEO_SESSIONS_PROFILE) as (service, raw, _):
            async def summon(principal, arguments):
                if edge == "legacy":
                    assert scope._current_foreground_operation_or_none() is None
                else:
                    operation = scope.current_foreground_operation()
                    operation.require_arguments(arguments)
                    held.append(operation)
                    entered.set()
                    if edge in {"disconnect", "binding"}:
                        await proceed.wait()
                        with pytest.raises(scope.ForegroundOperationRefusal) as error:
                            scope.current_foreground_operation()
                        assert error.value.code == ("foreground_unavailable" if edge == "disconnect" else "host_not_current")
                return {"status": "QUEUED", "dispatched": False}
            async def project(principal, kind):
                assert scope._current_foreground_operation_or_none() is None
                return []
            provider = InstalledSessionBridgeProvider(target_projector=project,
                reply_handler=lambda *_: None, summon_handler=summon)
            service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding,
                session_bridge_provider_factory=lambda _: private_ingress_owner(provider))
            original = service._handle_ceo_ingress_connection
            async def observe_stream(reader, writer):
                readers.append(reader)
                await original(reader, writer)
            service._handle_ceo_ingress_connection = observe_stream
            await service.start()
            path, f = Path(raw["ceo_ingress_socket_path"]), frame()
            c = CeoIngressClient(connect_timeout=.5, read_timeout=1)
            if edge == "readonly":
                f["tool"], f["arguments"] = "session_targets", {}
                result = await c.send_frame(path, f)
                assert result.ok and result.result["ok"]
            elif edge == "disconnect":
                reader, writer = await asyncio.open_unix_connection(str(path))
                writer.write((json.dumps({**f, "schema": FOREGROUND_PRIVATE_SCHEMA}) + "\n").encode())
                await writer.drain()
                await asyncio.wait_for(entered.wait(), 1)
                writer.close()
                await writer.wait_closed()
                await asyncio.wait_for(held[0].wait_closed(), 1)
                proceed.set()
                # The actual registered handler owns completion after client loss.
                await asyncio.wait_for(service._ceo_ingress_tasks.copy().pop(), 1)
            else:
                async def send():
                    if edge == "legacy":
                        return await c.send_frame(path, f)
                    async with _transport_source(deadline=1):
                        return await c.send_foreground_frame(path, f)
                task = asyncio.create_task(send())
                if edge == "binding":
                    await asyncio.wait_for(entered.wait(), 1)
                    service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding)
                    proceed.set()
                result = await task
                assert result.ok
                if edge == "binding":
                    assert result.result["error"]["code"] == "effect_unknown"
                else:
                    assert result.result["data"] == {"status": "QUEUED", "dispatched": False}
            assert all(op._closed for op in held)
            for op in held:
                await asyncio.wait_for(op.wait_closed(), .2)
            assert scope._current_foreground_operation_or_none() is None
    asyncio.run(run())


def test_framing_cannot_grant_foreground_to_another_tool(tmp_path, short_socket_root, monkeypatch):
    async def run():
        async with factory_service(tmp_path, short_socket_root, monkeypatch,
                profile=WEB_CEO_SESSIONS_PROFILE) as (service, raw, _):
            calls = []
            def forbidden(_):
                calls.append(True)
                pytest.fail("invalid framing reached the provider")
            service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding,
                session_bridge_provider_factory=forbidden)
            await service.start()
            f = {**frame(), "schema": FOREGROUND_PRIVATE_SCHEMA, "tool": "session_targets", "arguments": {}}
            result = await CeoIngressClient().send_frame(Path(raw["ceo_ingress_socket_path"]), f)
            assert not result.ok and result.error["code"] == "invalid_input" and calls == []
    asyncio.run(run())


@pytest.mark.parametrize("edge",["expiry","extra_frame"])
def test_private_source_end_observation_does_not_create_or_cancel_work(tmp_path,edge):
    from control_plane.executive_runtime import Runtime
    import time
    async def run():
        runtime=Runtime.at(tmp_path)
        f=frame(expires_at=int(time.time())+2)
        reader=asyncio.StreamReader()
        if edge=="extra_frame":reader.feed_data(b"unexpected-second-frame")
        async with scope._session_bridge_foreground_dispatch(runtime,f,lambda:None) as operation:
            async with scope._observe_private_request_end(operation,reader):
                await asyncio.wait_for(operation.wait_closed(),2.5)
                with pytest.raises(scope.ForegroundOperationClosed):scope.current_foreground_operation()
        assert runtime.jobs.list_jobs()==[]
    asyncio.run(run())
