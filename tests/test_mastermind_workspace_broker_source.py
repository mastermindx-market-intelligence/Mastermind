from __future__ import annotations

import asyncio
import json

import pytest

from integrations.mastermind_workspace_content.broker_source import BrokerTurnWindowSource
from integrations.mastermind_workspace_content.live_window import ContentDecision, LiveWindowError

SOURCE = "managed-window:test-turn"
SCOPE = ("generation-1", "native-1")


class Broker:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def observe(self, payload: dict[str, object]):
        self.calls.append(dict(payload))
        if not self.responses:
            raise AssertionError("unexpected observe call")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def item(text: str, *, state: str = "partial", publication: int = 1):
    return {
        "source_item_id": "message-a",
        "source_sequence": 1,
        "publication_sequence": publication,
        "state": state,
        "text": text,
        "byte_length": len(text.encode("utf-8")),
        "truncated": False,
        "gap": None,
    }


def page(*, items=(), cursor="cursor-1", terminal=False, epoch="epoch-1", gaps=()):
    return {
        "items": list(items),
        "next_cursor": cursor,
        "gaps": list(gaps),
        "terminal": terminal,
        "publication_epoch": epoch,
        "retained_scope": list(SCOPE),
        "resync_required": bool(gaps),
    }


def source(broker: Broker) -> BrokerTurnWindowSource:
    return BrokerTurnWindowSource(
        observe=broker.observe,
        attempt="attempt-1",
        epoch="epoch-id-1",
        generation="generation-1",
        turn="turn-1",
        reader_grant="grant-1",
        expected_scope=SCOPE,
        source_ref=SOURCE,
        classify=lambda visible: ContentDecision(
            "visible-response", visible.text, "VISIBLE_TEXT"
        ),
        observed_at=lambda: "2026-09-16T22:00:00+00:00",
        page_size=1,
        max_pages=4,
    )


def read(value: BrokerTurnWindowSource) -> dict:
    return json.loads(asyncio.run(value.read()))


def test_broker_wire_is_consumed_without_control_or_grant_operations() -> None:
    broker = Broker(page(items=[item("Draft")]), page(cursor="cursor-1"))
    document = read(source(broker))

    assert document["items"][0]["text"] == "Draft"
    assert broker.calls == [
        {
            "attempt": "attempt-1",
            "epoch": "epoch-id-1",
            "generation": "generation-1",
            "turn": "turn-1",
            "reader_grant": "grant-1",
            "cursor": None,
            "max_items": 1,
        },
        {
            "attempt": "attempt-1",
            "epoch": "epoch-id-1",
            "generation": "generation-1",
            "turn": "turn-1",
            "reader_grant": "grant-1",
            "cursor": "cursor-1",
            "max_items": 1,
        },
    ]


def test_completed_broker_item_replaces_partial_identity() -> None:
    first_broker = Broker(page(items=[item("Draft")]), page())
    final_broker = Broker(
        page(items=[item("Corrected final", state="completed", publication=2)]),
        page(cursor="cursor-1"),
    )

    first = read(source(first_broker))
    final = read(source(final_broker))

    assert first["items"][0]["id"] == final["items"][0]["id"]
    assert final["items"][0]["text"] == "Corrected final"
    assert final["items"][0]["state"] == "completed"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"unexpected": True}),
        lambda value: value["items"][0].update({"truncated": True}),
        lambda value: value["items"][0].update({"gap": {"reason": "hidden"}}),
        lambda value: value.update({"retained_scope": ["other", "native-1"]}),
    ],
)
def test_broker_response_must_match_exact_observer_contract(mutation) -> None:
    response = page(items=[item("Draft")])
    mutation(response)
    with pytest.raises(LiveWindowError):
        read(source(Broker(response)))


def test_broker_failure_is_typed_without_retry() -> None:
    broker = Broker(RuntimeError("native detail must not escape"))
    with pytest.raises(LiveWindowError, match="SOURCE_READ_REFUSED"):
        read(source(broker))
    assert len(broker.calls) == 1
