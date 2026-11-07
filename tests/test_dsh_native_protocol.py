"""Closed native observations and retained SDK wait ownership; no providers."""
import asyncio
import dataclasses
import json
from types import SimpleNamespace
import pytest

from integrations.deepseek_harness.native_protocol import (
    CLAIM_SCHEMA, TERMINAL_SCHEMA, NativeClaim, NativeResult, NativeTerminal, NativeProtocolError,
)
from integrations.deepseek_harness.native_connection import NativeClient, NativeAcpProcess, NativeEffectUnknown
from scripts.ohf.acp_probe_boundary import BoundaryViolation, StrictFrameReader


def claim_wire():
    return {"schema": CLAIM_SCHEMA, "operationId": "op-1", "requestId": 1,
            "sessionId": "session-1", "messageId": "message-1", "nativeTurn": 1, "throughSeq": 2}


def terminal_wire():
    return {"schema": TERMINAL_SCHEMA, "operationId": "op-1", "requestId": 1,
            "claim": claim_wire(), "throughSeq": 4, "observedLastTurn": 1, "observedTurnCount": 1}


@pytest.mark.parametrize("field,value", [
    ("schema", "wrong"), ("operationId", ""), ("requestId", True), ("requestId", -1),
    ("requestId", 2**53), ("sessionId", "session/other"), ("nativeTurn", False),
    ("nativeTurn", -1), ("throughSeq", -1), ("throughSeq", 2**53), ("extra", "field"),
])
def test_claim_preserves_exact_closed_wire_types(field, value):
    wire = claim_wire(); wire[field] = value
    with pytest.raises(NativeProtocolError):
        NativeClaim.parse(wire)


@pytest.mark.parametrize("field,value", [
    ("operationId", "op-other"), ("requestId", "1"), ("throughSeq", 1),
    ("observedLastTurn", 0), ("observedLastTurn", None), ("observedTurnCount", 0),
    ("observedTurnCount", True), ("extra", "field"),
])
def test_terminal_cannot_rebind_or_shrink_claim(field, value):
    wire = terminal_wire(); wire[field] = value
    with pytest.raises(NativeProtocolError):
        NativeTerminal.parse(wire)


def test_later_turn_observations_do_not_change_the_original_claim():
    wire = terminal_wire(); wire.update(observedLastTurn=5, observedTurnCount=3, throughSeq=20)
    terminal = NativeTerminal.parse(wire)
    assert terminal.claim == NativeClaim.parse(claim_wire())
    result = NativeResult("cancelled", terminal)
    assert NativeResult.parse(result.to_wire()) == result
    assert len(result.artifact_digest) == 64
    assert NativeResult("end_turn", terminal).artifact_digest != result.artifact_digest


def test_unclaimed_empty_terminal_keeps_negative_native_watermark():
    wire = terminal_wire(); wire.update(claim=None, throughSeq=-1, observedLastTurn=None, observedTurnCount=0)
    assert NativeTerminal.parse(wire).through_seq == -1


async def prepared_client():
    client = NativeClient(); client.bind_session("session-1"); client.advertised = True
    current = client.begin_native_prompt("op-1"); current.request_id = 1
    return client


@pytest.mark.parametrize("enabled", [False, True])
def test_private_claim_requires_explicit_default_deny_frame_policy(enabled):
    async def exercise():
        client = await prepared_client()
        reader = asyncio.StreamReader(limit=client.limits.frame_bytes)
        wire = {"jsonrpc": "2.0", "method": "_mastermind/native_claim", "params": claim_wire()}
        line = (json.dumps(wire)+"\n").encode(); reader.feed_data(line)
        guard = StrictFrameReader(reader, client, extension_policy=client if enabled else None)
        if enabled:
            assert await guard.readuntil() == line
            await client.ext_notification("mastermind/native_claim", claim_wire())
            assert client.current.claim == NativeClaim.parse(claim_wire())
        else:
            with pytest.raises(BoundaryViolation):
                await guard.readuntil()
    asyncio.run(exercise())


@pytest.mark.parametrize("case", ["foreign-operation", "foreign-request-type", "method", "request-not-notification", "turn-budget", "after-terminal"])
def test_extension_cannot_escape_original_owner_and_frame_boundaries(case):
    async def exercise():
        client = await prepared_client()
        wire = {"jsonrpc": "2.0", "method": "_mastermind/native_claim", "params": claim_wire()}
        if case == "foreign-operation": wire["params"]["operationId"] = "op-other"
        elif case == "foreign-request-type": wire["params"]["requestId"] = "1"
        elif case == "method": wire["method"] = "_mastermind/other"
        elif case == "request-not-notification": wire["id"] = 1
        elif case == "turn-budget": client.current.frames = 512
        else: client.current.wire_terminal = True
        reader = asyncio.StreamReader(limit=client.limits.frame_bytes)
        reader.feed_data((json.dumps(wire)+"\n").encode())
        with pytest.raises(BoundaryViolation):
            await StrictFrameReader(reader, client, extension_policy=client).readuntil()
        assert client.violation is not None and client.current.claim is None
    asyncio.run(exercise())


