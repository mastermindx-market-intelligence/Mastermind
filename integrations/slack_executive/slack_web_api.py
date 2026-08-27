"""Narrow stdlib-only Slack Web API transport for outbound C1 SOL_STATE.

The production Relay runs under the sealed Executive Python invocation
``-I -S -B``.  Therefore this module deliberately has no third-party runtime
dependency.  It exposes only the existing ``SlackStateClient`` publication
contract plus one small internal transport seam reused by C1 startup identity
qualification.

Security law:
- fixed ``https://slack.com/api/`` origin;
- exact closed method/path allowlist;
- ambient HTTP(S) proxies disabled;
- redirects refused;
- bounded response bytes and JSON;
- raw network/Slack error text never crosses the adapter boundary;
- no inbound/Socket Mode behavior.
"""
from __future__ import annotations

import asyncio
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .sol_state import HistoryPage, StateMessage

SLACK_API_ROOT = "https://slack.com/api/"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 64 * 1024
_ALLOWED_REQUESTS = frozenset(
    {
        ("GET", "conversations.history"),
        ("POST", "chat.postMessage"),
        ("POST", "chat.update"),
        ("POST", "auth.test"),
    }
)


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

    async def aclose(self) -> None: ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


class UrllibSlackHttpTransport:
    """Fixed-origin stdlib HTTPS transport for the four reviewed C1 calls."""

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

    async def aclose(self) -> None:
        return None

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
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("SLACK_API_UNAVAILABLE") from None

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
            raise RuntimeError("SLACK_API_REQUEST_REFUSED")
        if not isinstance(token, str) or not token:
            raise RuntimeError("SLACK_API_REQUEST_REFUSED")
        if normalized_method == "GET" and json_body is not None:
            raise RuntimeError("SLACK_API_REQUEST_REFUSED")
        if normalized_method == "POST" and query:
            raise RuntimeError("SLACK_API_REQUEST_REFUSED")

        url = SLACK_API_ROOT + path
        if query:
            pairs: list[tuple[str, str]] = []
            for key, value in sorted(query.items()):
                if not isinstance(key, str) or not isinstance(value, str):
                    raise RuntimeError("SLACK_API_REQUEST_REFUSED")
                pairs.append((key, value))
            url += "?" + urllib.parse.urlencode(pairs)

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mastermind-C1-SOL-State-Relay/1",
        }
        data: bytes | None = None
        if normalized_method == "POST":
            if json_body is None:
                data = b""
                headers["Content-Type"] = (
                    "application/x-www-form-urlencoded; charset=utf-8"
                )
            else:
                try:
                    data = json.dumps(
                        dict(json_body),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ).encode("utf-8")
                except (TypeError, ValueError):
                    raise RuntimeError("SLACK_API_REQUEST_REFUSED") from None
                headers["Content-Type"] = "application/json; charset=utf-8"

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
        try:
            with opener.open(request, timeout=self._timeout_seconds) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise RuntimeError("SLACK_API_INVALID_RESPONSE")
                response_headers = {
                    str(key).lower(): str(value)
                    for key, value in response.headers.items()
                }
                if any(
                    len(value.encode("utf-8")) > 4096
                    for value in response_headers.values()
                ):
                    raise RuntimeError("SLACK_API_INVALID_RESPONSE")
                content_type = response_headers.get("content-type", "")
                if not content_type.lower().startswith("application/json"):
                    raise RuntimeError("SLACK_API_INVALID_RESPONSE")
                final_url = str(response.geturl())
                if final_url != url:
                    raise RuntimeError("SLACK_API_UNAVAILABLE")
                return SlackHttpResponse(
                    status_code=int(response.status),
                    final_url=final_url,
                    headers=response_headers,
                    body=body,
                )
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("SLACK_API_UNAVAILABLE") from None


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError("SLACK_API_INVALID_RESPONSE")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> object:
    raise RuntimeError("SLACK_API_INVALID_RESPONSE")


