"""Native return proofs; fake transport is not a live native-session proof."""
import asyncio
import copy
import dataclasses
import importlib
from pathlib import Path

import pytest

from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.session_bridge.schemas import BridgeError

NATIVE = "11111111-2222-4444-8888-999999999999"
OTHER = "aaaaaaaa-1111-4444-8888-bbbbbbbbbbbb"
THREAD = "1787896128.625239"
OP = "native-return-001"
REQUEST = "asd-executive-continue-0001"
COMMISSION = {"repository": "mastermindx-market-intelligence/Mastermind", "commit": "1" * 40,
              "path": "docs/superpowers/plans/session-bridge.md", "content_sha256": "2" * 64}
APPLIES = {"kind": "executive_attempt", "job_id": "JOB-001", "attempt_id": "ATT-001", "worker_id": "W-001"}
ACTOR = {"kind": "worker_attempt", "job_id": "JOB-001", "attempt_id": "ATT-001", "worker_id": "W-001"}


def api():
    spec = importlib.util.find_spec("integrations.session_bridge.native_reply")
    assert spec is not None, "native original-parent reply adapter is not implemented"
    return importlib.import_module(spec.name)


def binding():
    return api().NativeReplyBinding(
        native_session_id=NATIVE, binding_id="bind-native-001", binding_generation=1,
        process_generation_id="generation-001", thread_ts=THREAD,
        request_message_key=REQUEST, reply_operation_key=OP,
        context=DialogueContextV2(work_ref="WS:DOT-BRIDGE", commission_ref=COMMISSION,
            session_ref="asd-session-dotbridge01", operation_key="dialogue-parent-001",
            watch_mode="turn_watch_v1", actor_ref=ACTOR, applies_to=APPLIES))


def request():
    return build_message_v2({"schema": MESSAGE_SCHEMA_V2, "message_key": REQUEST,
        "message_type": "CONTINUE", "work_ref": "WS:DOT-BRIDGE", "commission_ref": COMMISSION,
        "session_ref": "asd-session-dotbridge01", "actor_ref": {
            "kind": "executive_surface", "seat": "ceo", "reasoning_surface": "chatgpt"},
        "reply_to_message_key": "asd-worker-result-0001", "applies_to": APPLIES,
        "summary": "Continue bounded work.", "body": {"instruction": "Read the canonical question.",
            "stop_condition": "Return the finding.", "scope_change": False},
        "evidence_refs": [], "requires_response": False, "created_at": "2026-10-01T20:00:00Z"})


def arguments(**changes):
    return {"operation_key": OP, "in_reply_to": REQUEST,
            "text": "The native session found the missing binding.",
            "next_step": "Await the next bounded instruction.", **changes}


class Resolver:
    def __init__(self):
        self.binding = binding()
        self.calls = 0
    def resolve(self, **kwargs):
        self.calls += 1
        return self.binding


class Service:
    def __init__(self):
        self.items = [{"message": request(), "primary_ts": "1787896130.000001"}]
        self.calls = []
        self.on_read = None
        self.send_result = None
        self.send_exception = None
    async def __call__(self, path, payload):
        self.calls.append(copy.deepcopy(payload))
        if payload["operation"] == "read_thread":
            if self.on_read:
                self.on_read()
            return {"ok": True, "result": {"thread_ts": THREAD, "messages": copy.deepcopy(self.items),
                "historical_messages": [], "mutated_count": 0, "ineligible_count": 0}}
        if self.send_exception:
            raise self.send_exception
        if self.send_result is not None:
            return self.send_result
        message = payload["args"]["message"]
        self.items.append({"message": message, "primary_ts": "1787896140.000001"})
        return {"ok": True, "result": {"action": "POSTED", "message_key": message["message_key"],
                                      "fingerprint": message["fingerprint"]}}


def writer(resolver, service):
    return api().NativeReplyWriter(resolver, native_session_id=NATIVE,
        socket_path=Path("/private/tmp/native-reply-proof.sock"), service_call=service)


