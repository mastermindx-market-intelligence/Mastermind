from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timedelta, timezone

import pytest

from integrations.slack_executive.sol_state import PublicationReceipt


NOW = datetime(2026, 8, 27, 5, 30, 0, tzinfo=timezone.utc)


def _module():
    try:
        return importlib.import_module("integrations.slack_executive.c1_cycle")
    except ModuleNotFoundError:
        pytest.fail("C1 SOL_STATE cycle is not implemented")


class _Reader:
    def __init__(self, value=None, *, error: Exception | None = None):
        self.value = value
        self.error = error
        self.calls = 0

    async def read_state(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


class _SequenceReader:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    async def read_state(self):
        value = self.values[self.calls]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        return value


class _Publisher:
    def __init__(self):
        self.calls = []
        self.recover_calls = 0

    async def recover(self):
        self.recover_calls += 1
        return "1787800000.000001"

    async def publish(self, executive_state, *, relay_checked_at):
        self.calls.append((executive_state, relay_checked_at))
        return PublicationReceipt(
            action="updated",
            message_ts="1787800000.000001",
            state_hash="a" * 64,
            byte_count=321,
        )


def test_run_once_publishes_fresh_reader_result_with_injected_clock():
    c1_cycle = _module()
    state = {"schema": "mastermind.executive_hot_state.v1", "fixture": "fresh"}
    reader = _Reader(state)
    publisher = _Publisher()

    receipt = asyncio.run(
        c1_cycle.run_once(reader=reader, publisher=publisher, now=lambda: NOW)
    )

    assert reader.calls == 1
    assert publisher.calls == [(state, NOW)]
    assert receipt.action == "updated"


def test_run_once_publishes_degraded_none_when_executive_read_is_unavailable():
    c1_cycle = _module()
    reader = _Reader(error=RuntimeError("EXECUTIVE_STATE_UNAVAILABLE"))
    publisher = _Publisher()

    receipt = asyncio.run(
        c1_cycle.run_once(reader=reader, publisher=publisher, now=lambda: NOW)
    )

    assert reader.calls == 1
    assert publisher.calls == [(None, NOW)]
    assert receipt.state_hash == "a" * 64


def test_service_recovers_once_then_change_immediate_and_unchanged_heartbeat_only():
    c1_cycle = _module()
    reader = _SequenceReader(
        [
            RuntimeError("EXECUTIVE_STATE_UNAVAILABLE"),
            RuntimeError("EXECUTIVE_STATE_UNAVAILABLE"),
            RuntimeError("EXECUTIVE_STATE_UNAVAILABLE"),
            {"schema": "wrong-shape"},
        ]
    )
    publisher = _Publisher()

    async def exercise():
        service = c1_cycle.C1RelayService(
            reader=reader,
            publisher=publisher,
            heartbeat_seconds=60,
            max_executive_age_seconds=120,
            relay_version="c1-test",
        )
        await service.recover()
        first = await service.poll_once(checked_at=NOW)
        skipped = await service.poll_once(checked_at=NOW + timedelta(seconds=30))
        heartbeat = await service.poll_once(checked_at=NOW + timedelta(seconds=60))
        changed = await service.poll_once(checked_at=NOW + timedelta(seconds=75))
        return first, skipped, heartbeat, changed

    first, skipped, heartbeat, changed = asyncio.run(exercise())

    assert publisher.recover_calls == 1
    assert first is not None
    assert skipped is None
    assert heartbeat is not None
    assert changed is not None
    assert [state for state, _when in publisher.calls] == [None, None, {"schema": "wrong-shape"}]
    assert [when for _state, when in publisher.calls] == [
        NOW,
        NOW + timedelta(seconds=60),
        NOW + timedelta(seconds=75),
    ]
