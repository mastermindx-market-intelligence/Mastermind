"""Provider protocol and CLI contracts; these tests are not live agent proof."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from integrations.workspace_agent_api import (
    HOST, MAX_BODY_BYTES, InvalidObservation, decode_run, decode_trigger, read_run_once,
)

CHANNEL = "agtch_synthetic"
RUN = "apirun_synthetic"
URL = "https://chatgpt.com/c/synthetic"
BODY = {
    "object": "workspace_agent.trigger_run", "id": RUN, "status": "in_progress",
    "created_at": 1789257780, "agent_id": "agt_synthetic", "api_trigger_id": CHANNEL,
    "conversation_url": URL, "error": None,
}
NOW = 1789340800


def encode(data):
    return json.dumps(data).encode()


def observe(data=BODY, status=200, **kwargs):
    return decode_run(status, encode(data), channel_id=CHANNEL, run_id=RUN,
                      observed_at=NOW, **kwargs)


class TriggerTests(unittest.TestCase):
    def test_valid_beta_correlation_is_acceptance_not_result(self):
        result = decode_trigger(202, encode({"conversation_url": URL, "agent_trigger_run_id": RUN}))
        self.assertEqual((result.disposition, result.run_id, result.correlation_available),
                         ("accepted", RUN, True))
        self.assertFalse(hasattr(result, "answer"))
        self.assertFalse(hasattr(result, "company_accepted"))

    def test_legacy_acceptance_without_run(self):
        result = decode_trigger(202, encode({"conversation_url": URL}))
        self.assertEqual(result.disposition, "accepted")
        self.assertEqual(result.reason, "ACCEPTED_WITHOUT_RUN_ID")
        self.assertIsNone(result.run_id)
        self.assertFalse(result.correlation_available)

    def test_bad_202_correlation_never_becomes_no_effect(self):
        for body in (b"", b"not-json", b"[]", b"x" * (MAX_BODY_BYTES + 1),
                     encode({"conversation_url": "https://evil.invalid/c/a", "agent_trigger_run_id": RUN}),
                     encode({"conversation_url": URL, "agent_trigger_run_id": "../../other"}),
                     b'{"conversation_url":"a","conversation_url":"b"}'):
            with self.subTest(body_len=len(body)):
                result = decode_trigger(202, body)
                self.assertEqual(result.disposition, "accepted")
                self.assertFalse(result.correlation_available)
                self.assertIsNone(result.run_id)
                self.assertIsNone(result.conversation_url)

    def test_documented_rejections_do_not_copy_error_body(self):
        for code in (401, 403, 404, 409):
            result = decode_trigger(code, b"SECRET_TOKEN")
            self.assertEqual(result.disposition, "rejected")
            self.assertNotIn("SECRET_TOKEN", repr(result))

    def test_unknown_http_and_timeout_are_uncertain(self):
        for code in (None, True, False, "202", 200, 201, 301, 429, 500, 503):
            self.assertEqual(decode_trigger(code, b"{}").disposition, "unknown")


class RunTests(unittest.TestCase):
    def test_all_known_states_have_only_provider_terminal_meaning(self):
        for state in ("queued", "in_progress", "suspended", "completed", "failed"):
            with self.subTest(state=state):
                result = observe({**BODY, "status": state})
                self.assertTrue(result.available)
                self.assertEqual(result.provider_terminal, state in {"completed", "failed"})
                self.assertNotIn("answer", result.to_dict())
                self.assertNotIn("accepted", result.to_dict())

    def test_unknown_state_is_unknown_not_idle_or_terminal(self):
        result = observe({**BODY, "status": "future_state"})
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "UNKNOWN_PROVIDER_STATE")
        self.assertIsNone(result.provider_terminal)
        self.assertIsNone(result.provider_state)

    def test_tool_disabled_helper_repair_cases_are_independently_verified(self):
        # Five reviewed one-field cases from the repaired native helper result.
        # The original Flash response was invalid JSON and was not imported.
        cases = [({}, "OBSERVED"), ({"status": "suspended"}, "OBSERVED"),
                 ({"status": "future_state"}, "UNKNOWN_PROVIDER_STATE"),
                 ({"id": "apirun_other"}, "CORRELATION_MISMATCH"),
                 ({"created_at": True}, "INVALID_TIMESTAMP")]
        for mutation, expected_reason in cases:
            with self.subTest(mutation=mutation):
                self.assertEqual(observe({**BODY, **mutation}).reason, expected_reason)

    def test_wrong_run_and_channel_refuse_even_if_completed(self):
        for key, value in (("id", "apirun_other"), ("api_trigger_id", "agtch_other")):
            result = observe({**BODY, key: value, "status": "completed"})
            self.assertEqual(result.reason, "CORRELATION_MISMATCH")
            self.assertFalse(result.available)
            self.assertIsNone(result.provider_terminal)

    def test_broken_fixture_from_helper_is_not_promoted(self):
        result = observe({**BODY, "status": "completed", "agent_id": CHANNEL,
                          "api_trigger_id": RUN,
                          "conversation_url": "https://api.anthropic.com/v1/conversations/fixture"})
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "CORRELATION_MISMATCH")

    def test_correlation_with_expected_conversation(self):
        self.assertTrue(observe(expected_conversation_url=URL).available)
        self.assertEqual(observe(expected_conversation_url="https://chatgpt.com/c/other").reason,
                         "CONVERSATION_MISMATCH")

    def test_bad_timestamp_never_becomes_zero(self):
        for value in (True, None, -1, 1.5, "1789257780", 2**63):
            result = observe({**BODY, "created_at": value})
            self.assertEqual(result.reason, "INVALID_TIMESTAMP")
            self.assertIsNone(result.provider_created_at)
        self.assertEqual(observe({**BODY, "created_at": NOW + 1}).reason, "PROVIDER_CLOCK_AHEAD")

    def test_url_validation_blocks_foreign_host_and_normalization_tricks(self):
        for url in ("http://chatgpt.com/c/a", "https://chatgpt.com.evil.invalid/c/a",
                    "https://user@chatgpt.com/c/a", "https://chatgpt.com:443/c/a",
                    "\nhttps://chatgpt.com/c/a", "https://chatgpt.com/c/a?token=SECRET",
                    "https://chatgpt.com/c/a#x", "https://chatgpt.com/c/%2e%2e",
                    "https://chatgpt.com/c/a\t", "https://chatgpt.com/other/a"):
            with self.subTest(url=url):
                self.assertEqual(observe({**BODY, "conversation_url": url}).reason,
                                 "INVALID_CONVERSATION_URL")

    def test_noncanonical_url_spellings_are_rejected_before_correlation(self):
        for url in (URL + "?", URL + "#", URL.replace("https:", "HTTPS:")):
            with self.subTest(url=url):
                self.assertEqual(observe({**BODY, "conversation_url": url}).reason,
                                 "INVALID_CONVERSATION_URL")
                trigger = decode_trigger(202, encode({"conversation_url": url,
                                                      "agent_trigger_run_id": RUN}))
                self.assertEqual(trigger.disposition, "accepted")
                self.assertFalse(trigger.correlation_available)
                with self.assertRaises(InvalidObservation):
                    observe(expected_conversation_url=url)

    def test_error_category_is_closed_and_error_prose_not_retained(self):
        for code in ("dispatch_failed", "run_failed", "SECRET_TOKEN"):
            result = observe({**BODY, "status": "failed", "error": {"code": code, "message": "SECRET_TOKEN"}})
            self.assertTrue(result.available)
            self.assertEqual(result.failure_code, code if code != "SECRET_TOKEN" else "unknown")
            self.assertNotIn("SECRET_TOKEN", repr(result))

    def test_contradictory_and_malformed_errors_refuse(self):
        self.assertEqual(observe({**BODY, "status": "completed", "error": {"code": "run_failed"}}).reason,
                         "CONTRADICTORY_ERROR")
        for error in ("SECRET", [], {"message": "SECRET"}, {"code": []}):
            self.assertEqual(observe({**BODY, "status": "failed", "error": error}).reason,
                             "INVALID_ERROR_SHAPE")
        without_error = dict(BODY)
        del without_error["error"]
        self.assertEqual(observe(without_error).reason, "MISSING_ERROR_FIELD")

    def test_additive_answer_field_cannot_manufacture_result(self):
        result = observe({**BODY, "status": "completed", "answer": "SECRET", "job_status": "accepted"})
        self.assertTrue(result.available)
        self.assertNotIn("SECRET", repr(result))
        self.assertNotIn("job_status", result.to_dict())

    def test_duplicate_keys_and_nonfinite_json_refuse(self):
        for raw in (encode(BODY)[:-1] + b',"status":"completed"}',
                    encode(BODY).replace(b'1789257780', b'NaN'),
                    b'[' * 2000 + b']' * 2000):
            result = decode_run(200, raw, channel_id=CHANNEL, run_id=RUN, observed_at=NOW)
            self.assertFalse(result.available)

    def test_oversize_response_is_bounded(self):
        result = decode_run(200, b" " * (MAX_BODY_BYTES + 1), channel_id=CHANNEL,
                            run_id=RUN, observed_at=NOW)
        self.assertEqual(result.reason, "BODY_SIZE_OR_TYPE")

    def test_http_failure_is_not_a_failed_provider_run(self):
        for status in (404, 409, 500, None, True):
            result = decode_run(status, b"SECRET", channel_id=CHANNEL, run_id=RUN, observed_at=NOW)
            self.assertFalse(result.available)
            self.assertIsNone(result.provider_state)
            self.assertIsNone(result.provider_terminal)
            self.assertNotIn("SECRET", repr(result))


class FakeResponse:
    status = 200
    data = encode(BODY)
    content_type = "application/json; charset=utf-8"
    encoding = "identity"

    def getheader(self, name, default=None):
        return {"Content-Type": self.content_type, "Content-Encoding": self.encoding}.get(name, default)

    def read(self, amount):
        self.read_amount = amount
        return self.data[:amount]


class FakeConnection:
    def __init__(self, host, **kwargs):
        self.host, self.kwargs = host, kwargs
        self.calls = []
        self.closed = False
        self.response = FakeResponse()

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class TransportTests(unittest.TestCase):
    def read(self, factory, **extra):
        return read_run_once(channel_id=CHANNEL, run_id=RUN, token="SYNTHETIC_TOKEN",
                             connection_factory=factory, clock=lambda: NOW, **extra)

    def test_one_exact_get_and_bounded_read_no_post_or_redirect(self):
        conn = FakeConnection(HOST)
        calls = []
        def factory(host, **kwargs):
            calls.append((host, kwargs))
            return conn
        result = self.read(factory)
        self.assertTrue(result.available)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], HOST)
        self.assertEqual(len(conn.calls), 1)
        method, path, options = conn.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(path, f"/v1/workspace_agents/{CHANNEL}/runs/{RUN}")
        self.assertNotIn("SYNTHETIC_TOKEN", path)
        self.assertEqual(options["headers"]["Authorization"], "Bearer SYNTHETIC_TOKEN")
        self.assertEqual(conn.response.read_amount, MAX_BODY_BYTES + 1)
        self.assertTrue(conn.closed)
        self.assertNotIn("SYNTHETIC_TOKEN", repr(result))

    def test_redirect_is_not_followed(self):
        conn = FakeConnection(HOST)
        conn.response.status = 302
        result = self.read(lambda *a, **k: conn)
        self.assertEqual(result.reason, "STATUS_HTTP_302")
        self.assertEqual(len(conn.calls), 1)
        self.assertFalse(hasattr(conn.response, "read_amount"))
        self.assertTrue(conn.closed)

    def test_transport_exception_never_retries_or_leaks(self):
        conn = FakeConnection(HOST)
        def fail():
            raise OSError("SYNTHETIC_TOKEN")
        conn.getresponse = fail
        result = self.read(lambda *a, **k: conn)
        self.assertEqual(result.reason, "STATUS_TRANSPORT_UNAVAILABLE")
        self.assertEqual(len(conn.calls), 1)
        self.assertTrue(conn.closed)
        self.assertNotIn("SYNTHETIC_TOKEN", repr(result))

    def test_invalid_input_makes_zero_connections(self):
        def forbidden(*a, **k):
            self.fail("invalid input reached network")
        for field, value in (("channel_id", "../../escape"), ("run_id", "apirun_a?key=x"),
                             ("token", "x\r\nInjected: y"), ("timeout_seconds", True),
                             ("timeout_seconds", float("nan")), ("timeout_seconds", 31)):
            args = dict(channel_id=CHANNEL, run_id=RUN, token="test", connection_factory=forbidden)
            args[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(InvalidObservation):
                read_run_once(**args)

    def test_unsupported_body_encoding_or_content_type(self):
        for name, value, reason in (("encoding", "gzip", "UNSUPPORTED_CONTENT_ENCODING"),
                                    ("content_type", "text/html", "INVALID_CONTENT_TYPE")):
            conn = FakeConnection(HOST)
            setattr(conn.response, name, value)
            self.assertEqual(self.read(lambda *a, **k: conn).reason, reason)
            self.assertFalse(hasattr(conn.response, "read_amount"))

    def test_close_uncertainty_stays_visible(self):
        conn = FakeConnection(HOST)
        def fail():
            raise OSError("SECRET_CLOSE")
        conn.close = fail
        result = self.read(lambda *a, **k: conn)
        self.assertEqual(result.reason, "STATUS_CLOSE_UNCERTAIN")
        self.assertFalse(result.available)


class CliTests(unittest.TestCase):
    SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workspace_agent_api_probe.py"

    def invoke(self, *args, data=b""):
        env = dict(os.environ)
        env.pop("WORKSPACE_AGENT_ACCESS_TOKEN", None)
        result = subprocess.run([sys.executable, str(self.SCRIPT), *args], input=data,
                                capture_output=True, env=env, timeout=10)
        self.assertEqual(result.stderr, b"")
        return result.returncode, json.loads(result.stdout)

    def test_descriptor_has_no_registration_or_actuation_claim(self):
        rc, result = self.invoke("--describe")
        self.assertEqual(rc, 0)
        self.assertFalse(result["can_trigger"])
        self.assertFalse(result["registered_with_executive"])
        self.assertEqual(result["network_methods"], ["GET"])

    def test_cli_preserves_malformed_202_acceptance(self):
        rc, result = self.invoke("--decode-trigger", "--http-status", "202", data=b"not-json")
        self.assertEqual(rc, 0)
        self.assertEqual(result["disposition"], "accepted")
        self.assertFalse(result["correlation_available"])

    def test_cli_run_journey_to_useful_bounded_output(self):
        rc, result = self.invoke("--decode-run", "--http-status", "200", "--channel", CHANNEL,
                                 "--run", RUN, data=encode({**BODY, "status": "suspended"}))
        self.assertEqual(rc, 0)
        self.assertEqual(result["provider_state"], "suspended")
        self.assertFalse(result["provider_terminal"])
        self.assertNotIn("answer", result)

    def test_live_read_without_provisioned_token_fails_before_network(self):
        rc, result = self.invoke("--read-run", "--channel", CHANNEL, "--run", RUN)
        self.assertEqual(rc, 2)
        self.assertEqual(result["reason"], "WORKSPACE_AGENT_ACCESS_TOKEN_MISSING")

    def test_cli_mismatch_stays_unavailable(self):
        rc, result = self.invoke("--decode-run", "--http-status", "200", "--channel", CHANNEL,
                                 "--run", "apirun_different", data=encode(BODY))
        self.assertEqual(rc, 3)
        self.assertEqual(result["reason"], "CORRELATION_MISMATCH")


if __name__ == "__main__":
    unittest.main()
