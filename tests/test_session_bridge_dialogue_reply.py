import asyncio
from pathlib import Path

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
            "dot-reply-001",
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
