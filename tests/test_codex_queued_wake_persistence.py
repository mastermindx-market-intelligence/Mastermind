"""Real Executive/Wake persistence around the queued native client.

Only the vendor RPC endpoint and the host's current-binding observations are
fixtures. Durable reservation, arbitration and restart behavior are production
implementations, never a separate test idempotency store.
"""
from __future__ import annotations
import asyncio
import dataclasses

import pytest
from control_plane.executive_runtime import Runtime
from control_plane.wake_dispatcher import dispatch_persisted_nudge, PersistedNudgeState, WakeEffectUnknownError
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.codex_app_server import CodexAppServerWakeDispatcher
from integrations.executive_wake.codex_queued_wake import CodexQueuedWakeClient
from tests.test_executive_wake_persisted_dispatch import _pair, _seed_requested, _POLICY
from test_codex_queued_wake import binding, Rpc


@pytest.mark.parametrize("outcome", ["accepted", "lost_response", "cancelled"])
def test_runtime_reservation_survives_reconstruction_without_repeating_the_queue_add(tmp_path, outcome):
    async def exercise():
        runtime = Runtime.at(tmp_path)
        repo = WakeLedgerRepository(runtime)
        b = binding()
        obligation, route, _ = _pair(binding=b)
        _seed_requested(repo, (obligation, route))
        rpc = Rpc()
        def guard(bound, nudge_id, opaque_ids):
            assert bound == b
            assert obligation.obligation_id in opaque_ids
            phases = [r.record.phase for r in repo.list_records(obligation.obligation_id)]
            assert LedgerPhase.DELIVERY_ATTEMPT in phases
            return True
        def make():
            return CodexQueuedWakeClient(rpc=rpc, runtime_binding=b, guard=guard)
        if outcome == "lost_response": rpc.failure = TimeoutError("committed, reply lost")
        if outcome == "cancelled": rpc.failure = asyncio.CancelledError()
        dispatcher = CodexAppServerWakeDispatcher(make())
        async def dispatch(repository, client):
            return await dispatch_persisted_nudge(repository, [(obligation, route)],
                dispatcher=client, binding=b, retry_policy=_POLICY)
        if outcome == "cancelled":
            with pytest.raises(asyncio.CancelledError): await dispatch(repo, dispatcher)
        else:
            first = await dispatch(repo, dispatcher)
            assert first.state is (PersistedNudgeState.ACCEPTED if outcome == "accepted"
                                   else PersistedNudgeState.RECONCILIATION_REQUIRED)
        assert len(rpc.rows) == 1
        # Rebuild every process-local wrapper. Only the real Runtime records remain.
        repo = WakeLedgerRepository(Runtime.at(tmp_path))
        rpc.failure = None
        restarted = await dispatch(repo, CodexAppServerWakeDispatcher(make()))
        assert restarted.state is (PersistedNudgeState.ACCEPTED if outcome == "accepted"
                                   else PersistedNudgeState.RECONCILIATION_REQUIRED)
        assert sum(c["method"] == "thread/queue/add" for c in rpc.calls) == 1
        assert len(rpc.rows) == 1
        phases = [r.record.phase for r in repo.list_records(obligation.obligation_id)]
        assert phases.count(LedgerPhase.DELIVERY_ATTEMPT) == 1
        assert LedgerPhase.DELIVERED not in phases and LedgerPhase.TARGET_ACKNOWLEDGED not in phases
        # The unknown owner deliberately does not auto-retry. Its exact persisted
        # nudge can be inspected via this read-only adapter without rewriting state.
        nudge = restarted.nudge_attempt
        ids = tuple(nudge.obligation_ids) + tuple(a.attempt_command_id for a in nudge.attempts)
        readback = await make().reconcile_wake(native_handle=b.native_handle,
                    nudge_id=nudge.nudge_id, opaque_ids=ids)
        assert readback.accepted and not readback.delivered
        assert [r.record.phase for r in repo.list_records(obligation.obligation_id)] == phases
        assert sum(c["method"] == "thread/queue/add" for c in rpc.calls) == 1
        # A consumed/deleted vendor row is NOT permission to re-submit.
        rpc.rows.clear()
        with pytest.raises(WakeEffectUnknownError):
            await make().reconcile_wake(native_handle=b.native_handle,
                    nudge_id=nudge.nudge_id, opaque_ids=ids)
        assert sum(c["method"] == "thread/queue/add" for c in rpc.calls) == 1
    asyncio.run(exercise())


def test_concurrent_real_dispatchers_share_one_runtime_reservation(tmp_path):
    async def exercise():
        runtime = Runtime.at(tmp_path); repo = WakeLedgerRepository(runtime)
        b = binding(); obligation, route, _ = _pair(binding=b)
        _seed_requested(repo, (obligation, route))
        rpc = Rpc()
        entered, release = asyncio.Event(), asyncio.Event()
        async def guard(bound, nudge_id, opaque_ids):
            assert bound == b
            assert LedgerPhase.DELIVERY_ATTEMPT in [r.record.phase for r in repo.list_records(obligation.obligation_id)]
            entered.set()
            await release.wait()
            return True
        def make(): return CodexAppServerWakeDispatcher(CodexQueuedWakeClient(rpc=rpc, runtime_binding=b, guard=guard))
        async def dispatch():
            return await dispatch_persisted_nudge(repo, [(obligation, route)],
                dispatcher=make(), binding=b, retry_policy=_POLICY)
        first = asyncio.create_task(dispatch())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            second = await dispatch()
            assert second.state is PersistedNudgeState.RECONCILIATION_REQUIRED
        finally:
            release.set()
        committed = await first
        assert committed.state is PersistedNudgeState.ACCEPTED
        assert second.nudge_id == committed.nudge_id
        assert len(rpc.rows) == 1 and len(rpc.calls) == 1
        phases = [r.record.phase for r in repo.list_records(obligation.obligation_id)]
        assert phases == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.ACCEPTED]
    asyncio.run(exercise())
