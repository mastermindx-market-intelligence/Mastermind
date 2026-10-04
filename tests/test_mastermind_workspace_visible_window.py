from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest

from control_plane.visible_turn_projection import TurnKey, VisibleTurnProjection
from integrations.mastermind_workspace_content.live_window import (
    ContentDecision,
    LiveWindowError,
    LiveWindowReader,
    validate_visible_window,
)

REF = "managed-window:test-turn"
KEY = TurnKey(
    attempt_id="attempt-1",
    session_epoch_id="epoch-1",
    process_generation_id="generation-1",
    generation_number=1,
    worker_id="worker-1",
    local_turn_id="local-1",
    native_turn_id="native-1",
)
NOW = "2026-09-16T22:00:00+00:00"


class Source:
    def __init__(self) -> None:
        self.projection = VisibleTurnProjection()
        self.grant = self.projection.mint_grant(KEY)
        self.read_count = 0

    def publish(self, source_id: str, text: str, *, state: str = "partial", position: int = 1) -> None:
        method = "item/updated" if state == "partial" else "item/completed"
        self.projection.publish(
            KEY,
            method=method,
            params={
                "item": {
                    "type": "agentMessage",
                    "id": source_id,
                    "sequence": position,
                    "text": text,
                }
            },
            native_turn_id=KEY.native_turn_id,
        )

    async def read(self, cursor: str | None, limit: int):
        self.read_count += 1
        return self.projection.read(
            KEY,
            reader_grant=self.grant,
            cursor=cursor,
            max_items=limit,
        )


def build(source: Source, **overrides) -> LiveWindowReader:
    options = {
        "read_page": source.read,
        "source_ref": REF,
        "expected_scope": (KEY.process_generation_id, KEY.native_turn_id),
        "classify": lambda item: ContentDecision("visible-response", item.text, "VISIBLE_TEXT"),
        "observed_at": lambda: NOW,
        "page_size": 1,
        "max_pages": 8,
    }
    options.update(overrides)
    return LiveWindowReader(**options)


def read(reader: LiveWindowReader) -> dict:
    return json.loads(asyncio.run(reader.read()))


def test_partial_is_replaced_by_completed_same_display_identity() -> None:
    source = Source()
    source.publish("message-a", "Draft")
    first = read(build(source))
    source.publish("message-a", "Corrected final", state="completed")
    final = read(build(source))

    assert first["items"][0]["text"] == "Draft"
    assert final["items"][0]["text"] == "Corrected final"
    assert first["items"][0]["id"] == final["items"][0]["id"]
    assert final["items"][0]["publication_sequence"] > first["items"][0]["publication_sequence"]


def test_small_pages_preserve_unread_item_after_upsert() -> None:
    source = Source()
    source.publish("message-a", "Draft")
    source.publish("message-b", "Other", state="completed", position=2)
    source.publish("message-a", "Final", state="completed")

    document = read(build(source))
    assert [item["text"] for item in document["items"]] == ["Final", "Other"]


def test_withheld_content_is_not_serialized() -> None:
    source = Source()
    source.publish("message-a", "synthetic private body")
    document = read(
        build(source, classify=lambda _item: ContentDecision("withheld", None, "WITHHELD"))
    )

    assert document["items"][0]["text"] is None
    assert "synthetic private body" not in json.dumps(document)


def test_gap_is_explicit_and_history_never_promoted() -> None:
    source = Source()
    source.projection.publish(
        KEY,
        method="item/updated",
        params={"item": {"type": "agentMessage", "id": "broken"}},
        native_turn_id=KEY.native_turn_id,
    )
    document = read(build(source))

    assert document["coverage"] == "GAP_PRESENT"
    assert document["gaps"]
    assert document["history"] == "NOT_PROVEN"
    assert document["acceptance"] == "NOT_PROJECTED"


def test_epoch_change_refuses_mixed_snapshot() -> None:
    source = Source()
    source.publish("message-a", "One")
    source.publish("message-b", "Two", position=2)

    async def changing(cursor: str | None, limit: int):
        page = await source.read(cursor, limit)
        if source.read_count == 2:
            return dataclasses.replace(page, publication_epoch="changed")
        return page

    with pytest.raises(LiveWindowError, match="EPOCH_CHANGED"):
        read(build(source, read_page=changing))


def test_public_document_cannot_enable_send_or_claim_acceptance() -> None:
    document = read(build(Source()))
    document["capabilities"]["send"] = True
    with pytest.raises(LiveWindowError):
        validate_visible_window(document)

    document = read(build(Source()))
    document["acceptance"] = "ACCEPTED"
    with pytest.raises(LiveWindowError):
        validate_visible_window(document)
