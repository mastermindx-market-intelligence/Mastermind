"""Hermetic contracts for the dark Workspace Agent trigger transport."""
from __future__ import annotations

import json
import unittest

from integrations.workspace_agent_api import HOST, MAX_BODY_BYTES, InvalidObservation
from integrations.workspace_agent_trigger import (
    BETA_HEADER,
    MAX_TRIGGER_BODY_BYTES,
    WorkspaceAgentTriggerPlan,
    build_trigger_plan,
    trigger_once,
)

CHANNEL = "agtch_synthetic"
RUN = "apirun_synthetic"
URL = "https://chatgpt.com/c/synthetic"
OPERATION = "workspace-op-001"
TOKEN = "SYNTHETIC_TOKEN"
TRIGGER_BODY = {
    "conversation_url": URL,
    "agent_trigger_run_id": RUN,
}


class FakeResponse:
    def __init__(self, *, status=202, data=None):
        self.status = status
        self.data = (
            json.dumps(TRIGGER_BODY).encode()
            if data is None
            else data
        )
        self.content_type = "application/json; charset=utf-8"
        self.encoding = "identity"
        self.read_amount = None

    def getheader(self, name, default=None):
        return {
            "Content-Type": self.content_type,
            "Content-Encoding": self.encoding,
        }.get(name, default)

    def read(self, amount):
        self.read_amount = amount
        return self.data[:amount]


