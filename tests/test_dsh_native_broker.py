"""Original broker/native effect custody; fixture process, no provider calls."""
import asyncio
from dataclasses import replace
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_worker_broker import (
    BrokerPolicy, BrokerStateError, ExecutiveWorkerBroker, PeerCredentials,
)
from control_plane.operator_harness_contract import OperationId, ProviderSessionHandoff, compare_launch
from control_plane.operator_harness_wire import to_wire
from integrations.deepseek_harness.operator_adapter import NativeOperatorError
from test_dsh_native_operator import fixture as native_fixture, FixtureNative, cursor
from test_executive_operator_broker import _Sweeper, _request, _materialization_payload


async def configured(tmp_path, monkeypatch):
    f = await native_fixture(tmp_path, monkeypatch)
    workspace_root = tmp_path.resolve() / "workspaces"
    workspace_root.mkdir(mode=0o700)
    workspace = f.adapter.workspace.rename(workspace_root / "workspace")
    identity = replace(f.requested.workspace, workspace_path=str(workspace))
    f.requested = replace(f.requested, workspace=identity)
    f.observed = replace(f.observed, workspace=identity)
    f.adapter.workspace, f.adapter.requested = workspace, f.requested
    run_root = tmp_path.resolve() / "runs"
    run_root.mkdir(mode=0o700)
    policy = BrokerPolicy(
        control_uid=os.geteuid()+1000 if os.geteuid() else 501,
        worker_uid=os.geteuid(), worker_gid=os.getegid(),
        worker_user="fixture-worker", worker_id=f.epoch.worker_id,
        workspace_root=workspace_root, run_root=run_root,
        provider_home=f.adapter.binding.provider_home,
        allowed_supplementary_gids=frozenset(set(os.getgroups())-{os.getegid()}))
    f.factories, f.effects, f.authority = [], [], {"revoked": False}
    def factory(workspace, loader, requested):
        assert workspace == f.adapter.workspace and requested == f.requested
        f.factories.append(f.adapter)
        f.adapter.turn_input_loader = loader
        return f.adapter
    def authority():
        if f.authority["revoked"]:
            raise RuntimeError("fixture authority withdrawn")
    f.sweeper = _Sweeper()
    f.broker = ExecutiveWorkerBroker(None, policy, f.sweeper,
        adapter_id=None, operator_binary_attestation=f.adapter.binding.binary,
        operator_adapter_factory=factory, operator_harness_armed=True,
        autonomy_guard=authority, autonomy_canary_factory=lambda payload: dict(payload))
    f.peer = PeerCredentials(policy.control_uid, policy.worker_gid, os.getpid())
    def require(operation, epoch, generation, method, session):
        f.effects.append((operation, method, session))
        f.broker.require_native_operator_effect(f.adapter, operation, epoch, generation, method, session)
    def observe(native):
        # Exercise the same final-write callback used by passive native-v2
        # observation, including the preceding turn's accepted Stop identity.
        native.client.before_write()
        return f.observed
    f.adapter.binding = replace(f.adapter.binding, require_current_effect=require,
                                observe_attestation=observe)
    return f


async def request(f, operation, payload):
    return (await f.broker.execute(_request(operation, payload, operation), peer=f.peer))["result"]


def launch_payload(f, *, resume=False):
    return _materialization_payload(f.requested, f.epoch, f.generation,
                                   resume=resume, provider_session_id="original-session")


def begin_payload(f, *, turn=None, operation=None):
    return {"operation_id": to_wire(operation or OperationId("ohf-op:native-begin")),
            "turn": to_wire(turn or f.turn), "generation": to_wire(f.generation),
            "launch": to_wire(compare_launch(f.requested, f.observed)), "prompt": "original message"}


async def close(f):
    return await request(f, "ohf-stop", {"operation_id": to_wire(OperationId("ohf-op:native-close")),
                                       "generation": to_wire(f.generation)})


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("cancel_waiter", [False, True])
def test_original_launch_retained_before_effect_and_after_socket_loss(tmp_path, monkeypatch, resume, cancel_waiter):
    async def exercise():
        f = await configured(tmp_path, monkeypatch)
        if resume:
            f.generation = replace(f.generation, generation_number=2)
        await request(f, "ohf-validate", {"requested": to_wire(f.requested)})
        assert f.adapter.native is None and f.broker._operator_run is None
        entered, release = asyncio.Event(), asyncio.Event()
        original = f.adapter.binding.observe_attestation
        async def observe(native):
            original(native)
            entered.set()
            await release.wait()
            return f.observed
        f.adapter.binding = replace(f.adapter.binding, observe_attestation=observe)
        payload = launch_payload(f, resume=resume)
        waiter = asyncio.create_task(request(f, "ohf-resume" if resume else "ohf-start", payload))
        await asyncio.wait_for(entered.wait(), 2)
        state = f.broker._operator_run
        owned = state.materialization_task
        assert state.adapter is f.adapter and state.provider_dispatch_committed and state.busy
        assert state.materialization_operation.command_id == payload["operation_id"]["command_id"]
        assert state.materialization_receipt is None and not owned.done()
        assert state.native_connection is f.adapter.native and f.adapter.native.open_calls == 1
        if cancel_waiter:
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
        assert (await request(f, "ohf-materialization-status", payload))["status"] == "CONFLICT"
        with pytest.raises(BrokerStateError):
            await request(f, "ohf-resume" if resume else "ohf-start", payload)
        assert len(f.factories) == 2  # validate and the one accepted start
        release.set()
        result = await asyncio.wait_for(asyncio.shield(owned), 2)
        if not cancel_waiter:
            assert await waiter == result
        assert f.broker._operator_run is state and state.materialization_receipt is not None
        assert f.broker._quarantined_reason is None and not state.busy
        assert (await request(f, "ohf-materialization-status", payload))["status"] == "RECEIPT_CURRENT_IN_LIVE_BROKER"
        assert f.adapter.native.open_calls == 1 and f.sweeper.calls == []
        await close(f)
    asyncio.run(exercise())