def test_native_reply_returns_to_original_parent_without_claiming_consumption():
    resolver, service = Resolver(), Service()
    receipt = asyncio.run(writer(resolver, service)(arguments()))
    assert receipt["reply_committed"] is True and receipt["parent_consumed"] is False
    assert receipt["thread_ts"] == THREAD and receipt["in_reply_to"] == REQUEST
    sent = service.calls[-1]["args"]
    assert sent["send_protocol"] == "mastermind.agent_dialogue_exact_send.v1"
    assert sent["context"]["actor_ref"] == ACTOR
    assert sent["message"]["message_type"] == "PROGRESS"
    assert sent["message"]["body"]["stage"] == "message_reply"
    assert sent["message"]["reply_to_message_key"] == REQUEST
    assert resolver.calls == 2


@pytest.mark.parametrize("field", ["target_ref", "thread_ts", "actor_ref", "native_session_id", "permission", "status"])
def test_caller_cannot_supply_routing_or_authority(field):
    r, s = Resolver(), Service()
    with pytest.raises(BridgeError, match="fields"):
        asyncio.run(writer(r, s)(arguments(**{field: "forged"})))
    assert not s.calls


@pytest.mark.parametrize("change", [{"operation_key": "different-op"}, {"in_reply_to": "asd-other-request"},
    {"text": ""}, {"text": "x" * 701}, {"text": "\x00secret"}, {"next_step": False}])
def test_invalid_or_foreign_input_is_refused_before_send(change):
    r, s = Resolver(), Service()
    with pytest.raises(BridgeError):
        asyncio.run(writer(r, s)(arguments(**change)))
    assert not [c for c in s.calls if c["operation"] == "send_message"]


@pytest.mark.parametrize("change", [{"native_session_id": OTHER}, {"reply_operation_key": "wrong-op"},
    {"request_message_key": "asd-other-request"}, {"binding_generation": True}, {"process_generation_id": ""}])
def test_host_binding_must_be_exact_and_well_formed(change):
    r, s = Resolver(), Service()
    r.binding = dataclasses.replace(r.binding, **change)
    with pytest.raises(BridgeError):
        asyncio.run(writer(r, s)(arguments()))
    assert not s.calls


@pytest.mark.parametrize("change", [{"binding_generation": 2}, {"process_generation_id": "generation-002"},
    {"thread_ts": "1787896129.000001"}, {"native_session_id": OTHER}])
def test_binding_change_during_awaited_read_prevents_send(change):
    r, s = Resolver(), Service()
    s.on_read = lambda: setattr(r, "binding", dataclasses.replace(r.binding, **change))
    with pytest.raises(BridgeError):
        asyncio.run(writer(r, s)(arguments()))
    assert len(s.calls) == 1


def test_identical_reply_is_recovered_without_second_send():
    r, s = Resolver(), Service()
    first = asyncio.run(writer(r, s)(arguments()))
    second = asyncio.run(writer(r, s)(arguments()))
    assert second["action"] == "DUPLICATE"
    assert first["message_key"] == second["message_key"]
    assert len([c for c in s.calls if c["operation"] == "send_message"]) == 1


def test_changed_payload_under_same_operation_is_not_a_new_reply():
    r, s = Resolver(), Service()
    asyncio.run(writer(r, s)(arguments()))
    with pytest.raises(BridgeError):
        asyncio.run(writer(r, s)(arguments(text="Changed payload")))
    assert len([c for c in s.calls if c["operation"] == "send_message"]) == 1


@pytest.mark.parametrize("field,value", [("fingerprint", "0" * 64), ("applies_to", {**APPLIES, "attempt_id": "ATT-002"}),
    ("session_ref", "asd-session-other001"), ("actor_ref", ACTOR)])
def test_foreign_or_mutated_original_request_refuses(field, value):
    r, s = Resolver(), Service()
    s.items[0]["message"][field] = value
    with pytest.raises(BridgeError):
        asyncio.run(writer(r, s)(arguments()))
    assert len(s.calls) == 1


