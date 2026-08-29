from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request

import pytest

from integrations.slack_agent_dialogue.engine import (
    HistoryPage,
    SlackEffectUnknown,
    SlackMessage,
    SlackTransportUnavailable,
)
from integrations.slack_agent_dialogue.slack_web_api import (
    MAX_RESPONSE_BYTES,
    SLACK_API_ROOT,
    SlackHttpResponse,
    SlackWebApiDialogueClient,
    UrllibSlackHttpTransport,
)

TOKEN = "INERT-A2-AGENT-RELAY-TOKEN"
WORKSPACE = "T0BRD2AQXQV"
CHANNEL = "C0BRUL9F2V7"
BOT = "U0BST4WG996"
HUMAN = "U0BRETDUAS2"
THREAD_TS = "1787471000.000001"


def run(coro):
    return asyncio.run(coro)


def api_url(path: str, query: dict[str, str] | None = None) -> str:
    url = SLACK_API_ROOT + path
    if query:
        url += "?" + urllib.parse.urlencode(sorted(query.items()))
    return url


def response(
    path: str,
    payload,
    *,
    query: dict[str, str] | None = None,
    status: int = 200,
    final_url: str | None = None,
) -> SlackHttpResponse:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return SlackHttpResponse(
        status_code=status,
        final_url=final_url or api_url(path, query),
        headers={"content-type": "application/json; charset=utf-8"},
        body=body,
    )


class RecordingTransport:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    async def request(self, **kwargs):
        call = dict(kwargs)
        self.calls.append(call)
        return self.handler(call)


def client(handler):
    transport = RecordingTransport(handler)
    return (
        SlackWebApiDialogueClient(
            token=TOKEN,
            workspace_id=WORKSPACE,
            channel_id=CHANNEL,
            bot_user_id=BOT,
            transport=transport,
        ),
        transport,
    )


def message(
    *,
    ts: str,
    user: str = HUMAN,
    text: str = "frame",
    thread_ts: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "type": "message",
        "team": WORKSPACE,
        "user": user,
        "text": text,
        "ts": ts,
    }
    if thread_ts is not None:
        value["thread_ts"] = thread_ts
    return value


def page_payload(messages: list[dict], *, has_more=False, cursor="") -> dict:
    return {
        "ok": True,
        "messages": messages,
        "has_more": has_more,
        "response_metadata": {"next_cursor": cursor},
    }


def test_unedited_history_and_thread_parse_exactly_and_preserve_limit() -> None:
    history_query = {"channel": CHANNEL, "limit": "7"}
    thread_query = {"channel": CHANNEL, "ts": THREAD_TS, "limit": "3"}

    def handler(call):
        if call["path"] == "conversations.history":
            return response(
                call["path"],
                page_payload([message(ts=THREAD_TS, user=BOT, text="parent")]),
                query=history_query,
            )
        return response(
            call["path"],
            page_payload(
                [
                    message(ts=THREAD_TS, user=BOT, text="parent"),
                    message(
                        ts="1787471000.000002",
                        text="reply",
                        thread_ts=THREAD_TS,
                    ),
                ]
            ),
            query=thread_query,
        )

    adapter, transport = client(handler)
    history = run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=7))
    thread = run(
        adapter.fetch_thread(channel_id=CHANNEL, thread_ts=THREAD_TS, limit=3)
    )

    assert history == HistoryPage(
        messages=(SlackMessage(ts=THREAD_TS, author_user_id=BOT, text="parent"),),
        complete=True,
        mutation_evidence_complete=True,
    )
    assert thread == HistoryPage(
        messages=(
            SlackMessage(ts=THREAD_TS, author_user_id=BOT, text="parent"),
            SlackMessage(
                ts="1787471000.000002",
                author_user_id=HUMAN,
                text="reply",
                thread_ts=THREAD_TS,
            ),
        ),
        complete=True,
        mutation_evidence_complete=True,
    )
    assert [(call["method"], call["path"], call["query"]) for call in transport.calls] == [
        ("GET", "conversations.history", history_query),
        ("GET", "conversations.replies", thread_query),
    ]


