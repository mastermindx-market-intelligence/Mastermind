"""Deterministic recovered-cancellation identity and ownership regressions."""
from __future__ import annotations

import asyncio
import signal
from types import SimpleNamespace

import pytest
import control_plane.codex_worker as cw

P = cw._RecoveredPresence


def _state():
    return cw._RecoveredRunState(
        spec=SimpleNamespace(cancel_grace_seconds=0.0),
        ref=SimpleNamespace(run_id="recovery-race", pgid=12345),
        parser=None,
        baseline=None,
    )


def _adapter():
    return object.__new__(cw.CodexWorkerAdapter)


def _observe_sequence(monkeypatch, values):
    remaining = iter(values)
    observed = []
    def observe(_self, _ref):
        value = next(remaining)
        observed.append(value)
        return value
    monkeypatch.setattr(cw.CodexWorkerAdapter, "_observe_recovered_ref", observe)
    return observed


def _signals(monkeypatch):
    sent = []
    def send(state, value):
        sent.append((state.ref.pgid, value))
        return True
    monkeypatch.setattr(cw.CodexWorkerAdapter, "_signal_recovered_group", staticmethod(send))
    return sent


def test_recovered_wait_allows_residual_group_to_settle(monkeypatch):
    observed = _observe_sequence(monkeypatch, [P.RESIDUAL_GROUP, P.ABSENT])
    result = asyncio.run(_adapter()._wait_recovered_absence(_state(), timeout=1.0))
    assert result is P.ABSENT
    assert observed == [P.RESIDUAL_GROUP, P.ABSENT]


@pytest.mark.parametrize("uncertain", [P.UNKNOWN, P.BOOT_CHANGED, P.IDENTITY_CHANGED])
def test_recovered_wait_never_waits_through_uncertainty(monkeypatch, uncertain):
    observed = _observe_sequence(monkeypatch, [uncertain, P.ABSENT])
    result = asyncio.run(_adapter()._wait_recovered_absence(_state(), timeout=1.0))
    assert result is uncertain
    assert observed == [uncertain]


def test_recovered_wait_keeps_existing_deadline(monkeypatch):
    observed = _observe_sequence(monkeypatch, [P.RESIDUAL_GROUP])
    result = asyncio.run(_adapter()._wait_recovered_absence(_state(), timeout=0.0))
    assert result is P.RESIDUAL_GROUP
    assert observed == [P.RESIDUAL_GROUP]


def test_recovered_issue380_absence_at_escalation_is_graceful_success(monkeypatch):
    observed = _observe_sequence(monkeypatch, [P.LIVE, P.ABSENT])
    sent = _signals(monkeypatch)
    async def grace(_self, _state, *, timeout):
        return P.LIVE
    monkeypatch.setattr(cw.CodexWorkerAdapter, "_wait_recovered_absence", grace)
    assert asyncio.run(_adapter()._terminate_recovered(_state())) == (True, False, False)
    assert observed == [P.LIVE, P.ABSENT]
    assert sent == [(12345, signal.SIGTERM)]


@pytest.mark.parametrize("uncertain", [P.UNKNOWN, P.BOOT_CHANGED, P.IDENTITY_CHANGED])
def test_recovered_residual_rechecks_identity_before_escalation(monkeypatch, uncertain):
    observed = _observe_sequence(monkeypatch, [P.LIVE, uncertain])
    sent = _signals(monkeypatch)
    async def grace(_self, _state, *, timeout):
        return P.RESIDUAL_GROUP
    monkeypatch.setattr(cw.CodexWorkerAdapter, "_wait_recovered_absence", grace)
    with pytest.raises(cw.ProcessIdentityError):
        asyncio.run(_adapter()._terminate_recovered(_state()))
    assert observed == [P.LIVE, uncertain]
    assert sent == [(12345, signal.SIGTERM)]


def test_recovered_post_sigkill_residual_can_settle_without_second_signal(monkeypatch):
    observed = _observe_sequence(monkeypatch, [
        P.LIVE, P.RESIDUAL_GROUP, P.RESIDUAL_GROUP, P.RESIDUAL_GROUP, P.ABSENT
    ])
    sent = _signals(monkeypatch)
    assert asyncio.run(_adapter()._terminate_recovered(_state())) == (True, True, False)
    assert observed[-1] is P.ABSENT
    assert sent == [(12345, signal.SIGTERM), (12345, signal.SIGKILL)]


