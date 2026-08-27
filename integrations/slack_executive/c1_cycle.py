"""One-shot C1 Executive-state to SOL_STATE publication composition.

This module is deliberately not a scheduler or service.  It composes the
already-owned CeoIngress diagnostic read with the already-owned storeless
``SolStatePublisher`` exactly once.  If the Executive read is unavailable, C1
publishes an explicit degraded state instead of reusing stale green evidence.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from .sol_state import PublicationReceipt


class ExecutiveStateReader(Protocol):
    async def read_state(self) -> dict[str, Any]: ...


class StatePublisher(Protocol):
    async def publish(
        self,
        executive_state: dict[str, Any] | None,
        *,
        relay_checked_at: datetime,
    ) -> PublicationReceipt: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def run_once(
    *,
    reader: ExecutiveStateReader,
    publisher: StatePublisher,
    now: Callable[[], datetime] = _utc_now,
) -> PublicationReceipt:
    """Read one current Executive snapshot and publish one SOL_STATE update."""

    try:
        executive_state = await reader.read_state()
    except Exception:
        executive_state = None
    checked_at = now()
    return await publisher.publish(
        executive_state,
        relay_checked_at=checked_at,
    )
