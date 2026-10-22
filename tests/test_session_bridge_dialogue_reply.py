import asyncio
import dataclasses
from pathlib import Path
from types import MappingProxyType

import pytest

from integrations.session_bridge.dialogue_reply import (
    AgentDialogueContinueWriter,
    ExecutiveReplyBinding,
)
from integrations.session_bridge.schemas import BridgeError
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    build_message_v2,
)


COMMISSION = {
    "repository": "mastermindx-market-intelligence/Mastermind",
    "commit": "1" * 40,
    "path": "docs/superpowers/plans/session-bridge.md",
    "content_sha256": "2" * 64,
}
APPLIES = {
    "kind": "executive_attempt",
    "job_id": "JOB-001",
    "attempt_id": "ATT-001",
    "worker_id": "W-001",
}
THREAD_TS = "1787896128.625239"


def _worker_result():
    return build_message_v2(
        {
            "schema": MESSAGE_SCHEMA_V2,
            "message_key": "asd-worker-result-0001",
            "message_type": "RESULT",
            "work_ref": "WS:DOT-BRIDGE",
            "commission_ref": COMMISSION,
            "session_ref": "asd-session-dotbridge01",
            "actor_ref": {
                "kind": "worker_attempt",
                "job_id": "JOB-001",
                "attempt_id": "ATT-001",
                "worker_id": "W-001",
            },
            "reply_to_message_key": None,
            "applies_to": APPLIES,
            "summary": "Worker returned bounded evidence.",
            "body": {"status": "PASS", "result": "First slice complete."},
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2026-09-30T19:00:00Z",
        }
    )


def _binding():
    return ExecutiveReplyBinding(
        target_ref="codex:bind-001:g1",
        target_generation="g1",
        current_writer={"kind": "worker_attempt", "job_id": "JOB-001",
                        "attempt_id": "ATT-001", "worker_id": "W-001"},
        work_ref="WS:DOT-BRIDGE",
        commission_ref=COMMISSION,
        session_ref="asd-session-dotbridge01",
        dialogue_operation_key="dot-bridge-worker-op-001",
        watch_mode="turn_watch_v1",
        applies_to=APPLIES,
        thread_ts=THREAD_TS,
        reply_to_message_key="asd-worker-result-0001",
    )


class Resolver:
    def __init__(self, binding=None):
        self.binding = binding or _binding()
        self.calls = []

    def resolve(self, target_ref):
        self.calls.append(target_ref)
        return self.binding


class Service:
    def __init__(self, *, existing_reply=None, send_error=None):
        self.calls = []
        self.existing_reply = existing_reply
        self.send_error = send_error

    async def __call__(self, socket_path, request):
        self.calls.append((socket_path, request))
        if request["operation"] == "read_thread":
            messages = [
                {
                    "message": _worker_result(),
                    "primary_ts": "1787896129.000001",
                    "duplicate_timestamps": [],
                }
            ]
            if self.existing_reply is not None:
                messages.append(
                    {
                        "message": self.existing_reply,
                        "primary_ts": "1787896130.000001",
                        "duplicate_timestamps": [],
                    }
                )
            return {
                "ok": True,
                "result": {
                    "thread_ts": THREAD_TS,
                    "messages": messages,
                    "historical_messages": [],
                    "ineligible_count": 0,
                    "mutated_count": 0,
                },
            }
        if request["operation"] == "send_message":
            if self.send_error is not None:
                return {"ok": False, "error": {"code": self.send_error}}
            message = request["args"]["message"]
            return {
                "ok": True,
                "result": {
                    "action": "POSTED",
                    "message_key": message["message_key"],
                    "fingerprint": message["fingerprint"],
                },
            }
        raise AssertionError(request)


def _run(service):
    writer = AgentDialogueContinueWriter(
        Resolver(),
        socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
        service_call=service,
    )
    return asyncio.run(
        writer(
            "codex:bind-001:g1",
            "Inspect the next bounded failure.",
            "Stop after the next validated RESULT.",
            _binding().continuation_operation_key,
        )
    )


def test_continue_writer_fresh_reads_then_exact_sends():
    service = Service()
    result = _run(service)

    assert result["reply_committed"] is True
    assert result["action"] == "POSTED"
    assert [call[1]["operation"] for call in service.calls] == [
        "read_thread",
        "send_message",
    ]
    send = service.calls[1][1]
    assert send["args"]["send_protocol"] == "mastermind.agent_dialogue_exact_send.v1"
    message = send["args"]["message"]
    assert message["message_type"] == "CONTINUE"
    assert message["reply_to_message_key"] == "asd-worker-result-0001"
    assert message["body"] == {
        "instruction": "Inspect the next bounded failure.",
        "stop_condition": "Stop after the next validated RESULT.",
        "scope_change": False,
    }
    assert message["actor_ref"] == {
        "kind": "executive_surface",
        "seat": "ceo",
        "reasoning_surface": "chatgpt",
    }


