"""Explicit same-attempt recovery uses real Runtime/Wake persistence.

Only the provider observation is a fixture. No native session or production
service is contacted; default dispatch must retain its existing no-retry rule.
"""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane import wake_dispatcher as api
from control_plane.executive_runtime import Runtime
from control_plane.wake_ledger import LedgerPhase, attempt_record
from control_plane.wake_persist import WakeLedgerRepository
from tests.test_executive_wake_persisted_dispatch import _pair, _seed_requested, _POLICY

NOW = "2026-10-03T07:00:00Z"


def recover():
    value = getattr(api, "reconcile_persisted_nudge", None)
    assert callable(value), "explicit persisted same-nudge reconciliation is not implemented"
    return value


class Observations:
    transport_id = "codex-app-server"

    def __init__(self):
        self.adds = []
        self.reads = []
        self.change = lambda receipt: receipt
        self.on_read = None

    async def nudge(self, wake):
        self.adds.append(wake)
        raise api.WakeEffectUnknownError("fixture lost response after insertion")

    async def reconcile(self, wake):
        self.reads.append(wake)
        if self.on_read is not None:
            await self.on_read(wake)
        return self.change(api.TransportReceipt(
            outcome=api.TransportOutcome.ACCEPTED,
            reason_code="accepted", created_at=NOW,
            details=(("nudge_id", wake.nudge_id),)))


async def pending(path, count=1):
    repo = WakeLedgerRepository(Runtime.at(path))
    first = _pair()
    binding = first[2]
    pairs = [first[:2]] + [_pair(ordinal=i, binding=binding)[:2] for i in range(1, count)]
    _seed_requested(repo, *pairs)
    provider = Observations()
    result = await api.dispatch_persisted_nudge(
        repo, pairs, dispatcher=provider, binding=binding, retry_policy=_POLICY)
    assert result.state is api.PersistedNudgeState.RECONCILIATION_REQUIRED
    assert len(provider.adds) == 1
    return repo, pairs, binding, provider, result


def phases(repo, pair):
    return [item.record.phase for item in repo.list_records(pair[0].obligation_id)]


@pytest.mark.parametrize("count", [1, 2])
def test_explicit_recovery_records_original_acceptance_and_replays_without_rpc(tmp_path, count):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path, count)
        # Ordinary dispatch still cannot call either provider method for unknown effects.
        held = await api.dispatch_persisted_nudge(repo, pairs, dispatcher=provider,
            binding=binding, retry_policy=_POLICY)
        assert held.state is api.PersistedNudgeState.RECONCILIATION_REQUIRED
        assert provider.reads == [] and len(provider.adds) == 1
        fresh = WakeLedgerRepository(Runtime.at(tmp_path))
        result = await recover()(fresh, tuple(reversed(pairs)), nudge_id=original.nudge_id,
            dispatcher=provider, binding=binding)
        assert result.state is api.PersistedNudgeState.ACCEPTED
        assert result.nudge_id == original.nudge_id
        assert len(provider.reads) == 1 and len(provider.adds) == 1
        assert set(provider.reads[0].attempt_command_ids) == {
            a.attempt_command_id for a in original.nudge_attempt.attempts}
        for pair in pairs:
            assert phases(fresh, pair) == [LedgerPhase.WAKE_REQUESTED,
                LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.ACCEPTED]
        again = await recover()(WakeLedgerRepository(Runtime.at(tmp_path)), pairs,
            nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert again.state is api.PersistedNudgeState.ACCEPTED
        assert len(provider.reads) == 1 and len(provider.adds) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("case", ["missing_member", "duplicate", "wrong_nudge", "rotated_binding", "route_drift"])
def test_original_group_and_binding_required_before_provider_read(tmp_path, case):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path, 2)
        selected, nudge_id = list(pairs), original.nudge_id
        if case == "missing_member": selected.pop()
        elif case == "duplicate": selected.append(selected[0])
        elif case == "wrong_nudge": nudge_id = "NUDGE-" + "f" * 32
        elif case == "rotated_binding": binding = dataclasses.replace(binding, binding_generation=2)
        else: selected[0] = (selected[0][0], dataclasses.replace(selected[0][1], route_digest="0" * 64))
        with pytest.raises(api.WakeDispatchError):
            await recover()(repo, selected, nudge_id=nudge_id, dispatcher=provider, binding=binding)
        assert provider.reads == [] and len(provider.adds) == 1
        assert all(phases(repo, pair) == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
                   for pair in pairs)
    asyncio.run(exercise())


