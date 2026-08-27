from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timezone

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


class _Publisher:
    def __init__(self):
        self.calls = []

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
