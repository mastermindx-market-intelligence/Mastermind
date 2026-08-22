"""Deterministic, development-unarmed ``MMX/SOL_STATE_V1`` publisher.

This is an injected-client boundary, not a production Slack installation.  A
real third-party SDK adapter may later live under ``integrations/`` in C1, but
B1 intentionally imports no Slack SDK and contains no token, channel, app,
principal, Socket Mode, inbound command, or host lifecycle behavior.

Slack history is transport evidence used to recover exactly one state message;
it is never copied into a new database or replay cursor.  Executive OS remains
the sole Job/Attempt/Worker/Event lifecycle authority.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from common.executive_hot_state_contract import (
    HOT_STATE_SCHEMA,
    validate_hot_state_document,
)

DISCRIMINATOR = "MMX/SOL_STATE_V1"
SOL_STATE_SCHEMA = "mastermind.sol_state.v1"
MAX_MESSAGE_BYTES = 4500
DEFAULT_MAX_EXECUTIVE_AGE_SECONDS = 120
DEFAULT_HISTORY_LIMIT = 100
DEFAULT_RELAY_VERSION = "mas-108-b1-development"

ERROR_CODES = frozenset(
    {
        "STATE_HISTORY_INCOMPLETE",
        "STATE_MESSAGE_AMBIGUOUS",
        "STATE_PUBLICATION_REFUSED",
        "SOL_STATE_TOO_LARGE",
    }
)
RELAY_DEGRADATION_CODES = frozenset(
    {
        "EXECUTIVE_STATE_INVALID",
        "EXECUTIVE_STATE_STALE",
        "EXECUTIVE_STATE_UNAVAILABLE",
    }
)

class SolStateError(RuntimeError):
    """One fixed, caller-visible publisher refusal code."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown SOL_STATE error code {code!r}")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class StateMessage:
    """Normalized Slack history/write result; no SDK type crosses this seam."""

    ts: str
    author_user_id: str
    text: str


@dataclass(frozen=True)
class HistoryPage:
    """One bounded history result plus proof that the searched window is complete."""

    messages: tuple[StateMessage, ...]
    complete: bool


@dataclass(frozen=True)
class PublicationReceipt:
    action: str
    message_ts: str
    state_hash: str | None
    byte_count: int


class SlackStateClient(Protocol):
    """B1's only outbound client contract, satisfied by deterministic fakes."""

    async def fetch_history(self, *, channel_id: str, limit: int) -> HistoryPage: ...

    async def create_message(self, *, channel_id: str, text: str) -> StateMessage: ...

    async def update_message(
        self, *, channel_id: str, message_ts: str, text: str
    ) -> StateMessage: ...