def test_history_accepts_official_ordinary_message_shape_without_team() -> None:
    query = {"channel": CHANNEL, "limit": "1"}
    ordinary = message(ts=THREAD_TS, user=BOT, text="parent")
    ordinary.pop("team")
    adapter, _transport = client(
        lambda call: response(
            call["path"], page_payload([ordinary]), query=query
        )
    )

    page = run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=1))

    assert page.messages == (
        SlackMessage(ts=THREAD_TS, author_user_id=BOT, text="parent"),
    )


def test_replies_accept_official_ordinary_message_shape_without_team() -> None:
    query = {"channel": CHANNEL, "ts": THREAD_TS, "limit": "2"}
    parent = message(ts=THREAD_TS, user=BOT, text="parent")
    reply = message(
        ts="1787471000.000002", text="reply", thread_ts=THREAD_TS
    )
    parent.pop("team")
    reply.pop("team")
    adapter, _transport = client(
        lambda call: response(
            call["path"], page_payload([parent, reply]), query=query
        )
    )

    page = run(
        adapter.fetch_thread(channel_id=CHANNEL, thread_ts=THREAD_TS, limit=2)
    )

    assert page.messages == (
        SlackMessage(ts=THREAD_TS, author_user_id=BOT, text="parent"),
        SlackMessage(
            ts="1787471000.000002",
            author_user_id=HUMAN,
            text="reply",
            thread_ts=THREAD_TS,
        ),
    )


def test_present_mismatched_team_remains_refused() -> None:
    query = {"channel": CHANNEL, "limit": "1"}
    ordinary = message(ts=THREAD_TS)
    ordinary["team"] = "T0000000000"
    adapter, _transport = client(
        lambda call: response(
            call["path"], page_payload([ordinary]), query=query
        )
    )

    with pytest.raises(SlackTransportUnavailable, match="^SLACK_TRANSPORT_UNAVAILABLE$"):
        run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=1))


@pytest.mark.parametrize(
    ("has_more", "cursor", "complete"),
    [(False, "", True), (True, "next", False), (False, "next", False)],
)
def test_history_complete_requires_both_terminal_cursor_signals(
    has_more: bool, cursor: str, complete: bool
) -> None:
    query = {"channel": CHANNEL, "limit": "1"}
    adapter, _transport = client(
        lambda call: response(
            call["path"],
            page_payload([message(ts=THREAD_TS)], has_more=has_more, cursor=cursor),
            query=query,
        )
    )
    page = run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=1))
    assert page.complete is complete


def test_mutation_evidence_is_exact_or_explicitly_incomplete() -> None:
    edited = message(ts=THREAD_TS, text="current")
    edited["edited"] = {"user": HUMAN, "ts": "1787471001.000001"}
    query = {"channel": CHANNEL, "limit": "2"}
    adapter, _transport = client(
        lambda call: response(
            call["path"], page_payload([edited]), query=query
        )
    )
    page = run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=2))
    assert page.messages == (
        SlackMessage(
            ts=THREAD_TS,
            author_user_id=HUMAN,
            text="current",
            edited=True,
            created_text=None,
        ),
    )
    assert page.mutation_evidence_complete is False

    previous = message(ts=THREAD_TS, text="created bytes")
    deleted = {
        "type": "message",
        "subtype": "message_deleted",
        "team": WORKSPACE,
        "deleted_ts": THREAD_TS,
        "previous_message": previous,
    }
    adapter, _transport = client(
        lambda call: response(
            call["path"], page_payload([deleted]), query=query
        )
    )
    page = run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=2))
    assert page.messages == (
        SlackMessage(
            ts=THREAD_TS,
            author_user_id=HUMAN,
            text="",
            deleted=True,
            created_text="created bytes",
        ),
    )
    assert page.mutation_evidence_complete is True


