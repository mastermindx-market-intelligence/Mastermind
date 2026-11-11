"""Hermetic contracts for Workspace Agent candidate-return ingress."""
from __future__ import annotations

import copy
from pathlib import Path
import unittest

from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.slack_agent_dialogue.service import DialogueServiceError
from integrations.workspace_agent_return import (
    MAX_TICKET_TTL_MS,
    WORKSPACE_ACTOR_REF,
    WorkspaceCandidateReturnGateway,
    WorkspaceReturnError,
    WorkspaceReturnTicketCodec,
    binding_digest,
)

KEY = b"k" * 32
NOW = 1789822800000
EXPIRES = NOW + 10 * 60 * 1000
SOCKET = Path("/private/tmp/mastermind-agent-dialogue.sock")


def binding(**overrides) -> DialogueBinding:
    values = {
        "actor_ref": {
            "kind": "worker_attempt",
            "job_id": "JOB-001",
            "attempt_id": "ATT-001",
            "worker_id": "W-001",
        },
        "work_ref": "WS:WORKSPACE-AGENT-PROGRAM",
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "1" * 40,
            "path": "research/WORKSPACE_AGENT_SUPERVISION_INTEGRATION_2026-09-13.md",
            "content_sha256": "2" * 64,
        },
        "session_ref": "asd-session-workspace-agent-program-001",
        "operation_key": "workspace-agent-supervision-001",
        "watch_mode": None,
        "applies_to": {
            "kind": "executive_attempt",
            "job_id": "JOB-001",
            "attempt_id": "ATT-001",
            "worker_id": "W-001",
        },
        "thread_ts": "1787896128.625239",
        "allowed_message_types": (
            "ACK",
            "PROGRESS",
            "BLOCKED",
            "DECISION_REQUEST",
            "RESULT",
        ),
        "reply_to_message_key": None,
    }
    values.update(overrides)
    return DialogueBinding(**values)


class Resolver:
    def __init__(self, value=None, *, error=None):
        self.value = value or binding()
        self.error = error
        self.calls = []

    def resolve(self, operation_key: str) -> DialogueBinding:
        self.calls.append(operation_key)
        if self.error is not None:
            raise self.error
        return self.value


class RecordingService:
    def __init__(self, *, action="POSTED", error=None, malformed=False):
        self.action = action
        self.error = error
        self.malformed = malformed
        self.calls = []

    async def __call__(self, socket_path: Path, request: dict) -> dict:
        self.calls.append((socket_path, copy.deepcopy(request)))
        if self.error is not None:
            raise self.error
        if self.malformed:
            return {"ok": True, "result": {"untrusted": "SECRET"}}
        message = request["args"]["message"]
        return {
            "ok": True,
            "result": {
                "action": self.action,
                "message_key": message["message_key"],
                "fingerprint": message["fingerprint"],
                "message_ts": "1789822800.111111",
                "duplicate_timestamps": [],
                "thread_ts": request["args"]["thread_ts"],
                "parent_author_user_id": "U-RELAY",
                "parent_fingerprint": "3" * 64,
            },
        }


def mint(codec=None, current=None, **overrides):
    codec = codec or WorkspaceReturnTicketCodec(KEY)
    current = current or binding()
    args = {
        "binding": current,
        "ticket_id": "wr-workspace-return-001",
        "issued_at_ms": NOW,
        "expires_at_ms": EXPIRES,
    }
    args.update(overrides)
    return codec, codec.mint(**args)


def arguments(token, **overrides):
    value = {
        "return_ref": token,
        "status": "PASS",
        "result": "Candidate only; review the attached evidence before acceptance.",
        "evidence_refs": ["https://github.com/example/repo/pull/1"],
    }
    value.update(overrides)
    return value