def test_continue_writer_reconciles_identical_existing_reply_without_resend():
    first = Service()
    first_result = _run(first)
    existing = first.calls[1][1]["args"]["message"]

    second = Service(existing_reply=existing)
    result = _run(second)

    assert result["reply_committed"] is True
    assert result["action"] == "DUPLICATE"
    assert [call[1]["operation"] for call in second.calls] == ["read_thread"]
    assert result["message_key"] == first_result["message_key"]


def test_continue_writer_refuses_different_existing_executive_reply():
    first = Service()
    _run(first)
    existing = dict(first.calls[1][1]["args"]["message"])
    existing["body"] = {
        "instruction": "Different instruction.",
        "stop_condition": "Different stop.",
        "scope_change": False,
    }

    service = Service(existing_reply=existing)
    try:
        _run(service)
    except BridgeError as exc:
        assert exc.code == "carrier_stale"
    else:
        raise AssertionError("different prior executive reply must block")


def test_continue_writer_preserves_effect_unknown_and_does_not_retry():
    service = Service(send_error="SEND_EFFECT_UNKNOWN")
    try:
        _run(service)
    except BridgeError as exc:
        assert exc.code == "carrier_effect_unknown"
    else:
        raise AssertionError("effect unknown must surface")
    assert [call[1]["operation"] for call in service.calls] == [
        "read_thread",
        "send_message",
    ]


def test_continue_writer_re_resolves_complete_binding_after_awaited_read():
    original = _binding()
    rotated = dataclasses.replace(
        original,
        session_ref="asd-session-dotbridge02",
        dialogue_operation_key="dot-bridge-worker-op-002",
    )

    class RotatingResolver:
        def __init__(self):
            self.calls = []

        def resolve(self, target_ref):
            self.calls.append(target_ref)
            return original if len(self.calls) == 1 else rotated

    resolver = RotatingResolver()
    service = Service()
    writer = AgentDialogueContinueWriter(
        resolver,
        socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
        service_call=service,
    )

    with pytest.raises(BridgeError) as error:
        asyncio.run(
            writer(
                original.target_ref,
                "Inspect the next bounded failure.",
                "Stop after the next validated RESULT.",
                _binding().continuation_operation_key,
            )
        )

    assert error.value.code == "binding_unavailable"
    assert resolver.calls == [original.target_ref, original.target_ref]
    assert [call[1]["operation"] for call in service.calls] == ["read_thread"]


def test_continue_writer_re_resolve_detects_in_place_nested_binding_mutation():
    commission = dict(COMMISSION)
    applies = dict(APPLIES)
    binding = ExecutiveReplyBinding(
        target_ref="codex:bind-001:g1",
        target_generation="g1",
        current_writer={"kind": "worker_attempt", "job_id": "JOB-001",
                        "attempt_id": "ATT-001", "worker_id": "W-001"},
        work_ref="WS:DOT-BRIDGE",
        commission_ref=commission,
        session_ref="asd-session-dotbridge01",
        dialogue_operation_key="dot-bridge-worker-op-001",
        watch_mode="turn_watch_v1",
        applies_to=applies,
        thread_ts=THREAD_TS,
        reply_to_message_key="asd-worker-result-0001",
    )

    class AliasedResolver:
        def __init__(self):
            self.calls = []

        def resolve(self, target_ref):
            self.calls.append(target_ref)
            return binding

    class MutatingService(Service):
        async def __call__(self, socket_path, request):
            response = await super().__call__(socket_path, request)
            if request["operation"] == "read_thread":
                commission["commit"] = "9" * 40
            return response

    resolver = AliasedResolver()
    service = MutatingService()
    writer = AgentDialogueContinueWriter(
        resolver,
        socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
        service_call=service,
    )

    with pytest.raises(BridgeError) as error:
        asyncio.run(
            writer(
                binding.target_ref,
                "Inspect the next bounded failure.",
                "Stop after the next validated RESULT.",
                _binding().continuation_operation_key,
            )
        )

    assert error.value.code == "binding_unavailable"
    assert resolver.calls == [binding.target_ref, binding.target_ref]
    assert [call[1]["operation"] for call in service.calls] == ["read_thread"]


@pytest.mark.parametrize("change", [
    {"target_ref": "codex:bind-002:g1"},
    {"target_generation": "g2"},
    {"thread_ts": "1787896128.999999"},
    {"reply_to_message_key": "asd-worker-result-0002"},
    {"current_writer": {"kind": "worker_attempt", "job_id": "JOB-001",
                        "attempt_id": "ATT-002", "worker_id": "W-001"},
     "applies_to": {**APPLIES, "attempt_id": "ATT-002"}},
])
def test_other_carrier_cannot_reuse_continuation_key_before_any_read(change):
    original = _binding()
    second = dataclasses.replace(original, **change)
    assert second.continuation_operation_key != original.continuation_operation_key
    service = Service()
    writer = AgentDialogueContinueWriter(
        Resolver(second), socket_path=Path("/private/tmp/dialogue.sock"), service_call=service)
    with pytest.raises(BridgeError) as exc:
        asyncio.run(writer(second.target_ref, "Continue.", "Return.", original.continuation_operation_key))
    assert exc.value.code == "operation_carrier_conflict"
    assert service.calls == []