class FakeConnection:
    def __init__(self, host=HOST, **kwargs):
        self.host = host
        self.kwargs = kwargs
        self.calls = []
        self.closed = False
        self.response = FakeResponse()

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class TriggerPlanTests(unittest.TestCase):
    def build(self, **kwargs):
        return build_trigger_plan(
            channel_id=kwargs.pop("channel_id", CHANNEL),
            operation_key=kwargs.pop("operation_key", OPERATION),
            input_text=kwargs.pop("input_text", "Review the bounded candidate."),
            conversation_key=kwargs.pop("conversation_key", "mastermind-program-1"),
            **kwargs,
        )

    def test_plan_is_deterministic_and_hides_prompt_from_repr(self):
        left = self.build(input_text="SECRET prompt\nwith context")
        right = self.build(input_text="SECRET prompt\nwith context")
        self.assertEqual(left.payload_sha256, right.payload_sha256)
        self.assertEqual(left.idempotency_key, right.idempotency_key)
        self.assertNotIn("SECRET", repr(left))
        self.assertRegex(left.payload_sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(left.idempotency_key, r"^mmx-wa-v1-[0-9a-f]{64}$")

    def test_payload_and_operation_changes_change_idempotency_identity(self):
        original = self.build()
        changed_payload = self.build(input_text="Different bounded candidate.")
        changed_operation = self.build(operation_key="workspace-op-002")
        self.assertNotEqual(original.idempotency_key, changed_payload.idempotency_key)
        self.assertNotEqual(original.idempotency_key, changed_operation.idempotency_key)

    def test_fabricated_plan_cannot_change_payload_under_old_fingerprint(self):
        good = self.build()
        with self.assertRaisesRegex(InvalidObservation, "PAYLOAD_FINGERPRINT_MISMATCH"):
            WorkspaceAgentTriggerPlan(
                channel_id=good.channel_id,
                operation_key=good.operation_key,
                payload_sha256=good.payload_sha256,
                idempotency_key=good.idempotency_key,
                _body=b'{"input":"changed"}',
            )

    def test_plan_body_is_canonical_and_locally_bounded(self):
        plan = self.build(input_text="hello", conversation_key="conv-1")
        self.assertEqual(
            json.loads(plan._body),
            {"conversation_key": "conv-1", "input": "hello"},
        )
        self.assertLessEqual(len(plan._body), MAX_TRIGGER_BODY_BYTES)
        with self.assertRaisesRegex(InvalidObservation, "TRIGGER_BODY_TOO_LARGE"):
            self.build(input_text="x" * MAX_TRIGGER_BODY_BYTES)

    def test_invalid_plan_inputs_fail_before_effect(self):
        cases = (
            {"channel_id": "../../escape"},
            {"operation_key": "BAD KEY"},
            {"input_text": ""},
            {"input_text": "bad\x00prompt"},
            {"conversation_key": "bad\nkey"},
            {"conversation_key": ""},
        )
        for mutation in cases:
            with self.subTest(mutation=mutation), self.assertRaises(InvalidObservation):
                self.build(**mutation)


class TriggerTransportTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_trigger_plan(
            channel_id=CHANNEL,
            operation_key=OPERATION,
            input_text="Review the bounded candidate.",
            conversation_key="mastermind-program-1",
        )

    def invoke(self, connection, **kwargs):
        return trigger_once(
            plan=kwargs.pop("plan", self.plan),
            token=kwargs.pop("token", TOKEN),
            connection_factory=lambda host, **options: connection,
            **kwargs,
        )

    def test_one_exact_post_uses_beta_and_idempotency_headers(self):
        connection = FakeConnection()
        result = self.invoke(connection)
        self.assertEqual(
            (result.disposition, result.reason, result.run_id),
            ("accepted", "ACCEPTED_CORRELATED", RUN),
        )
        self.assertEqual(connection.host, HOST)
        self.assertEqual(len(connection.calls), 1)
        method, path, request = connection.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, f"/v1/workspace_agents/{CHANNEL}/trigger")
        self.assertEqual(request["body"], self.plan._body)
        headers = request["headers"]
        self.assertEqual(headers["OpenAI-Beta"], BETA_HEADER)
        self.assertEqual(headers["Idempotency-Key"], self.plan.idempotency_key)
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertNotIn(TOKEN, path)
        self.assertNotIn(TOKEN.encode(), request["body"])
        self.assertTrue(connection.closed)
        self.assertNotIn(TOKEN, repr(result))

    def test_accepted_with_bad_representation_never_becomes_no_effect(self):
        cases = []
        malformed = FakeConnection()
        malformed.response.data = b"not-json"
        cases.append(malformed)
        wrong_type = FakeConnection()
        wrong_type.response.content_type = "text/html"
        cases.append(wrong_type)
        compressed = FakeConnection()
        compressed.response.encoding = "gzip"
        cases.append(compressed)
        oversize = FakeConnection()
        oversize.response.data = b"x" * 70000
        cases.append(oversize)
        for connection in cases:
            with self.subTest(
                content_type=connection.response.content_type,
                encoding=connection.response.encoding,
                body_len=len(connection.response.data),
            ):
                result = self.invoke(connection)
                self.assertEqual(result.disposition, "accepted")
                self.assertEqual(result.reason, "ACCEPTED_CORRELATION_UNAVAILABLE")
                self.assertIsNone(result.run_id)
                self.assertEqual(len(connection.calls), 1)

    def test_accepted_body_read_failure_preserves_known_provider_acceptance(self):
        connection = FakeConnection()

        def fail_read(amount):
            connection.response.read_amount = amount
            raise OSError("SECRET_BODY_READ")

        connection.response.read = fail_read
        result = self.invoke(connection)
        self.assertEqual(
            (result.disposition, result.reason),
            ("accepted", "ACCEPTED_CORRELATION_UNAVAILABLE"),
        )
        self.assertEqual(connection.response.read_amount, MAX_BODY_BYTES + 1)
        self.assertEqual(len(connection.calls), 1)
        self.assertTrue(connection.closed)
        self.assertNotIn("SECRET_BODY_READ", repr(result))

    def test_known_provider_rejections_do_not_read_or_copy_error_body(self):
        for status in (401, 403, 404, 409):
            connection = FakeConnection()
            connection.response.status = status
            connection.response.data = b"SECRET_VENDOR_ERROR"
            result = self.invoke(connection)
            self.assertEqual(result.disposition, "rejected")
            self.assertEqual(result.reason, f"PROVIDER_REJECTED_{status}")
            self.assertIsNone(connection.response.read_amount)
            self.assertNotIn("SECRET_VENDOR_ERROR", repr(result))

    def test_unknown_http_and_redirect_are_not_retried(self):
        for status in (302, 429, 500, 503):
            connection = FakeConnection()
            connection.response.status = status
            result = self.invoke(connection)
            self.assertEqual(result.disposition, "unknown")
            self.assertEqual(result.reason, "TRIGGER_EFFECT_UNKNOWN")
            self.assertEqual(len(connection.calls), 1)
            self.assertIsNone(connection.response.read_amount)

    def test_transport_failure_after_request_is_effect_unknown_and_single_attempt(self):
        connection = FakeConnection()
        def fail():
            raise OSError("SECRET_TRANSPORT")
        connection.getresponse = fail
        result = self.invoke(connection)
        self.assertEqual(
            (result.disposition, result.reason),
            ("unknown", "TRIGGER_EFFECT_UNKNOWN"),
        )
        self.assertEqual(len(connection.calls), 1)
        self.assertTrue(connection.closed)
        self.assertNotIn("SECRET_TRANSPORT", repr(result))

    def test_close_failure_after_known_response_preserves_provider_disposition(self):
        connection = FakeConnection()
        def fail_close():
            raise OSError("SECRET_CLOSE")
        connection.close = fail_close
        result = self.invoke(connection)
        self.assertEqual(result.disposition, "accepted")
        self.assertEqual(result.reason, "ACCEPTED_CORRELATED")
        self.assertNotIn("SECRET_CLOSE", repr(result))

    def test_invalid_effect_inputs_make_zero_connections(self):
        calls = []
        def forbidden(*args, **kwargs):
            calls.append((args, kwargs))
            self.fail("invalid effect input reached network")

        for mutation in (
            {"plan": None},
            {"token": ""},
            {"token": "bad\nheader"},
            {"timeout_seconds": True},
            {"timeout_seconds": 0},
            {"timeout_seconds": 31},
            {"timeout_seconds": float("nan")},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(InvalidObservation):
                trigger_once(
                    plan=mutation.get("plan", self.plan),
                    token=mutation.get("token", TOKEN),
                    timeout_seconds=mutation.get("timeout_seconds", 10),
                    connection_factory=forbidden,
                )
        self.assertEqual(calls, [])

    def test_frozen_plan_is_revalidated_immediately_before_io(self):
        forged = object.__new__(WorkspaceAgentTriggerPlan)
        object.__setattr__(forged, "channel_id", CHANNEL)
        object.__setattr__(forged, "operation_key", OPERATION)
        object.__setattr__(forged, "payload_sha256", "0" * 64)
        object.__setattr__(forged, "idempotency_key", "mmx-wa-v1-" + "0" * 64)
        object.__setattr__(forged, "_body", b'{"input":"changed"}')
        calls = []
        with self.assertRaises(InvalidObservation):
            trigger_once(
                plan=forged,
                token=TOKEN,
                connection_factory=lambda *args, **kwargs: calls.append(1),
            )
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
