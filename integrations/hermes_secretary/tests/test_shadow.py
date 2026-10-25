from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from constants import SECRETARY_USER_ID
from fixture_loader import load_fixture
from parity import compare, load_decisions, secretary_posts_from_readonly
from roster import roster_with
from shadow import run_shadow
from slack_readonly import ReadOnlySlackClient, ReadOnlySlackError


class ShadowRunner(unittest.TestCase):
    def test_ping_scan_writes_jsonl_and_makes_no_slack_writes(self):
        client, ledger = load_fixture()
        output = Path(self.id().replace(".", "_") + ".jsonl")
        # Keep the artifact out of the repo tree the test might be collected from.
        output = Path("/tmp") / "hermes-secretary-shadow-ping.jsonl"
        if output.exists():
            output.unlink()
        roster = roster_with(other_seats=("U0OTHERSEAT1",))
        first = run_shadow(client, mode="ping_scan", ledger=ledger, output_path=output, roster=roster)
        second = run_shadow(client, mode="ping_scan", ledger=ledger, output_path=output, roster=roster)
        self.assertEqual(len(first), 7)
        self.assertEqual(second, [])
        lines = output.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 7)
        blob = output.read_text(encoding="utf-8")
        self.assertNotIn("xoxb-not-a-real-token", blob)
        self.assertNotIn("chat_postMessage", blob)
        for line in lines:
            row = json.loads(line)
            self.assertFalse(row["would_post"])
            self.assertEqual(row["mode"], "ping_scan")
        methods = {call[0] for call in client.calls}
        self.assertEqual(methods, {"conversations_history", "conversations_replies"})
        self.assertTrue(all(call[0] != "chat_postMessage" for call in client.calls))
        output.unlink()

    def test_a_client_with_a_write_method_is_rejected_before_any_call(self):
        class Writing(ReadOnlySlackClient):
            def chat_postMessage(self, **kwargs):
                self.calls.append(("chat_postMessage", kwargs))

        client = Writing({})
        with self.assertRaises(ReadOnlySlackError) as caught:
            run_shadow(client, mode="ping_scan", ledger=[], output_path=Path("/tmp/unused-shadow.jsonl"))
        self.assertEqual(caught.exception.code, "SLACK_CLIENT_WRITE_SURFACE")
        self.assertEqual(client.calls, [])

    def test_unmarked_client_is_rejected(self):
        with self.assertRaises(ReadOnlySlackError) as caught:
            run_shadow(object(), mode="ping_scan", ledger=[], output_path=Path("/tmp/unused-shadow.jsonl"))
        self.assertEqual(caught.exception.code, "SLACK_CLIENT_NOT_READ_ONLY")

    def test_overnight_sweep_skips_returns_and_the_later_rooms(self):
        client, ledger = load_fixture()
        output = Path("/tmp/hermes-secretary-shadow-overnight.jsonl")
        if output.exists():
            output.unlink()
        decisions = run_shadow(
            client,
            mode="overnight_sweep",
            ledger=ledger,
            output_path=output,
            roster=roster_with(other_seats=("U0OTHERSEAT1",)),
        )
        self.assertEqual(
            [(item["ts"], item["decision"]) for item in decisions],
            [
                ("1761410014.000100", "PLACE_ON_TITLED_WORKER"),
                ("1761410001.000100", "HAND_TO_COORDINATOR"),
                ("1761410005.000100", "PLACE_ON_TITLED_WORKER"),
                ("1761410008.000100", "BLOCKED_WAKE"),
                ("1761410009.000200", "HAND_TO_COORDINATOR"),
            ],
        )
        output.unlink()

    def test_blocked_trigger_reads_only_the_thread(self):
        client, ledger = load_fixture()
        output = Path("/tmp/hermes-secretary-shadow-blocked.jsonl")
        if output.exists():
            output.unlink()
        found = run_shadow(
            client,
            mode="blocked_trigger",
            ledger=ledger,
            output_path=output,
            channel="C0BSBM78V1N",
            thread_ts="1761410008.000100",
        )
        quiet_client, _ledger = load_fixture()
        quiet = run_shadow(
            quiet_client,
            mode="blocked_trigger",
            ledger=ledger,
            output_path=output,
            channel="C0BSBM78V1N",
            thread_ts="1761410007.000100",
        )
        self.assertEqual([item["decision"] for item in found], ["BLOCKED_WAKE"])
        self.assertEqual(quiet, [])
        self.assertEqual(
            [call[0] for call in client.calls],
            ["conversations_replies"],
        )
        output.unlink()

    def test_shadow_source_does_not_name_a_slack_write(self):
        source = (ROOT / "shadow.py").read_text(encoding="utf-8")
        self.assertNotIn("chat_postMessage", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("slack_sdk", source)
        for path in ROOT.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("import socket", text)
            self.assertNotIn("import urllib", text)
            self.assertNotIn("import requests", text)
            self.assertNotIn("subprocess", text)


class Parity(unittest.TestCase):
    def test_window_compares_shadow_decisions_with_secretary_posts(self):
        client, ledger = load_fixture()
        output = Path("/tmp/hermes-secretary-shadow-parity.jsonl")
        if output.exists():
            output.unlink()
        run_shadow(
            client,
            mode="ping_scan",
            ledger=ledger,
            output_path=output,
            roster=roster_with(other_seats=("U0OTHERSEAT1",)),
        )
        decisions = load_decisions(output)
        posts = [
            {
                "channel": "C0BSBM78V1N",
                "ts": "1761410001.000300",
                "thread_ts": "1761410001.000100",
                "user": SECRETARY_USER_ID,
                "text": "ACK hermes-wp5-shadow-001",
            },
            {
                "channel": "C0CCNK7JFAL",
                "ts": "1761410010.000300",
                "thread_ts": "1761410010.000100",
                "user": SECRETARY_USER_ID,
                "text": "ACTION NEEDED RETURN rf-t01",
            },
            {
                "channel": "C0BSBM78V1N",
                "ts": "1761410005.000300",
                "thread_ts": "1761410005.000100",
                "user": SECRETARY_USER_ID,
                "text": "noted without a marker",
            },
            {
                "channel": "C0CBC6AEAQZ",
                "ts": "1761410020.000100",
                "user": SECRETARY_USER_ID,
                "text": "ACK stray",
            },
            {
                "channel": "C0BSBM78V1N",
                "ts": "1761410099.000100",
                "user": SECRETARY_USER_ID,
                "text": "ACK outside the window",
            },
        ]
        report = compare(
            decisions=decisions,
            posts=posts,
            start_ts="1761410000.000000",
            end_ts="1761410090.000000",
        )
        self.assertIn("C0BSBM78V1N:1761410001.000100", report.matched)
        self.assertIn("C0CCNK7JFAL:1761410010.000100", report.matched)
        self.assertIn("C0BSBM78V1N:1761410005.000100", report.mismatched_kind)
        self.assertIn("C0BSBM78V1N:1761410008.000100", report.shadow_only)
        self.assertIn("C0C5FCK1F45:1761410012.000100", report.withheld)
        self.assertIn("C0CBC6AEAQZ:1761410020.000100", report.secretary_only)
        self.assertNotIn("C0BSBM78V1N:1761410099.000100", report.secretary_only)
        output.unlink()

    def test_readonly_post_fetch_does_not_write(self):
        client, _ledger = load_fixture()
        posts = secretary_posts_from_readonly(
            client,
            channels=("C0BSBM78V1N",),
            secretary_user_id=SECRETARY_USER_ID,
        )
        self.assertTrue(any(item["user"] == SECRETARY_USER_ID for item in posts))
        self.assertTrue(all(call[0] in {"conversations_history", "conversations_replies"} for call in client.calls))


if __name__ == "__main__":
    unittest.main()
