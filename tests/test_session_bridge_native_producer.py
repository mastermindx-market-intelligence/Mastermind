"""Proposal proof: fake authenticated host, real Runtime; no provider launch."""
import asyncio
from pathlib import Path

import pytest

from integrations.session_bridge.installed import build_runtime_native_reply_writer
from integrations.session_bridge.dialogue_reply import AgentDialogueContinueWriter
from integrations.session_bridge.schemas import BridgeError
from tests.test_session_bridge_runtime_return import setup, bind, read, NATIVE
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector


@pytest.fixture(autouse=True)
def target_owner(setup, monkeypatch):
    resolver = setup.owner.fabric.resolve
    monkeypatch.setattr(RuntimeFabricTargetProjector, "resolve", lambda self, ref: resolver(ref))


def request(s):
    ref = bind(s)
    context = AgentDialogueContinueWriter._context(s.binding)
    message = AgentDialogueContinueWriter._message(
        request_message={"message_key": s.binding.reply_to_message_key,
                         "created_at": "2026-10-01T20:00:00Z"},
        context=context, instruction=s.args["instruction"],
        stop_condition=s.args["stop_condition"], operation_key=s.args["operation_key"])
    s.service.items = [{"message": message, "primary_ts": "1788000001.123456"}]
    return ref, dict(operation_key=s.args["operation_key"], in_reply_to=message["message_key"],
                     text="The host returned the bounded finding.", next_step="Continue the parent task.")


def compose(s, guard):
    # Existing owners are used, never selected from native tool arguments.
    return build_runtime_native_reply_writer(
        s.runtime, dialogue_socket_path=Path("/private/tmp/runtime-return.sock"),
        native_session_id=NATIVE, current_writer_guard=guard,
        codex_owner_configured=lambda: s.enabled[0], service_call=s.service,
        )


def test_host_callback_returns_on_original_carrier_and_read_never_consumes(setup):
    s = setup
    ref, args = request(s)
    checked = []
    def guard(binding):
        checked.append(binding)
        return (binding.native_session_id == NATIVE
                and binding.process_generation_id == s.facts.process_generation_id)
    callback = compose(s, guard)
    assert not s.service.calls  # Composition is inert.
    receipt = asyncio.run(callback(args))
    assert receipt["reply_committed"] and receipt["parent_consumed"] is False
    assert len(checked) == 3 and checked[0] == checked[1] == checked[2]
    assert read(s, ref)["text"] == args["text"]
    assert read(s, ref)["parent_consumed"] is False
    assert asyncio.run(callback(args))["action"] == "DUPLICATE"
    assert sum(c["operation"] == "send_message" for c in s.service.calls) == 1


@pytest.mark.parametrize("guard_result", [False, None, 1, "held"])
def test_missing_current_writer_receipt_refuses_without_carrier_effect(setup, guard_result):
    s = setup
    _, args = request(s)
    with pytest.raises(BridgeError, match="binding"):
        asyncio.run(compose(s, lambda _: guard_result)(args))
    assert not s.service.calls


def test_writer_moves_after_read_refuses_before_send(setup):
    s = setup
    _, args = request(s)
    held = [True]
    s.service.on_read = lambda: held.__setitem__(0, False)
    with pytest.raises(BridgeError):
        asyncio.run(compose(s, lambda _: held[0])(args))
    assert all(c["operation"] == "read_thread" for c in s.service.calls)


@pytest.mark.parametrize("field,value", [("generation_number", 2),
    ("process_generation_id", "other-process"), ("provider_session_id", "foreign-session")])
def test_runtime_generation_drift_refuses(setup, field, value):
    s = setup
    _, args = request(s)
    setattr(s.facts, field, value)
    with pytest.raises(BridgeError):
        asyncio.run(compose(s, lambda _: True)(args))
    assert not s.service.calls


def test_native_owner_disarmed_refuses(setup):
    s = setup
    _, args = request(s)
    s.enabled[0] = False
    with pytest.raises(BridgeError):
        asyncio.run(compose(s, lambda _: True)(args))
    assert not s.service.calls


