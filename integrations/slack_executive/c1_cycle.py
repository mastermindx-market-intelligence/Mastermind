"""C1 Executive-state to SOL_STATE publication composition.

The one-shot helper is useful for canaries. ``C1RelayService`` adds only the
reviewed in-memory poll/heartbeat decision for a long-lived process: one
startup Slack-history recovery, immediate semantic-change publication and an
unchanged heartbeat. It owns no scheduler database, cursor, queue, retry
ledger, Runtime or message-ts persistence.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from .sol_state import (
    PublicationReceipt,
    build_sol_state_document,
)


class ExecutiveStateReader(Protocol):
    async def read_state(self) -> dict[str, Any]: ...


class StatePublisher(Protocol):
    async def recover(self) -> str | None: ...

    async def publish(
        self,
        executive_state: dict[str, Any] | None,
        *,
        relay_checked_at: datetime,
    ) -> PublicationReceipt: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _read_current(reader: ExecutiveStateReader) -> dict[str, Any] | None:
    try:
        return await reader.read_state()
    except Exception:
        return None


async def run_once(
    *,
    reader: ExecutiveStateReader,
    publisher: StatePublisher,
    now: Callable[[], datetime] = _utc_now,
) -> PublicationReceipt:
    """Read one current Executive snapshot and publish one SOL_STATE update."""

    executive_state = await _read_current(reader)
    checked_at = now()
    return await publisher.publish(
        executive_state,
        relay_checked_at=checked_at,
    )


class C1RelayService:
    """Storeless in-process publication cadence for the C1 Relay."""

    def __init__(
        self,
        *,
        reader: ExecutiveStateReader,
        publisher: StatePublisher,
        heartbeat_seconds: int,
        max_executive_age_seconds: int,
        relay_version: str,
    ) -> None:
        if heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        if max_executive_age_seconds <= 0:
            raise ValueError("max_executive_age_seconds must be positive")
        if not isinstance(relay_version, str) or not relay_version.strip():
            raise ValueError("relay_version must be non-empty")
        self._reader = reader
        self._publisher = publisher
        self._heartbeat_seconds = int(heartbeat_seconds)
        self._max_executive_age_seconds = int(max_executive_age_seconds)
        self._relay_version = relay_version.strip()
        self._last_semantic_hash: str | None = None
        self._last_published_at: datetime | None = None

    async def recover(self) -> str | None:
        """Perform the one required startup bounded Slack-history recovery."""

        return await self._publisher.recover()

    async def poll_once(
        self,
        *,
        checked_at: datetime,
    ) -> PublicationReceipt | None:
        executive_state = await _read_current(self._reader)
        candidate = build_sol_state_document(
            executive_state,
            relay_checked_at=checked_at,
            max_executive_age_seconds=self._max_executive_age_seconds,
            relay_version=self._relay_version,
        )
        semantic_hash = candidate["state_hash"]

        due_to_change = self._last_semantic_hash != semantic_hash
        due_to_heartbeat = (
            self._last_published_at is None
            or (checked_at - self._last_published_at).total_seconds()
            >= self._heartbeat_seconds
        )
        if not due_to_change and not due_to_heartbeat:
            return None

        receipt = await self._publisher.publish(
            executive_state,
            relay_checked_at=checked_at,
        )
        self._last_semantic_hash = semantic_hash
        self._last_published_at = checked_at
        return receipt