def test_newer_executive_instruction_refuses_old_reply():
    r, s = Resolver(), Service()
    newer = request()
    newer["message_key"] = "asd-executive-continue-0002"
    newer.pop("fingerprint")
    newer = build_message_v2(newer)
    s.items.append({"message": newer, "primary_ts": "1787896131.000001"})
    with pytest.raises(BridgeError):
        asyncio.run(writer(r, s)(arguments()))
    assert len(s.calls) == 1


@pytest.mark.parametrize("response", [{}, {"ok": False, "error": {"code": "anything"}},
    {"ok": True, "result": {"action": "POSTED", "message_key": "foreign", "fingerprint": "0" * 64}},
    {"ok": True, "result": {"action": "UNKNOWN"}}])
def test_ambiguous_send_receipt_is_effect_unknown_without_retry(response):
    r, s = Resolver(), Service()
    s.send_result = response
    with pytest.raises(BridgeError) as raised:
        asyncio.run(writer(r, s)(arguments()))
    assert raised.value.code == "carrier_effect_unknown"
    assert len(s.calls) == 2


def test_lost_send_response_is_effect_unknown_and_one_call_only():
    r, s = Resolver(), Service()
    s.send_exception = TimeoutError("private diagnostic must not escape")
    with pytest.raises(BridgeError) as raised:
        asyncio.run(writer(r, s)(arguments()))
    assert raised.value.code == "carrier_effect_unknown"
    assert "private" not in str(raised.value)
    assert len(s.calls) == 2


def test_cancellation_after_send_begins_is_not_reclassified_as_no_effect():
    r, s = Resolver(), Service()
    s.send_exception = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(writer(r, s)(arguments()))
    assert len(s.calls) == 2


def test_revoked_binding_during_duplicate_read_does_not_return_stale_receipt():
    r, s = Resolver(), Service()
    asyncio.run(writer(r, s)(arguments()))
    s.on_read = lambda: setattr(r, "binding", dataclasses.replace(r.binding, binding_generation=2))
    with pytest.raises(BridgeError):
        asyncio.run(writer(r, s)(arguments()))
    assert len([c for c in s.calls if c["operation"] == "send_message"]) == 1


def test_async_host_resolver_is_awaited_before_both_boundaries():
    r, s = Resolver(), Service()
    class AsyncResolver:
        def __init__(self):
            self.calls = 0
        async def resolve(self, **kwargs):
            await asyncio.sleep(0)
            self.calls += 1
            return r.binding
    async_resolver = AsyncResolver()
    receipt = asyncio.run(writer(async_resolver, s)(arguments()))
    assert receipt["reply_committed"] is True and async_resolver.calls == 2


@pytest.mark.parametrize("seat,surface", [("ceo", "codex"), ("coo", "claude")])
def test_native_executive_keeps_existing_role_and_repository_scope(seat, surface):
    r, s = Resolver(), Service()
    actor = {"kind": "executive_surface", "seat": seat, "reasoning_surface": surface}
    applies = {"kind": "repository", "repository": COMMISSION["repository"],
               "head_sha": "1" * 40, "pr": COMMISSION["repository"] + "#1112"}
    r.binding = dataclasses.replace(r.binding, context=dataclasses.replace(r.binding.context,
        actor_ref=actor, applies_to=applies))
    original = request()
    original.pop("fingerprint")
    original["applies_to"] = applies
    s.items[0]["message"] = build_message_v2(original)
    receipt = asyncio.run(writer(r, s)(arguments()))
    assert receipt["reply_committed"] is True
    sent = s.calls[-1]["args"]["message"]
    assert sent["actor_ref"] == actor and sent["applies_to"] == applies
    assert sent["message_type"] == "PROGRESS"


@pytest.mark.parametrize("seat,surface", [("chairman", "chatgpt"), ("ceo", "chatgpt")])
def test_native_channel_does_not_impersonate_web_or_chairman(seat, surface):
    r, s = Resolver(), Service()
    r.binding = dataclasses.replace(r.binding, context=dataclasses.replace(r.binding.context,
        actor_ref={"kind": "executive_surface", "seat": seat, "reasoning_surface": surface}))
    with pytest.raises(BridgeError):
        asyncio.run(writer(r, s)(arguments()))
    assert not s.calls
