from __future__ import annotations

import asyncio
import json

import pytest

from control_plane.visible_turn_projection import TurnKey, VisibleTurnProjection
from integrations.mastermind_workspace_content.live_window import ContentDecision, LiveWindowError
from integrations.mastermind_workspace_content.projection_source import ManagedTurnWindowSource

KEY = TurnKey(
    attempt_id="attempt-1",
    session_epoch_id="epoch-1",
    process_generation_id="generation-1",
    generation_number=1,
    worker_id="worker-1",
    local_turn_id="local-1",
    native_turn_id="native-1",
)
SOURCE_REF = "managed-window:test-turn"


def publish(projection: VisibleTurnProjection, text: str, *, state: str = "partial") -> None:
    projection.publish(
        KEY,
        method="item/updated" if state == "partial" else "item/completed",
        params={
            "item": {
                "type": "agentMessage",
                "id": "message-a",
                "sequence": 1,
                "text": text,
            }
        },
        native_turn_id=KEY.native_turn_id,
    )


def source(projection: VisibleTurnProjection, grant: str) -> ManagedTurnWindowSource:
    return ManagedTurnWindowSource(
        projection=projection,
        key=KEY,
        reader_grant=grant,
        source_ref=SOURCE_REF,
        classify=lambda item: ContentDecision("visible-response", item.text, "VISIBLE_TEXT"),
        observed_at=lambda: "2026-09-16T22:00:00+00:00",
    )


def test_existing_grant_is_consumed_without_minting_or_releasing() -> None:
    projection = VisibleTurnProjection()
    grant = projection.mint_grant(KEY)
    publish(projection, "Draft")
    before = dict(projection._grants)

    document = json.loads(asyncio.run(source(projection, grant).read()))

    assert document["items"][0]["text"] == "Draft"
    assert projection._grants == before


def test_completed_update_replaces_same_display_item() -> None:
    projection = VisibleTurnProjection()
    grant = projection.mint_grant(KEY)
    reader = source(projection, grant)
    publish(projection, "Draft")
    first = json.loads(asyncio.run(reader.read()))
    publish(projection, "Final", state="completed")
    final = json.loads(asyncio.run(reader.read()))

    assert first["items"][0]["id"] == final["items"][0]["id"]
    assert final["items"][0]["text"] == "Final"
    assert final["items"][0]["state"] == "completed"


def test_revoked_existing_grant_is_not_replaced_by_consumer() -> None:
    projection = VisibleTurnProjection()
    grant = projection.mint_grant(KEY)
    publish(projection, "Draft")
    reader = source(projection, grant)
    projection.revoke_grant(grant)

    with pytest.raises(LiveWindowError, match="SOURCE_ACCESS_LOST"):
        asyncio.run(reader.read())
    assert projection.check_grant(grant) is None