@pytest.mark.parametrize("case", ["missing_nudge", "wrong_nudge", "duplicate_nudge", "failure", "delivered", "bad_time", "shape", "unknown"])
def test_unqualified_observation_never_closes_uncertainty(tmp_path, case):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path)
        def change(receipt):
            if case == "missing_nudge": return dataclasses.replace(receipt, details=())
            if case == "wrong_nudge": return dataclasses.replace(receipt, details=(("nudge_id", "NUDGE-" + "f" * 32),))
            if case == "duplicate_nudge": return dataclasses.replace(receipt, details=receipt.details * 2)
            if case == "failure": return dataclasses.replace(receipt, outcome=api.TransportOutcome.FAILED, reason_code="transport_failed")
            if case == "delivered": return dataclasses.replace(receipt, outcome=api.TransportOutcome.DELIVERED, reason_code="delivered")
            if case == "bad_time": return dataclasses.replace(receipt, created_at="yesterday")
            if case == "shape": return {"accepted": True}
            raise api.WakeEffectUnknownError("fixture not observed")
        provider.change = change
        result = await recover()(repo, pairs, nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert result.state is api.PersistedNudgeState.RECONCILIATION_REQUIRED
        assert result.transport_receipt is None
        assert len(provider.reads) == 1 and len(provider.adds) == 1
        assert phases(repo, pairs[0]) == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
    asyncio.run(exercise())


def test_missing_reconciliation_seam_does_not_invoke_submission(tmp_path):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path)
        provider.reconcile = None
        result = await recover()(repo, pairs, nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert result.state is api.PersistedNudgeState.RECONCILIATION_REQUIRED
        assert provider.reads == [] and len(provider.adds) == 1
    asyncio.run(exercise())


def test_cancellation_preserves_original_unknown_attempt(tmp_path):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path)
        async def cancelled(_): raise asyncio.CancelledError()
        provider.on_read = cancelled
        with pytest.raises(asyncio.CancelledError):
            await recover()(repo, pairs, nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert phases(repo, pairs[0]) == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
        assert len(provider.adds) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("winner", [LedgerPhase.ACCEPTED, LedgerPhase.FAILED, LedgerPhase.DELIVERED])
def test_concurrent_canonical_winner_is_not_overwritten_by_late_acceptance(tmp_path, winner):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path)
        async def complete_elsewhere(_):
            # A separate current owner writes while the provider read is in flight.
            # This also proves no repository transaction spans the external await.
            other = WakeLedgerRepository(Runtime.at(tmp_path))
            other.append_record(attempt_record(original.nudge_attempt.attempts[0], winner), obligation=pairs[0][0])
        provider.on_read = complete_elsewhere
        result = await recover()(repo, pairs, nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert result.state is (api.PersistedNudgeState.ACCEPTED if winner is LedgerPhase.ACCEPTED
                                else api.PersistedNudgeState.RECONCILIATION_REQUIRED)
        assert phases(repo, pairs[0]) == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT, winner]
        assert len(provider.adds) == 1
    asyncio.run(exercise())


def test_concurrent_recovery_records_one_acceptance_per_obligation(tmp_path):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path, 2)
        both = asyncio.Event()
        async def rendezvous(_):
            if len(provider.reads) == 2: both.set()
            await asyncio.wait_for(both.wait(), 1)
        provider.on_read = rendezvous
        results = await asyncio.gather(*(
            recover()(WakeLedgerRepository(Runtime.at(tmp_path)), pairs,
                nudge_id=original.nudge_id, dispatcher=provider, binding=binding) for _ in range(2)))
        assert all(r.state is api.PersistedNudgeState.ACCEPTED for r in results)
        assert len(provider.reads) == 2 and len(provider.adds) == 1
        for pair in pairs: assert phases(repo, pair).count(LedgerPhase.ACCEPTED) == 1
    asyncio.run(exercise())


