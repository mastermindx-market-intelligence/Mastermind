from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routine_catalog import CatalogError, hermes_create_kwargs, install_into_hermes_home, load_catalog
from wake_bridge import try_mint_dialogue_wake


class RoutineCatalog(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.jobs = {job["id"]: job for job in self.catalog["jobs"]}

    def test_seven_routines_keep_their_cadence_dedup_and_pause(self):
        self.assertEqual(
            list(self.jobs),
            [
                "slack-secretary-ping-scan",
                "overnight-three-room-sweep",
                "blocked-hold-listener",
                "chatgpt-browser-session-watcher",
                "codex-usage-reset-watcher",
                "m2studio-browser-tab-sweep",
                "codex-continuity-audit",
            ],
        )
        self.assertEqual(self.jobs["slack-secretary-ping-scan"]["hermes_schedule"], "12,42 * * * *")
        self.assertEqual(self.jobs["slack-secretary-ping-scan"]["timezone"], "America/Vancouver")
        self.assertEqual(self.jobs["overnight-three-room-sweep"]["hermes_schedule"], "34 * * * *")
        self.assertEqual(self.jobs["overnight-three-room-sweep"]["timezone_source"], "assumed_secretary_home")
        self.assertEqual(self.jobs["chatgpt-browser-session-watcher"]["hermes_schedule"], "5,35 * * * *")
        self.assertEqual(self.jobs["codex-usage-reset-watcher"]["hermes_schedule"], "30m")
        self.assertEqual(self.jobs["codex-usage-reset-watcher"]["timezone"], "America/Los_Angeles")
        self.assertEqual(self.jobs["m2studio-browser-tab-sweep"]["hermes_schedule"], "40 */3 * * *")
        self.assertEqual(self.jobs["codex-continuity-audit"]["hermes_schedule"], "20 */2 * * *")
        self.assertEqual(self.jobs["codex-continuity-audit"]["timezone"], "America/Denver")
        for job in self.jobs.values():
            self.assertFalse(job["enabled"])
            self.assertEqual(job["state"], "paused")
            self.assertEqual(job["deliver"], "local")
            self.assertIsNone(job["origin"])
            self.assertIn("Do not post to Slack", job["prompt"])
            self.assertNotIn("xox", job["prompt"])
        self.assertEqual(self.jobs["slack-secretary-ping-scan"]["dedup"], "slack_ts")
        self.assertEqual(self.jobs["chatgpt-browser-session-watcher"]["dedup"], "session_id")
        self.assertEqual(self.jobs["codex-continuity-audit"]["dedup"], "project_slug")
        self.assertEqual(self.jobs["blocked-hold-listener"]["trigger"]["keyword"], "BLOCKED")
        self.assertIsNone(self.jobs["blocked-hold-listener"]["schedule"])

    def test_cron_expressions_are_five_fields_and_install_is_refused(self):
        for job in self.jobs.values():
            if job["schedule_backend"] != "hermes_cron":
                continue
            if job["schedule"]["kind"] == "cron":
                parts = job["schedule"]["expr"].split()
                self.assertEqual(len(parts), 5)
                self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9*/,-]+", part) for part in parts))
                self.assertEqual(hermes_create_kwargs(job)["paused"], True)
                self.assertEqual(hermes_create_kwargs(job)["deliver"], "local")
        with self.assertRaises(ValueError):
            hermes_create_kwargs(self.jobs["blocked-hold-listener"])
        with self.assertRaises(RuntimeError):
            install_into_hermes_home("/tmp/hermes-home")

    def test_catalog_rejects_an_installed_flag(self):
        with self.assertRaises(CatalogError):
            load_catalog(ROOT / "tests" / "fixtures" / "ping_scan.json")

    def test_wake_mints_only_a_canonical_dialogue_ref(self):
        source_ref = "agent_dialogue_attention:" + ("ab" * 32)
        minted = try_mint_dialogue_wake(source_ref, emitted_at="2026-10-25T14:00:00Z")
        again = try_mint_dialogue_wake(source_ref, emitted_at="2026-10-25T14:00:00Z")
        self.assertEqual(minted["status"], "MINTED")
        self.assertEqual(minted["schedule_backend"], "hermes_cron")
        self.assertEqual(minted["obligation"]["declared_target_seat"], "ceo")
        self.assertEqual(minted["obligation"]["obligation_id"], again["obligation"]["obligation_id"])
        self.assertNotIn("prompt", minted["obligation"])
        refused = try_mint_dialogue_wake("C0BSBM78V1N/1761410001.000100")
        self.assertEqual(refused["status"], "WAKE_SOURCE_NOT_ADMITTED")
        self.assertNotIn("obligation", refused)


if __name__ == "__main__":
    unittest.main()