@pytest.mark.parametrize("outcome", ["success", "failed", "authority-withdrawn"])
def test_late_materialization_uses_original_future_and_receipt(tmp_path, monkeypatch, outcome):
    async def exercise():
        f = await configured(tmp_path, monkeypatch)
        entered, release = asyncio.Event(), asyncio.Event()
        original_call = f.adapter._call
        def bounded(coroutine, **kwargs):
            return original_call(coroutine, timeout=0.02, **kwargs)
        monkeypatch.setattr(f.adapter, "_call", bounded)
        async def observe(native):
            native.client.before_write()
            entered.set()
            await release.wait()
            if outcome == "failed":
                raise ValueError("fixture observation refused")
            return f.observed
        f.adapter.binding = replace(f.adapter.binding, observe_attestation=observe)
        payload = launch_payload(f)
        with pytest.raises(BrokerStateError, match="effect is unknown"):
            await request(f, "ohf-start", payload)
        await entered.wait()
        state = f.broker._operator_run
        original_future = f.adapter.materialization_call[1]
        assert state.adapter is f.adapter and not original_future.done()
        assert (await request(f, "ohf-materialization-status", payload))["status"] == "CONFLICT"
        with pytest.raises(BrokerStateError, match="quarantined"):
            await request(f, "ohf-start", payload)
        if outcome == "authority-withdrawn":
            f.authority["revoked"] = True
            with pytest.raises(BrokerStateError, match="autonomy"):
                f.broker._require_current_autonomy()
        release.set()
        if outcome == "failed":
            with pytest.raises(NativeOperatorError):
                await asyncio.wrap_future(original_future)
        else:
            observed = await asyncio.wrap_future(original_future)
            assert observed.provider_session_id == f.adapter.native.provider_session_id
        assert original_future not in f.adapter.pending_calls
        monkeypatch.setattr(f.adapter, "_call", original_call)
        status = await request(f, "ohf-materialization-status", payload)
        expected = "RECEIPT_CURRENT_IN_LIVE_BROKER" if outcome == "success" else "CONFLICT"
        assert status["status"] == expected
        assert f.broker._operator_run is state and f.adapter.native.open_calls == 1
        assert len(f.factories) == 1 and f.sweeper.calls == []
        if outcome == "success":
            first = status["receipt"]
            assert (await request(f, "ohf-materialization-status", payload))["receipt"] == first
            with pytest.raises(NativeOperatorError, match="differs"):
                f.adapter.observe_materialization_result(operation_id=OperationId("ohf-op:foreign"),
                    requested=f.requested, epoch=f.epoch, generation=f.generation)
            await close(f)
            assert (await request(f, "ohf-materialization-status", payload))["status"] == "CONFLICT"
            with pytest.raises(NativeOperatorError):
                f.adapter.observe_materialization_result(operation_id=state.materialization_operation,
                    requested=f.requested, epoch=f.epoch, generation=f.generation)
        elif outcome == "authority-withdrawn":
            assert f.broker._quarantined_reason == "autonomy_receipt_refused"
    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["adapter", "operation", "epoch", "generation", "session", "connection", "method", "authority", "launch-after-turn", "thread"])
def test_final_write_requires_original_broker_owner(tmp_path, monkeypatch, change):
    async def exercise():
        f = await configured(tmp_path, monkeypatch)
        await request(f, "ohf-start", launch_payload(f))
        await request(f, "ohf-begin-turn", begin_payload(f))
        state = f.broker._operator_run
        args = [f.adapter, state.current_begin[0], f.epoch, f.generation,
                "session/prompt", f.adapter.native.provider_session_id]
        native = f.adapter.native
        if change == "adapter": args[0] = object()
        elif change == "operation": args[1] = OperationId("ohf-op:foreign")
        elif change == "epoch": args[2] = replace(f.epoch, attempt_id="other-attempt")
        elif change == "generation": args[3] = replace(f.generation, generation_number=2)
        elif change == "session": args[5] = "foreign-session"
        elif change == "connection": f.adapter.native = SimpleNamespace(provider_session_id=args[5])
        elif change == "method": args[4] = "arbitrary/write"
        elif change == "launch-after-turn":
            args[1], args[4] = state.materialization_operation, "session/new"
        elif change == "authority": f.authority["revoked"] = True
        with pytest.raises(BrokerStateError):
            if change == "thread":
                await asyncio.to_thread(f.broker.require_native_operator_effect, *args)
            else:
                f.broker.require_native_operator_effect(*args)
        f.adapter.native = native
        assert native.open_calls == native.prompt_calls == 1
        assert state.prompts == {} and state.current_begin[1] == f.turn
        if change != "authority":
            native.client.before_write()
            await close(f)
            with pytest.raises(BrokerStateError, match="owner differs"):
                native.client.before_write()
    asyncio.run(exercise())


