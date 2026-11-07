"""Explicit recovery on original authenticated FreshConversation/Control owners."""
import asyncio
from dataclasses import replace

import pytest

from common import fresh_conversation_contract as wire
from control_plane.executive_orchestration_principal import digest
from control_plane.executive_operator_supervisor import PendingNativeOperatorTurn
from control_plane.native_conversation_result import NativeConversationBeginObservation
from control_plane.operator_harness_wire import to_wire
from integrations.deepseek_harness.native_connection import NativeEffectUnknown
from test_dsh_native_fresh_conversation import native_case, frame, opened
from tests.test_fresh_conversation import cleanup


def delay_original(service, monkeypatch, *, ordinal, phase="begin"):
    supervisor = service.operator_supervisor
    factory = supervisor._claimed_adapter_factory
    state = {"ready": False, "observations": 0, "ordinal": ordinal}
    def wrapped(*args, **kwargs):
        adapter = factory(*args, **kwargs)
        begin, read = adapter.begin_turn, adapter.read_events
        def begin_once(**values):
            result = begin(**values)
            if adapter.calls == state["ordinal"] and phase == "begin":
                raise NativeEffectUnknown("NATIVE_CLAIM_UNOBSERVED")
            return result
        def collect(*args, **kwargs):
            if adapter.calls == state["ordinal"] and phase == "collect" and not state["ready"]:
                raise TimeoutError("original native terminal still pending")
            return read(*args, **kwargs)
        def observe(*, operation_id, turn, generation):
            state["observations"] += 1
            assert turn == adapter.turn and operation_id.command_id == adapter.result.terminal.claim.operation_id
            assert generation == adapter.f.generation
            if not state["ready"]: return None
            return NativeConversationBeginObservation(turn, generation, adapter.result.terminal.claim,
                digest(to_wire(adapter.profile)), digest(to_wire(adapter.observed_attestation(generation))))
        monkeypatch.setattr(adapter, "begin_turn", begin_once)
        monkeypatch.setattr(adapter, "read_events", collect)
        monkeypatch.setattr(adapter, "observe_native_begin", observe)
        return adapter
    monkeypatch.setattr(supervisor, "_claimed_adapter_factory", wrapped)
    return state


async def next_turn(owner, principal, selected, initial, key, message):
    request = {**selected, "initial_digest": initial["digest"], "turn_key": key, "message": message}
    preview = await frame(owner, principal, request, "turn_preview")
    assert preview["ok"], (preview, owner._fixture_native_errors)
    request["preview_digest"] = preview["data"]["preview_digest"]
    return request, await frame(owner, principal, request, "turn")


