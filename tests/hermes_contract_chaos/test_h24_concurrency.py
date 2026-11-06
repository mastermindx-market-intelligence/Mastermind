"""Seeded interleavings over real claim, principal, event and Wake owners."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from control_plane import wake_dispatcher as wake
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.wake_ledger import LedgerPhase, attempt_record
from control_plane.wake_persist import WakeLedgerRepository
from integrations.session_bridge.schemas import BridgeError

from .fixtures import Schedule, counts, event_digest, native_case, selected_case


def test_two_parents_select_the_same_original_child(tmp_path, monkeypatch, chaos_seed):
    async def exercise():
        async with selected_case(tmp_path) as (service, supervisor, work, command, composition, received, finish):
            before = counts(service.runtime)
            schedule = Schedule(chaos_seed)
            original = service.selected_child_status

            async def observe(**kwargs):
                result = await original(**kwargs)
                actor = asyncio.current_task().get_name()
                if actor in {"parent-a", "parent-b"} and actor not in schedule.parked:
                    assert result["state"] == "NOT_CLAIMED"
                    await schedule.park(actor)
                return result

            monkeypatch.setattr(service, "selected_child_status", observe)
            parents = {name: asyncio.create_task(replace(composition).submit_async(command), name=name)
                       for name in ("parent-a", "parent-b")}
            for name in parents:
                await schedule.entered(name)
            results = []
            for name in schedule.order(parents):
                schedule.release(name)
                results.append(await asyncio.wait_for(parents[name], 5))
            claimed = service.runtime.jobs.get_job(work.job_id)
            assert counts(service.runtime)[:2] == (before[0], before[1] + 1)
            assert claimed.attempt_count == 1
            assert all(result["command_id"] == command for result in results)
            assert {result["state"] for result in results} <= {"ACTIVE", "REFUSED"}
            assert any(result["state"] == "ACTIVE" for result in results)
            assert len(service._dispatch_tasks) <= 1
            for _ in range(4):
                replay = await composition.submit_async(command)
                assert replay["attempt_id"] == claimed.current_attempt_id
            assert counts(service.runtime)[:2] == (before[0], before[1] + 1)
            finish.set()
    asyncio.run(exercise())


def test_concurrent_principals_never_share_a_native_answer(native_case, chaos_seed):
    from tests.test_hermes_session_runtime import arguments, original_events

    async def exercise():
        s = native_case
        args = await arguments(s)
        sent = await s.owner.send_hermes(s.principal, args)
        before = counts(s.runtime), event_digest(s.runtime)
        foreign = replace(s.principal, subject_digest="f" * 64)
        schedule = Schedule(chaos_seed)

        async def read(name, principal):
            await schedule.park(name)
            try:
                return await s.owner.read_hermes(principal, sent["read_ref"])
            except BridgeError as error:
                return error

        tasks = {
            "valid": asyncio.create_task(read("valid", s.principal)),
            "foreign": asyncio.create_task(read("foreign", foreign)),
        }
        for name in tasks:
            await schedule.entered(name)
        s.state.calls.clear()
        results = {}
        for name in schedule.order(tasks):
            schedule.release(name)
            results[name] = await tasks[name]
        assert isinstance(results["foreign"], BridgeError)
        assert results["valid"]["answer"] == "Actual original answer: 日本語 ✓"
        assert s.state.calls == ["read_original"] and s.state.writes == 1
        assert len(original_events(s, args)) == 2
        assert (counts(s.runtime), event_digest(s.runtime)) == before
    asyncio.run(exercise())


@pytest.mark.parametrize("parent_count", [2, 16])
@pytest.mark.parametrize("lost_return", [False, True])
def test_duplicate_native_sends_with_target_drift_keep_one_original(native_case, chaos_seed, parent_count, lost_return):
    from tests.test_hermes_session_runtime import arguments, original_events

    async def exercise():
        s = native_case
        args = await arguments(s)
        before = counts(s.runtime)
        schedule = Schedule(chaos_seed)
        s.state.lose_submit = s.state.read_unavailable = lost_return

        async def observe():
            await schedule.park(asyncio.current_task().get_name())

        s.state.before_observe = observe
        tasks = {name: asyncio.create_task(s.owner.send_hermes(s.principal, args), name=name)
                 for name in (f"native-{index}" for index in range(parent_count))}
        for name in tasks:
            await schedule.entered(name)
        order = schedule.order(tasks)
        schedule.release(order[0])
        first = await tasks[order[0]]
        s.state.target["revision"] += 1
        s.state.submit_allowed = False
        for name in order[1:]:
            schedule.release(name)
            second = await tasks[name]
            assert first["read_ref"] == second["read_ref"]
            assert first["commit_started"] and second["commit_started"]
            assert second["native_status"] == (None if lost_return else "OBSERVED")
            assert len(original_events(s, args)) == 2
        assert s.state.writes == 1 and len(original_events(s, args)) == 2
        assert counts(s.runtime)[:2] == before[:2]
        assert len(schedule.parked) == parent_count
        assert all(task.done() for task in tasks.values())
    asyncio.run(exercise())


def test_event_delivery_before_commit_cannot_see_or_dispatch_it(tmp_path, chaos_seed):
    from tests.test_executive_wake_persisted_dispatch import _pair, _POLICY
    from control_plane.wake_ledger import requested_record

    async def exercise():
        runtime = Runtime.at(tmp_path)
        repository = WakeLedgerRepository(runtime)
        obligation, route, binding = _pair(ordinal=chaos_seed)
        calls = []

        class Transport:
            transport_id = "codex-app-server"

            async def nudge(self, nudge):
                calls.append(nudge)
                raise AssertionError("uncommitted event reached transport")

        before = counts(runtime)
        with pytest.raises(ConnectionError, match="injected pre-commit loss"):
            with runtime.store.transaction() as connection:
                repository.append_records_on_connection(connection, ((requested_record(obligation), obligation),))
                # A separate connection must not observe the uncommitted Event.
                assert repository.list_records(obligation.obligation_id) == ()
                with pytest.raises((wake.WakeDispatchError, StateConflict)):
                    await wake.dispatch_persisted_nudge(repository, [(obligation, route)],
                        dispatcher=Transport(), binding=binding, retry_policy=_POLICY)
                raise ConnectionError("injected pre-commit loss")
        assert calls == [] and counts(runtime) == before
    asyncio.run(exercise())


def test_reordered_duplicate_wakes_reconcile_the_original_nudge(tmp_path, chaos_seed):
    from tests.test_wake_explicit_reconciliation import pending, phases

    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path, 3)
        before = counts(repo.runtime)
        schedule = Schedule(chaos_seed)
        ordered = schedule.order(pairs)
        with pytest.raises(wake.WakeDispatchError):
            await wake.reconcile_persisted_nudge(repo, ordered + [ordered[0]],
                nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert provider.reads == []
        first = await wake.reconcile_persisted_nudge(repo, ordered,
            nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        again = await wake.reconcile_persisted_nudge(repo, list(reversed(ordered)),
            nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert first.state is again.state is wake.PersistedNudgeState.ACCEPTED
        assert first.nudge_id == again.nudge_id == original.nudge_id
        assert len(provider.adds) == len(provider.reads) == 1
        for pair in pairs:
            assert phases(repo, pair) == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.ACCEPTED]
        assert counts(repo.runtime)[:2] == before[:2]
    asyncio.run(exercise())


@pytest.mark.parametrize("terminal", [LedgerPhase.DELIVERED, LedgerPhase.FAILED])
def test_late_callback_cannot_replace_committed_terminal_wake(tmp_path, chaos_seed, terminal):
    from tests.test_wake_explicit_reconciliation import pending, phases

    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path)
        schedule = Schedule(chaos_seed)

        async def callback(_):
            await schedule.park("callback")

        provider.on_read = callback
        task = asyncio.create_task(wake.reconcile_persisted_nudge(repo, pairs,
            nudge_id=original.nudge_id, dispatcher=provider, binding=binding))
        await schedule.entered("callback")
        other = WakeLedgerRepository(Runtime.at(tmp_path))
        other.append_record(attempt_record(original.nudge_attempt.attempts[0], terminal), obligation=pairs[0][0])
        schedule.release("callback")
        result = await task
        assert result.state is wake.PersistedNudgeState.RECONCILIATION_REQUIRED
        assert phases(repo, pairs[0]) == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT, terminal]
        assert len(provider.adds) == len(provider.reads) == 1
    asyncio.run(exercise())
