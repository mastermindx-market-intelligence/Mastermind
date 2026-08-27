from __future__ import annotations

import asyncio
import importlib
import json

import httpx
import pytest

from integrations.slack_executive import sol_state


BOT = "U-C1-RELAY-FIXTURE"
CHANNEL = "C-C1-SOL-RUNTIME-FIXTURE"
TOKEN = "xoxb-c1-test-secret"


def _module():
    try:
        return importlib.import_module("integrations.slack_executive.slack_web_api")
    except ModuleNotFoundError:
        pytest.fail("production Slack Web API state adapter is not implemented")


def test_fetch_history_uses_fixed_slack_origin_and_normalizes_exact_window():
    slack_web_api = _module()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
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
            request=request,
        )

    async def exercise():
        client = slack_web_api.SlackWebApiStateClient(
            token=TOKEN,
            bot_user_id=BOT,
            transport=httpx.MockTransport(handler),
        )
        try:
            page = await client.fetch_history(channel_id=CHANNEL, limit=100)
        finally:
            await client.aclose()
        return page

    page = asyncio.run(exercise())

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
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert request.url.scheme == "https"
    assert request.url.host == "slack.com"
    assert request.url.path == "/api/conversations.history"
    assert request.url.params["channel"] == CHANNEL
    assert request.url.params["limit"] == "100"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"


def test_create_message_uses_chat_post_message_and_normalizes_exact_write():
    slack_web_api = _module()
    requests: list[httpx.Request] = []
    text = f"{sol_state.DISCRIMINATOR}\n{{\"state_hash\":\"abc\"}}"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "channel": CHANNEL,
                "ts": "1787800001.000002",
                "message": {
                    "user": BOT,
                    "text": text,
                    "ts": "1787800001.000002",
                },
            },
            request=request,
        )

    async def exercise():
        client = slack_web_api.SlackWebApiStateClient(
            token=TOKEN,
            bot_user_id=BOT,
            transport=httpx.MockTransport(handler),
        )
        try:
            message = await client.create_message(channel_id=CHANNEL, text=text)
        finally:
            await client.aclose()
        return message

    message = asyncio.run(exercise())
    assert message == sol_state.StateMessage(
        ts="1787800001.000002",
        author_user_id=BOT,
        text=text,
    )
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.scheme == "https"
    assert request.url.host == "slack.com"
    assert request.url.path == "/api/chat.postMessage"
    assert json.loads(request.content) == {"channel": CHANNEL, "text": text}
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
