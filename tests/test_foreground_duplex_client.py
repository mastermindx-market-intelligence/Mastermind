"""Real local Unix transport fixtures; no admission, Runtime or provider."""
import asyncio
import json
import tempfile
import contextlib
import time
from types import SimpleNamespace
from starlette.requests import Request
from pathlib import Path

import pytest

from integrations.mastermind_executive_app import gateway
from integrations.session_bridge import installed
from tests import test_session_bridge_installed as incumbent


FRAME = {"schema": installed.PRIVATE_SCHEMA, "tool": "session_summon",
         "principal": {}, "arguments": {}}

@contextlib.asynccontextmanager
async def _transport_source(deadline=.2):
    # Lifetime fixture only; the actual authenticated ASGI producer is tested
    # separately. This cannot grant Runtime or provider execution.
    from integrations.session_bridge.http_foreground import owned_request, bind_request
    async def receive():
        await asyncio.Event().wait()
    async with owned_request({"type":"http"}, receive, deadline_seconds=deadline) as scope:
        now=int(time.time())
        with bind_request(Request(scope),SimpleNamespace(issued_at=now-1,expires_at=now+10)):
            yield


def test_incumbent_half_close_and_duplex_reply_are_distinct_on_real_stream():
    async def run(mode):
        result = asyncio.get_running_loop().create_future()
        async def peer(reader, writer):
            try:
                await reader.readline()
                if mode == "incumbent":
                    assert await reader.read(1) == b""
                snapshot = (reader.at_eof(), writer.is_closing())
                writer.write(b'{"ok":true,"result":{}}\n')
                await writer.drain()
                assert await reader.read(1) == b""
                result.set_result(snapshot)
            finally:
                writer.close()
                await writer.wait_closed()
        with tempfile.TemporaryDirectory(prefix="fg-duplex-") as td:
            path = str(Path(td) / "s")
            server = await asyncio.start_unix_server(peer, path=path)
            async with server:
                c = gateway.CeoIngressClient(connect_timeout=.2, read_timeout=.2)
                if mode == "incumbent":
                    response = await c.send_frame(path, FRAME)
                else:
                    async with _transport_source():
                        response = await c.send_foreground_frame(path, FRAME)
                assert response.ok and response.transport == gateway.TRANSPORT_SENT_OK
                return await asyncio.wait_for(result, .5)
    assert asyncio.run(run("incumbent")) == (True, False)
    assert asyncio.run(run("foreground")) == (False, False)


@pytest.mark.parametrize("edge", ["cancel", "timeout"])
def test_duplex_cancel_or_timeout_closes_the_same_call_without_retry(edge):
    async def run():
        received, disconnected = asyncio.Event(), asyncio.Event()
        calls = []
        async def peer(reader, writer):
            try:
                calls.append(await reader.readline())
                assert not reader.at_eof()
                received.set()
                assert await reader.read(1) == b""
                disconnected.set()
            finally:
                writer.close()
                await writer.wait_closed()
        with tempfile.TemporaryDirectory(prefix="fg-duplex-") as td:
            path = str(Path(td) / "s")
            server = await asyncio.start_unix_server(peer, path=path)
            async with server:
                c = gateway.CeoIngressClient(connect_timeout=.2, read_timeout=.05)
                async with _transport_source(deadline=.05):
                    task = asyncio.create_task(c.send_foreground_frame(path, FRAME))
                    await asyncio.wait_for(received.wait(), .5)
                    if edge == "cancel":
                        task.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await task
                    else:
                        assert (await task).transport == gateway.TRANSPORT_SENT_UNKNOWN
                    await asyncio.wait_for(disconnected.wait(), .5)
                    assert len(calls) == 1
    asyncio.run(run())


@pytest.mark.parametrize("frame", [
    {}, {"schema": "caller-selected", "tool": "session_summon"},
    {"schema": installed.PRIVATE_SCHEMA, "tool": "session_targets"},
    {"schema": installed.PRIVATE_SCHEMA, "tool": "session_send"},
    {"schema": installed.PRIVATE_SCHEMA, "tool": "session_reply_read"},
])
def test_foreground_method_refuses_other_frames_before_connect(monkeypatch, frame):
    async def forbidden(*_, **__):
        pytest.fail("invalid foreground mode reached connection")
    monkeypatch.setattr(asyncio, "open_unix_connection", forbidden)
    response = asyncio.run(gateway.CeoIngressClient().send_foreground_frame("/absent", frame))
    assert response.transport == gateway.TRANSPORT_NOT_SENT


def test_installed_summon_uses_actual_foreground_method_and_read_stays_incumbent():
    class Transport:
        def __init__(self):
            self.calls = []
        async def send_frame(self, path, frame):
            self.calls.append(("incumbent", frame))
            return incumbent.ok_result(frame["tool"], [])
        async def send_foreground_frame(self, path, frame):
            self.calls.append(("foreground", frame))
            return incumbent.ok_result(frame["tool"], {"status": "QUEUED", "dispatched": False})
    t = Transport()
    c = installed.InstalledSessionBridgeClient("/fixture.sock", client=t)
    args = {"objective": "Inspect a bounded source.", "execution_profile": "research_only",
        "operation_key": "duplex-source-only", "department": "executive-infrastructure",
        "priority": 0, "workstream": "WS:DOT-SESSION-BRIDGE", "attempt_limit": 2,
        "allowed_write_paths": [], "validation": {}}
    async def summon_from_source():
        async with _transport_source():
            return await c.summon(incumbent.PRINCIPAL, args)
    result = asyncio.run(summon_from_source())
    assert result == {"status": "QUEUED", "dispatched": False}
    assert set(t.calls[0][1]) == {"schema", "tool", "principal", "arguments"}
    asyncio.run(c.targets(incumbent.PRINCIPAL))
    assert [mode for mode, _ in t.calls] == ["foreground", "incumbent"]


def test_injected_incumbent_client_still_returns_queued_without_attendance_claim():
    c, fake = incumbent.client(incumbent.ok_result("session_summon",
        {"status": "QUEUED", "dispatched": False}))
    result = asyncio.run(c.summon(incumbent.PRINCIPAL, {
        "objective": "Inspect a bounded source.", "execution_profile": "research_only",
        "operation_key": "legacy-source-only", "department": "executive-infrastructure",
        "priority": 0, "workstream": "WS:DOT-SESSION-BRIDGE", "attempt_limit": 2,
        "allowed_write_paths": [], "validation": {}}))
    assert result == {"status": "QUEUED", "dispatched": False} and len(fake.calls) == 1
