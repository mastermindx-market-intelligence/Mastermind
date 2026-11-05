"""Rehydrate the executive broker's JSON-visible read wire to typed results."""

from __future__ import annotations

from typing import Any

from control_plane.visible_turn_projection import GapRecord, ReadResult, VisibleItem
from integrations.mastermind_window_reader.live_window_read import WindowError


_TOP_LEVEL_KEYS = {
    "items",
    "next_cursor",
    "gaps",
    "terminal",
    "publication_epoch",
    "retained_scope",
    "resync_required",
}
_ITEM_KEYS = {
    "source_item_id",
    "source_sequence",
    "publication_sequence",
    "state",
    "text",
    "byte_length",
    "truncated",
    "gap",
}
_GAP_KEYS = {
    "from_publication_sequence",
    "to_publication_sequence",
    "reason",
}
_MAX_SAFE_INTEGER = 2**53 - 1


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise WindowError(code)


def rehydrate(value: Any, *, expected_scope: tuple[str, str] | None = None) -> ReadResult:
    _require(type(value) is dict and set(value) == _TOP_LEVEL_KEYS, "WIRE_SCHEMA")
    _require(type(value["items"]) is list and len(value["items"]) <= 256, "ITEM_BOUND")
    _require(
        type(value["next_cursor"]) is str
        and 0 < len(value["next_cursor"]) <= 2048,
        "CURSOR_INVALID",
    )
    _require(type(value["gaps"]) is list and len(value["gaps"]) <= 256, "GAP_BOUND")
    _require(type(value["terminal"]) is bool, "TERMINAL_INVALID")
    _require(
        type(value["publication_epoch"]) is str
        and 0 < len(value["publication_epoch"]) <= 256,
        "EPOCH_INVALID",
    )
    _require(
        type(value["retained_scope"]) is list
        and len(value["retained_scope"]) == 2
        and all(type(part) is str and 0 < len(part) <= 256 for part in value["retained_scope"]),
        "SCOPE_INVALID",
    )
    _require(type(value["resync_required"]) is bool, "RESYNC_INVALID")
    scope = (value["retained_scope"][0], value["retained_scope"][1])
    if expected_scope is not None:
        _require(
            type(expected_scope) is tuple
            and len(expected_scope) == 2
            and all(type(part) is str for part in expected_scope)
            and scope == expected_scope,
            "SCOPE_MISMATCH",
        )

    items = tuple(_item(item) for item in value["items"])
    gaps = tuple(_gap(gap) for gap in value["gaps"])
    if value["resync_required"] and not gaps:
        raise WindowError("SOURCE_RESYNC_REQUIRED")
    return ReadResult(
        items=items,
        next_cursor=value["next_cursor"],
        gaps=gaps,
        terminal=value["terminal"],
        publication_epoch=value["publication_epoch"],
        retained_scope=scope,
        resync_required=value["resync_required"],
    )


def _item(value: Any) -> VisibleItem:
    _require(type(value) is dict and set(value) == _ITEM_KEYS, "ITEM_INVALID")
    _require(
        type(value["source_item_id"]) is str
        and 0 < len(value["source_item_id"]) <= 256,
        "ITEM_INVALID",
    )
    _require(
        type(value["source_sequence"]) is int
        and 0 <= value["source_sequence"] <= _MAX_SAFE_INTEGER
        and type(value["publication_sequence"]) is int
        and 0 < value["publication_sequence"] <= _MAX_SAFE_INTEGER,
        "ORDER_INVALID",
    )
    _require(value["state"] in ("partial", "completed"), "ITEM_INVALID")
    _require(type(value["text"]) is str, "ITEM_INVALID")
    try:
        byte_length = len(value["text"].encode("utf-8"))
    except UnicodeError:
        raise WindowError("TEXT_INVALID") from None
    _require(
        type(value["byte_length"]) is int
        and value["byte_length"] == byte_length
        and byte_length <= 16384,
        "ITEM_BOUND",
    )
    _require(type(value["truncated"]) is bool, "ITEM_INVALID")
    _require(value["truncated"] is False, "TRUNCATION_UNSUPPORTED")
    _require(value["gap"] is None, "ITEM_INVALID")
    return VisibleItem(
        source_item_id=value["source_item_id"],
        source_sequence=value["source_sequence"],
        state=value["state"],
        text=value["text"],
        byte_length=value["byte_length"],
        publication_sequence=value["publication_sequence"],
    )


def _gap(value: Any) -> GapRecord:
    _require(type(value) is dict and set(value) == _GAP_KEYS, "GAP_INVALID")
    _require(
        type(value["from_publication_sequence"]) is int
        and 0 <= value["from_publication_sequence"] <= _MAX_SAFE_INTEGER
        and type(value["to_publication_sequence"]) is int
        and value["from_publication_sequence"]
        <= value["to_publication_sequence"]
        <= _MAX_SAFE_INTEGER,
        "GAP_INVALID",
    )
    _require(
        type(value["reason"]) is str and 0 < len(value["reason"]) <= 256,
        "GAP_INVALID",
    )
    return GapRecord(
        from_publication_sequence=value["from_publication_sequence"],
        to_publication_sequence=value["to_publication_sequence"],
        reason=value["reason"],
    )
