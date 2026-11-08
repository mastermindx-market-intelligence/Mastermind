"""Late native ACK recovery through original protocol/broker/remote owners."""
import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from control_plane.executive_worker_broker import BrokerStateError
from control_plane.native_conversation_result import (
    DSH_NATIVE_RESULT_CONTRACT, NativeConversationBeginObservation, NativeConversationResultError,
)
from control_plane.operator_harness_contract import EventCursor, OperationId
from control_plane.operator_harness_wire import CONTINUATION_OPERATION_PREFIX, to_wire
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from integrations.deepseek_harness import operator_adapter as adapter_module
from integrations.deepseek_harness.native_connection import NativeAcpProcess, NativeEffectUnknown
from integrations.deepseek_harness.native_protocol import NativeClaim, NativeTerminal, NativeProtocolError
from test_dsh_native_broker import configured, request, launch_payload, begin_payload, close
from test_dsh_native_operator import FixtureNative


class ProtocolNative(NativeAcpProcess):
    """Real original prompt/claim owner over one inert physical resource."""
    def __init__(self, client):
        super().__init__(client)
        FixtureNative.__init__(self, client)
        self.prompt_entered = asyncio.Event()
        self.claim_release = asyncio.Event()
        self.terminal_release = asyncio.Event()

    async def open(self, **kwargs):
        await FixtureNative.open(self, **kwargs)
        self.client.bind_session(self.provider_session_id)
        self.client.advertised = True
        self.connection = SimpleNamespace(prompt=self.prompt)

    async def prompt(self, **kwargs):
        self.client.before_send("session/prompt")
        operation = kwargs["mastermindNative"]["operationId"]
        self.client.bind_outgoing({"method": "session/prompt", "id": 1, "params": {
            "sessionId": self.provider_session_id, "prompt": [],
            "_meta": {"mastermindNative": {"operationId": operation}},
        }})
        self.client.before_write()
        self.prompt_calls += 1
        self.prompt_entered.set()
        await self.claim_release.wait()
        claim = NativeClaim(operation, 1, self.provider_session_id, "original-message", 1, 5)
        await self.client.ext_notification("mastermind/native_claim", claim.to_wire())
        await self.terminal_release.wait()
        terminal = NativeTerminal(operation, 1, claim, 9, 2, 1)
        response = {"stopReason": "end_turn", "_meta": {"mastermindNative": terminal.to_wire()}}
        self.client.observe_wire(SimpleNamespace(direction="incoming", message={"id": 1, "result": response}))
        return response

    async def begin_prompt(self, operation_id, text, **kwargs):
        return await super().begin_prompt(operation_id, text, timeout_seconds=0.01)

    async def close(self, reason=None):
        return await FixtureNative.close(self, reason)


async def uncertain(tmp_path, monkeypatch, *, continuation=False):
    f = await configured(tmp_path, monkeypatch)
    monkeypatch.setattr(adapter_module, "NativeAcpProcess", ProtocolNative)
    await request(f, "ohf-start", launch_payload(f))
    f.operation = OperationId(CONTINUATION_OPERATION_PREFIX+"original" if continuation else "ohf-op:native-begin")
    with pytest.raises(BrokerStateError, match="begin turn failed"):
        await request(f, "ohf-begin-turn", begin_payload(f, operation=f.operation))
    f.state = f.broker._operator_run
    f.native = f.adapter.native
    f.original_turn = f.adapter.current
    f.original_prompt = f.native.client.current
    assert f.original_prompt.task is not None and not f.original_prompt.task.done()
    assert f.original_turn.claim is None and f.state.pending_begin == (f.operation, f.turn)
    assert f.native.prompt_calls == 1 and f.adapter.begin_calls[f.turn][1].done()
    assert type(f.adapter.begin_calls[f.turn][1].exception()) is NativeEffectUnknown
    return f


def status_payload(f):
    return {"operation_id": to_wire(f.operation), "turn": to_wire(f.turn), "generation": to_wire(f.generation)}


async def settle(f):
    f.native.claim_release.set()
    f.native.terminal_release.set()
    return await asyncio.gather(f.original_prompt.task, return_exceptions=True)