def test_claim_timeout_retains_original_prompt_and_refuses_replay():
    async def exercise():
        client = NativeClient(); client.bind_session("session-1"); client.advertised = True
        owner = NativeAcpProcess(client); owner.provider_session_id = "session-1"
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        class Connection:
            async def prompt(self, **kwargs):
                calls.append(kwargs)
                client.bind_outgoing({"method":"session/prompt", "id":1, "params":{
                    "sessionId":"session-1", "prompt":[], "_meta":{"mastermindNative":{"operationId":"op-1"}}}})
                entered.set(); await release.wait()
                await client.ext_notification("mastermind/native_claim", claim_wire())
                return {"stopReason":"end_turn", "_meta":{"mastermindNative":terminal_wire()}}
        owner.connection = Connection()
        with pytest.raises(NativeEffectUnknown, match="CLAIM_UNOBSERVED"):
            await owner.begin_prompt("op-1", "original input", timeout_seconds=0.01)
        await entered.wait()
        physical = client.current.task
        assert not physical.done() and not physical.cancelled() and len(calls) == 1
        with pytest.raises(NativeProtocolError, match="NOT_READY"):
            await owner.begin_prompt("op-2", "must not replay", timeout_seconds=0.01)
        release.set()
        result = await physical
        assert result.terminal.claim == NativeClaim.parse(claim_wire()) and len(calls) == 1
    asyncio.run(exercise())


def test_stop_timeout_rejoins_the_one_original_cancel_request():
    async def exercise():
        client = await prepared_client()
        await client.ext_notification("mastermind/native_claim", claim_wire())
        claim = client.current.claim
        owner = NativeAcpProcess(client)
        calls, release = [], asyncio.Event()
        class Connection:
            async def ext_method(self, method, params):
                calls.append((method, params)); await release.wait()
                return {"status":"requested"}
        owner.connection = Connection()
        with pytest.raises(NativeEffectUnknown, match="STOP_OUTCOME_UNOBSERVED"):
            await owner.interrupt(claim, timeout_seconds=0.01)
        original = client.current.cancel_task
        assert original is not None and not original.done()
        client.current.result = NativeResult("cancelled", NativeTerminal.parse(terminal_wire()))
        with pytest.raises(NativeProtocolError, match="NOT_READY"):
            client.begin_native_prompt("op-2")
        with pytest.raises(NativeEffectUnknown):
            await owner.interrupt(claim, timeout_seconds=0.01)
        assert client.current.cancel_task is original and len(calls) == 1 and not original.cancelled()
        release.set()
        assert await owner.interrupt(claim) == "requested"
        assert await owner.interrupt(claim) == "requested" and len(calls) == 1
        assert client.begin_native_prompt("op-2").operation_id == "op-2"
    asyncio.run(exercise())


def test_original_probe_digest_commits_only_accepted_callbacks_once():
    import hashlib
    from scripts.ohf.acp_probe_boundary import ProbeClient, ProbeLimits
    async def exercise():
        client = ProbeClient(ProbeLimits(text_bytes=3))
        client.bind_session("session-1"); client.begin_prompt()
        reader = asyncio.StreamReader(limit=client.limits.frame_bytes)
        updates = [{"sessionUpdate":"agent_message_chunk", "content":{"type":"text", "text":text}} for text in ("abc", "d")]
        for update in updates:
            reader.feed_data((json.dumps({"jsonrpc":"2.0", "method":"session/update", "params":{"sessionId":"session-1", "update":update}})+"\n").encode())
        guard = StrictFrameReader(reader, client)
        await guard.readuntil()
        assert client.snapshot()["text_sha256"] == hashlib.sha256(b"").hexdigest()
        await client.session_update("session-1", updates[0])
        await guard.readuntil()
        await client.session_update("session-1", updates[1])
        snapshot = client.snapshot()
        assert snapshot["text_sha256"] == hashlib.sha256(b"abc").hexdigest()
        assert snapshot["updates"] == 1 and snapshot["text_bytes"] == 3
        assert snapshot["boundary_violation"] == "TEXT_BUDGET_EXCEEDED"
    asyncio.run(exercise())


def test_sdk_generated_id_binds_before_send_can_yield_to_a_fast_claim():
    from integrations.deepseek_harness.native_connection import NativeTransport
    async def exercise():
        client = NativeClient(); client.bind_session("session-1"); client.advertised = True
        client.begin_native_prompt("op-1")
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        class Transport:
            async def send(self, message):
                calls.append(message)
                frame = {"jsonrpc":"2.0", "method":"_mastermind/native_claim", "params":claim_wire()}
                assert client.admit_extension_frame(frame) is True
                await client.ext_notification("mastermind/native_claim", frame["params"])
                entered.set()
                await release.wait()
            async def receive(self): return None
            async def close(self): pass
        wrapper = NativeTransport(Transport(), client)
        message = {"jsonrpc":"2.0", "id":1, "method":"session/prompt", "params":{
            "sessionId":"session-1", "prompt":[], "_meta":{"mastermindNative":{"operationId":"op-1"}}}}
        pending = asyncio.create_task(wrapper.send(message))
        await entered.wait()
        assert not pending.done() and client.current.claim == NativeClaim.parse(claim_wire())
        release.set(); await pending
        # SDK outgoing observers arrive only after the physical send completes.
        client.observe_wire(SimpleNamespace(direction="outgoing", message=message))
        assert client.violation is None
        with pytest.raises(NativeProtocolError, match="REPLAY"):
            await wrapper.send(message)
        assert len(calls) == 1
    asyncio.run(exercise())