def test_recovered_initial_verified_residual_group_gets_one_graceful_signal(
    monkeypatch,
):
    observed = _observe_sequence(monkeypatch, [P.RESIDUAL_GROUP, P.ABSENT])
    sent = _signals(monkeypatch)

    assert asyncio.run(_adapter()._terminate_recovered(_state())) == (
        True,
        False,
        False,
    )
    assert observed == [P.RESIDUAL_GROUP, P.ABSENT]
    assert sent == [(12345, signal.SIGTERM)]


@pytest.mark.parametrize("initial", [P.UNKNOWN, P.BOOT_CHANGED, P.IDENTITY_CHANGED])
def test_recovered_initial_uncertainty_never_signals(monkeypatch, initial):
    _observe_sequence(monkeypatch, [initial])
    sent = _signals(monkeypatch)
    with pytest.raises(cw.ProcessIdentityError):
        asyncio.run(_adapter()._terminate_recovered(_state()))
    assert sent == []


def test_recovered_already_absent_receipt_is_truthful(monkeypatch):
    _observe_sequence(monkeypatch, [P.ABSENT])
    sent = _signals(monkeypatch)
    assert asyncio.run(_adapter()._terminate_recovered(_state())) == (False, False, True)
    assert sent == []


def test_recovered_signal_refusal_cannot_be_blindly_retried(monkeypatch):
    monkeypatch.setattr(cw.CodexWorkerAdapter, "_observe_recovered_ref", lambda *_: P.LIVE)
    calls = []
    def refuse(pgid, value):
        calls.append((pgid, value))
        raise PermissionError("refused test signal")
    monkeypatch.setattr(cw.os, "killpg", refuse)
    async def scenario():
        adapter, state = _adapter(), _state()
        with pytest.raises(cw.ProcessIdentityError) as first:
            await adapter._terminate_recovered(state)
        with pytest.raises(cw.ProcessIdentityError) as second:
            await adapter._terminate_recovered(state)
        assert second.value is first.value
        assert isinstance(first.value.__cause__, PermissionError)
    asyncio.run(scenario())
    assert calls == [(12345, signal.SIGTERM)]


def test_recovered_caller_cancellation_retains_later_typed_failure(monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        failure = cw.ProcessIdentityError("exact cancellation transaction failed")
        calls = []
        async def fail(_self, state):
            calls.append(state.ref.run_id)
            entered.set()
            await release.wait()
            raise failure
        monkeypatch.setattr(cw.CodexWorkerAdapter, "_terminate_recovered", fail)
        task = asyncio.create_task(_adapter()._cancel_recovered(_state(), "requested"))
        await entered.wait()
        task.cancel("original caller cancellation")
        await asyncio.sleep(0)
        task.cancel("repeated caller cancellation")
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert str(caught.value) == "original caller cancellation"
        assert caught.value.__cause__ is failure
        assert "exact cancellation transaction failed" in caught.value.__notes__
        assert calls == ["recovery-race"]
    asyncio.run(scenario())


def _identity_fixture():
    ref = SimpleNamespace(
        run_id="identity-race", pid=12345, pgid=12345,
        process_start_identity="exact-start", boot_session_id="exact-boot",
        session_id=12345, effective_uid=2001, effective_gid=2001,
        real_uid=2001, real_gid=2001,
    )
    values = dict(start_identity=ref.process_start_identity, pgid=ref.pgid,
                  session_id=ref.session_id, effective_uid=ref.effective_uid,
                  effective_gid=ref.effective_gid, real_uid=ref.real_uid,
                  real_gid=ref.real_gid)
    return ref, values


@pytest.mark.parametrize("field", ["start_identity", "pgid", "session_id", "effective_uid", "effective_gid", "real_uid", "real_gid"])
def test_recovered_full_observation_rejects_identity_reuse(monkeypatch, field):
    ref, values = _identity_fixture()
    values[field] = "changed" if field == "start_identity" else 98765
    adapter = _adapter()
    object.__setattr__(adapter, "inspector", SimpleNamespace(
        boot_session_id=lambda: ref.boot_session_id,
        inspect=lambda pid: SimpleNamespace(**values),
    ))
    monkeypatch.setattr(cw.os, "killpg", lambda *_: pytest.fail("reuse must not be signalled"))
    assert adapter._observe_recovered_ref(ref) is P.IDENTITY_CHANGED


def test_recovered_changed_boot_never_observes_old_process(monkeypatch):
    ref, _ = _identity_fixture()
    adapter = _adapter()
    object.__setattr__(adapter, "inspector", SimpleNamespace(
        boot_session_id=lambda: "different-boot",
        inspect=lambda pid: pytest.fail("old-boot process must not be trusted"),
    ))
    assert adapter._observe_recovered_ref(ref) is P.BOOT_CHANGED


@pytest.mark.parametrize("leader", ["live-unreadable", "permission", "os-error"])
def test_recovered_unreadable_identity_is_not_absence(monkeypatch, leader):
    ref, _ = _identity_fixture()
    adapter = _adapter()
    def unreadable(pid):
        raise cw.ProcessIdentityError("cannot read identity")
    object.__setattr__(adapter, "inspector", SimpleNamespace(
        boot_session_id=lambda: ref.boot_session_id, inspect=unreadable,
    ))
    def probe(pid, value):
        assert pid == ref.pid and value == 0
        if leader == "permission":
            raise PermissionError()
        if leader == "os-error":
            raise OSError()
    monkeypatch.setattr(cw.os, "kill", probe)
    monkeypatch.setattr(cw.os, "killpg", lambda *_: pytest.fail("no guessed group action"))
    assert adapter._observe_recovered_ref(ref) is P.UNKNOWN


@pytest.mark.parametrize("group, expected", [("absent", P.ABSENT), ("unreadable", P.UNKNOWN)])
def test_recovered_absent_leader_requires_group_absence_or_exact_members(monkeypatch, group, expected):
    ref, _ = _identity_fixture()
    adapter = _adapter()
    object.__setattr__(adapter, "inspector", SimpleNamespace(
        boot_session_id=lambda: ref.boot_session_id,
        inspect=lambda pid: (_ for _ in ()).throw(cw.ProcessIdentityError("leader absent")),
    ))
    monkeypatch.setattr(cw.os, "kill", lambda *_: (_ for _ in ()).throw(ProcessLookupError()))
    def group_probe(pgid, value):
        assert pgid == ref.pgid and value == 0
        if group == "absent":
            raise ProcessLookupError()
        raise PermissionError()
    monkeypatch.setattr(cw.os, "killpg", group_probe)
    monkeypatch.setattr(
        cw, "_run_checked",
        lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout="9001 9001\n", stderr=""
        ),
    )
    assert adapter._observe_recovered_ref(ref) is expected