class TicketCodecTests(unittest.TestCase):
    def test_round_trip_binds_operation_current_target_and_message_identity(self):
        codec, token = mint()
        ticket = codec.decode(token, now_ms=NOW + 1)
        self.assertEqual(ticket.operation_key, binding().operation_key)
        self.assertEqual(ticket.binding_digest, binding_digest(binding()))
        self.assertRegex(ticket.message_key, r"^asd-wsa-[0-9a-f]{32}$")
        self.assertNotIn("JOB-001", token)
        self.assertNotIn("ATT-001", token)
        self.assertNotIn("W-001", token)

    def test_same_ticket_identity_and_binding_is_deterministic(self):
        codec = WorkspaceReturnTicketCodec(KEY)
        _, left = mint(codec=codec)
        _, right = mint(codec=codec)
        self.assertEqual(left, right)
        self.assertEqual(
            codec.decode(left, now_ms=NOW).message_key,
            codec.decode(right, now_ms=NOW).message_key,
        )

    def test_binding_change_changes_frozen_digest(self):
        original = binding()
        moved = binding(
            actor_ref={
                "kind": "worker_attempt",
                "job_id": "JOB-001",
                "attempt_id": "ATT-002",
                "worker_id": "W-002",
            },
            applies_to={
                "kind": "executive_attempt",
                "job_id": "JOB-001",
                "attempt_id": "ATT-002",
                "worker_id": "W-002",
            },
        )
        self.assertNotEqual(binding_digest(original), binding_digest(moved))

    def test_tamper_expiry_and_future_tokens_refuse(self):
        codec, token = mint()
        head, sig = token.split(".")
        replacement = ("A" if head[0] != "A" else "B") + head[1:]
        with self.assertRaisesRegex(WorkspaceReturnError, "INVALID_RETURN_REF"):
            codec.decode(replacement + "." + sig, now_ms=NOW)
        with self.assertRaisesRegex(WorkspaceReturnError, "RETURN_REF_EXPIRED"):
            codec.decode(token, now_ms=EXPIRES + 1)
        with self.assertRaisesRegex(WorkspaceReturnError, "RETURN_REF_NOT_YET_VALID"):
            codec.decode(token, now_ms=NOW - 1)

    def test_mint_refuses_bad_key_ticket_and_ttl(self):
        with self.assertRaises(ValueError):
            WorkspaceReturnTicketCodec(b"short")
        codec = WorkspaceReturnTicketCodec(KEY)
        with self.assertRaisesRegex(WorkspaceReturnError, "INVALID_TICKET_ID"):
            codec.mint(
                binding=binding(),
                ticket_id="bad",
                issued_at_ms=NOW,
                expires_at_ms=EXPIRES,
            )
        with self.assertRaisesRegex(WorkspaceReturnError, "INVALID_TICKET_TIME"):
            codec.mint(
                binding=binding(),
                ticket_id="wr-workspace-return-001",
                issued_at_ms=NOW,
                expires_at_ms=NOW + MAX_TICKET_TTL_MS + 1,
            )