def test_group_acceptance_is_atomic_if_later_append_fails(tmp_path, monkeypatch):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path, 2)
        append_one = repo._append_one
        writes = []
        def fail_second(connection, record, **kwargs):
            if record.phase is LedgerPhase.ACCEPTED:
                writes.append(record)
                if len(writes) == 2: raise RuntimeError("fixture storage failure")
            return append_one(connection, record, **kwargs)
        monkeypatch.setattr(repo, "_append_one", fail_second)
        result = await recover()(repo, pairs, nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert result.state is api.PersistedNudgeState.RECONCILIATION_REQUIRED
        assert len(writes) == 2
        for pair in pairs:
            assert phases(repo, pair) == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
        assert len(provider.adds) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("case", ["no_attempt", "closed", "partial_acceptance", "obligation_drift", "disabled_route", "wrong_dispatcher", "unaddressable"])
def test_ineligible_snapshot_never_reads_provider_or_allocates_work(tmp_path, case):
    async def exercise():
        if case == "no_attempt":
            repo = WakeLedgerRepository(Runtime.at(tmp_path))
            pair = _pair(); pairs, binding = [pair[:2]], pair[2]
            _seed_requested(repo, *pairs)
            provider = Observations(); nudge_id = "NUDGE-" + "e" * 32
        else:
            repo, pairs, binding, provider, original = await pending(tmp_path, 2)
            nudge_id = original.nudge_id
            if case == "closed":
                repo.append_records_atomic(tuple(
                    (attempt_record(a, LedgerPhase.FAILED), pair[0])
                    for a, pair in zip(original.nudge_attempt.attempts, pairs)))
            elif case == "partial_acceptance":
                repo.append_record(attempt_record(original.nudge_attempt.attempts[0], LedgerPhase.ACCEPTED), obligation=pairs[0][0])
            elif case == "obligation_drift":
                pairs[0] = (dataclasses.replace(pairs[0][0], emitted_at=NOW), pairs[0][1])
            elif case == "disabled_route":
                pairs[0] = (pairs[0][0], dataclasses.replace(pairs[0][1], target_enabled=False))
            elif case == "wrong_dispatcher": provider.transport_id = "not-the-original-transport"
            else: binding = dataclasses.replace(binding, native_handle=None)
        before = tuple(tuple(repo.list_records(pair[0].obligation_id)) for pair in pairs)
        with pytest.raises(api.WakeDispatchError):
            await recover()(repo, pairs, nudge_id=nudge_id, dispatcher=provider, binding=binding)
        assert provider.reads == []
        assert len(provider.adds) == (0 if case == "no_attempt" else 1)
        assert tuple(tuple(repo.list_records(pair[0].obligation_id)) for pair in pairs) == before
    asyncio.run(exercise())


def test_old_nudge_cannot_select_a_later_persisted_attempt(tmp_path):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path)
        first = original.nudge_attempt.attempts[0]
        repo.append_record(attempt_record(first, LedgerPhase.FAILED), obligation=pairs[0][0])
        second = api.make_delivery_attempt(pairs[0][0], pairs[0][1], attempt_n=2)
        ids = (second.attempt_command_id,)
        second = dataclasses.replace(second, nudge_id=api.mint_nudge_id(second.destination_digest, ids), nudge_attempt_command_ids=ids)
        repo.append_record(attempt_record(second, LedgerPhase.DELIVERY_ATTEMPT), obligation=pairs[0][0])
        with pytest.raises(api.WakeDispatchError):
            await recover()(repo, pairs, nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert provider.reads == [] and len(provider.adds) == 1
        assert phases(repo, pairs[0]) == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT,
                                        LedgerPhase.FAILED, LedgerPhase.DELIVERY_ATTEMPT]
    asyncio.run(exercise())


