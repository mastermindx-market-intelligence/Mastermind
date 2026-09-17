"""Typed rehydration of the executive worker broker's observed-turn wire."""

import asyncio
import json

import pytest

from integrations.mastermind_window_reader import broker_window_source
from integrations.mastermind_window_reader.live_window_read import (
    ContentDecision,
    WindowError,
    WindowReader,
)


def wire():
    return {
        "items": [
            {
                "source_item_id": "fixture-item",
                "source_sequence": 1,
                "publication_sequence": 1,
                "state": "partial",
                "text": "Fixture visible text",
                "byte_length": 20,
                "truncated": False,
                "gap": None,
            }
        ],
        "next_cursor": "fixture-cursor",
        "gaps": [
            {
                "from_publication_sequence": 2,
                "to_publication_sequence": 3,
                "reason": "SOURCE_REPORTED_GAP",
            }
        ],
        "terminal": False,
        "publication_epoch": "fixture-epoch",
        "retained_scope": ["fixture-generation", "fixture-native-turn"],
        "resync_required": False,
    }


@pytest.mark.parametrize(
    "missing",
    [
        "items",
        "next_cursor",
        "gaps",
        "terminal",
        "publication_epoch",
        "retained_scope",
        "resync_required",
    ],
)
def test_missing_top_level_key_refuses_whole_window(missing):
    value = wire()
    del value[missing]
    with pytest.raises(WindowError):
        broker_window_source.rehydrate(value)


def test_wrong_type_refuses_whole_window():
    value = wire()
    value["terminal"] = "false"
    with pytest.raises(WindowError):
        broker_window_source.rehydrate(value)


def test_wrong_item_type_refuses_whole_window():
    value = wire()
    value["items"][0]["truncated"] = "false"
    with pytest.raises(WindowError):
        broker_window_source.rehydrate(value)


def test_truncated_true_is_refused_as_unsupported():
    value = wire()
    value["items"][0]["truncated"] = True
    with pytest.raises(WindowError) as raised:
        broker_window_source.rehydrate(value)
    assert str(raised.value) == "TRUNCATION_UNSUPPORTED"


def test_missing_item_key_refuses_whole_window():
    value = wire()
    del value["items"][0]["truncated"]
    with pytest.raises(WindowError):
        broker_window_source.rehydrate(value)


def test_mismatched_retained_scope_refuses_whole_window():
    value = wire()
    value["retained_scope"] = ["other-generation", "other-native-turn"]
    with pytest.raises(WindowError):
        broker_window_source.rehydrate(
            value,
            expected_scope=("fixture-generation", "fixture-native-turn"),
        )


def test_rehydrated_result_is_readable_by_window_reader():
    result = broker_window_source.rehydrate(
        wire(),
        expected_scope=("fixture-generation", "fixture-native-turn"),
    )
    reader = WindowReader(
        read_page=lambda cursor, limit: _read(result, cursor),
        source_ref="managed-window:fixture-visible-turn",
        expected_scope=("fixture-generation", "fixture-native-turn"),
        classify=lambda item: ContentDecision(
            "visible-response", item.text, "VISIBLE_TEXT"
        ),
        now=lambda: "2026-09-17T00:00:00+00:00",
        page_size=1,
        max_pages=1,
    )
    view = json.loads(asyncio.run(reader.read()))
    assert view["items"][0]["text"] == "Fixture visible text"
    assert view["gaps"] == [
        {"first": 2, "last": 3, "reason": "SOURCE_REPORTED_GAP"}
    ]


async def _read(result, cursor):
    assert cursor is None
    return result