def test_recovered_absent_leader_accepts_exact_residual_group(monkeypatch):
    ref, values = _identity_fixture()
    residual_pid = ref.pid + 11
    adapter = _adapter()
    def inspect(pid):
        if pid == ref.pid:
            raise cw.ProcessIdentityError("leader absent")
        assert pid == residual_pid
        return SimpleNamespace(**{**values, "start_identity": "child-start"})
    object.__setattr__(adapter, "inspector", SimpleNamespace(
        boot_session_id=lambda: ref.boot_session_id, inspect=inspect,
    ))
    monkeypatch.setattr(cw.os, "kill", lambda *_: (_ for _ in ()).throw(ProcessLookupError()))
    monkeypatch.setattr(cw.os, "killpg", lambda *_: None)
    monkeypatch.setattr(
        cw, "_run_checked",
        lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout=f"{residual_pid} {ref.pgid}\n", stderr=""
        ),
    )
    assert adapter._observe_recovered_ref(ref) is P.RESIDUAL_GROUP


def test_recovered_unreadable_residual_member_is_uncertain(monkeypatch):
    ref, _ = _identity_fixture()
    residual_pid = ref.pid + 22
    adapter = _adapter()
    def inspect(pid):
        raise cw.ProcessIdentityError("unreadable residual")
    object.__setattr__(adapter, "inspector", SimpleNamespace(
        boot_session_id=lambda: ref.boot_session_id, inspect=inspect,
    ))
    monkeypatch.setattr(cw.os, "kill", lambda *_: (_ for _ in ()).throw(ProcessLookupError()))
    monkeypatch.setattr(cw.os, "killpg", lambda *_: None)
    monkeypatch.setattr(
        cw, "_run_checked",
        lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout=f"{residual_pid} {ref.pgid}\n", stderr=""
        ),
    )
    assert adapter._observe_recovered_ref(ref) is P.UNKNOWN


def test_recovered_sigkill_lookup_race_does_not_claim_escalation(monkeypatch):
    _observe_sequence(monkeypatch, [P.LIVE, P.LIVE, P.ABSENT])
    sent = []
    def send(state, value):
        if value == signal.SIGKILL:
            return False
        sent.append(value)
        return True
    async def grace(_self, _state, *, timeout):
        return P.LIVE
    monkeypatch.setattr(cw.CodexWorkerAdapter, "_signal_recovered_group", staticmethod(send))
    monkeypatch.setattr(cw.CodexWorkerAdapter, "_wait_recovered_absence", grace)
    assert asyncio.run(_adapter()._terminate_recovered(_state())) == (True, False, False)
    assert sent == [signal.SIGTERM]