def test_revoked_native_observation_stays_unknown_and_cannot_mark_failed(tmp_path):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path)
        async def revoked(_):
            raise api.WakePreSubmitError("fixture current owner no longer permits observation")
        provider.on_read = revoked
        result = await recover()(repo, pairs, nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert result.state is api.PersistedNudgeState.RECONCILIATION_REQUIRED
        assert phases(repo, pairs[0]) == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
        assert len(provider.adds) == 1
    asyncio.run(exercise())


def test_input_sequence_cannot_substitute_another_obligation_during_read(tmp_path):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path)
        selected = list(pairs)
        foreign = _pair(ordinal=99, binding=binding)[:2]
        _seed_requested(repo, foreign)
        async def change_inputs(_): selected[0] = foreign
        provider.on_read = change_inputs
        result = await recover()(repo, selected, nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert result.state is api.PersistedNudgeState.ACCEPTED
        assert phases(repo, pairs[0])[-1] is LedgerPhase.ACCEPTED
        assert phases(repo, foreign) == [LedgerPhase.WAKE_REQUESTED]
        assert provider.reads[0].obligation_ids == original.nudge_attempt.obligation_ids
    asyncio.run(exercise())


def test_lost_commit_response_is_reconciled_from_canonical_acceptance(tmp_path, monkeypatch):
    from contextlib import contextmanager

    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path)
        transaction = repo.store.transaction
        calls = []
        @contextmanager
        def lost_response(*args, **kwargs):
            calls.append(1)
            with transaction(*args, **kwargs) as connection:
                yield connection
            if len(calls) == 2:
                raise RuntimeError("fixture reply lost after transaction committed")
        monkeypatch.setattr(repo.store, "transaction", lost_response)
        first = await recover()(repo, pairs, nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert first.state is api.PersistedNudgeState.RECONCILIATION_REQUIRED
        assert phases(repo, pairs[0])[-1] is LedgerPhase.ACCEPTED
        result = await recover()(WakeLedgerRepository(Runtime.at(tmp_path)), pairs,
            nudge_id=original.nudge_id, dispatcher=provider, binding=binding)
        assert result.state is api.PersistedNudgeState.ACCEPTED
        assert len(provider.reads) == 1 and len(provider.adds) == 1
        assert phases(repo, pairs[0]).count(LedgerPhase.ACCEPTED) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("alias", [" nudge_id", "nudge_id ", "\tnudge_id"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("contradictory", [False, True])
@pytest.mark.parametrize("count", [1, 2])
def test_noncanonical_receipt_keys_cannot_alias_original_nudge(
    tmp_path, alias, reverse, contradictory, count
):
    """Different raw keys must never become one ambiguous correlation."""
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path, count)
        before = [phases(repo, pair) for pair in pairs]
        expected = ("nudge_id", original.nudge_id)
        disguised = (alias, "NUDGE-" + "f" * 32 if contradictory else original.nudge_id)
        details = (expected, disguised) if reverse else (disguised, expected)
        provider.change = lambda receipt: dataclasses.replace(receipt, details=details)
        result = await recover()(repo, pairs, nudge_id=original.nudge_id,
                                 dispatcher=provider, binding=binding)
        assert result.state is api.PersistedNudgeState.RECONCILIATION_REQUIRED
        assert [phases(repo, pair) for pair in pairs] == before
        assert len(provider.adds) == 1 and len(provider.reads) == 1
        assert all(LedgerPhase.ACCEPTED not in phases(repo, pair) for pair in pairs)
    asyncio.run(exercise())


@pytest.mark.parametrize("reverse", [False, True])
def test_canonical_distinct_receipt_keys_keep_valid_acceptance(tmp_path, reverse):
    async def exercise():
        repo, pairs, binding, provider, original = await pending(tmp_path, 2)
        expected = ("nudge_id", original.nudge_id)
        other = ("policy_version", "fixture-v1")
        details = (expected, other) if reverse else (other, expected)
        provider.change = lambda receipt: dataclasses.replace(receipt, details=details)
        result = await recover()(repo, pairs, nudge_id=original.nudge_id,
                                 dispatcher=provider, binding=binding)
        assert result.state is api.PersistedNudgeState.ACCEPTED
        assert all(phases(repo, pair).count(LedgerPhase.ACCEPTED) == 1 for pair in pairs)
        assert len(provider.adds) == 1 and len(provider.reads) == 1
    asyncio.run(exercise())
