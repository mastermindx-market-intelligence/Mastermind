from __future__ import annotations

import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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
        self.assertEqual(self.catalog["profile_timezone"], "America/Cancun")
        self.assertEqual(self.catalog["profile_utc_offset"], "-05:00")
        self.assertFalse(self.catalog["profile_observes_dst"])
        self.assertEqual(self.jobs["slack-secretary-ping-scan"]["hermes_schedule"], "12,42 * * * *")
        self.assertIn("America/Vancouver", self.jobs["slack-secretary-ping-scan"]["wall_clock_intent"])
        self.assertEqual(self.jobs["overnight-three-room-sweep"]["hermes_schedule"], "34 * * * *")
        self.assertIn("America/Vancouver", self.jobs["overnight-three-room-sweep"]["wall_clock_intent"])
        self.assertEqual(self.jobs["chatgpt-browser-session-watcher"]["hermes_schedule"], "5,35 * * * *")
        self.assertEqual(self.jobs["codex-usage-reset-watcher"]["hermes_schedule"], "30m")
        self.assertIn("America/Los_Angeles", self.jobs["codex-usage-reset-watcher"]["wall_clock_intent"])
        self.assertEqual(self.jobs["m2studio-browser-tab-sweep"]["hermes_schedule"], "40 2-23/3 * * *")
        self.assertEqual(
            self.jobs["m2studio-browser-tab-sweep"]["schedule"]["expr"],
            "40 2-23/3 * * *",
        )
        self.assertIn("UTC-7", self.jobs["m2studio-browser-tab-sweep"]["wall_clock_intent"])
        self.assertEqual(self.jobs["codex-continuity-audit"]["hermes_schedule"], "20 */2 * * *")
        self.assertIn("America/Denver", self.jobs["codex-continuity-audit"]["wall_clock_intent"])
        self.assertIn("one hour later", self.jobs["codex-continuity-audit"]["wall_clock_intent"])
        self.assertEqual(self.jobs["blocked-hold-listener"]["timezone_source"], "not_a_clock")
        for job in self.jobs.values():
            self.assertEqual(job["timezone"], "America/Cancun")
            self.assertIn("wall_clock_intent", job)
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

    def test_cancun_fire_times_match_source_wall_clocks(self):
        before = datetime(2026, 10, 25, tzinfo=timezone.utc)
        after = datetime(2026, 11, 2, tzinfo=timezone.utc)
        day = timedelta(days=1)
        vancouver = (
            ("slack-secretary-ping-scan", "12,42 * * * *"),
            ("overnight-three-room-sweep", "34 * * * *"),
            ("chatgpt-browser-session-watcher", "5,35 * * * *"),
            ("m2studio-browser-tab-sweep", "40 */3 * * *"),
        )
        for job_id, source_expr in vancouver:
            cancun_expr = self.jobs[job_id]["hermes_schedule"]
            for start in (before, after):
                with self.subTest(job=job_id, start=start.date().isoformat()):
                    self.assertEqual(
                        _utc_fires(source_expr, "America/Vancouver", start, start + day),
                        _utc_fires(cancun_expr, "America/Cancun", start, start + day),
                    )
        self.assertEqual(self.jobs["m2studio-browser-tab-sweep"]["hermes_schedule"], "40 2-23/3 * * *")

        denver_expr = "20 */2 * * *"
        cancun_expr = self.jobs["codex-continuity-audit"]["hermes_schedule"]
        self.assertEqual(
            _utc_fires(denver_expr, "America/Denver", after, after + day),
            _utc_fires(cancun_expr, "America/Cancun", after, after + day),
        )
        denver_mdt = _utc_fires(denver_expr, "America/Denver", before, before + day)
        cancun_mdt = _utc_fires(cancun_expr, "America/Cancun", before, before + day)
        self.assertEqual(cancun_mdt, [item + timedelta(hours=1) for item in denver_mdt])

        usage = self.jobs["codex-usage-reset-watcher"]
        self.assertEqual(usage["hermes_schedule"], "30m")
        self.assertEqual(usage["schedule"]["kind"], "interval")
        los_angeles = ZoneInfo("America/Los_Angeles")
        cancun = ZoneInfo("America/Cancun")
        self.assertNotEqual(
            datetime(2026, 10, 25, 12, tzinfo=los_angeles).utcoffset(),
            datetime(2026, 11, 2, 12, tzinfo=los_angeles).utcoffset(),
        )
        self.assertEqual(
            datetime(2026, 10, 25, 12, tzinfo=cancun).utcoffset(),
            datetime(2026, 11, 2, 12, tzinfo=cancun).utcoffset(),
        )
        self.assertIsNone(self.jobs["blocked-hold-listener"]["schedule"])


def _expand(field: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(part)
        values.update(range(start, end + 1, step))
    return {value for value in values if low <= value <= high}


def _matches(expr: str, local: datetime) -> bool:
    minute, hour, dom, month, dow = expr.split()
    cron_dow = (local.weekday() + 1) % 7
    return (
        local.minute in _expand(minute, 0, 59)
        and local.hour in _expand(hour, 0, 23)
        and local.day in _expand(dom, 1, 31)
        and local.month in _expand(month, 1, 12)
        and cron_dow in _expand(dow, 0, 6)
    )


def _utc_fires(expr: str, zone_name: str, start: datetime, end: datetime) -> list[datetime]:
    zone = ZoneInfo(zone_name)
    found = []
    cursor = start
    while cursor < end:
        if _matches(expr, cursor.astimezone(zone)):
            found.append(cursor)
        cursor += timedelta(minutes=1)
    return found


if __name__ == "__main__":
    unittest.main()
