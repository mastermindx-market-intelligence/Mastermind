from __future__ import annotations

import asyncio
import importlib
import json

import pytest

from integrations.slack_executive import sol_state


BOT = "U-C1-RELAY-FIXTURE"
CHANNEL = "C-C1-SOL-RUNTIME-FIXTURE"
TOKEN = "INERT-C1-STATE-TOKEN"


def _module():
    try:
        return importlib.import_module("integrations.slack_executive.slack_web_api")
    except ModuleNotFoundError:
        pytest.fail("production Slack Web API state adapter is not implemented")


class _RecordingTransport:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.closed = False

    async def request(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.handler(dict(kwargs))

    async def aclose(self):
        self.closed = True


def _response(slack_web_api, path: str, payload, *, status: int = 200):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    return slack_web_api.SlackHttpResponse(
        status_code=status,
        final_url=slack_web_api.SLACK_API_ROOT + path,
        headers={"content-type": "application/json; charset=utf-8"},
        body=body,
    )


def _client(slack_web_api, handler):
    transport = _RecordingTransport(handler)
    client = slack_web_api.SlackWebApiStateClient(
        token=TOKEN,
        bot_user_id=BOT,
        transport=transport,
    )
    return client, transport


def test_fetch_history_uses_fixed_reviewed_call_and_normalizes_exact_window():
    slack_web_api = _module()

    def handler(call):
        return _response(
            slack_web_api,
            "conversations.history",
            {
                "ok": True,
                "messages": [
                    {
                        "ts": "1787800000.000001",
                        "user": BOT,
                        "text": f"{sol_state.DISCRIMINATOR}\n{{}}",
                    }
                ],
                "has_more": False,
                "response_metadata": {"next_cursor": ""},
            },
        )

    async def exercise():
        client, transport = _client(slack_web_api, handler)
        try:
            page = await client.fetch_history(channel_id=CHANNEL, limit=100)
            return page, transport
        finally:
            await client.aclose()

    page, transport = asyncio.run(exercise())
    assert page == sol_state.HistoryPage(
        messages=(
            sol_state.StateMessage(
                ts="1787800000.000001",
                author_user_id=BOT,
                text=f"{sol_state.DISCRIMINATOR}\n{{}}",
            ),
        ),
        complete=True,
    )
    assert transport.closed is True
    assert transport.calls == [
        {
            "method": "GET",
            "path": "conversations.history",
            "token": TOKEN,
            "query": {"channel": CHANNEL, "limit": "100"},
            "json_body": None,
        }
    ]


def test_create_message_uses_chat_post_message_and_normalizes_exact_write():
    slack_web_api = _module()
    text = f"{sol_state.DISCRIMINATOR}\n{{\"state_hash\":\"abc\"}}"

    def handler(call):
        return _response(
            slack_web_api,
            "chat.postMessage",
            {
                "ok": True,
                "channel": CHANNEL,
                "ts": "1787800001.000002",
                "message": {
                    "user": BOT,
                    "text": text,
                    "ts": "1787800001.000002",
                },
            },
        )

    async def exercise():
        client, transport = _client(slack_web_api, handler)
        try:
            message = await client.create_message(channel_id=CHANNEL, text=text)
            return message, transport
        finally:
            await client.aclose()

    message, transport = asyncio.run(exercise())
    assert message == sol_state.StateMessage(
        ts="1787800001.000002",
        author_user_id=BOT,
        text=text,
    )
    assert transport.calls == [
        {
            "method": "POST",
            "path": "chat.postMessage",
            "token": TOKEN,
            "query": None,
            "json_body": {"channel": CHANNEL, "text": text},
        }
    ]


def test_update_message_uses_chat_update_and_normalizes_exact_write():
    slack_web_api = _module()
    message_ts = "1787800001.000002"
    text = f"{sol_state.DISCRIMINATOR}\n{{\"state_hash\":\"def\"}}"

    def handler(call):
        return _response(
            slack_web_api,
            "chat.update",
            {
                "ok": True,
                "channel": CHANNEL,
                "ts": message_ts,
                "text": text,
            },
        )

    async def exercise():
        client, transport = _client(slack_web_api, handler)
        try:
            message = await client.update_message(
                channel_id=CHANNEL,
                message_ts=message_ts,
                text=text,
            )
            return message, transport
        finally:
            await client.aclose()

    message, transport = asyncio.run(exercise())
    assert message == sol_state.StateMessage(
        ts=message_ts,
        author_user_id=BOT,
        text=text,
    )
    assert transport.calls == [
        {
            "method": "POST",
            "path": "chat.update",
            "token": TOKEN,
            "query": None,
            "json_body": {"channel": CHANNEL, "ts": message_ts, "text": text},
        }
    ]


def test_malformed_slack_response_is_fixed_opaque_error_without_secret_leak():
    slack_web_api = _module()

    def handler(call):
        return _response(
            slack_web_api,
            call["path"],
            f"malformed payload carrying {TOKEN}".encode("utf-8"),
        )

    async def exercise():
        client, _transport = _client(slack_web_api, handler)
        try:
            with pytest.raises(RuntimeError) as caught:
                await client.fetch_history(channel_id=CHANNEL, limit=100)
            return str(caught.value)
        finally:
            await client.aclose()

    message = asyncio.run(exercise())
    assert message == "SLACK_API_INVALID_RESPONSE"
    assert TOKEN not in message


def test_http_failure_is_fixed_opaque_unavailable_without_body_leak():
    slack_web_api = _module()

    def handler(call):
        return _response(
            slack_web_api,
            call["path"],
            f"upstream failure carrying {TOKEN}".encode("utf-8"),
            status=503,
        )

    async def exercise():
        client, _transport = _client(slack_web_api, handler)
        try:
            with pytest.raises(RuntimeError) as caught:
                await client.fetch_history(channel_id=CHANNEL, limit=100)
            return str(caught.value)
        finally:
            await client.aclose()

    message = asyncio.run(exercise())
    assert message == "SLACK_API_UNAVAILABLE"
    assert TOKEN not in message


def test_transport_failure_is_fixed_opaque_unavailable_without_exception_leak():
    slack_web_api = _module()

    def handler(_call):
        raise RuntimeError(f"transport carried {TOKEN}")

    async def exercise():
        client, _transport = _client(slack_web_api, handler)
        try:
            with pytest.raises(RuntimeError) as caught:
                await client.fetch_history(channel_id=CHANNEL, limit=100)
            return str(caught.value)
        finally:
            await client.aclose()

    message = asyncio.run(exercise())
    assert message == "SLACK_API_UNAVAILABLE"
    assert TOKEN not in message


def test_default_transport_refuses_unreviewed_method_path_before_network():
    slack_web_api = _module()
    transport = slack_web_api.UrllibSlackHttpTransport()

    async def exercise():
        try:
            with pytest.raises(RuntimeError) as caught:
                await transport.request(
                    method="GET",
                    path="users.list",
                    token=TOKEN,
                )
            return str(caught.value)
        finally:
            await transport.aclose()

    assert asyncio.run(exercise()) == "SLACK_API_REQUEST_REFUSED"
