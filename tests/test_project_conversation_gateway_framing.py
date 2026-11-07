"""Real local socket framing, independent of Runtime/authentication authority."""
import asyncio
import copy
import tempfile

import pytest

from common import project_conversation_read_contract as wire
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN,
)
from tests.test_project_conversation_read_contract import principal


def request():
    return wire.frame({'schema': wire.SCHEMA, 'operation': 'catalogue',
                       'principal': principal(), 'arguments': {'work_ref': 'WS:ONE'}})


@pytest.mark.parametrize('raw,expected', [
    (b'{"ok":true,"result":{},"ok":true}\n', TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{},"extra":true}\n', TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{"value":NaN}}\n', TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{"value":1e999}}\n', TRANSPORT_SENT_UNKNOWN),
    (b'{"ok":true,"result":{}}\n', TRANSPORT_SENT_OK),
    (b'{"ok":true,"result":{"text":"' + b'x' * 32768 + b'"}}\n', TRANSPORT_SENT_UNKNOWN),
])
def test_read_socket_uses_canonical_request_and_closed_bounded_response(raw, expected):
    async def run():
        captured = []
        with tempfile.TemporaryDirectory(prefix='conversation-read-', dir='/tmp') as directory:
            async def respond(reader, writer):
                try:
                    captured.append(await reader.readline())
                    writer.write(raw)
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()
            path = directory + '/s'
            server = await asyncio.start_unix_server(respond, path=path)
            try:
                result = await CeoIngressClient().send_frame(path, request())
                assert result.transport == expected
                assert captured == [wire.encode_frame(request())]
            finally:
                server.close()
                await server.wait_closed()
    asyncio.run(run())


def test_invalid_read_frame_never_connects(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail('invalid request reached socket')
    monkeypatch.setattr(asyncio, 'open_unix_connection', forbidden)
    frame = copy.deepcopy(request())
    frame['arguments']['operation_key'] = 'foreign'
    result = asyncio.run(CeoIngressClient().send_frame('/no-source.sock', frame))
    assert result.transport == TRANSPORT_NOT_SENT
