"""Bounded read projection for one existing managed turn's visible hot window.

This module owns no provider session, reader grant, transcript history, lifecycle,
authorization, queue, or persistence.  The caller supplies one already-qualified
page reader plus the existing content owner's classification decision.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from control_plane.visible_turn_projection import ProjectionError, ReadResult, VisibleItem

SCHEMA = "mastermind.workspace.visible_window.v1"
MAX_SAFE_INTEGER = 2**53 - 1
MAX_WINDOW_ITEMS = 256
MAX_WINDOW_TEXT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 1_200_000
_SOURCE_REF = re.compile(r"\Amanaged-window:[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_HEX_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")


class LiveWindowError(ValueError):
    """The supplied owner result cannot support the claimed workspace view."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise LiveWindowError(code)


def _timestamp(value: object) -> str:
    _require(isinstance(value, str) and 0 < len(value) <= 50, "TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise LiveWindowError("TIME_INVALID") from None
    _require(parsed.tzinfo is not None, "TIME_INVALID")
    return value


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ContentDecision:
    """One existing content owner's display decision for a visible source item."""

    kind: str
    text: str | None
    representation: str


class LiveWindowReader:
    """Compose one source-qualified, request-local visible-window document."""

    def __init__(
        self,
        *,
        read_page: Callable[[str | None, int], Awaitable[ReadResult]],
        source_ref: str,
        expected_scope: tuple[str, str],
        classify: Callable[[VisibleItem], ContentDecision],
        observed_at: Callable[[], str],
        page_size: int = 64,
        max_pages: int = 8,
    ) -> None:
        if not callable(read_page) or not callable(classify) or not callable(observed_at):
            raise TypeError("existing read and content owners are required")
        _require(
            isinstance(source_ref, str)
            and _SOURCE_REF.fullmatch(source_ref) is not None
            and ".." not in source_ref,
            "SOURCE_INVALID",
        )
        _require(
            type(expected_scope) is tuple
            and len(expected_scope) == 2
            and all(type(value) is str and 0 < len(value) <= 256 for value in expected_scope),
            "SCOPE_INVALID",
        )
        _require(type(page_size) is int and 1 <= page_size <= 64, "BOUND_INVALID")
        _require(type(max_pages) is int and 1 <= max_pages <= 16, "BOUND_INVALID")
        self._read_page = read_page
        self._source_ref = source_ref
        self._expected_scope = expected_scope
        self._classify = classify
        self._observed_at = observed_at
        self._page_size = page_size
        self._max_pages = max_pages

    async def read(self) -> bytes:
        cursor: str | None = None
        epoch: str | None = None
        terminal = False
        items: dict[str, VisibleItem] = {}
        gaps: set[tuple[int, int]] = set()
        coverage = "OBSERVED_WINDOW"

        for _page_number in range(self._max_pages):
            try:
                page = await self._read_page(cursor, self._page_size)
            except ProjectionError:
                raise LiveWindowError("SOURCE_READ_REFUSED") from None
            _require(isinstance(page, ReadResult), "SOURCE_INVALID")
            _require(page.retained_scope == self._expected_scope, "SCOPE_MISMATCH")
            _require(type(page.terminal) is bool and type(page.resync_required) is bool, "SOURCE_INVALID")
            _require(isinstance(page.publication_epoch, str) and 0 < len(page.publication_epoch) <= 256, "EPOCH_INVALID")
            if epoch is None:
                epoch = page.publication_epoch
            _require(epoch == page.publication_epoch, "EPOCH_CHANGED")
            if terminal:
                _require(page.terminal, "TERMINAL_REGRESSED")
            terminal = page.terminal
            _require(type(page.items) is tuple and len(page.items) <= self._page_size, "SOURCE_BOUND")
            _require(type(page.gaps) is tuple and len(page.gaps) <= MAX_WINDOW_ITEMS, "GAP_BOUND")
            _require(isinstance(page.next_cursor, str) and 0 < len(page.next_cursor) <= 2048, "CURSOR_INVALID")

            for gap in page.gaps:
                _require(
                    type(gap.from_publication_sequence) is int
                    and type(gap.to_publication_sequence) is int
                    and 0 <= gap.from_publication_sequence <= gap.to_publication_sequence <= MAX_SAFE_INTEGER,
                    "GAP_INVALID",
                )
                gaps.add((gap.from_publication_sequence, gap.to_publication_sequence))
            _require(len(gaps) <= MAX_WINDOW_ITEMS, "GAP_BOUND")
            if page.resync_required and not page.gaps:
                raise LiveWindowError("SOURCE_RESYNC_REQUIRED")

            for item in page.items:
                _require(isinstance(item, VisibleItem), "ITEM_INVALID")
                _require(isinstance(item.source_item_id, str) and 0 < len(item.source_item_id) <= 256, "ITEM_INVALID")
                _require(
                    type(item.source_sequence) is int
                    and 0 <= item.source_sequence <= MAX_SAFE_INTEGER
                    and type(item.publication_sequence) is int
                    and 0 < item.publication_sequence <= MAX_SAFE_INTEGER,
                    "ORDER_INVALID",
                )
                _require(item.state in {"partial", "completed"} and isinstance(item.text, str), "ITEM_INVALID")
                try:
                    byte_length = len(item.text.encode("utf-8"))
                except UnicodeError:
                    raise LiveWindowError("TEXT_INVALID") from None
                _require(type(item.byte_length) is int and item.byte_length == byte_length <= 16_384, "ITEM_BOUND")
                previous = items.get(item.source_item_id)
                if previous is not None:
                    _require(item.publication_sequence >= previous.publication_sequence, "SOURCE_ORDER_REGRESSED")
                    if item.publication_sequence == previous.publication_sequence:
                        _require(item == previous, "ITEM_CONFLICT")
                items[item.source_item_id] = item
                _require(len(items) <= MAX_WINDOW_ITEMS, "WINDOW_BOUND")

            if not page.items:
                break
            _require(page.next_cursor != cursor, "CURSOR_STALLED")
            cursor = page.next_cursor
        else:
            coverage = "READ_LIMIT_REACHED"

        if gaps:
            coverage = "GAP_PRESENT"
        _require(epoch is not None, "EPOCH_INVALID")

        public_items: list[dict[str, object]] = []
        total_text_bytes = 0
        for item in sorted(items.values(), key=lambda value: (value.source_sequence, value.publication_sequence)):
            decision = self._classify(item)
            _require(type(decision) is ContentDecision, "CONTENT_DECISION_REQUIRED")
            _require(decision.kind in {"visible-response", "withheld"}, "CONTENT_KIND_REFUSED")
            if decision.kind == "withheld":
                _require(decision.text is None and decision.representation == "WITHHELD", "CONTENT_DECISION_INVALID")
                text = None
                text_digest = None
            else:
                _require(
                    isinstance(decision.text, str)
                    and decision.representation in {"VISIBLE_TEXT", "FILTERED_VISIBLE_TEXT"},
                    "CONTENT_DECISION_INVALID",
                )
                if decision.representation == "VISIBLE_TEXT":
                    _require(decision.text == item.text, "FALSE_VERBATIM")
                text = decision.text
                try:
                    text_bytes = len(text.encode("utf-8"))
                except UnicodeError:
                    raise LiveWindowError("TEXT_INVALID") from None
                total_text_bytes += text_bytes
                _require(text_bytes <= 16_384 and total_text_bytes <= MAX_WINDOW_TEXT_BYTES, "TEXT_BOUND")
                text_digest = _digest(text)
            display_id = _digest(f"{self._source_ref}\0{epoch}\0{item.source_item_id}")
            public_items.append(
                {
                    "id": f"visible:{display_id}",
                    "source_sequence": item.source_sequence,
                    "publication_sequence": item.publication_sequence,
                    "state": item.state,
                    "kind": decision.kind,
                    "text": text,
                    "representation": decision.representation,
                    "display_sha256": text_digest,
                }
            )

        document = {
            "schema": SCHEMA,
            "source_ref": self._source_ref,
            "scope": "one-managed-turn-window",
            "observed_at": _timestamp(self._observed_at()),
            "epoch": _digest(epoch),
            "terminal": terminal,
            "coverage": coverage,
            "history": "NOT_PROVEN",
            "acceptance": "NOT_PROJECTED",
            "capabilities": {"send": False, "provider_control": False, "history": False},
            "items": public_items,
            "gaps": [
                {"first": first, "last": last, "reason": "SOURCE_REPORTED_GAP"}
                for first, last in sorted(gaps)
            ],
        }
        clean = validate_visible_window(document)
        encoded = json.dumps(clean, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
        _require(len(encoded) <= MAX_OUTPUT_BYTES, "RESPONSE_BOUND")
        return encoded


def validate_visible_window(value: object) -> dict[str, object]:
    """Validate the public wire shape without authenticating its source."""

    expected_keys = {
        "schema",
        "source_ref",
        "scope",
        "observed_at",
        "epoch",
        "terminal",
        "coverage",
        "history",
        "acceptance",
        "capabilities",
        "items",
        "gaps",
    }
    _require(type(value) is dict and set(value) == expected_keys, "WINDOW_SCHEMA")
    assert isinstance(value, dict)
    _require(value["schema"] == SCHEMA, "WINDOW_SCHEMA")
    source_ref = value["source_ref"]
    _require(
        isinstance(source_ref, str) and _SOURCE_REF.fullmatch(source_ref) is not None and ".." not in source_ref,
        "SOURCE_INVALID",
    )
    _require(value["scope"] == "one-managed-turn-window", "CLAIM_REFUSED")
    _timestamp(value["observed_at"])
    _require(isinstance(value["epoch"], str) and _HEX_DIGEST.fullmatch(value["epoch"]) is not None, "EPOCH_INVALID")
    _require(type(value["terminal"]) is bool, "SOURCE_INVALID")
    _require(value["coverage"] in {"OBSERVED_WINDOW", "READ_LIMIT_REACHED", "GAP_PRESENT"}, "COVERAGE_INVALID")
    _require(value["history"] == "NOT_PROVEN" and value["acceptance"] == "NOT_PROJECTED", "CLAIM_REFUSED")
    capabilities = value["capabilities"]
    _require(
        type(capabilities) is dict
        and set(capabilities) == {"send", "provider_control", "history"}
        and all(flag is False for flag in capabilities.values()),
        "CAPABILITY_REFUSED",
    )
    public_items = value["items"]
    _require(type(public_items) is list and len(public_items) <= MAX_WINDOW_ITEMS, "ITEM_BOUND")
    seen_ids: set[str] = set()
    total_text_bytes = 0
    for item in public_items:
        _require(
            type(item) is dict
            and set(item)
            == {
                "id",
                "source_sequence",
                "publication_sequence",
                "state",
                "kind",
                "text",
                "representation",
                "display_sha256",
            },
            "ITEM_INVALID",
        )
        item_id = item["id"]
        _require(
            isinstance(item_id, str)
            and re.fullmatch(r"visible:[0-9a-f]{64}", item_id) is not None
            and item_id not in seen_ids,
            "ITEM_ID_INVALID",
        )
        seen_ids.add(item_id)
        _require(
            type(item["source_sequence"]) is int
            and 0 <= item["source_sequence"] <= MAX_SAFE_INTEGER
            and type(item["publication_sequence"]) is int
            and 0 < item["publication_sequence"] <= MAX_SAFE_INTEGER,
            "ORDER_INVALID",
        )
        _require(item["state"] in {"partial", "completed"}, "ITEM_INVALID")
        _require(item["kind"] in {"visible-response", "withheld"}, "ITEM_INVALID")
        if item["kind"] == "withheld":
            _require(
                item["text"] is None
                and item["display_sha256"] is None
                and item["representation"] == "WITHHELD",
                "CONTENT_REFUSED",
            )
        else:
            _require(
                isinstance(item["text"], str)
                and item["representation"] in {"VISIBLE_TEXT", "FILTERED_VISIBLE_TEXT"},
                "CONTENT_INVALID",
            )
            try:
                item_bytes = len(item["text"].encode("utf-8"))
            except UnicodeError:
                raise LiveWindowError("TEXT_INVALID") from None
            total_text_bytes += item_bytes
            _require(
                item_bytes <= 16_384
                and total_text_bytes <= MAX_WINDOW_TEXT_BYTES
                and item["display_sha256"] == _digest(item["text"]),
                "TEXT_BOUND",
            )
    public_gaps = value["gaps"]
    _require(type(public_gaps) is list and len(public_gaps) <= MAX_WINDOW_ITEMS, "GAP_BOUND")
    for gap in public_gaps:
        _require(
            type(gap) is dict
            and set(gap) == {"first", "last", "reason"}
            and gap["reason"] == "SOURCE_REPORTED_GAP"
            and type(gap["first"]) is int
            and type(gap["last"]) is int
            and 0 <= gap["first"] <= gap["last"] <= MAX_SAFE_INTEGER,
            "GAP_INVALID",
        )
    _require(not public_gaps or value["coverage"] == "GAP_PRESENT", "COVERAGE_INVALID")
    return json.loads(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
