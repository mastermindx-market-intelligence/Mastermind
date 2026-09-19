"""Operator preflight tests for Workspace Agent profile activation."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.workspace_agent_profile_check import MAX_INPUT_BYTES, main, run

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "config" / "workspace_agents" / "profile_catalog.v1.json"
NOW = 1789822800000


def economic():
    return {
        "schema": "mastermind.workspace_agent_economic_envelope.v1",
        "authority_ref": "AUTH:workspace-canary-20260919",
        "accounting_source_ref": "COST:workspace-seat-observation-20260919",
        "billing_currency": "USD",
        "incremental_spend_cap_minor_units": 500,
        "usage_unit": "workspace-credit",
        "usage_cap_quantity": 100,
        "max_trigger_count": 1,
        "overflow_policy": "REFUSE",
        "issued_at_ms": NOW,
        "expires_at_ms": NOW + 3600000,
    }


class WorkspaceAgentProfileCheckTests(unittest.TestCase):
    def write_json(self, directory, name, value):
        path = Path(directory) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_catalog_command_projects_digests_and_draft_state_only(self):
        result = run(["catalog", "--catalog", str(CATALOG)])
        self.assertTrue(result["ok"])
        self.assertEqual(result["publication_state"], "DRAFT_NOT_PUBLISHED")
        self.assertRegex(result["catalog_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            [row["profile_id"] for row in result["profiles"]],
            [
                "program-continuity-adviser",
                "independent-outcome-reviewer",
            ],
        )
        self.assertTrue(
            all(
                len(row["profile_digest"]) == 64
                for row in result["profiles"]
            )
        )

    def test_activation_command_is_effect_free_and_binds_exact_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            envelope = self.write_json(tmp, "economic.json", economic())
            result = run(
                [
                    "activation",
                    "--catalog",
                    str(CATALOG),
                    "--economic-envelope",
                    str(envelope),
                    "--profile-id",
                    "program-continuity-adviser",
                    "--channel-id",
                    "agtch_synthetic123",
                    "--agent-version-ref",
                    "agent-version-20260919-01",
                    "--now-ms",
                    str(NOW + 1),
                ]
            )
        self.assertTrue(result["ok"])
        self.assertFalse(result["provider_effect_performed"])
        self.assertFalse(result["authority_granted"])
        self.assertRegex(result["activation_digest"], r"^[0-9a-f]{64}$")
        binding = result["activation_binding"]
        self.assertEqual(binding["concurrency_limit"], 1)
        self.assertFalse(binding["live_source_write_allowed"])
        self.assertFalse(binding["production_release_allowed"])
        self.assertEqual(
            binding["app_bindings"],
            ["mastermind-steward", "mastermind-workspace-agent-return"],
        )

    def test_expired_or_invalid_input_returns_one_fixed_public_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            expired = economic()
            expired["expires_at_ms"] = NOW + 1
            envelope = self.write_json(tmp, "economic-secret-name.json", expired)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(
                    [
                        "activation",
                        "--catalog",
                        str(CATALOG),
                        "--economic-envelope",
                        str(envelope),
                        "--profile-id",
                        "program-continuity-adviser",
                        "--channel-id",
                        "agtch_synthetic123",
                        "--agent-version-ref",
                        "agent-version-20260919-01",
                        "--now-ms",
                        str(NOW + 2),
                    ]
                )
            self.assertEqual(code, 2)
            result = json.loads(out.getvalue())
            self.assertEqual(
                result,
                {
                    "ok": False,
                    "schema": "mastermind.workspace_agent_profile_preflight.v1",
                    "error": "PREFLIGHT_REFUSED",
                },
            )
            self.assertNotIn("economic-secret-name", out.getvalue())

    def test_oversized_or_non_json_input_is_refused_without_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            oversized = Path(tmp) / "oversized-SYNTHETIC-SECRET.json"
            oversized.write_bytes(b"x" * (MAX_INPUT_BYTES + 1))
            for path in (oversized, Path(tmp) / "missing-SYNTHETIC-SECRET.json"):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = main(["catalog", "--catalog", str(path)])
                self.assertEqual(code, 2)
                self.assertNotIn("SYNTHETIC", out.getvalue())
                self.assertEqual(json.loads(out.getvalue())["error"], "PREFLIGHT_REFUSED")

    def test_cli_source_has_no_token_credential_or_network_argument(self):
        source = (
            ROOT / "scripts" / "workspace_agent_profile_check.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "--token",
            "--api-key",
            "--password",
            "requests.",
            "httpx.",
            "HTTPSConnection",
            "urlopen",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
