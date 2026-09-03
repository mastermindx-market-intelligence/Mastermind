"""Discriminating tests for process-local W3C runtime primitives.

These tests pin the protected W3C-P0 boundary: exact waiter identity is
process-local and compare-delete safe; candidate acquisition/iteration is an
async, bounded, single-flight operation that never falls back to a thread or
executor and always releases owned state on refusal/cancellation.
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from integrations.slack_agent_dialogue import turn_runtime_primitives as primitives


def _key(*, fingerprint: str = "a" * 64, operation_key: str = "w3c-op"):
    return primitives.ActiveWaiterKey(
        parent_fingerprint=fingerprint,
        operation_key=operation_key,
        session_ref_canonical='{"kind":"codex","session_id":"session-1"}',
        target_seat="ceo",
    )


def test_waiter_registry_is_exact_single_registration_and_compare_delete() -> None:
    tokens = iter(("a" * 24, "b" * 24))
    registry = primitives.ActiveWaiterRegistry(token_factory=lambda: next(tokens))
    key = _key()

    first = registry.register(key)
    assert registry.is_active(key) is True
    assert registry.active_count == 1

    with pytest.raises(primitives.ActiveWaiterConflict):
        registry.register(key)
    assert registry.active_count == 1

    stale = primitives.ActiveWaiterRegistration(key=key, token="z" * 24)
    assert registry.unregister(stale) is False
    assert registry.is_active(key) is True

    assert registry.unregister(first) is True
    assert registry.active_count == 0

    second = registry.register(key)
    assert second.token != first.token
    assert registry.unregister(first) is False
    assert registry.is_active(key) is True
    assert registry.unregister(second) is True
    assert registry.active_count == 0


def test_waiter_registry_restart_is_empty_and_hold_cleans_up() -> None:
    async def scenario() -> None:
        registry = primitives.ActiveWaiterRegistry(token_factory=lambda: "q" * 24)
        key = _key(operation_key="hold-op")
        async with registry.hold(key) as registration:
            assert registration.key == key
            assert registry.is_active(key) is True
            assert registry.active_count == 1
        assert registry.is_active(key) is False
        assert registry.active_count == 0

        restarted = primitives.ActiveWaiterRegistry(token_factory=lambda: "r" * 24)
        assert restarted.active_count == 0
        assert restarted.is_active(key) is False

    asyncio.run(scenario())


def test_waiter_key_rejects_noncanonical_or_incomplete_identity() -> None:
    with pytest.raises(primitives.TurnRuntimePrimitiveError, match="WAITER_KEY_INVALID"):
        primitives.ActiveWaiterKey(
            parent_fingerprint="not-a-fingerprint",
            operation_key="w3c-op",
            session_ref_canonical='{"kind":"codex"}',
            target_seat="ceo",
        )
    with pytest.raises(primitives.TurnRuntimePrimitiveError, match="WAITER_KEY_INVALID"):
        primitives.ActiveWaiterKey(
            parent_fingerprint="a" * 64,
            operation_key="w3c-op",
            session_ref_canonical='{"session_id":"session-1", "kind":"codex"}',
            target_seat="ceo",
        )


class _Iterator:
    def __init__(self, values=(), *, gate: asyncio.Event | None = None, fail=False):
        self.values = list(values)
        self.gate = gate
        self.fail = fail
        self.closed = False
        self.started = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("source failure")
        if not self.values:
            raise StopAsyncIteration
        return self.values.pop(0)

    async def aclose(self):
        self.closed = True


def _collector(source, *, maximum=4, timeout=0.2):
    return primitives.AsyncCandidateCollector(
        source=source,
        max_candidates=maximum,
        timeout_seconds=timeout,
        cleanup_timeout_seconds=0.1,
    )


def test_collector_requires_an_async_source_factory_without_invoking_sync_code() -> None:
    calls = 0

    def sync_source():
        nonlocal calls
        calls += 1
        return _Iterator((1,))

    with pytest.raises(TypeError, match="source must be an async callable"):
        _collector(sync_source)
    assert calls == 0


def test_collector_returns_one_immutable_tuple_and_closes_source() -> None:
    async def scenario() -> None:
        iterator = _Iterator((1, 2, 3))

        async def source():
            return iterator

        collector = _collector(source)
        assert await collector.collect() == (1, 2, 3)
        assert iterator.closed is True
        assert collector.inflight is False

    asyncio.run(scenario())


def test_collector_bounds_async_source_acquisition_with_timeout() -> None:
    async def scenario() -> None:
        never = asyncio.Event()

        async def source():
            await never.wait()
            return _Iterator(())

        collector = _collector(source, timeout=0.01)
        with pytest.raises(primitives.CandidateCollectionTimeout):
            await collector.collect()
        assert collector.inflight is False

    asyncio.run(scenario())


def test_collector_timeout_closes_iterator_and_releases_single_flight() -> None:
    async def scenario() -> None:
        gate = asyncio.Event()
        iterator = _Iterator(gate=gate)

        async def source():
            return iterator

        collector = _collector(source, timeout=0.01)
        with pytest.raises(primitives.CandidateCollectionTimeout):
            await collector.collect()
        assert iterator.closed is True
        assert collector.inflight is False

    asyncio.run(scenario())


def test_collector_max_plus_one_refuses_before_returning_partial_candidates() -> None:
    async def scenario() -> None:
        iterator = _Iterator((1, 2, 3))

        async def source():
            return iterator

        collector = _collector(source, maximum=2)
        with pytest.raises(primitives.CandidateCollectionOverflow):
            await collector.collect()
        assert iterator.closed is True
        assert collector.inflight is False

    asyncio.run(scenario())


def test_collector_allows_only_one_inflight_collection_and_later_recovers() -> None:
    async def scenario() -> None:
        gate = asyncio.Event()
        first_iterator = _Iterator(gate=gate)
        later_iterator = _Iterator(("recovered",))
        calls = 0

        async def source():
            nonlocal calls
            calls += 1
            return first_iterator if calls == 1 else later_iterator

        collector = _collector(source, timeout=1.0)
        first = asyncio.create_task(collector.collect())
        await first_iterator.started.wait()
        assert collector.inflight is True

        with pytest.raises(primitives.CandidateCollectionBusy):
            await collector.collect()
        assert calls == 1

        gate.set()
        assert await first == ()
        assert collector.inflight is False
        assert await collector.collect() == ("recovered",)
        assert calls == 2
        assert later_iterator.closed is True

    asyncio.run(scenario())


def test_collector_cancellation_closes_owned_iterator_and_clears_inflight() -> None:
    async def scenario() -> None:
        gate = asyncio.Event()
        iterator = _Iterator(gate=gate)

        async def source():
            return iterator

        collector = _collector(source, timeout=5.0)
        task = asyncio.create_task(collector.collect())
        await iterator.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert iterator.closed is True
        assert collector.inflight is False

    asyncio.run(scenario())


def test_collector_source_failure_is_payload_free_and_next_pass_can_recover() -> None:
    async def scenario() -> None:
        bad = _Iterator(fail=True)
        good = _Iterator(("ok",))
        calls = 0

        async def source():
            nonlocal calls
            calls += 1
            return bad if calls == 1 else good

        collector = _collector(source)
        with pytest.raises(primitives.CandidateCollectionUnavailable) as raised:
            await collector.collect()
        assert str(raised.value) == "CANDIDATE_SOURCE_UNAVAILABLE"
        assert bad.closed is True
        assert collector.inflight is False
        assert await collector.collect() == ("ok",)
        assert good.closed is True

    asyncio.run(scenario())


def test_collector_has_no_thread_or_executor_escape() -> None:
    source = Path(primitives.__file__).read_text(encoding="utf-8")
    assert "asyncio.to_thread" not in source
    assert "run_in_executor" not in source
    assert "concurrent.futures" not in source
    assert "import threading" not in source
    assert inspect.iscoroutinefunction(primitives.AsyncCandidateCollector.collect)
