"""Discriminating tests for process-local W3C runtime primitives.

These tests pin the protected W3C-P0 boundary: exact waiter identity is
process-local and compare-delete safe; candidate acquisition/iteration is an
async, bounded, single-flight operation that never falls back to a thread or
executor and always releases owned state on refusal/cancellation.
"""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
from pathlib import Path

import pytest

from integrations.slack_agent_dialogue import runtime as relay_runtime
from integrations.slack_agent_dialogue import turn_runtime_primitives as primitives


def _key(*, fingerprint: str = "a" * 64, operation_key: str = "w3c-op"):
    return primitives.ActiveWaiterKey(
        parent_fingerprint=fingerprint,
        operation_key=operation_key,
        session_ref_canonical="asd-session-exec-job-200",
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


def test_waiter_registry_never_reissues_a_process_lifetime_token() -> None:
    registry = primitives.ActiveWaiterRegistry(token_factory=lambda: "u" * 24)
    key = _key(operation_key="token-reuse-op")
    first = registry.register(key)
    assert registry.unregister(first) is True

    second = registry.register(key)
    assert second.token != first.token
    assert registry.unregister(first) is False
    assert registry.is_active(key) is True
    assert registry.unregister(second) is True
    assert registry.active_count == 0


@pytest.mark.parametrize(
    "changed",
    [
        {"parent_fingerprint": "b" * 64},
        {"operation_key": "w3c-other-op"},
        {"session_ref_canonical": "asd-session-exec-job-201"},
        {"target_seat": "coo"},
    ],
)
def test_waiter_registry_identity_includes_every_frozen_key_component(changed) -> None:
    exact = _key()
    different = primitives.ActiveWaiterKey(
        parent_fingerprint=changed.get(
            "parent_fingerprint", exact.parent_fingerprint
        ),
        operation_key=changed.get("operation_key", exact.operation_key),
        session_ref_canonical=changed.get(
            "session_ref_canonical", exact.session_ref_canonical
        ),
        target_seat=changed.get("target_seat", exact.target_seat),
    )
    registry = primitives.ActiveWaiterRegistry(token_factory=lambda: "e" * 24)
    registration = registry.register(exact)

    assert registry.is_active(exact) is True
    assert registry.is_active(different) is False
    assert registry.unregister(registration) is True


def test_waiter_key_accepts_actual_v2_session_ref_from_validated_parent() -> None:
    from tests.test_company_dialogue_runtime_binding import parent

    exact_parent = parent()
    key = primitives.ActiveWaiterKey.from_parent(
        exact_parent,
        target_seat="ceo",
    )

    assert key == primitives.ActiveWaiterKey(
        parent_fingerprint=exact_parent["fingerprint"],
        operation_key=exact_parent["operation_key"],
        session_ref_canonical=exact_parent["session_ref"],
        target_seat="ceo",
    )


def test_waiter_key_rejects_noncanonical_or_incomplete_identity() -> None:
    with pytest.raises(primitives.TurnRuntimePrimitiveError, match="WAITER_KEY_INVALID"):
        primitives.ActiveWaiterKey(
            parent_fingerprint="not-a-fingerprint",
            operation_key="w3c-op",
            session_ref_canonical="asd-session-exec-job-200",
            target_seat="ceo",
        )
    with pytest.raises(primitives.TurnRuntimePrimitiveError, match="WAITER_KEY_INVALID"):
        primitives.ActiveWaiterKey(
            parent_fingerprint="a" * 64,
            operation_key="w3c-op",
            session_ref_canonical="not a session ref",
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


class _CollectorProbe:
    def __init__(self, *, result=(), error: Exception | None = None, gate=None):
        self.result = tuple(result)
        self.error = error
        self.gate = gate
        self.calls = 0
        self.started = asyncio.Event()

    async def collect(self):
        self.calls += 1
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        return self.result


def _runtime_with_collector(collector: _CollectorProbe):
    runtime = object.__new__(relay_runtime.AgentRelayTurnRuntime)
    runtime._candidate_collector = collector
    return runtime


def test_agent_relay_runtime_source_consumes_the_accepted_collector() -> None:
    source = Path(relay_runtime.__file__).read_text(encoding="utf-8")
    assert "from collections.abc import AsyncIterator, Awaitable, Callable" in source
    assert "from integrations.slack_agent_dialogue.turn_runtime_primitives import (" in source
    assert "self._candidate_collector = AsyncCandidateCollector(" in source
    assert "collected = await self._candidate_collector.collect()" in source
    assert "iter(self._candidate_source())" not in source
    assert "Callable[[], Iterable[RelayTurnCandidate]]" not in source


def test_agent_relay_runtime_awaits_collector_without_blocking_event_loop() -> None:
    async def scenario() -> None:
        gate = asyncio.Event()
        collector = _CollectorProbe(gate=gate)
        runtime = _runtime_with_collector(collector)

        task = asyncio.create_task(runtime.reconcile_once())
        await asyncio.wait_for(collector.started.wait(), timeout=0.1)
        await asyncio.sleep(0)
        assert task.done() is False

        gate.set()
        assert await task == ()
        assert collector.calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("error", "reason"),
    (
        (
            primitives.CandidateCollectionUnavailable(),
            "TURN_CANDIDATE_SOURCE_UNAVAILABLE",
        ),
        (
            primitives.CandidateCollectionTimeout(),
            "TURN_CANDIDATE_COLLECTION_TIMEOUT",
        ),
        (
            primitives.CandidateCollectionOverflow(),
            "TURN_CANDIDATE_LIMIT_EXCEEDED",
        ),
        (
            primitives.CandidateCollectionBusy(),
            "TURN_CANDIDATE_COLLECTION_INFLIGHT",
        ),
    ),
)
def test_agent_relay_runtime_maps_collector_refusals_payload_free(error, reason) -> None:
    async def scenario() -> None:
        collector = _CollectorProbe(error=error)
        runtime = _runtime_with_collector(collector)
        receipts = await runtime.reconcile_once()
        assert collector.calls == 1
        assert len(receipts) == 1
        assert receipts[0].outcome is relay_runtime.ObservationOutcome.REFUSED
        assert receipts[0].reason == reason

    asyncio.run(scenario())


def test_agent_relay_runtime_processes_only_the_collector_immutable_result() -> None:
    async def scenario() -> None:
        candidates = (object(), object())
        collector = _CollectorProbe(result=candidates)
        runtime = _runtime_with_collector(collector)
        seen = []

        async def reconcile(candidate):
            seen.append(candidate)
            return relay_runtime.AgentRelayTurnRuntime._receipt(
                relay_runtime.ObservationOutcome.NO_ACTION,
                "TEST_ONLY",
            )

        runtime._reconcile_candidate = reconcile
        receipts = await runtime.reconcile_once()
        assert collector.calls == 1
        assert tuple(seen) == candidates
        assert tuple(receipt.reason for receipt in receipts) == (
            "TEST_ONLY",
            "TEST_ONLY",
        )

    asyncio.run(scenario())


def _watch_carrier():
    return primitives.ExactWatcherCarrier(
        workspace_id="T0BRD2AQXQV",
        channel_id="C0BRUL9F2V7",
        thread_ts="1788506138.811609",
    )


def _runtime_binding(*, binding_id: str = "bind-ceoruntime0001", generation: int = 7):
    return primitives.RuntimeBindingIdentity(
        session_alias="EXECUTIVE-CEO-A",
        binding_id=binding_id,
        binding_generation=generation,
        reasoning_surface="chatgpt-sol",
    )


def _watched_source(
    *,
    responsibility=None,
    operation_key: str = "rch2-builder-op",
    source_revision: str = "a" * 40,
    disposition=None,
    branch_writer_released: bool = False,
    branch: str = "codex/rch2-builder",
    pull_request: int = 455,
    purpose: str = "sol-worker-continuation",
    runtime_binding=True,
):
    return primitives.WatchedSource(
        side=primitives.WatcherSide.WORKER,
        responsibility=(
            responsibility
            or primitives.WatchedResponsibility.IMPLEMENTATION_BRANCH_WRITER
        ),
        operation_key=operation_key,
        exact_carrier=_watch_carrier(),
        purpose=purpose,
        source_revision=source_revision,
        disposition=disposition or primitives.SourceDisposition.CURRENT,
        repository="mastermindx-market-intelligence/Mastermind",
        pull_request=pull_request,
        branch=branch,
        runtime_binding=_runtime_binding() if runtime_binding else None,
        root_job_id="JOB-" + "1" * 32,
        job_id="JOB-" + "2" * 32,
        attempt_id="ATT-" + "3" * 32,
        worker_id="WRK-" + "4" * 32,
        branch_writer_released=branch_writer_released,
    )


def _watch_pass(
    source,
    *,
    opportunity: str,
    outcome=None,
    generation: str = "b" * 64,
    execution=None,
    binding=None,
):
    selected_outcome = outcome or primitives.WatcherPassOutcome.NO_MATERIAL_CHANGE
    if execution is None:
        execution = (
            primitives.HostExecutionState.NOT_INVOKED
            if selected_outcome is primitives.WatcherPassOutcome.HOST_NOT_INVOKED
            else primitives.HostExecutionState.IDLE_GATED
        )
    return primitives.WatcherPassReceipt(
        source=source,
        schedule_generation=generation,
        expected_opportunity=opportunity,
        host_execution=execution,
        actual_fire_id=(
            None
            if execution is primitives.HostExecutionState.NOT_INVOKED
            else f"fire-{opportunity}"
        ),
        outcome=selected_outcome,
        observed_at=f"2026-09-04T08:{int(opportunity[-2:]):02d}:00Z",
        evidence_digest=f"{int(opportunity[-2:]) % 16:x}" * 64,
        runtime_binding=binding,
    )


def test_watched_source_identity_is_closed_and_revision_conflicts_refuse() -> None:
    source = _watched_source()
    assert source.identity == (
        primitives.WatcherSide.WORKER,
        primitives.WatchedResponsibility.IMPLEMENTATION_BRANCH_WRITER,
        "rch2-builder-op",
        _watch_carrier(),
        "sol-worker-continuation",
        "a" * 40,
        primitives.SourceDisposition.CURRENT,
    )
    assert source.canonical_source_identity == (
        "JOB-" + "1" * 32,
        "JOB-" + "2" * 32,
        "ATT-" + "3" * 32,
        "WRK-" + "4" * 32,
    )
    assert primitives.normalize_watched_sources((source, source)) == (source,)

    conflicting_revision = dataclasses.replace(source, source_revision="c" * 40)
    with pytest.raises(
        primitives.WatchedSourceConflict,
        match="WATCH_SOURCE_REVISION_CONFLICT",
    ):
        primitives.normalize_watched_sources((source, conflicting_revision))


def test_builder_and_release_sources_never_coexist_as_active_branch_writers() -> None:
    builder = _watched_source(
        disposition=primitives.SourceDisposition.REMOTE_COMPLETE_AWAITING_STOP,
    )
    release = _watched_source(
        responsibility=primitives.WatchedResponsibility.RELEASE_MAINTAINER,
        operation_key="rch2-release-op",
        purpose="same-pr-release",
    )

    with pytest.raises(
        primitives.WatchedSourceConflict,
        match="ACTIVE_BRANCH_WRITER_CONFLICT",
    ):
        primitives.normalize_watched_sources((builder, release))

    stopped_builder = dataclasses.replace(
        builder,
        disposition=primitives.SourceDisposition.TERMINAL_STOPPED,
    )
    with pytest.raises(
        primitives.WatchedSourceConflict,
        match="ACTIVE_BRANCH_WRITER_CONFLICT",
    ):
        primitives.normalize_watched_sources((stopped_builder, release))

    terminal_builder = dataclasses.replace(
        builder,
        disposition=primitives.SourceDisposition.TERMINAL_SUPPRESSED,
        branch_writer_released=True,
    )
    assert primitives.normalize_watched_sources((terminal_builder, release)) == (
        terminal_builder,
        release,
    )


def test_schedule_generation_change_does_not_inherit_old_misses() -> None:
    source = _watched_source()
    old_generation = "1" * 64
    current_generation = "2" * 64
    receipts = (
        _watch_pass(
            source,
            opportunity="window-01",
            generation=old_generation,
            outcome=primitives.WatcherPassOutcome.HOST_NOT_INVOKED,
        ),
        _watch_pass(
            source,
            opportunity="window-02",
            generation=old_generation,
            outcome=primitives.WatcherPassOutcome.HOST_NOT_INVOKED,
        ),
        _watch_pass(
            source,
            opportunity="window-03",
            generation=current_generation,
        ),
    )

    old = primitives.project_watched_source(
        source,
        schedule_generation=old_generation,
        receipts=receipts,
    )
    current = primitives.project_watched_source(
        source,
        schedule_generation=current_generation,
        receipts=receipts,
    )

    assert old.state is primitives.WatcherHealth.WATCH_DEGRADED
    assert old.missed_opportunities == 2
    assert current.state is primitives.WatcherHealth.CURRENT
    assert current.missed_opportunities == 0
    assert current.last_successful_opportunity == "window-03"


@pytest.mark.parametrize(
    "outcome_name",
    (
        "HOST_NOT_INVOKED",
        "CARRIER_READ_FAILED",
        "SAME_CARRIER_ACTION_FAILED",
        "EXACT_WAKE_FAILED",
        "WAKE_EFFECT_UNKNOWN",
        "EXACT_TARGET_UNAVAILABLE",
    ),
)
def test_degraded_projection_preserves_each_host_supplied_failure(
    outcome_name: str,
) -> None:
    source = _watched_source()
    outcome = primitives.WatcherPassOutcome(outcome_name)
    projection = primitives.project_watched_source(
        source,
        schedule_generation="b" * 64,
        receipts=(
            _watch_pass(source, opportunity="window-01", outcome=outcome),
            _watch_pass(source, opportunity="window-02", outcome=outcome),
        ),
    )

    assert projection.state is primitives.WatcherHealth.WATCH_DEGRADED
    assert projection.latest_outcome is outcome
    assert projection.reason == outcome.value
    assert projection.missed_opportunities == 2


def test_host_not_invoked_is_not_no_material_change() -> None:
    source = _watched_source()
    not_invoked = _watch_pass(
        source,
        opportunity="window-01",
        outcome=primitives.WatcherPassOutcome.HOST_NOT_INVOKED,
    )
    no_change = _watch_pass(source, opportunity="window-02")

    projection = primitives.project_watched_source(
        source,
        schedule_generation="b" * 64,
        receipts=(not_invoked, no_change),
    )

    assert not_invoked.host_execution is primitives.HostExecutionState.NOT_INVOKED
    assert not_invoked.actual_fire_id is None
    assert no_change.host_execution is primitives.HostExecutionState.IDLE_GATED
    assert no_change.actual_fire_id == "fire-window-02"
    assert projection.state is primitives.WatcherHealth.CURRENT
    assert projection.missed_opportunities == 1
    assert projection.last_fire_opportunity == "window-02"
    assert projection.last_successful_opportunity == "window-02"

    with pytest.raises(
        primitives.WatchedSourceConflict,
        match="WATCH_PASS_INVALID",
    ):
        dataclasses.replace(not_invoked, actual_fire_id="forged-fire")

    with pytest.raises(
        primitives.WatchedSourceConflict,
        match="WATCH_PASS_INVALID",
    ):
        dataclasses.replace(no_change, actual_fire_id=None)


def test_conflicting_receipts_for_one_expected_opportunity_refuse() -> None:
    source = _watched_source()
    accepted = _watch_pass(source, opportunity="window-01")
    conflict = dataclasses.replace(
        accepted,
        outcome=primitives.WatcherPassOutcome.CARRIER_READ_FAILED,
        evidence_digest="f" * 64,
    )

    with pytest.raises(
        primitives.WatchedSourceConflict,
        match="WATCH_PASS_CONFLICT",
    ):
        primitives.project_watched_source(
            source,
            schedule_generation="b" * 64,
            receipts=(accepted, conflict),
        )


def test_equal_time_receipts_project_deterministically_by_opportunity_identity() -> None:
    source = _watched_source()
    first = _watch_pass(source, opportunity="window-01")
    second = dataclasses.replace(
        _watch_pass(
            source,
            opportunity="window-02",
            outcome=primitives.WatcherPassOutcome.CARRIER_READ_FAILED,
        ),
        observed_at=first.observed_at,
    )

    forward = primitives.project_watched_source(
        source,
        schedule_generation="b" * 64,
        receipts=(first, second),
    )
    reversed_input = primitives.project_watched_source(
        source,
        schedule_generation="b" * 64,
        receipts=(second, first),
    )

    assert forward == reversed_input
    assert forward.latest_outcome is primitives.WatcherPassOutcome.CARRIER_READ_FAILED


def test_terminal_suppression_requires_branch_writer_release() -> None:
    with pytest.raises(
        primitives.WatchedSourceConflict,
        match="WATCH_SOURCE_INVALID",
    ):
        _watched_source(
            disposition=primitives.SourceDisposition.TERMINAL_SUPPRESSED,
            branch_writer_released=False,
        )

    with pytest.raises(
        primitives.WatchedSourceConflict,
        match="WATCH_SOURCE_INVALID",
    ):
        _watched_source(
            disposition=primitives.SourceDisposition.TERMINAL_STOPPED,
            branch_writer_released=True,
        )


def test_wake_receipt_without_target_ack_never_claims_success() -> None:
    source = _watched_source()
    receipts = tuple(
        _watch_pass(
            source,
            opportunity=f"window-0{index}",
            outcome=primitives.WatcherPassOutcome.EXACT_WAKE_RECORDED_ACK_ABSENT,
            binding=source.runtime_binding,
        )
        for index in (1, 2)
    )

    projection = primitives.project_watched_source(
        source,
        schedule_generation="b" * 64,
        receipts=receipts,
    )

    assert projection.state is primitives.WatcherHealth.WATCH_DEGRADED
    assert projection.last_successful_opportunity is None
    assert projection.latest_outcome is (
        primitives.WatcherPassOutcome.EXACT_WAKE_RECORDED_ACK_ABSENT
    )


def test_late_fire_on_terminal_source_is_suppressed_without_successor_action() -> None:
    source = _watched_source(
        disposition=primitives.SourceDisposition.TERMINAL_SUPPRESSED,
        branch_writer_released=True,
    )
    late = _watch_pass(
        source,
        opportunity="window-01",
        outcome=primitives.WatcherPassOutcome.ACTIONABLE_EVENT_DETECTED,
        binding=source.runtime_binding,
    )

    projection = primitives.project_watched_source(
        source,
        schedule_generation="b" * 64,
        receipts=(late,),
        current_sol_can_act=True,
    )

    assert projection.state is primitives.WatcherHealth.TERMINAL_SUPPRESSED
    assert projection.action is primitives.WatcherAction.SUPPRESS_TERMINAL_SOURCE
    assert projection.reason == "SOURCE_TERMINAL_SUPPRESSED"
    assert projection.release_origination_authorized is False


def test_watch_stop_failed_keeps_child_terminal_and_aggregate_sibling_active() -> None:
    stopped = _watched_source(
        disposition=primitives.SourceDisposition.TERMINAL_STOPPED,
    )
    sibling = _watched_source(
        operation_key="sibling-op",
        branch="codex/unrelated-sibling",
        pull_request=456,
        purpose="sibling-continuation",
    )
    cleanup_failure = _watch_pass(
        stopped,
        opportunity="window-01",
        outcome=primitives.WatcherPassOutcome.WATCH_STOP_FAILED,
    )

    projection = primitives.project_watched_source(
        stopped,
        schedule_generation="b" * 64,
        receipts=(cleanup_failure,),
        aggregate_sources=(stopped, sibling),
    )

    assert projection.state is primitives.WatcherHealth.TERMINAL_SUPPRESSED
    assert projection.watch_stop_failed is True
    assert projection.active_sibling_sources == 1
    assert projection.aggregate_resource_active is True
    assert projection.action is primitives.WatcherAction.SUPPRESS_TERMINAL_SOURCE


def test_projection_has_descriptive_evidence_and_zero_mutation_authority() -> None:
    source = _watched_source()
    projection = primitives.project_watched_source(
        source,
        schedule_generation="b" * 64,
        receipts=(),
    )

    assert projection.authority_effect == "NONE"
    assert projection.job_write_authorized is False
    assert projection.attempt_write_authorized is False
    assert projection.worker_write_authorized is False
    assert projection.cadence_write_authorized is False
    assert projection.task_creation_authorized is False
    assert projection.retry_authorized is False
    assert projection.release_origination_authorized is False
    assert projection.merge_authorized is False