def _utc_seconds(value: datetime) -> tuple[datetime, str]:
    observed = value
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    observed = observed.astimezone(timezone.utc).replace(microsecond=0)
    return observed, observed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_seconds(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _valid_executive_state(value: Any) -> bool:
    return validate_hot_state_document(value)


def build_sol_state_document(
    executive_state: dict[str, Any] | None,
    *,
    relay_checked_at: datetime,
    max_executive_age_seconds: int = DEFAULT_MAX_EXECUTIVE_AGE_SECONDS,
    relay_version: str = DEFAULT_RELAY_VERSION,
) -> dict[str, Any]:
    """Wrap one current Executive snapshot without caching stale green values.

    B1 has no command transport by construction.  Its wrapper therefore always
    keeps ``do_not_submit=true`` even when the embedded read plane is healthy;
    C1 proves the real production read lane and B2 owns any later command-ready
    transition.
    """

    if max_executive_age_seconds <= 0:
        raise ValueError("max_executive_age_seconds must be positive")
    if not isinstance(relay_version, str) or not relay_version.strip():
        raise ValueError("relay_version must be a non-empty string")
    checked_dt, checked_text = _utc_seconds(relay_checked_at)

    relay_degraded: list[str] = []
    current: dict[str, Any] | None = None
    if executive_state is None:
        relay_degraded.append("EXECUTIVE_STATE_UNAVAILABLE")
    elif not _valid_executive_state(executive_state):
        relay_degraded.append("EXECUTIVE_STATE_INVALID")
    else:
        generated = _parse_utc_seconds(executive_state["generated_at"])
        assert generated is not None
        age_seconds = (checked_dt - generated).total_seconds()
        if age_seconds < 0:
            relay_degraded.append("EXECUTIVE_STATE_INVALID")
        elif age_seconds > max_executive_age_seconds:
            relay_degraded.append("EXECUTIVE_STATE_STALE")
        else:
            # Copy through canonical JSON so caller-owned mutable mappings can
            # never be changed underneath an in-flight publication.
            try:
                current = json.loads(_canonical_json(executive_state))
            except (TypeError, ValueError):
                relay_degraded.append("EXECUTIVE_STATE_INVALID")

    if not set(relay_degraded).issubset(RELAY_DEGRADATION_CODES):
        raise RuntimeError("Relay degradation vocabulary widened")

    if current is None:
        generated_at = checked_text
        state_hash = None
        status = "DEGRADED"
    else:
        generated_at = current["generated_at"]
        state_hash = current["snapshot_hash"]
        status = "DEGRADED" if current["do_not_submit"] or current["degraded"] else "OK"

    return {
        "schema": SOL_STATE_SCHEMA,
        "generated_at": generated_at,
        "relay_checked_at": checked_text,
        "state_hash": state_hash,
        "status": status,
        "executive": current,
        "relay": {
            "state_publisher": "READY",
            "command_transport": "NOT_INSTALLED",
            "reconciliation": "NOT_REQUIRED",
            "version": relay_version.strip(),
        },
        "relay_degraded": sorted(relay_degraded),
        "do_not_submit": True,
    }


def _render_document(document: dict[str, Any]) -> str:
    text = f"{DISCRIMINATOR}\n{_canonical_json(document)}"
    if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise SolStateError("SOL_STATE_TOO_LARGE")
    return text


def render_sol_state(
    executive_state: dict[str, Any] | None,
    *,
    relay_checked_at: datetime,
    max_executive_age_seconds: int = DEFAULT_MAX_EXECUTIVE_AGE_SECONDS,
    relay_version: str = DEFAULT_RELAY_VERSION,
) -> str:
    return _render_document(
        build_sol_state_document(
            executive_state,
            relay_checked_at=relay_checked_at,
            max_executive_age_seconds=max_executive_age_seconds,
            relay_version=relay_version,
        )
    )


def _is_exact_state_message(message: StateMessage, *, bot_user_id: str) -> bool:
    first_line, separator, _rest = message.text.partition("\n")
    return (
        message.author_user_id == bot_user_id
        and separator == "\n"
        and first_line == DISCRIMINATOR
    )


def _valid_write_result(
    message: Any,
    *,
    bot_user_id: str,
    expected_text: str,
    expected_ts: str | None = None,
) -> bool:
    return (
        isinstance(message, StateMessage)
        and isinstance(message.ts, str)
        and 0 < len(message.ts) <= 64
        and (expected_ts is None or message.ts == expected_ts)
        and message.author_user_id == bot_user_id
        and message.text == expected_text
        and _is_exact_state_message(message, bot_user_id=bot_user_id)
    )


class SolStatePublisher:
    """Recover and atomically maintain one bot-authored state message in memory."""

    def __init__(
        self,
        client: SlackStateClient,
        *,
        channel_id: str,
        bot_user_id: str,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        max_executive_age_seconds: int = DEFAULT_MAX_EXECUTIVE_AGE_SECONDS,
        relay_version: str = DEFAULT_RELAY_VERSION,
    ) -> None:
        if not isinstance(channel_id, str) or not channel_id:
            raise ValueError("channel_id must be a non-empty injected value")
        if not isinstance(bot_user_id, str) or not bot_user_id:
            raise ValueError("bot_user_id must be a non-empty injected value")
        if history_limit <= 0:
            raise ValueError("history_limit must be positive")
        self._client = client
        self._channel_id = channel_id
        self._bot_user_id = bot_user_id
        self._history_limit = int(history_limit)
        self._max_executive_age_seconds = int(max_executive_age_seconds)
        self._relay_version = relay_version
        self._publication_lock = asyncio.Lock()
        self._recovered = False
        self._message_ts: str | None = None

    async def _recover_unlocked(self) -> str | None:
        try:
            page = await self._client.fetch_history(
                channel_id=self._channel_id, limit=self._history_limit
            )
        except Exception as exc:
            raise SolStateError("STATE_HISTORY_INCOMPLETE") from exc
        if (
            not isinstance(page, HistoryPage)
            or page.complete is not True
            or not isinstance(page.messages, tuple)
        ):
            raise SolStateError("STATE_HISTORY_INCOMPLETE")
        matches = [
            message
            for message in page.messages
            if isinstance(message, StateMessage)
            and _is_exact_state_message(message, bot_user_id=self._bot_user_id)
        ]
        if len(matches) > 1:
            raise SolStateError("STATE_MESSAGE_AMBIGUOUS")
        recovered_ts = matches[0].ts if matches else None
        if recovered_ts is not None and (
            not isinstance(recovered_ts, str) or not (0 < len(recovered_ts) <= 64)
        ):
            raise SolStateError("STATE_PUBLICATION_REFUSED")
        self._message_ts = recovered_ts
        self._recovered = True
        return self._message_ts

    async def recover(self) -> str | None:
        async with self._publication_lock:
            return await self._recover_unlocked()

    async def publish(
        self,
        executive_state: dict[str, Any] | None,
        *,
        relay_checked_at: datetime,
    ) -> PublicationReceipt:
        async with self._publication_lock:
            document = build_sol_state_document(
                executive_state,
                relay_checked_at=relay_checked_at,
                max_executive_age_seconds=self._max_executive_age_seconds,
                relay_version=self._relay_version,
            )
            text = _render_document(document)
            if not self._recovered:
                await self._recover_unlocked()

            if self._message_ts is None:
                try:
                    message = await self._client.create_message(
                        channel_id=self._channel_id, text=text
                    )
                except Exception as exc:
                    # The remote effect may be unknown.  Force a fresh bounded
                    # history recovery before any later create attempt so an ACK
                    # loss cannot produce a second active state message.
                    self._recovered = False
                    self._message_ts = None
                    raise SolStateError("STATE_PUBLICATION_REFUSED") from exc
                if not _valid_write_result(
                    message,
                    bot_user_id=self._bot_user_id,
                    expected_text=text,
                ):
                    self._recovered = False
                    self._message_ts = None
                    raise SolStateError("STATE_PUBLICATION_REFUSED")
                self._message_ts = message.ts
                action = "created"
            else:
                try:
                    message = await self._client.update_message(
                        channel_id=self._channel_id,
                        message_ts=self._message_ts,
                        text=text,
                    )
                except Exception as exc:
                    raise SolStateError("STATE_PUBLICATION_REFUSED") from exc
                if not _valid_write_result(
                    message,
                    bot_user_id=self._bot_user_id,
                    expected_text=text,
                    expected_ts=self._message_ts,
                ):
                    raise SolStateError("STATE_PUBLICATION_REFUSED")
                action = "updated"

            return PublicationReceipt(
                action=action,
                message_ts=self._message_ts,
                state_hash=document["state_hash"],
                byte_count=len(text.encode("utf-8")),
            )