@pytest.mark.parametrize("phase", ["begin", "collect", "journal-before", "journal-after"])
def test_closed_creation_reader_recovers_original_answer_without_cleanup_or_resend(tmp_path, monkeypatch, phase):
    async def run():
        service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
        state = delay_original(service, monkeypatch, ordinal=1, phase="collect" if phase == "collect" else "begin")
        if phase.startswith("journal-"):
            original_write = runtime.operator_harness.record_effect_unknown
            first = True
            def lost_receipt(**kwargs):
                nonlocal first
                if first and kwargs["phase"] == "begin_turn":
                    first = False
                    if phase == "journal-after": original_write(**kwargs)
                    raise OSError("original uncertainty journal write did not return")
                return original_write(**kwargs)
            monkeypatch.setattr(runtime.operator_harness, "record_effect_unknown", lost_receipt)
        try:
            preview = await frame(owner, principal, request, "preview")
            reader = asyncio.StreamReader()
            created = await frame(owner, principal,
                {**request, "preview_digest": preview["data"]["preview"]["digest"]}, "create", reader=reader)
            reader.feed_eof()
            dispatch = service._native_operator_dispatch
            assert dispatch is not None and type(dispatch.pending_turn) is PendingNativeOperatorTurn, (
                created, service._dispatch_errors, owner._fixture_native_errors)
            pending = dispatch.pending_turn
            first_unknown = runtime.events.get_event_by_command_id(pending.operation_id.command_id+":effect-unknown")
            if phase == "journal-before": assert first_unknown is None
            if phase == "journal-after": assert first_unknown is not None
            assert dispatch.retained is None and service._service_state == "READY"
            assert len(adapters) == adapters[0].start_calls == adapters[0].calls == 1
            assert adapters[0].stop_calls == adapters[0].cancel_calls == 0
            selected = {key: request[key] for key in ("work_ref", "operation_key")}
            count = state["observations"]
            before = runtime.events.list_events()
            for action in ("status", "read"):
                passive = await frame(owner, principal, selected, action)
                assert passive["ok"] and passive["data"]["state"] == "RECONCILIATION_REQUIRED"
            assert state["observations"] == count and runtime.events.list_events() == before
            unresolved = await frame(owner, principal, selected, "recover")
            assert unresolved["ok"] and unresolved["data"]["state"] == "RECONCILIATION_REQUIRED", unresolved
            assert service._native_operator_dispatch is dispatch and dispatch.pending_turn is pending
            state["ready"] = True
            responses = await asyncio.gather(*(frame(owner, principal, selected, "recover") for _ in range(2)))
            assert all(value["ok"] and value["data"]["state"] == "CREATED" for value in responses), (
                responses, owner._fixture_native_errors, service._dispatch_errors)
            assert responses[0]["data"]["result"] == responses[1]["data"]["result"]
            assert dispatch.pending_turn is None and dispatch.retained.native_result is not None
            assert dispatch is service._native_operator_dispatch and dispatch.native_phase == "READY"
            assert len(adapters) == adapters[0].start_calls == adapters[0].calls == 1
            assert adapters[0].stop_calls == adapters[0].cancel_calls == 0
            assert adapters[0].prompts == [request["message"]]
            value = runtime.operator_harness.native_conversation_result(
                attempt_id=pending.turn.attempt_id, reference=dispatch.retained.native_result)
            assert value["tx5_intent_command_id"] == pending.operation_id.command_id
            assert value["schema_version"].endswith("/v1" if phase == "collect" else "/v2")
            final_unknown = runtime.events.get_event_by_command_id(pending.operation_id.command_id+":effect-unknown")
            if first_unknown is not None: assert final_unknown == first_unknown
            if phase == "journal-before":
                assert final_unknown.payload["phase"] == "begin_turn_dispatch"
                assert final_unknown.payload["detail"] == "dispatch_committed_without_terminal_receipt"
            initial = responses[0]["data"]["result"]
            consumed = await frame(owner, principal, {**selected, "initial_digest": initial["digest"]}, "consume")
            assert consumed["ok"] and consumed["data"]["can_send"]
            _, following = await next_turn(owner, principal, selected, initial, "after-original-recovery", "Continue once.")
            assert following["ok"] and following["data"]["state"] == "RECORDED", (following, owner._fixture_native_errors)
            assert adapters[0].calls == 2 and service._native_operator_dispatch is dispatch
            assert len(runtime.attempts.list_attempts()) == 1 and len(runtime.jobs.list_jobs()) == 2
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_followup_recovery_keeps_original_request_and_blocks_another_send(tmp_path, monkeypatch):
    async def run():
        service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
        state = delay_original(service, monkeypatch, ordinal=2)
        try:
            created = await opened(owner, principal, request)
            selected = {key: request[key] for key in ("work_ref", "operation_key")}
            initial = created["result"]
            await frame(owner, principal, {**selected, "initial_digest": initial["digest"]}, "consume")
            sent, unknown = await next_turn(owner, principal, selected, initial, "original-late-turn", "Original second input.")
            dispatch = service._native_operator_dispatch
            assert unknown["ok"] and unknown["data"]["state"] == "RECONCILIATION_REQUIRED", (
                unknown, owner._fixture_native_errors, service._dispatch_errors)
            pending, source, previous = dispatch.pending_turn, dispatch._fresh_turn_source, dispatch.retained.native_result
            assert type(pending) is PendingNativeOperatorTurn
            assert source.check_record()[1]["operation_id"] == pending.operation_id.command_id
            assert dispatch.native_phase == "RECONCILIATION_REQUIRED" and service._service_state == "READY"
            before = runtime.events.list_events()
            observed = state["observations"]
            recovered = await frame(owner, principal, {**selected, "turn_key": sent["turn_key"]}, "turn_read")
            assert recovered["data"]["state"] == "RECONCILIATION_REQUIRED"
            assert runtime.events.list_events() == before and state["observations"] == observed
            wrong = await frame(owner, principal, {**selected, "turn_key": "different-original"}, "turn_recover")
            assert not wrong["ok"] and state["observations"] == observed
            new = await frame(owner, principal, {**selected, "initial_digest": initial["digest"],
                "turn_key": "unsafe-new-turn", "message": "Must not send."}, "turn_preview")
            assert not new["ok"] and adapters[0].calls == 2
            state["ready"] = True
            result = await frame(owner, principal, {**selected, "turn_key": sent["turn_key"]}, "turn_recover")
            assert result["ok"] and result["data"]["state"] == "RECORDED", (
                result, owner._fixture_native_errors, service._dispatch_errors)
            assert result["data"]["can_send"] is False and result["data"]["result"] is not None
            assert dispatch.retained.native_result != previous and dispatch.pending_turn is None
            assert dispatch._fresh_turn_source is None and not dispatch.continuation.done()
            assert adapters[0].calls == 2 and adapters[0].stop_calls == adapters[0].cancel_calls == 0
            assert adapters[0].prompts == [request["message"], sent["message"]]
            record = runtime.events.get_event_by_command_id(pending.operation_id.command_id+":effect-unknown")
            assert record is not None and record.payload["phase"] == "begin_turn"
            assert runtime.events.get_event_by_command_id(pending.operation_id.command_id+":applied") is None
            _, following = await next_turn(owner, principal, selected, initial, "after-followup-recovery", "Third input.")
            assert following["ok"] and following["data"]["state"] == "RECORDED"
            assert adapters[0].calls == 3 and service._native_operator_dispatch is dispatch
        finally:
            await cleanup(service)
    asyncio.run(run())