def test_recovered_concurrent_cancellation_joins_one_transaction(monkeypatch):
    """One recovered run has one transaction and one immutable cancellation receipt."""
    async def scenario():
        adapter, state = _adapter(), _state()
        entered, release = asyncio.Event(), asyncio.Event()
        operations, monitors = [], []
        async def terminate(_self, target):
            operations.append(target.ref.run_id)
            entered.set()
            await release.wait()
            return True, False, False
        async def monitored():
            monitors.append(state.ref.run_id)
        monkeypatch.setattr(cw.CodexWorkerAdapter, "_terminate_recovered", terminate)
        monkeypatch.setattr(cw.CodexWorkerAdapter, "_ensure_recovered_monitor", lambda *_: monitored())
        first = asyncio.create_task(adapter._cancel_recovered(state, "original reason"))
        await entered.wait()
        second = asyncio.create_task(adapter._cancel_recovered(state, "later diagnostic"))
        await asyncio.sleep(0)
        release.set()
        left, right = await asyncio.gather(first, second)
        assert operations == [state.ref.run_id]
        assert monitors == [state.ref.run_id]
        assert left is right is state.cancel_receipt
        assert left.reason == "original reason"
        assert (left.signal_sent, left.escalated_to_sigkill, left.already_exited) == (True, False, False)
    asyncio.run(scenario())


def test_recovered_terminal_transaction_failure_cannot_be_restarted(monkeypatch):
    async def scenario():
        adapter, state = _adapter(), _state()
        failure = cw.ProcessIdentityError("original exact operation failed")
        operations = []
        async def fail(_self, target):
            operations.append(target.ref.run_id)
            raise failure
        monkeypatch.setattr(cw.CodexWorkerAdapter, "_terminate_recovered", fail)
        for _ in range(2):
            with pytest.raises(cw.ProcessIdentityError) as caught:
                await adapter._cancel_recovered(state, "one cancellation")
            assert caught.value is failure
        assert operations == [state.ref.run_id]
        assert state.cancel_receipt is None
    asyncio.run(scenario())


def test_recovered_cancelled_waiter_does_not_duplicate_joined_operation(monkeypatch):
    async def scenario():
        adapter, state = _adapter(), _state()
        entered, release = asyncio.Event(), asyncio.Event()
        operations = []
        async def terminate(_self, target):
            operations.append(target.ref.run_id)
            entered.set()
            await release.wait()
            return True, False, False
        async def monitored():
            return None
        monkeypatch.setattr(cw.CodexWorkerAdapter, "_terminate_recovered", terminate)
        monkeypatch.setattr(cw.CodexWorkerAdapter, "_ensure_recovered_monitor", lambda *_: monitored())
        first = asyncio.create_task(adapter._cancel_recovered(state, "original reason"))
        await entered.wait()
        second = asyncio.create_task(adapter._cancel_recovered(state, "original reason"))
        await asyncio.sleep(0)
        first.cancel("caller interrupted")
        await asyncio.sleep(0)
        first.cancel("repeated interrupt")
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError, match="caller interrupted"):
            await first
        receipt = await second
        assert operations == [state.ref.run_id]
        assert receipt is state.cancel_receipt
        assert receipt.reason == "original reason"
    asyncio.run(scenario())


def test_recovered_absent_leader_rejects_reused_group_identity(monkeypatch):
    ref, values = _identity_fixture()
    residual_pid = ref.pid + 77
    adapter = _adapter()

    def inspect(pid):
        if pid == ref.pid:
            raise cw.ProcessIdentityError("leader absent")
        assert pid == residual_pid
        return SimpleNamespace(**{**values, "start_identity": "residual-start", "session_id": ref.session_id + 1})

    object.__setattr__(adapter, "inspector", SimpleNamespace(
        boot_session_id=lambda: ref.boot_session_id,
        inspect=inspect,
    ))
    monkeypatch.setattr(cw.os, "kill", lambda *_: (_ for _ in ()).throw(ProcessLookupError()))
    monkeypatch.setattr(cw.os, "killpg", lambda *_: None)
    monkeypatch.setattr(
        cw,
        "_run_checked",
        lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout=f"{residual_pid} {ref.pgid}\n", stderr=""
        ),
    )

    assert adapter._observe_recovered_ref(ref) is P.IDENTITY_CHANGED
