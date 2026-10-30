"""Regression: GLM third-party SDK model warnings must never outrank a terminal result.

Uses inert JSON events and a mocked usage ledger. No provider, lease or worker.
"""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
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
    def render(self, subtype, cli_rc):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "synthetic-stream.json"
            result_text = (
                '[claude-code:unrecognized_model] '
                '{"model":"glm-5.3-flash","query_source":"sdk"}'
                if subtype == "error_max_turns" else "STATUS: COMPLETE\n"
            )
            raw = [
                {"type": "system", "subtype": "init"},
                {"type": "result", "subtype": subtype,
                 "terminal_reason": "max_turns" if subtype == "error_max_turns" else "completed",
                 "is_error": subtype != "success", "num_turns": 40,
                 "result": result_text},
            ]
            source.write_text(json.dumps(raw))
            rendered = StringIO()
            with mock.patch.dict(os.environ, {"POOL_OUTCOME_FILE": ""}), \
                 mock.patch.object(pool_ledger, "append"), \
                 redirect_stdout(rendered), redirect_stderr(rendered):
                rc = provider_outcome.claude_main(
                    [str(source), str(cli_rc), "glm", "glm-5.3-flash"])
            return rc, rendered.getvalue()

    def test_terminal_subtype_precedes_nonfatal_sdk_catalog_diagnostic(self):
        rc, rendered = self.render("error_max_turns", 1)
        self.assertEqual(rc, 1)
        self.assertTrue(rendered.startswith("PROVIDER_TERMINAL kind=turn_limit rc=1\n"), rendered)
        self.assertIn("[claude-code:unrecognized_model]", rendered)
        self.assertEqual(rendered.count("PROVIDER_TERMINAL kind="), 1)

    def test_structured_terminal_error_overrides_zero_process_exit(self):
        rc, rendered = self.render("error_max_turns", 0)
        self.assertEqual(rc, 1)
        self.assertTrue(rendered.startswith("PROVIDER_TERMINAL kind=turn_limit rc=1\n"))

    def test_success_keeps_original_stdout_without_spurious_terminal_marker(self):
        rc, rendered = self.render("success", 0)
        self.assertEqual(rc, 0)
        self.assertEqual(rendered, "STATUS: COMPLETE\n")


if __name__ == "__main__":
    unittest.main()