def test_message_changed_uses_only_exact_previous_bytes_as_creation_evidence() -> None:
    previous = message(ts=THREAD_TS, text="created bytes")
    current = message(ts=THREAD_TS, text="current bytes")
    current["edited"] = {"user": HUMAN, "ts": "1787471001.000001"}
    changed = {
        "type": "message",
        "subtype": "message_changed",
        "team": WORKSPACE,
        "message": current,
        "previous_message": previous,
    }
    query = {"channel": CHANNEL, "limit": "1"}
    adapter, _transport = client(
        lambda call: response(
            call["path"], page_payload([changed]), query=query
        )
    )

    page = run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=1))

    assert page == HistoryPage(
        messages=(
            SlackMessage(
                ts=THREAD_TS,
                author_user_id=HUMAN,
                text="current bytes",
                edited=True,
                created_text="created bytes",
            ),
        ),
        complete=True,
        mutation_evidence_complete=True,
    )


@pytest.mark.parametrize(
    "mutation",
    ["workspace", "author", "timestamp", "thread", "duplicate_ts"],
)
def test_history_refuses_wrong_identity_or_duplicate_message(mutation: str) -> None:
    first = message(ts=THREAD_TS, user=BOT, text="parent")
    second = message(
        ts="1787471000.000002", text="reply", thread_ts=THREAD_TS
    )
    if mutation == "workspace":
        second["team"] = "T0000000000"
    elif mutation == "author":
        second["user"] = "not-a-user"
    elif mutation == "timestamp":
        second["ts"] = "bad-ts"
    elif mutation == "thread":
        second["thread_ts"] = "1787479999.000001"
    else:
        second["ts"] = THREAD_TS
    query = {"channel": CHANNEL, "ts": THREAD_TS, "limit": "3"}
    adapter, _transport = client(
        lambda call: response(
            call["path"], page_payload([first, second]), query=query
        )
    )
    with pytest.raises(SlackTransportUnavailable, match="^SLACK_TRANSPORT_UNAVAILABLE$"):
        run(adapter.fetch_thread(channel_id=CHANNEL, thread_ts=THREAD_TS, limit=3))


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b'{"ok":true,"ok":false}',
        b"{" + b'"padding":"' + b"x" * MAX_RESPONSE_BYTES + b'"}',
    ],
)
def test_malformed_duplicate_key_and_oversized_json_are_opaque(payload: bytes) -> None:
    query = {"channel": CHANNEL, "limit": "1"}
    adapter, _transport = client(
        lambda call: response(call["path"], payload, query=query)
    )
    with pytest.raises(SlackTransportUnavailable) as caught:
        run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=1))
    assert str(caught.value) == "SLACK_TRANSPORT_UNAVAILABLE"
    assert TOKEN not in str(caught.value)


def test_redirect_and_wrong_channel_argument_refuse_before_trust() -> None:
    query = {"channel": CHANNEL, "limit": "1"}
    adapter, transport = client(
        lambda call: response(
            call["path"],
            page_payload([message(ts=THREAD_TS)]),
            query=query,
            final_url="https://example.invalid/redirect",
        )
    )
    with pytest.raises(SlackTransportUnavailable, match="^SLACK_TRANSPORT_UNAVAILABLE$"):
        run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=1))
    with pytest.raises(SlackTransportUnavailable, match="^SLACK_TRANSPORT_UNAVAILABLE$"):
        run(adapter.fetch_channel_history(channel_id="C0000000000", limit=1))
    assert len(transport.calls) == 1


def test_post_success_returns_only_exact_bound_bot_reply() -> None:
    text = "MASTERMINDA2/1\n{}"

    def handler(call):
        return response(
            call["path"],
            {
                "ok": True,
                "channel": CHANNEL,
                "ts": "1787471000.000003",
                "message": message(
                    ts="1787471000.000003",
                    user=BOT,
                    text=text,
                    thread_ts=THREAD_TS,
                ),
            },
        )

    adapter, transport = client(handler)
    result = run(adapter.post_reply(channel_id=CHANNEL, thread_ts=THREAD_TS, text=text))
    assert result == SlackMessage(
        ts="1787471000.000003",
        author_user_id=BOT,
        text=text,
        thread_ts=THREAD_TS,
    )
    assert transport.calls == [
        {
            "method": "POST",
            "path": "chat.postMessage",
            "token": TOKEN,
            "query": None,
            "json_body": {"channel": CHANNEL, "thread_ts": THREAD_TS, "text": text},
        }
    ]