def decode_slack_json(response: SlackHttpResponse) -> dict[str, Any]:
    if not isinstance(response, SlackHttpResponse):
        raise RuntimeError("SLACK_API_INVALID_RESPONSE")
    if response.status_code != 200 or len(response.body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("SLACK_API_UNAVAILABLE")
    try:
        payload: Any = json.loads(
            response.body.decode("utf-8"),
            object_pairs_hook=_closed_json_object,
            parse_constant=_reject_json_constant,
        )
    except RuntimeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("SLACK_API_INVALID_RESPONSE") from None
    if not isinstance(payload, dict):
        raise RuntimeError("SLACK_API_INVALID_RESPONSE")
    return payload


class SlackWebApiStateClient:
    """``SlackStateClient`` over the reviewed fixed C1 transport."""

    def __init__(
        self,
        *,
        token: str,
        bot_user_id: str,
        transport: SlackHttpTransport | None = None,
    ) -> None:
        if not isinstance(token, str) or not token:
            raise ValueError("token must be a non-empty string")
        if not isinstance(bot_user_id, str) or not bot_user_id:
            raise ValueError("bot_user_id must be a non-empty string")
        self._token = token
        self._bot_user_id = bot_user_id
        self._transport = transport or UrllibSlackHttpTransport()

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def _request(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> SlackHttpResponse:
        try:
            response = await self._transport.request(
                method=method,
                path=path,
                token=self._token,
                query=query,
                json_body=json_body,
            )
        except Exception:
            raise RuntimeError("SLACK_API_UNAVAILABLE") from None
        if not isinstance(response, SlackHttpResponse):
            raise RuntimeError("SLACK_API_INVALID_RESPONSE")
        if response.status_code != 200:
            raise RuntimeError("SLACK_API_UNAVAILABLE")
        return response

    async def fetch_history(self, *, channel_id: str, limit: int) -> HistoryPage:
        if not isinstance(channel_id, str) or not channel_id:
            raise ValueError("channel_id must be a non-empty string")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit must be a positive integer")

        response = await self._request(
            method="GET",
            path="conversations.history",
            query={"channel": channel_id, "limit": str(limit)},
        )
        payload = decode_slack_json(response)
        if payload.get("ok") is not True:
            raise RuntimeError("SLACK_API_REFUSED")
        raw_messages = payload.get("messages")
        if not isinstance(raw_messages, list):
            raise RuntimeError("SLACK_API_INVALID_RESPONSE")

        messages: list[StateMessage] = []
        for raw in raw_messages:
            if not isinstance(raw, dict):
                raise RuntimeError("SLACK_API_INVALID_RESPONSE")
            ts = raw.get("ts")
            author_user_id = raw.get("user")
            text = raw.get("text")
            if not all(isinstance(value, str) for value in (ts, author_user_id, text)):
                raise RuntimeError("SLACK_API_INVALID_RESPONSE")
            messages.append(
                StateMessage(
                    ts=ts,
                    author_user_id=author_user_id,
                    text=text,
                )
            )

        metadata = payload.get("response_metadata")
        next_cursor = metadata.get("next_cursor") if isinstance(metadata, dict) else None
        complete = payload.get("has_more") is False and not next_cursor
        return HistoryPage(messages=tuple(messages), complete=complete)

    async def create_message(self, *, channel_id: str, text: str) -> StateMessage:
        if not isinstance(channel_id, str) or not channel_id:
            raise ValueError("channel_id must be a non-empty string")
        if not isinstance(text, str) or not text:
            raise ValueError("text must be a non-empty string")

        response = await self._request(
            method="POST",
            path="chat.postMessage",
            json_body={"channel": channel_id, "text": text},
        )
        payload = decode_slack_json(response)
        if payload.get("ok") is not True:
            raise RuntimeError("SLACK_API_REFUSED")
        if payload.get("channel") != channel_id:
            raise RuntimeError("SLACK_API_INVALID_RESPONSE")
        ts = payload.get("ts")
        message = payload.get("message")
        if not isinstance(ts, str) or not isinstance(message, dict):
            raise RuntimeError("SLACK_API_INVALID_RESPONSE")
        if (
            message.get("ts") != ts
            or message.get("user") != self._bot_user_id
            or message.get("text") != text
        ):
            raise RuntimeError("SLACK_API_INVALID_RESPONSE")
        return StateMessage(ts=ts, author_user_id=self._bot_user_id, text=text)

    async def update_message(
        self,
        *,
        channel_id: str,
        message_ts: str,
        text: str,
    ) -> StateMessage:
        if not isinstance(channel_id, str) or not channel_id:
            raise ValueError("channel_id must be a non-empty string")
        if not isinstance(message_ts, str) or not message_ts:
            raise ValueError("message_ts must be a non-empty string")
        if not isinstance(text, str) or not text:
            raise ValueError("text must be a non-empty string")

        response = await self._request(
            method="POST",
            path="chat.update",
            json_body={"channel": channel_id, "ts": message_ts, "text": text},
        )
        payload = decode_slack_json(response)
        if payload.get("ok") is not True:
            raise RuntimeError("SLACK_API_REFUSED")
        if (
            payload.get("channel") != channel_id
            or payload.get("ts") != message_ts
            or payload.get("text") != text
        ):
            raise RuntimeError("SLACK_API_INVALID_RESPONSE")
        return StateMessage(
            ts=message_ts,
            author_user_id=self._bot_user_id,
            text=text,
        )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_RESPONSE_BYTES",
    "SLACK_API_ROOT",
    "SlackHttpResponse",
    "SlackHttpTransport",
    "SlackWebApiStateClient",
    "UrllibSlackHttpTransport",
    "decode_slack_json",
]
