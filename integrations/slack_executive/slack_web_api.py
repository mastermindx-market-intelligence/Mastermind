"""Narrow production Slack Web API adapter for outbound SOL_STATE transport.

C1 keeps this boundary deliberately small: fixed Slack HTTPS origin, bounded
history reads/writes, normalized B1 dataclasses, and no Socket Mode or inbound
command behavior. Executive OS remains the sole lifecycle authority.
"""
from __future__ import annotations

from typing import Any

import httpx

from .sol_state import HistoryPage, StateMessage

SLACK_API_ROOT = "https://slack.com/api/"
_DEFAULT_TIMEOUT_SECONDS = 10.0


def _require_success(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        raise RuntimeError("SLACK_API_UNAVAILABLE") from None


def _decode_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload: Any = response.json()
    except ValueError:
        raise RuntimeError("SLACK_API_INVALID_RESPONSE") from None
    if not isinstance(payload, dict):
        raise RuntimeError("SLACK_API_INVALID_RESPONSE")
    return payload


class SlackWebApiStateClient:
    """`SlackStateClient` implementation over the fixed Slack Web API origin."""

    def __init__(
        self,
        *,
        token: str,
        bot_user_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(token, str) or not token:
            raise ValueError("token must be a non-empty string")
        if not isinstance(bot_user_id, str) or not bot_user_id:
            raise ValueError("bot_user_id must be a non-empty string")
        self._bot_user_id = bot_user_id
        self._client = httpx.AsyncClient(
            base_url=SLACK_API_ROOT,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(_DEFAULT_TIMEOUT_SECONDS),
            follow_redirects=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise RuntimeError("SLACK_API_UNAVAILABLE") from None
        _require_success(response)
        return response

    async def fetch_history(self, *, channel_id: str, limit: int) -> HistoryPage:
        if not isinstance(channel_id, str) or not channel_id:
            raise ValueError("channel_id must be a non-empty string")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit must be a positive integer")

        response = await self._request(
            "GET",
            "conversations.history",
            params={"channel": channel_id, "limit": limit},
        )
        payload = _decode_payload(response)
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
            "POST",
            "chat.postMessage",
            json={"channel": channel_id, "text": text},
        )
        payload = _decode_payload(response)
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
            "POST",
            "chat.update",
            json={"channel": channel_id, "ts": message_ts, "text": text},
        )
        payload = _decode_payload(response)
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
