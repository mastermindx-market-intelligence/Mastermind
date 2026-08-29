"""Production-disarmed Slack Web API transport for Agent Dialogue.

The adapter owns no token discovery, service lifecycle, retry, persistence, or
provider enrollment.  A dedicated Agent Relay token is injected in memory and
used only as the Authorization header on three fixed Slack API calls.
"""
from __future__ import annotations

import asyncio
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from integrations.slack_agent_dialogue.engine import (
    HistoryPage,
    SlackEffectUnknown,
    SlackMessage,
    SlackTransportUnavailable,
)

SLACK_API_ROOT = "https://slack.com/api/"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 64 * 1024
_ALLOWED_REQUESTS = frozenset(
    {
        ("GET", "conversations.history"),
        ("GET", "conversations.replies"),
        ("POST", "chat.postMessage"),
    }
)
_WORKSPACE_RE = re.compile(r"\AT[A-Z0-9]{8,31}\Z")
_CHANNEL_RE = re.compile(r"\A[CG][A-Z0-9]{8,31}\Z")
_USER_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_TS_RE = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")
_UNAVAILABLE = "SLACK_TRANSPORT_UNAVAILABLE"
_EFFECT_UNKNOWN = "SLACK_EFFECT_UNKNOWN"


def _unavailable() -> SlackTransportUnavailable:
    return SlackTransportUnavailable(_UNAVAILABLE)


def _effect_unknown() -> SlackEffectUnknown:
    return SlackEffectUnknown(_EFFECT_UNKNOWN)


@dataclass(frozen=True)
class SlackHttpResponse:
    status_code: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes


