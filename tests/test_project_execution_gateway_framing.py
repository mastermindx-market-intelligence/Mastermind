"""Project private carrier framing; all sockets are isolated test-owned peers."""
import asyncio
import copy
import json
import tempfile

import pytest

from common import project_execution_private_contract as wire
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN,
)
from tests.test_project_conversation_read_contract import principal


def request():
    return wire.frame(dict(schema=wire.SCHEMA, operation="status",
        principal=principal(), workspace_principal=principal(),
        arguments=dict(operation_key="mmos-project-execute-" + "a" * 40, work_ref="WS:EXAMPLE")))


@pytest.mark.parametrize("raw,expected", [
    (b'{"ok":true,"result":{},"ok":true}\n', TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{},"extra":true}\n', TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{"value":NaN}}\n', TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{"value":1e999}}\n', TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{}}\n', TRANSPORT_SENT_OK),
    (b'{"ok":true,"result":{"text":"' + b"x" * wire.MAX_BYTES + b'"}}\n', TRANSPORT_SENT_UNKNOWN),
])
def test_project_socket_uses_closed_bounded_response_without_retry(raw, expected):
    async def run():
        captured = []
        with tempfile.TemporaryDirectory(prefix="project-frame-", dir="/tmp") as directory:
            async def respond(reader, writer):
                try:
                    captured.append(await reader.readline())
                    writer.write(raw)
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()
            path = directory + "/s"
            server = await asyncio.start_unix_server(respond, path=path)
            try:
                result = await CeoIngressClient().send_frame(path, request())
                assert result.transport == expected
                assert len(captured) == 1 and json.loads(captured[0]) == request()
            finally:
                server.close()
                await server.wait_closed()
    asyncio.run(run())


def test_execution_request_requires_original_http_lifetime_before_connect(monkeypatch):
    async def forbidden(*_, **__):
        pytest.fail("request without its original foreground lifetime reached socket")
    monkeypatch.setattr(asyncio, "open_unix_connection", forbidden)
    result = asyncio.run(CeoIngressClient().send_project_execution_frame("/no-source.sock", request()))
    assert result.transport == TRANSPORT_NOT_SENT


def test_invalid_project_frame_never_connects(monkeypatch):
    async def forbidden(*_, **__):
        pytest.fail("invalid request reached socket")
    monkeypatch.setattr(asyncio, "open_unix_connection", forbidden)
    frame = copy.deepcopy(request())
    frame["arguments"]["endpoint"] = "https://foreign.example"
    result = asyncio.run(CeoIngressClient().send_frame("/no-source.sock", frame))
    assert result.transport == TRANSPORT_NOT_SENT
