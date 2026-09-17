"""Existing-projection adapter for one authorized managed-turn hot window."""
from __future__ import annotations

from collections.abc import Callable

from control_plane.visible_turn_projection import TurnKey, VisibleItem, VisibleTurnProjection
from integrations.mastermind_workspace_content.live_window import (
    ContentDecision,
    LiveWindowError,
    LiveWindowReader,
)


class ManagedTurnWindowSource:
    """Read an existing projection/grant without minting or owning either one."""

    def __init__(
        self,
        *,
        projection: VisibleTurnProjection,
        key: TurnKey,
        reader_grant: str,
        source_ref: str,
        classify: Callable[[VisibleItem], ContentDecision],
        observed_at: Callable[[], str],
        page_size: int = 64,
        max_pages: int = 8,
    ) -> None:
        if not isinstance(projection, VisibleTurnProjection):
            raise TypeError("existing VisibleTurnProjection is required")
        if not isinstance(key, TurnKey):
            raise TypeError("existing TurnKey is required")
        if not isinstance(reader_grant, str) or not reader_grant:
            raise TypeError("existing reader grant is required")
        if projection.check_grant(reader_grant) != key:
            raise LiveWindowError("SOURCE_ACCESS_LOST")
        self._projection = projection
        self._key = key
        self._grant = reader_grant
        self._reader = LiveWindowReader(
            read_page=self._read_page,
            source_ref=source_ref,
            expected_scope=(key.process_generation_id, key.native_turn_id),
            classify=classify,
            observed_at=observed_at,
            page_size=page_size,
            max_pages=max_pages,
        )

    async def _read_page(self, cursor: str | None, limit: int):
        return self._projection.read(
            self._key,
            reader_grant=self._grant,
            cursor=cursor,
            max_items=limit,
        )

    async def read(self) -> bytes:
        if self._projection.check_grant(self._grant) != self._key:
            raise LiveWindowError("SOURCE_ACCESS_LOST")
        return await self._reader.read()

    def is_current(self) -> bool:
        return self._projection.check_grant(self._grant) == self._key


__all__ = ["ManagedTurnWindowSource"]