class SlackHttpTransport(Protocol):
    async def request(
        self,
        *,
        method: str,
        path: str,
        token: str,
        query: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> SlackHttpResponse: ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


def _request_url(path: str, query: Mapping[str, str] | None) -> str:
    if not isinstance(path, str) or not path:
        raise _unavailable()
    url = SLACK_API_ROOT + path
    if query:
        pairs: list[tuple[str, str]] = []
        for key, value in sorted(query.items()):
            if not isinstance(key, str) or not isinstance(value, str):
                raise _unavailable()
            pairs.append((key, value))
        url += "?" + urllib.parse.urlencode(pairs)
    return url


class UrllibSlackHttpTransport:
    """Fixed-origin stdlib transport with no ambient proxy or redirect use."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = float(timeout_seconds)
        self._ssl_context = ssl_context or ssl.create_default_context()

    async def request(
        self,
        *,
        method: str,
        path: str,
        token: str,
        query: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> SlackHttpResponse:
        try:
            return await asyncio.to_thread(
                self._request_sync,
                method=method,
                path=path,
                token=token,
                query=query,
                json_body=json_body,
            )
        except (SlackTransportUnavailable, SlackEffectUnknown):
            raise
        except Exception:
            if str(method).upper() == "POST":
                raise _effect_unknown() from None
            raise _unavailable() from None

    def _request_sync(
        self,
        *,
        method: str,
        path: str,
        token: str,
        query: Mapping[str, str] | None,
        json_body: Mapping[str, Any] | None,
    ) -> SlackHttpResponse:
        normalized_method = str(method).upper()
        if (normalized_method, path) not in _ALLOWED_REQUESTS:
            raise _unavailable()
        if not isinstance(token, str) or not token:
            raise _unavailable()
        if normalized_method == "GET" and json_body is not None:
            raise _unavailable()
        if normalized_method == "POST" and query:
            raise _unavailable()

        url = _request_url(path, query)
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mastermind-Agent-Relay/1",
        }
        data: bytes | None = None
        if normalized_method == "POST":
            if json_body is None:
                raise _unavailable()
            try:
                data = json.dumps(
                    dict(json_body),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            except (TypeError, ValueError):
                raise _unavailable() from None
            headers["Content-Type"] = "application/json; charset=utf-8"

        try:
            request = urllib.request.Request(
                url,
                data=data,
                method=normalized_method,
                headers=headers,
            )
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                _NoRedirectHandler(),
                urllib.request.HTTPSHandler(context=self._ssl_context),
            )
        except Exception:
            raise _unavailable() from None

        try:
            with opener.open(request, timeout=self._timeout_seconds) as raw:
                body = raw.read(MAX_RESPONSE_BYTES + 1)
                raw_headers = {
                    str(key).lower(): str(value) for key, value in raw.headers.items()
                }
                return SlackHttpResponse(
                    status_code=int(raw.status),
                    final_url=str(raw.geturl()),
                    headers=raw_headers,
                    body=body,
                )
        except (SlackTransportUnavailable, SlackEffectUnknown):
            raise
        except Exception:
            if normalized_method == "POST":
                raise _effect_unknown() from None
            raise _unavailable() from None


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ValueError("invalid constant")


def _decode_response(
    response: SlackHttpResponse,
    *,
    expected_url: str,
) -> dict[str, Any]:
    if (
        not isinstance(response, SlackHttpResponse)
        or response.status_code != 200
        or response.final_url != expected_url
        or not isinstance(response.body, bytes)
        or len(response.body) > MAX_RESPONSE_BYTES
    ):
        raise ValueError("invalid response")
    content_type = next(
        (
            str(value)
            for key, value in response.headers.items()
            if str(key).lower() == "content-type"
        ),
        "",
    )
    if not content_type.lower().startswith("application/json"):
        raise ValueError("invalid response")
    try:
        payload: Any = json.loads(
            response.body.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ValueError("invalid response") from None
    if not isinstance(payload, dict):
        raise ValueError("invalid response")
    return payload


def _valid_ts(value: object) -> bool:
    return isinstance(value, str) and _TS_RE.fullmatch(value) is not None


class SlackWebApiDialogueClient:
    """The exact three-method ``SlackDialogueClient`` Web API implementation."""

    def __init__(
        self,
        *,
        token: str,
        workspace_id: str,
        channel_id: str,
        bot_user_id: str,
        transport: SlackHttpTransport | None = None,
    ) -> None:
        if not isinstance(token, str) or not token:
            raise ValueError("token must be non-empty")
        if not isinstance(workspace_id, str) or _WORKSPACE_RE.fullmatch(workspace_id) is None:
            raise ValueError("invalid workspace_id")
        if not isinstance(channel_id, str) or _CHANNEL_RE.fullmatch(channel_id) is None:
            raise ValueError("invalid channel_id")
        if not isinstance(bot_user_id, str) or _USER_RE.fullmatch(bot_user_id) is None:
            raise ValueError("invalid bot_user_id")
        self._token = token
        self._workspace_id = workspace_id
        self._channel_id = channel_id
        self._bot_user_id = bot_user_id
        self._transport = transport or UrllibSlackHttpTransport()

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(workspace_id={self._workspace_id!r}, "
            f"channel_id={self._channel_id!r}, bot_user_id={self._bot_user_id!r})"
        )

    def _require_channel(self, channel_id: str) -> None:
        if channel_id != self._channel_id:
            raise _unavailable()

    @staticmethod
    def _require_limit(limit: int) -> None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise _unavailable()

    async def _get(self, *, path: str, query: Mapping[str, str]) -> dict[str, Any]:
        expected_url = _request_url(path, query)
        try:
            response = await self._transport.request(
                method="GET",
                path=path,
                token=self._token,
                query=query,
                json_body=None,
            )
            payload = _decode_response(response, expected_url=expected_url)
        except Exception:
            raise _unavailable() from None
        if payload.get("ok") is not True:
            raise _unavailable()
        return payload

    async def _post(self, *, json_body: Mapping[str, Any]) -> dict[str, Any]:
        path = "chat.postMessage"
        try:
            response = await self._transport.request(
                method="POST",
                path=path,
                token=self._token,
                query=None,
                json_body=json_body,
            )
        except SlackTransportUnavailable:
            raise _unavailable() from None
        except SlackEffectUnknown:
            raise _effect_unknown() from None
        except Exception:
            raise _effect_unknown() from None
        try:
            payload = _decode_response(response, expected_url=_request_url(path, None))
            if payload.get("ok") is not True:
                raise ValueError("untrusted write response")
            return payload
        except Exception:
            raise _effect_unknown() from None

    def _standard_message(
        self,
        raw: Mapping[str, Any],
    ) -> tuple[SlackMessage, bool]:
        if raw.get("type") != "message" or raw.get("team") != self._workspace_id:
            raise ValueError("invalid message")
        ts = raw.get("ts")
        user = raw.get("user")
        text = raw.get("text")
        thread_ts = raw.get("thread_ts")
        if (
            not _valid_ts(ts)
            or not isinstance(user, str)
            or _USER_RE.fullmatch(user) is None
            or not isinstance(text, str)
            or (thread_ts is not None and not _valid_ts(thread_ts))
        ):
            raise ValueError("invalid message")
        if raw.get("bot_id") is not None and user != self._bot_user_id:
            raise ValueError("invalid bot identity")
        edited_raw = raw.get("edited")
        edited = edited_raw is not None
        if edited:
            if (
                not isinstance(edited_raw, Mapping)
                or not isinstance(edited_raw.get("user"), str)
                or _USER_RE.fullmatch(str(edited_raw["user"])) is None
                or not _valid_ts(edited_raw.get("ts"))
            ):
                raise ValueError("invalid edit evidence")
        return (
            SlackMessage(
                ts=str(ts),
                author_user_id=user,
                text=text,
                thread_ts=str(thread_ts) if thread_ts is not None else None,
                edited=edited,
                created_text=None,
            ),
            not edited,
        )

    def _parse_message(self, raw: Any) -> tuple[SlackMessage, bool]:
        if not isinstance(raw, Mapping):
            raise ValueError("invalid message")
        subtype = raw.get("subtype")
        if subtype == "message_deleted":
            if raw.get("team") != self._workspace_id:
                raise ValueError("invalid deletion")
            previous = raw.get("previous_message")
            if not isinstance(previous, Mapping):
                raise ValueError("incomplete deletion evidence")
            prior, prior_complete = self._standard_message(previous)
            deleted_ts = raw.get("deleted_ts")
            if not prior_complete or deleted_ts != prior.ts:
                raise ValueError("invalid deletion evidence")
            return (
                SlackMessage(
                    ts=prior.ts,
                    author_user_id=prior.author_user_id,
                    text="",
                    thread_ts=prior.thread_ts,
                    deleted=True,
                    created_text=prior.text,
                ),
                True,
            )
        if subtype == "message_changed":
            current = raw.get("message")
            if raw.get("team") != self._workspace_id or not isinstance(current, Mapping):
                raise ValueError("invalid change evidence")
            current_message, _current_complete = self._standard_message(current)
            previous = raw.get("previous_message")
            if previous is None:
                return (
                    SlackMessage(
                        ts=current_message.ts,
                        author_user_id=current_message.author_user_id,
                        text=current_message.text,
                        thread_ts=current_message.thread_ts,
                        edited=True,
                        created_text=None,
                    ),
                    False,
                )
            if not isinstance(previous, Mapping):
                raise ValueError("invalid change evidence")
            prior, prior_complete = self._standard_message(previous)
            if (
                not prior_complete
                or prior.ts != current_message.ts
                or prior.author_user_id != current_message.author_user_id
                or prior.thread_ts != current_message.thread_ts
            ):
                raise ValueError("invalid change evidence")
            return (
                SlackMessage(
                    ts=current_message.ts,
                    author_user_id=current_message.author_user_id,
                    text=current_message.text,
                    thread_ts=current_message.thread_ts,
                    edited=True,
                    created_text=prior.text,
                ),
                True,
            )
        return self._standard_message(raw)

    def _history_page(
        self,
        payload: Mapping[str, Any],
        *,
        limit: int,
        thread_ts: str | None,
    ) -> HistoryPage:
        raw_messages = payload.get("messages")
        has_more = payload.get("has_more")
        metadata = payload.get("response_metadata")
        if (
            not isinstance(raw_messages, list)
            or len(raw_messages) > limit
            or not isinstance(has_more, bool)
            or not isinstance(metadata, Mapping)
            or not isinstance(metadata.get("next_cursor"), str)
        ):
            raise _unavailable()
        messages: list[SlackMessage] = []
        mutation_complete = True
        seen: set[str] = set()
        try:
            for raw in raw_messages:
                parsed, evidence_complete = self._parse_message(raw)
                if parsed.ts in seen:
                    raise ValueError("duplicate timestamp")
                seen.add(parsed.ts)
                messages.append(parsed)
                mutation_complete = mutation_complete and evidence_complete
            if thread_ts is not None:
                parents = [message for message in messages if message.ts == thread_ts]
                if len(parents) != 1 or parents[0].thread_ts not in {None, thread_ts}:
                    raise ValueError("thread parent mismatch")
                if any(
                    message.ts != thread_ts and message.thread_ts != thread_ts
                    for message in messages
                ):
                    raise ValueError("thread reply mismatch")
        except (TypeError, ValueError):
            raise _unavailable() from None
        complete = has_more is False and metadata["next_cursor"] == ""
        return HistoryPage(
            messages=tuple(messages),
            complete=complete,
            mutation_evidence_complete=mutation_complete,
        )

    async def fetch_channel_history(
        self, *, channel_id: str, limit: int
    ) -> HistoryPage:
        self._require_channel(channel_id)
        self._require_limit(limit)
        payload = await self._get(
            path="conversations.history",
            query={"channel": channel_id, "limit": str(limit)},
        )
        return self._history_page(payload, limit=limit, thread_ts=None)

    async def fetch_thread(
        self, *, channel_id: str, thread_ts: str, limit: int
    ) -> HistoryPage:
        self._require_channel(channel_id)
        self._require_limit(limit)
        if not _valid_ts(thread_ts):
            raise _unavailable()
        payload = await self._get(
            path="conversations.replies",
            query={"channel": channel_id, "ts": thread_ts, "limit": str(limit)},
        )
        return self._history_page(payload, limit=limit, thread_ts=thread_ts)

    async def post_reply(
        self, *, channel_id: str, thread_ts: str, text: str
    ) -> SlackMessage:
        self._require_channel(channel_id)
        if not _valid_ts(thread_ts) or not isinstance(text, str) or not text:
            raise _unavailable()
        payload = await self._post(
            json_body={"channel": channel_id, "thread_ts": thread_ts, "text": text}
        )
        try:
            if payload.get("channel") != self._channel_id:
                raise ValueError("wrong channel")
            raw = payload.get("message")
            if not isinstance(raw, Mapping):
                raise ValueError("missing message")
            parsed, evidence_complete = self._parse_message(raw)
            if (
                payload.get("ts") != parsed.ts
                or parsed.author_user_id != self._bot_user_id
                or parsed.thread_ts != thread_ts
                or parsed.text != text
                or parsed.edited
                or parsed.deleted
                or not evidence_complete
            ):
                raise ValueError("untrusted write receipt")
            return parsed
        except Exception:
            raise _effect_unknown() from None


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_RESPONSE_BYTES",
    "SLACK_API_ROOT",
    "SlackHttpResponse",
    "SlackHttpTransport",
    "SlackWebApiDialogueClient",
    "UrllibSlackHttpTransport",
]