@pytest.mark.parametrize("change", [
    {"target_generation": "g2"},
    {"thread_ts": "1787896128.999999"},
    {"reply_to_message_key": "asd-worker-result-0002"},
    {"current_writer": {"kind": "worker_attempt", "job_id": "JOB-001",
                        "attempt_id": "ATT-002", "worker_id": "W-001"},
     "applies_to": {**APPLIES, "attempt_id": "ATT-002"}},
])
def test_continuation_binding_rotation_across_read_never_sends(change):
    first = _binding()
    class Rotating:
        calls = 0
        def resolve(self, target_ref):
            self.calls += 1
            return first if self.calls == 1 else dataclasses.replace(first, **change)
    service = Service()
    writer = AgentDialogueContinueWriter(
        Rotating(), socket_path=Path("/private/tmp/dialogue.sock"), service_call=service)
    with pytest.raises(BridgeError) as exc:
        asyncio.run(writer(first.target_ref, "Continue.", "Return.", first.continuation_operation_key))
    assert exc.value.code == "binding_unavailable"
    assert [call[1]["operation"] for call in service.calls] == ["read_thread"]


def test_carrier_message_must_be_from_bound_current_writer():
    class WrongWriter(Service):
        async def __call__(self, socket_path, request):
            response = await super().__call__(socket_path, request)
            if request["operation"] == "read_thread":
                response["result"]["messages"][0]["message"]["actor_ref"]["worker_id"] = "W-OTHER"
            return response
    service = WrongWriter()
    with pytest.raises(BridgeError) as exc:
        _run(service)
    assert exc.value.code == "carrier_stale"
    assert [call[1]["operation"] for call in service.calls] == ["read_thread"]


@pytest.mark.parametrize("bad", [
    object(),
    dataclasses.replace(_binding(), target_generation=object()),
    dataclasses.replace(_binding(), current_writer=None),
    dataclasses.replace(_binding(), current_writer=MappingProxyType(dict(_binding().current_writer))),
])
@pytest.mark.parametrize("after_read", [False, True])
def test_malformed_binding_is_pre_send_refusal(bad, after_read):
    first = _binding()
    class Malformed:
        calls = 0
        def resolve(self, target_ref):
            self.calls += 1
            return first if after_read and self.calls == 1 else bad
    service = Service()
    writer = AgentDialogueContinueWriter(
        Malformed(), socket_path=Path("/private/tmp/dialogue.sock"), service_call=service)
    with pytest.raises(BridgeError) as exc:
        asyncio.run(writer(first.target_ref, "Continue.", "Return.", first.continuation_operation_key))
    assert exc.value.code == "binding_unavailable"
    assert [call[1]["operation"] for call in service.calls] == (["read_thread"] if after_read else [])


@pytest.mark.parametrize("fault", [None, "unknown", "binding", "callback"])
def test_commit_hook_runs_after_ready_and_refuses_before_commit(fault):
    from integrations.slack_agent_dialogue.service import DialogueServiceError
    resolver, service, order = Resolver(), Service(), []
    def commit(**facts):
        order.append("admit")
        assert facts["message"]["body"]["instruction"] == "Continue."
        if fault == "callback":
            raise BridgeError("carrier_effect_unknown", "sticky commit")
    async def exact_service(path, request, **kwargs):
        if request["operation"] == "read_thread":
            order.append("read")
            assert not kwargs
            return await service(path, request)
        assert set(kwargs) == {"before_write"}
        order.append("ready")
        if fault == "binding":
            resolver.binding = dataclasses.replace(resolver.binding, target_generation="changed")
        await kwargs["before_write"]()
        order.append("commit")
        if fault == "unknown":
            raise DialogueServiceError("SEND_EFFECT_UNKNOWN")
        return await service(path, request)
    writer = AgentDialogueContinueWriter(resolver, socket_path=Path("/private/tmp/test.sock"),
        service_call=exact_service, before_commit=commit)
    async def run():
        return await writer(_binding().target_ref, "Continue.", "Return.", _binding().continuation_operation_key)
    if fault:
        with pytest.raises(BridgeError):
            asyncio.run(run())
    else:
        assert asyncio.run(run())["reply_committed"]
    assert order[:3] == ["read", "ready", "read"]
    assert order.count("commit") == (0 if fault in {"binding", "callback"} else 1)
    assert order.count("admit") == (0 if fault == "binding" else 1)