@pytest.mark.parametrize("terminal_before_read", [False, True])
@pytest.mark.parametrize("continuation", [False, True])
def test_inner_claim_timeout_recovers_original_ack_and_answer_without_send(
        tmp_path, monkeypatch, terminal_before_read, continuation):
    async def exercise():
        f = await uncertain(tmp_path, monkeypatch, continuation=continuation)
        loop = asyncio.get_running_loop()
        calls = []
        class Client:
            def request_sync(self, operation, payload, **kwargs):
                calls.append(operation)
                return asyncio.run_coroutine_threadsafe(request(f, operation, payload), loop).result(3)
        proxy = RemoteOperatorHarnessAdapter(Client(), turn_input_loader=lambda _turn: pytest.fail("no input read"),
            capabilities=f.adapter.describe_capabilities(), result_contract=DSH_NATIVE_RESULT_CONTRACT)
        for _ in range(2):
            assert await asyncio.to_thread(proxy.observe_native_begin,
                operation_id=f.operation, turn=f.turn, generation=f.generation) is None
        assert f.native.prompt_calls == 1 and f.state.pending_begin is not None
        f.native.claim_release.set()
        claim = await asyncio.wait_for(asyncio.shield(f.original_prompt.claim_ready), 2)
        if terminal_before_read:
            f.native.terminal_release.set()
            await f.original_prompt.task
            assert not f.native.client._active and f.original_prompt.wire_terminal
        observed = await asyncio.to_thread(proxy.observe_native_begin,
            operation_id=f.operation, turn=f.turn, generation=f.generation)
        assert type(observed) is NativeConversationBeginObservation and observed.native_claim == claim
        assert NativeConversationBeginObservation.from_wire(json.loads(json.dumps(to_wire(observed)))) == observed
        assert f.adapter.current is f.original_turn and f.original_turn.claim == claim
        assert f.native.client.current is f.original_prompt
        assert f.state.current_begin == (f.operation, f.turn) and f.state.pending_begin is None
        assert f.state.prompts == {} and f.native.prompt_calls == f.native.open_calls == 1
        assert await asyncio.to_thread(proxy.observe_native_begin,
            operation_id=f.operation, turn=f.turn, generation=f.generation) == observed
        if continuation:
            assert f.state.retained_plain_turns[f.turn] == f.generation
            assert proxy._retained_plain_turns[f.turn] == (f.generation, observed.start)
        f.native.terminal_release.set()
        cursor = EventCursor(f.epoch.attempt_id, f.epoch.session_epoch_id,
                             f.generation.process_generation_id, turn_id=f.turn.turn_id)
        events, following = await asyncio.to_thread(proxy.read_events, cursor, timeout_seconds=2)
        native_result = proxy.observe_native_conversation_result(f.turn)
        assert native_result.native_claim == claim
        assert native_result.native_terminal.claim == claim
        assert any(event.kind == "native_terminal" for event in events)
        assert following.turn_id == f.turn.turn_id
        assert f.native.prompt_calls == 1 and "ohf-begin-turn" not in calls
        assert calls.count("ohf-collect-turn") == 1
        assert f.sweeper.calls == []
        await close(f)
        with pytest.raises(BrokerStateError, match="unavailable"):
            await request(f, "ohf-native-begin-status", status_payload(f))
    asyncio.run(exercise())


