"""Supported Workspace Agent API contract; these tests are not live-agent proof."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from integrations.workspace_agent_api import (
    InvalidObservation,
    decode_run,
    decode_trigger,
    read_run_once,
)

CHANNEL = "agtch_synthetic"
RUN = "apirun_synthetic"
NOW = 1789340800


class TriggerTests(unittest.TestCase):
    def test_accepted_trigger_is_never_correlated_from_response_bytes(self):
        bodies = (
            b"",
            b"not-json",
            b'{"conversation_url":"https://chatgpt.com/c/synthetic","agent_trigger_run_id":"apirun_synthetic"}',
            b"SECRET_PROVIDER_BODY",
        )
        for body in bodies:
            with self.subTest(body=body):
                result = decode_trigger(202, body)
                self.assertEqual(result.disposition, "accepted")
                self.assertEqual(result.reason, "ACCEPTED_UNCORRELATED")
                self.assertIsNone(result.run_id)
                self.assertIsNone(result.conversation_url)
                self.assertFalse(result.correlation_available)
                self.assertNotIn("SECRET_PROVIDER_BODY", repr(result))

    def test_documented_rejections_do_not_copy_error_body(self):
        for code in (401, 403, 404, 409):
            result = decode_trigger(code, b"SECRET_TOKEN")
            self.assertEqual(result.disposition, "rejected")
            self.assertNotIn("SECRET_TOKEN", repr(result))

    def test_unknown_http_and_timeout_are_uncertain(self):
        for code in (None, True, False, "202", 200, 201, 301, 429, 500, 503):
            self.assertEqual(decode_trigger(code, b"{}").disposition, "unknown")

    def test_nonbytes_body_is_refused_before_classification(self):
        with self.assertRaisesRegex(InvalidObservation, "BODY_SIZE_OR_TYPE"):
            decode_trigger(202, "not-bytes")


class NotAdmittedRunObservationTests(unittest.TestCase):
    def test_decode_run_is_explicitly_not_admitted(self):
        result = decode_run(
            200,
            b'{"status":"completed"}',
            channel_id=CHANNEL,
            run_id=RUN,
            observed_at=NOW,
            expected_conversation_url="https://chatgpt.com/c/synthetic",
        )
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "RUN_OBSERVATION_NOT_ADMITTED")
        self.assertIsNone(result.provider_state)
        self.assertIsNone(result.provider_terminal)

    def test_read_run_once_performs_zero_network_io(self):
        calls = []

        def forbidden(*args, **kwargs):
            calls.append((args, kwargs))
            self.fail("non-admitted run observation reached network")

        result = read_run_once(
            channel_id=CHANNEL,
            run_id=RUN,
            token="SYNTHETIC_TOKEN",
            connection_factory=forbidden,
            clock=lambda: NOW,
        )
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "RUN_OBSERVATION_NOT_ADMITTED")
        self.assertEqual(result.observed_at, NOW)
        self.assertEqual(calls, [])

    def test_invalid_identifiers_still_fail_closed_without_network(self):
        for channel, run in (("../../escape", RUN), (CHANNEL, "bad-run")):
            with self.subTest(channel=channel, run=run), self.assertRaises(
                InvalidObservation
            ):
                read_run_once(channel_id=channel, run_id=run)


class CliTests(unittest.TestCase):
    SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workspace_agent_api_probe.py"

    def invoke(self, *args, data=b""):
        env = dict(os.environ)
        env.pop("WORKSPACE_AGENT_ACCESS_TOKEN", None)
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), *args],
            input=data,
            capture_output=True,
            env=env,
            timeout=10,
        )
        self.assertEqual(result.stderr, b"")
        return result.returncode, json.loads(result.stdout)

    def test_descriptor_is_zero_network_and_truthful(self):
        rc, result = self.invoke("--describe")
        self.assertEqual(rc, 0)
        self.assertEqual(result["network_methods"], [])
        self.assertIsNone(result["network_host"])
        self.assertFalse(result["trigger_response_body_supported"])
        self.assertFalse(result["run_status_supported"])
        self.assertFalse(result["can_trigger"])
        self.assertFalse(result["registered_with_executive"])

    def test_cli_202_acceptance_ignores_body_correlation(self):
        rc, result = self.invoke(
            "--decode-trigger",
            "--http-status",
            "202",
            data=b'{"agent_trigger_run_id":"apirun_synthetic"}',
        )
        self.assertEqual(rc, 0)
        self.assertEqual(result["disposition"], "accepted")
        self.assertEqual(result["reason"], "ACCEPTED_UNCORRELATED")
        self.assertFalse(result["correlation_available"])

    def test_cli_run_decode_is_explicitly_unsupported(self):
        rc, result = self.invoke(
            "--decode-run",
            "--http-status",
            "200",
            "--channel",
            CHANNEL,
            "--run",
            RUN,
            data=b'{"status":"completed"}',
        )
        self.assertEqual(rc, 3)
        self.assertEqual(result["reason"], "RUN_OBSERVATION_NOT_ADMITTED")

    def test_cli_read_run_needs_no_token_and_performs_no_network(self):
        rc, result = self.invoke("--read-run", "--channel", CHANNEL, "--run", RUN)
        self.assertEqual(rc, 3)
        self.assertEqual(result["reason"], "RUN_OBSERVATION_NOT_ADMITTED")


if __name__ == "__main__":
    unittest.main()