def test_missing_host_guard_is_not_an_enabled_default(setup):
    with pytest.raises(TypeError):
        compose(setup, None)


def test_lost_reply_reconciles_same_operation_without_second_post(setup):
    s = setup
    ref, args = request(s)
    original = s.service
    class LostResponse:
        async def __call__(self, path, payload, *, before_write=None):
            result = await original(path, payload, before_write=before_write)
            if payload["operation"] == "send_message":
                raise TimeoutError("reply lost after canonical post")
            return result
    s.service = LostResponse()
    callback = compose(s, lambda _: True)
    with pytest.raises(BridgeError) as error:
        asyncio.run(callback(args))
    assert error.value.code == "carrier_effect_unknown"
    assert asyncio.run(callback(args))["action"] == "DUPLICATE"
    assert sum(c["operation"] == "send_message" for c in original.calls) == 1
    s.service = original
    assert read(s, ref)["text"] == args["text"]
    with pytest.raises(BridgeError) as error:
        asyncio.run(callback({**args, "text": "Changed reply."}))
    assert error.value.code == "operation_conflict"


def test_async_writer_guard_is_not_an_ownership_receipt(setup):
    async def guard(binding):
        return True
    with pytest.raises(TypeError, match="synchronous"):
        compose(setup, guard)


@pytest.mark.parametrize("fault", ["writer", "generation", "process", "newer_request"])
def test_drift_after_ready_refuses_before_commit(setup, fault):
    s = setup
    _, args = request(s)
    original = s.service
    held = [True]
    committed = []

    async def prepared_service(path, payload, *, before_write=None):
        if payload["operation"] != "send_message":
            return await original(path, payload)
        if fault == "writer":
            held[0] = False
        elif fault == "generation":
            s.facts.generation_number += 1
        elif fault == "process":
            s.facts.process_generation_id = "other-process"
        else:
            from integrations.slack_agent_dialogue.contract_v2 import build_message_v2
            newer = dict(original.items[0]["message"])
            newer.pop("fingerprint")
            newer["message_key"] = "asd-newer-executive-001"
            original.items.append({"message": build_message_v2(newer),
                                   "primary_ts": "1788000002.123456"})
        if before_write is not None:
            await before_write()
        committed.append(payload)
        return await original(path, payload)

    s.service = prepared_service
    with pytest.raises(BridgeError) as error:
        asyncio.run(compose(s, lambda _: held[0])(args))
    assert error.value.code in {"binding_unavailable", "carrier_stale"}
    assert not committed
    assert not any(c["operation"] == "send_message" for c in original.calls)


@pytest.mark.parametrize("transport_code,expected", [
    ("SERVICE_UNAVAILABLE", "carrier_unavailable"),
    ("SEND_EFFECT_UNKNOWN", "carrier_effect_unknown"),
])
def test_typed_canonical_transport_failure_preserves_effect_stage(setup, transport_code, expected):
    from integrations.slack_agent_dialogue.service import DialogueServiceError
    s = setup
    _, args = request(s)
    original = s.service

    async def failing_service(path, payload, *, before_write=None):
        if payload["operation"] == "send_message":
            raise DialogueServiceError(transport_code)
        return await original(path, payload)

    s.service = failing_service
    with pytest.raises(BridgeError) as error:
        asyncio.run(compose(s, lambda _: True)(args))
    assert error.value.code == expected


def test_post_commit_bridge_error_is_not_a_pre_commit_refusal(setup):
    s = setup
    _, args = request(s)
    original = s.service

    async def losing_service(path, payload, *, before_write=None):
        response = await original(path, payload, before_write=before_write)
        if payload["operation"] == "send_message":
            raise BridgeError("binding_unavailable", "transport raised after posting")
        return response

    s.service = losing_service
    callback = compose(s, lambda _: True)
    with pytest.raises(BridgeError) as error:
        asyncio.run(callback(args))
    assert error.value.code == "carrier_effect_unknown"
    assert asyncio.run(callback(args))["action"] == "DUPLICATE"
    assert sum(c["operation"] == "send_message" for c in original.calls) == 1