def test_previous_begin_and_stop_survive_next_observation_until_ack(tmp_path, monkeypatch):
    async def exercise():
        f = await configured(tmp_path, monkeypatch)
        await request(f, "ohf-start", launch_payload(f))
        await request(f, "ohf-begin-turn", begin_payload(f))
        state = f.broker._operator_run
        first = state.current_begin
        interrupt = OperationId("ohf-op:original-stop")
        await request(f, "ohf-interrupt", {"operation_id": to_wire(interrupt), "turn": to_wire(f.turn)})
        await asyncio.to_thread(f.adapter.read_events, cursor(f))
        assert state.current_interrupt == (interrupt, f.turn)
        next_turn = replace(f.turn, turn_id="turn-next")
        next_operation = OperationId("ohf-op:native-next")
        seen = []
        async def observe(native):
            assert state.current_begin == first and state.pending_begin == (next_operation, next_turn)
            assert state.current_interrupt == (interrupt, f.turn)
            native.client.before_write()
            seen.extend(f.effects[-2:])
            return f.observed
        f.adapter.binding = replace(f.adapter.binding, observe_attestation=observe)
        await request(f, "ohf-begin-turn", begin_payload(f, turn=next_turn, operation=next_operation))
        assert [row[0] for row in seen] == [first[0], interrupt]
        assert state.current_begin == (next_operation, next_turn) and state.pending_begin is None
        assert state.current_interrupt is None and state.prompts == {}
        with pytest.raises(BrokerStateError):
            await request(f, "ohf-begin-turn", begin_payload(f, turn=next_turn, operation=next_operation))
        assert f.adapter.native.prompt_calls == 2
        await close(f)
    asyncio.run(exercise())


def test_begin_socket_cancellation_retains_physical_task_and_late_ack(tmp_path, monkeypatch):
    async def exercise():
        f = await configured(tmp_path, monkeypatch)
        await request(f, "ohf-start", launch_payload(f))
        entered, release = asyncio.Event(), asyncio.Event()
        original = f.adapter.native.begin_prompt
        async def delayed(*args, **kwargs):
            claim = await original(*args, **kwargs)
            entered.set()
            await release.wait()
            return claim
        f.adapter.native.begin_prompt = delayed
        waiter = asyncio.create_task(request(f, "ohf-begin-turn", begin_payload(f)))
        await asyncio.wait_for(entered.wait(), 2)
        state = f.broker._operator_run
        owned = state.begin_task
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert state.busy and state.pending_begin is not None and not owned.done()
        with pytest.raises(BrokerStateError, match="active operation"):
            await request(f, "ohf-begin-turn", begin_payload(f))
        release.set()
        result = await asyncio.wait_for(asyncio.shield(owned), 2)
        assert result["observation"]["acknowledged"] is True
        assert not state.busy and state.pending_begin is None and state.current_begin[1] == f.turn
        assert f.adapter.native.prompt_calls == 1
        await close(f)
    asyncio.run(exercise())


def test_timed_out_close_cannot_sweep_a_pending_original_launch(tmp_path, monkeypatch):
    async def exercise():
        f = await configured(tmp_path, monkeypatch)
        entered, release = asyncio.Event(), asyncio.Event()
        original_call = f.adapter._call
        monkeypatch.setattr(f.adapter, "_call",
            lambda coroutine, **kwargs: original_call(coroutine, timeout=0.02, **kwargs))
        async def observe(native):
            entered.set()
            await release.wait()
            return f.observed
        f.adapter.binding = replace(f.adapter.binding, observe_attestation=observe)
        with pytest.raises(BrokerStateError, match="effect is unknown"):
            await request(f, "ohf-start", launch_payload(f))
        state = f.broker._operator_run
        with pytest.raises(BrokerStateError, match="remain unsettled"):
            await close(f)
        assert f.adapter.close_operation == OperationId("ohf-op:native-close")
        assert f.sweeper.calls == [] and f.adapter.has_pending_native_calls()
        assert f.broker._operator_run is state
        original_futures = tuple(f.adapter.pending_calls)
        release.set()
        await asyncio.gather(*(asyncio.wrap_future(future) for future in original_futures),
                             return_exceptions=True)
        assert not f.adapter.has_pending_native_calls()
        assert f.adapter.native.open_calls == 1 and f.adapter.native.prompt_calls == 0
        assert f.sweeper.calls == []
    asyncio.run(exercise())
