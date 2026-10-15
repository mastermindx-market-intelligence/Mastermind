"""Strict adapter for the existing broker's ``ohf-observe-turn`` read result.

The caller owns broker transport, authorization, reader-grant issuance, exact
binding, and provider lifecycle. This module only validates the bounded returned
wire document and projects it through ``LiveWindowReader``.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from control_plane.visible_turn_projection import GapRecord, ReadResult, VisibleItem
from integrations.mastermind_workspace_content.live_window import (
    ContentDecision,
    LiveWindowError,
    LiveWindowReader,
)

_MAX_ID = 256
_ITEM_KEYS = frozenset(
    {
        "source_item_id",
        "source_sequence",
        "publication_sequence",
        "state",
        "text",
        "byte_length",
        "truncated",
        "gap",
    }
)
_RESULT_KEYS = frozenset(
    {
        "items",
        "next_cursor",
        "gaps",
        "terminal",
        "publication_epoch",
        "retained_scope",
        "resync_required",
    }
)
_GAP_KEYS = frozenset(
    {"from_publication_sequence", "to_publication_sequence", "reason"}
)


def _identity(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_ID
        or value != value.strip()
        or any(ord(character) < 0x21 or ord(character) == 0x7F for character in value)
    ):
        raise LiveWindowError(f"{label}_INVALID")
    return value


def _nonnegative(value: object, code: str) -> int:
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise LiveWindowError(code)
    return value


def _parse_result(value: object, *, limit: int) -> ReadResult:
    if not isinstance(value, Mapping) or set(value) != _RESULT_KEYS:
        raise LiveWindowError("BROKER_SCHEMA_INVALID")
    raw_items = value["items"]
    raw_gaps = value["gaps"]
    if (
        type(raw_items) is not list
        or len(raw_items) > limit
        or type(raw_gaps) is not list
        or len(raw_gaps) > 256
    ):
        raise LiveWindowError("BROKER_BOUND")

    items: list[VisibleItem] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping) or set(raw) != _ITEM_KEYS:
            raise LiveWindowError("BROKER_ITEM_INVALID")
        if raw["truncated"] is not False or raw["gap"] is not None:
            raise LiveWindowError("BROKER_ITEM_UNSUPPORTED")
        source_id = _identity(raw["source_item_id"], "BROKER_ITEM")
        source_sequence = _nonnegative(raw["source_sequence"], "BROKER_ORDER_INVALID")
        publication_sequence = _nonnegative(
            raw["publication_sequence"], "BROKER_ORDER_INVALID"
        )
        if publication_sequence < 1:
            raise LiveWindowError("BROKER_ORDER_INVALID")
        state = raw["state"]
        text = raw["text"]
        byte_length = raw["byte_length"]
        if state not in {"partial", "completed"} or not isinstance(text, str):
            raise LiveWindowError("BROKER_ITEM_INVALID")
        try:
            actual_bytes = len(text.encode("utf-8"))
        except UnicodeError:
            raise LiveWindowError("BROKER_ITEM_INVALID") from None
        if type(byte_length) is not int or byte_length != actual_bytes or actual_bytes > 16_384:
            raise LiveWindowError("BROKER_ITEM_BOUND")
        items.append(
            VisibleItem(
                source_item_id=source_id,
                source_sequence=source_sequence,
                state=state,
                text=text,
                byte_length=byte_length,
                publication_sequence=publication_sequence,
            )
        )

    gaps: list[GapRecord] = []
    for raw in raw_gaps:
        if not isinstance(raw, Mapping) or set(raw) != _GAP_KEYS:
            raise LiveWindowError("BROKER_GAP_INVALID")
        first = _nonnegative(
            raw["from_publication_sequence"], "BROKER_GAP_INVALID"
        )
        last = _nonnegative(raw["to_publication_sequence"], "BROKER_GAP_INVALID")
        reason = raw["reason"]
        if first > last or not isinstance(reason, str) or not reason or len(reason) > 128:
            raise LiveWindowError("BROKER_GAP_INVALID")
        gaps.append(GapRecord(first, last, reason))

    next_cursor = value["next_cursor"]
    publication_epoch = value["publication_epoch"]
    retained_scope = value["retained_scope"]
    terminal = value["terminal"]
    resync_required = value["resync_required"]
    if (
        not isinstance(next_cursor, str)
        or not next_cursor
        or len(next_cursor) > 2048
        or not isinstance(publication_epoch, str)
        or not publication_epoch
        or len(publication_epoch) > _MAX_ID
        or type(retained_scope) is not list
        or len(retained_scope) != 2
        or not all(isinstance(item, str) and 0 < len(item) <= _MAX_ID for item in retained_scope)
        or type(terminal) is not bool
        or type(resync_required) is not bool
    ):
        raise LiveWindowError("BROKER_RESULT_INVALID")
    return ReadResult(
        items=tuple(items),
        next_cursor=next_cursor,
        gaps=tuple(gaps),
        terminal=terminal,
        publication_epoch=publication_epoch,
        retained_scope=(retained_scope[0], retained_scope[1]),
        resync_required=resync_required,
    )


class BrokerTurnWindowSource:
    """Read one exact broker-bound turn using an already-issued reader grant."""

    def __init__(
        self,
        *,
        observe: Callable[[dict[str, object]], Awaitable[object]],
        attempt: str,
        epoch: str,
        generation: str,
        turn: str,
        reader_grant: str,
        expected_scope: tuple[str, str],
        source_ref: str,
        classify: Callable[[VisibleItem], ContentDecision],
        observed_at: Callable[[], str],
        page_size: int = 64,
        max_pages: int = 8,
    ) -> None:
        if not callable(observe):
            raise TypeError("existing broker observe callback is required")
        self._observe = observe
        self._attempt = _identity(attempt, "ATTEMPT")
        self._epoch = _identity(epoch, "EPOCH")
        self._generation = _identity(generation, "GENERATION")
        self._turn = _identity(turn, "TURN")
        self._grant = _identity(reader_grant, "GRANT")
        self._reader = LiveWindowReader(
            read_page=self._read_page,
            source_ref=source_ref,
            expected_scope=expected_scope,
            classify=classify,
            observed_at=observed_at,
            page_size=page_size,
            max_pages=max_pages,
        )

    async def _read_page(self, cursor: str | None, limit: int) -> ReadResult:
        payload = {
            "attempt": self._attempt,
            "epoch": self._epoch,
            "generation": self._generation,
            "turn": self._turn,
            "reader_grant": self._grant,
            "cursor": cursor,
            "max_items": limit,
        }
        try:
            result = await self._observe(payload)
        except Exception:
            raise LiveWindowError("SOURCE_READ_REFUSED") from None
        return _parse_result(result, limit=limit)

    async def read(self) -> bytes:
        return await self._reader.read()


__all__ = ["BrokerTurnWindowSource"]