class CandidateReturnGatewayTests(unittest.IsolatedAsyncioTestCase):
    def make_gateway(self, *, current=None, resolver=None, service=None, now=NOW + 1):
        resolver = resolver or Resolver(current or binding())
        service = service or RecordingService()
        gateway = WorkspaceCandidateReturnGateway(
            codec=WorkspaceReturnTicketCodec(KEY),
            binding_resolver=resolver,
            socket_path=SOCKET,
            clock_ms=lambda: now,
            utc_now=lambda: "2026-09-19T14:20:00Z",
            service_call=service,
        )
        return gateway, resolver, service

    async def test_success_uses_workspace_actor_and_existing_dialogue_owner_once(self):
        current = binding()
        codec, token = mint(current=current)
        gateway, resolver, service = self.make_gateway(current=current)
        gateway._codec = codec
        result = await gateway.call(arguments(token))
        self.assertEqual(
            result,
            {
                "schema": "mastermind.workspace_agent_candidate_return.v1",
                "ok": True,
                "state": "CANDIDATE_RECORDED",
                "message_key": result["message_key"],
                "transport_action": "POSTED",
                "accepted": False,
                "wake_acknowledged": False,
            },
        )
        self.assertEqual(resolver.calls, [current.operation_key])
        self.assertEqual(len(service.calls), 1)
        socket_path, request = service.calls[0]
        self.assertEqual(socket_path, SOCKET)
        self.assertEqual(request["version"], "mastermind.agent_dialogue_control.v2")
        self.assertEqual(request["operation"], "send_message")
        self.assertEqual(
            request["args"]["send_protocol"],
            "mastermind.agent_dialogue_exact_send.v1",
        )
        self.assertEqual(request["args"]["thread_ts"], current.thread_ts)
        context = request["args"]["context"]
        message = request["args"]["message"]
        self.assertEqual(context["actor_ref"], WORKSPACE_ACTOR_REF)
        self.assertEqual(message["actor_ref"], WORKSPACE_ACTOR_REF)
        self.assertEqual(message["applies_to"], current.applies_to)
        self.assertEqual(message["message_type"], "RESULT")
        self.assertEqual(message["body"]["status"], "PASS")
        self.assertFalse(message["requires_response"])
        self.assertNotIn(token, repr(result))

    async def test_current_target_change_refuses_before_carrier_effect(self):
        original = binding()
        moved = binding(
            actor_ref={
                "kind": "worker_attempt",
                "job_id": "JOB-001",
                "attempt_id": "ATT-002",
                "worker_id": "W-002",
            },
            applies_to={
                "kind": "executive_attempt",
                "job_id": "JOB-001",
                "attempt_id": "ATT-002",
                "worker_id": "W-002",
            },
        )
        _, token = mint(current=original)
        gateway, resolver, service = self.make_gateway(current=moved)
        result = await gateway.call(arguments(token))
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "CURRENT_TARGET_CHANGED")
        self.assertEqual(len(resolver.calls), 1)
        self.assertEqual(service.calls, [])

    async def test_invalid_or_expired_ref_has_zero_resolver_and_service_calls(self):
        codec, token = mint()
        for return_ref, now, state in (
            ("not-a-ticket", NOW, "INVALID_RETURN_REF"),
            (token, EXPIRES + 1, "RETURN_REF_EXPIRED"),
        ):
            resolver = Resolver()
            service = RecordingService()
            gateway, _, _ = self.make_gateway(
                resolver=resolver,
                service=service,
                now=now,
            )
            result = await gateway.call(arguments(return_ref))
            self.assertFalse(result["ok"])
            self.assertEqual(result["state"], state)
            self.assertEqual(resolver.calls, [])
            self.assertEqual(service.calls, [])

    async def test_effect_unknown_never_retries_and_preserves_message_identity(self):
        _, token = mint()
        service = RecordingService(error=DialogueServiceError("SEND_EFFECT_UNKNOWN"))
        gateway, _, service = self.make_gateway(service=service)
        result = await gateway.call(arguments(token))
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertRegex(result["message_key"], r"^asd-wsa-[0-9a-f]{32}$")
        self.assertEqual(len(service.calls), 1)

    async def test_predispatch_service_unavailable_is_distinct_from_unknown_effect(self):
        _, token = mint()
        service = RecordingService(error=DialogueServiceError("SERVICE_UNAVAILABLE"))
        gateway, _, service = self.make_gateway(service=service)
        result = await gateway.call(arguments(token))
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "SERVICE_UNAVAILABLE")
        self.assertEqual(len(service.calls), 1)

    async def test_malformed_success_receipt_is_effect_unknown_not_success(self):
        _, token = mint()
        service = RecordingService(malformed=True)
        gateway, _, service = self.make_gateway(service=service)
        result = await gateway.call(arguments(token))
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual(len(service.calls), 1)
        self.assertNotIn("SECRET", repr(result))

    async def test_duplicate_is_safe_carrier_evidence_not_company_acceptance(self):
        _, token = mint()
        service = RecordingService(action="DUPLICATE")
        gateway, _, _ = self.make_gateway(service=service)
        result = await gateway.call(arguments(token))
        self.assertTrue(result["ok"])
        self.assertEqual(result["transport_action"], "DUPLICATE")
        self.assertFalse(result["accepted"])
        self.assertFalse(result["wake_acknowledged"])

    async def test_argument_widening_and_result_overflow_refuse_before_resolution(self):
        _, token = mint()
        cases = (
            {"return_ref": token, "status": "PASS", "result": "ok", "job_id": "JOB-999"},
            {"return_ref": token, "status": "ACCEPTED", "result": "ok"},
            {"return_ref": token, "status": "PASS", "result": "x" * 901},
            {"return_ref": token, "status": "PASS", "result": "ok", "evidence_refs": ["https://evil.invalid/x"]},
        )
        for value in cases:
            resolver = Resolver()
            service = RecordingService()
            gateway, _, _ = self.make_gateway(resolver=resolver, service=service)
            with self.subTest(value=value):
                result = await gateway.call(value)
                self.assertFalse(result["ok"])
                self.assertEqual(result["state"], "INVALID_REQUEST")
                self.assertEqual(resolver.calls, [])
                self.assertEqual(service.calls, [])

    async def test_resolver_exception_is_redacted_and_zero_carrier_effect(self):
        _, token = mint()
        resolver = Resolver(error=RuntimeError("xoxb-SYNTHETIC-SECRET"))
        service = RecordingService()
        gateway, _, _ = self.make_gateway(resolver=resolver, service=service)
        result = await gateway.call(arguments(token))
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "BINDING_UNAVAILABLE")
        self.assertEqual(service.calls, [])
        self.assertNotIn("SYNTHETIC", repr(result))


if __name__ == "__main__":
    unittest.main()