@pytest.mark.parametrize("field", ["channel", "team", "user", "ts", "thread_ts", "text"])
def test_post_untrustworthy_receipt_is_effect_unknown(field: str) -> None:
    text = "frame"
    payload = {
        "ok": True,
        "channel": CHANNEL,
        "ts": "1787471000.000003",
        "message": message(
            ts="1787471000.000003", user=BOT, text=text, thread_ts=THREAD_TS
        ),
    }
    if field == "channel":
        payload["channel"] = "C0000000000"
    elif field == "team":
        payload["message"]["team"] = "T0000000000"
    elif field == "user":
        payload["message"]["user"] = HUMAN
    elif field == "ts":
        payload["message"]["ts"] = "1787471000.000004"
    elif field == "thread_ts":
        payload["message"]["thread_ts"] = "1787479999.000001"
    else:
        payload["message"]["text"] = "drift"
    adapter, transport = client(
        lambda call: response(call["path"], payload)
    )
    with pytest.raises(SlackEffectUnknown, match="^SLACK_EFFECT_UNKNOWN$"):
        run(adapter.post_reply(channel_id=CHANNEL, thread_ts=THREAD_TS, text=text))
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    ("failure", "error_type", "message_text"),
    [
        (
            SlackTransportUnavailable("private pre-send detail"),
            SlackTransportUnavailable,
            "SLACK_TRANSPORT_UNAVAILABLE",
        ),
        (
            SlackEffectUnknown("private post-send detail"),
            SlackEffectUnknown,
            "SLACK_EFFECT_UNKNOWN",
        ),
        (RuntimeError("ambiguous private detail"), SlackEffectUnknown, "SLACK_EFFECT_UNKNOWN"),
    ],
)
def test_post_failure_mapping_is_opaque_and_never_retries(
    failure: Exception, error_type: type[Exception], message_text: str
) -> None:
    def handler(_call):
        raise failure

    adapter, transport = client(handler)
    with pytest.raises(error_type) as caught:
        run(adapter.post_reply(channel_id=CHANNEL, thread_ts=THREAD_TS, text="frame"))
    assert str(caught.value) == message_text
    assert len(transport.calls) == 1


def test_default_transport_disables_proxies_and_keeps_token_out_of_url(monkeypatch) -> None:
    observed = {}

    class RawResponse:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b'{"ok":true,"messages":[],"has_more":false,"response_metadata":{"next_cursor":""}}'

        def geturl(self):
            return observed["url"]

    class Opener:
        def open(self, request, timeout):
            observed["url"] = request.full_url
            observed["authorization"] = request.get_header("Authorization")
            observed["timeout"] = timeout
            return RawResponse()

    def build_opener(*handlers):
        observed["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    transport = UrllibSlackHttpTransport(timeout_seconds=2)
    result = run(
        transport.request(
            method="GET",
            path="conversations.history",
            token=TOKEN,
            query={"channel": CHANNEL, "limit": "1"},
            json_body=None,
        )
    )
    assert result.status_code == 200
    assert TOKEN not in observed["url"]
    assert TOKEN not in urllib.parse.urlparse(observed["url"]).query
    assert observed["authorization"] == f"Bearer {TOKEN}"
    proxy = next(
        handler for handler in observed["handlers"]
        if isinstance(handler, urllib.request.ProxyHandler)
    )
    assert proxy.proxies == {}


def test_token_never_appears_in_repr_result_exception_url_query_or_logs(caplog) -> None:
    query = {"channel": CHANNEL, "limit": "1"}
    adapter, transport = client(
        lambda call: response(call["path"], b"not json", query=query)
    )
    with pytest.raises(SlackTransportUnavailable) as caught:
        run(adapter.fetch_channel_history(channel_id=CHANNEL, limit=1))
    combined = "\n".join(
        [repr(adapter), str(caught.value), api_url("conversations.history", query), caplog.text]
    )
    assert TOKEN not in combined
    assert TOKEN not in repr(transport.calls[0]["query"])