@pytest.mark.parametrize("change", [
    "operation", "turn", "generation", "request-type", "session", "claim",
    "violation", "connection", "profile", "attestation",
    "native-connection", "client", "prompt", "task", "claim-future",
])
def test_late_ack_refuses_foreign_original_or_source(tmp_path, monkeypatch, change):
    async def exercise():
        f = await uncertain(tmp_path, monkeypatch)
        f.native.claim_release.set()
        await f.original_prompt.claim_ready
        payload = status_payload(f)
        original_client, original_connection = f.native.client, f.native.connection
        original_task, original_claim_ready = f.original_prompt.task, f.original_prompt.claim_ready
        replacement_task = None
        if change == "operation":
            payload["operation_id"]["command_id"] = "ohf-op:foreign"
        elif change == "turn":
            payload["turn"]["turn_id"] = "foreign-turn"
        elif change == "generation":
            payload["generation"]["generation_number"] += 1
        elif change == "request-type":
            f.original_prompt.request_id = "1"
        elif change == "session":
            f.native.provider_session_id = "foreign-session"
        elif change == "claim":
            f.original_prompt.claim = replace(f.original_prompt.claim, message_id="foreign-message")
        elif change == "violation":
            f.native.client.poison("fixture-boundary-violation")
        elif change == "connection":
            f.adapter.native = SimpleNamespace(provider_session_id=f.native.provider_session_id)
        elif change == "profile":
            f.adapter.requested = replace(f.requested, authority_policy_hash="d"*64)
        elif change == "attestation":
            f.adapter.attestation = replace(f.observed, served_model="foreign-model")
        elif change == "native-connection":
            f.native.connection = SimpleNamespace(prompt=f.native.prompt)
        elif change == "client":
            from copy import copy
            f.native.client = copy(original_client)
        elif change == "prompt":
            original_client.current = replace(f.original_prompt)
        elif change == "task":
            replacement_task = asyncio.create_task(asyncio.sleep(0))
            f.original_prompt.task = replacement_task
        else:
            f.original_prompt.claim_ready = asyncio.get_running_loop().create_future()
            f.original_prompt.claim_ready.set_result(f.original_prompt.claim)
        try:
            with pytest.raises(BrokerStateError):
                await request(f, "ohf-native-begin-status", payload)
            assert f.state.pending_begin == (f.operation, f.turn)
            assert f.native.prompt_calls == 1 and f.state.current_begin is None
        finally:
            f.adapter.native = f.native
            f.native.client, f.native.connection = original_client, original_connection
            original_client.current = f.original_prompt
            f.original_prompt.task, f.original_prompt.claim_ready = original_task, original_claim_ready
            await settle(f)
            if replacement_task is not None:
                await replacement_task
    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["extra", "missing", "request-bool", "digest", "worker", "generation-bool"])
def test_closed_native_begin_codec_refuses_unqualified_evidence(tmp_path, monkeypatch, change):
    async def exercise():
        f = await uncertain(tmp_path, monkeypatch)
        await settle(f)
        result = await request(f, "ohf-native-begin-status", status_payload(f))
        value = result["observation"]
        if change == "extra": value["ready"] = True
        elif change == "missing": del value["observed_attestation_digest"]
        elif change == "request-bool": value["native_claim"]["requestId"] = True
        elif change == "digest": value["requested_profile_digest"] = "unobserved"
        elif change == "worker": value["generation"]["worker_id"] = ""
        else: value["generation"]["generation_number"] = True
        with pytest.raises(NativeConversationResultError):
            NativeConversationBeginObservation.from_wire(value)
        assert f.native.prompt_calls == 1
        await close(f)
    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["cancelled", "other-unknown", "failure", "missing", "foreign-operation"])
def test_retained_begin_recovery_requires_original_observable_call(tmp_path, monkeypatch, change):
    async def exercise():
        from concurrent.futures import Future
        f = await uncertain(tmp_path, monkeypatch)
        original = f.adapter.begin_calls[f.turn]
        await settle(f)
        future = Future()
        if change == "cancelled": future.cancel()
        elif change == "other-unknown": future.set_exception(NativeEffectUnknown("NATIVE_TERMINAL_UNOBSERVED"))
        elif change == "failure": future.set_exception(RuntimeError("original begin refused"))
        else: future.set_result(None)
        if change == "missing":
            del f.adapter.begin_calls[f.turn]
        else:
            operation = OperationId("ohf-op:foreign") if change == "foreign-operation" else f.operation
            f.adapter.begin_calls[f.turn] = (operation, future)
        try:
            with pytest.raises(BrokerStateError):
                await request(f, "ohf-native-begin-status", status_payload(f))
            assert f.state.pending_begin == (f.operation, f.turn)
            assert f.native.prompt_calls == 1 and f.state.current_begin is None
        finally:
            f.adapter.begin_calls[f.turn] = original
            await close(f)
    asyncio.run(exercise())


def test_retained_claim_refuses_session_retarget_before_late_callback(tmp_path, monkeypatch):
    async def exercise():
        f = await uncertain(tmp_path, monkeypatch)
        original_session = f.native.provider_session_id
        f.native.provider_session_id = f.native.client.session_id = "foreign-session"
        f.native.claim_release.set()
        await f.original_prompt.claim_ready
        try:
            with pytest.raises(NativeProtocolError, match="RETAINED_CLAIM_OWNER"):
                f.native.observe_prompt_claim(f.operation.command_id)
            assert f.native.prompt_calls == 1 and f.original_turn.claim is None
        finally:
            await settle(f)
            f.native.provider_session_id = f.native.client.session_id = original_session
            await close(f)
    asyncio.run(exercise())
