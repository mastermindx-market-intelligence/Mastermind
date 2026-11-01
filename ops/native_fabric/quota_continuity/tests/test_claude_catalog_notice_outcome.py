"""A Claude SDK model catalog notice must not obscure the terminal CLI reason.

Inert stream/result fixtures, no provider/worker launch or actual lease.
"""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source")]
import pool_ledger
import provider_outcome


class CatalogNoticeOutcome(unittest.TestCase):
    NOTICE = ('[claude-code:unrecognized_model] '
              '{"model":"glm-5.3-flash","query_source":"sdk"}')
    MARKER = "PROVIDER_TERMINAL kind=turn_limit rc=1\n"

    def render(self, subtype, cli_rc, *, result_text=None, reason=None):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "synthetic-stream.json"
            target = Path(temp) / "typed.provider.json"
            if result_text is None:
                result_text = self.NOTICE if subtype == "error_max_turns" else "STATUS: COMPLETE\n"
            if reason is None:
                reason = "max_turns" if subtype == "error_max_turns" else "completed"
            raw = [
                {"type": "system", "subtype": "init"},
                {"type": "result", "subtype": subtype,
                 "terminal_reason": reason, "is_error": subtype != "success",
                 "num_turns": 40, "result": result_text},
            ]
            source.write_text(json.dumps(raw))
            output, errors = StringIO(), StringIO()
            env = {"POOL_OUTCOME_FILE": str(target),
                   "REMOTE_SUB_RUN_ID": "fixture-glm-turn",
                   "POOL_LEASE_ID": "fixturelease",
                   "POOL_ACCOUNT": "fixtureaccount",
                   "POOL_ORCHESTRATOR_ID": "fixtureroot",
                   "LANE_REMOTE_HOST": "fixturehost"}
            with mock.patch.dict(os.environ, env), \
                 mock.patch.object(pool_ledger, "append"), \
                 redirect_stdout(output), redirect_stderr(errors):
                rc = provider_outcome.claude_main(
                    [str(source), str(cli_rc), "glm", "glm-5.3-flash"])
            self.assertTrue(target.is_file(), errors.getvalue())
            receipt = json.loads(target.read_text())
            self.assertEqual(receipt["stdout_sha256"],
                             hashlib.sha256(output.getvalue().encode()).hexdigest())
            self.assertEqual(receipt["command_rc"], rc)
            return rc, output.getvalue(), errors.getvalue(), receipt

    def test_terminal_subtype_leads_fabric_result_before_sdk_catalog_notice(self):
        rc, stdout, stderr, receipt = self.render("error_max_turns", 1)
        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith(self.MARKER), stdout)
        self.assertIn(self.NOTICE, stdout)
        self.assertEqual(stdout.count("PROVIDER_TERMINAL kind="), 1)
        self.assertIn(self.MARKER.strip(), stderr)
        self.assertEqual(receipt["kind"], "turn_limit")
        self.assertEqual(receipt["cli_subtype"], "error_max_turns")

    def test_structured_terminal_overrides_zero_process_exit_and_rebinds_hash(self):
        rc, stdout, stderr, receipt = self.render("error_max_turns", 0)
        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith(self.MARKER), stdout)
        self.assertEqual(receipt["cli_command_rc"], 0)
        self.assertEqual(receipt["command_rc"], 1)

    def test_success_preserves_stdout_even_with_nonfatal_sdk_notice(self):
        rc, stdout, stderr, receipt = self.render(
            "success", 0, result_text=self.NOTICE)
        self.assertEqual(rc, 0)
        self.assertEqual(stdout, self.NOTICE + "\n")
        self.assertEqual(stderr, "")
        self.assertEqual(receipt["kind"], "success")

    def test_ordinary_success_unmodified(self):
        rc, stdout, stderr, receipt = self.render("success", 0)
        self.assertEqual(rc, 0)
        self.assertEqual(stdout, "STATUS: COMPLETE\n")
        self.assertEqual(stderr, "")

    def test_uncorroborated_max_turns_does_not_claim_verified_turn_limit(self):
        rc, stdout, stderr, receipt = self.render(
            "error_max_turns", 1, reason="future_unknown")
        self.assertEqual(rc, 1)
        self.assertFalse(stdout.startswith(self.MARKER))
        self.assertEqual(stdout, self.NOTICE + "\n")
        self.assertEqual(receipt["cli_terminal_reason"], "other")


if __name__ == "__main__":
    unittest.main()
