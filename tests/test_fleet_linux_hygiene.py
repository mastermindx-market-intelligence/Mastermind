"""Hermetic safety checks: never start actual host GC or cache removal."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "ops/fleet_storage_cleanup/linux_hygiene.py"
spec = importlib.util.spec_from_file_location("linux_hygiene", SOURCE)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class FleetLinuxHygieneTests(unittest.TestCase):
    def test_pressure_levels_and_enforced_reserve(self):
        self.assertEqual(h.classify(900, 800, 0.4), "CALM")
        self.assertEqual(h.classify(900, 180, 0.4), "CAUTION")
        self.assertEqual(h.classify(900, 75, 0.4), "CRITICAL")
        self.assertEqual(h.classify(900, 500, 0.01), "CRITICAL")
        self.assertEqual(h.classify(900, 500, 0.03), "CAUTION")
        self.assertEqual(h.classify(900, 300, 0.5, 315), "CRITICAL")
        self.assertEqual(h.classify(900, 320, 0.5, 315), "CAUTION")
        self.assertEqual(h.classify(900, 901, 0.5), "UNVERIFIED")
        self.assertEqual(h.classify(900, 500, 1.1), "UNVERIFIED")

    def test_meminfo_requires_actual_available(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "meminfo"
            p.write_text("MemTotal: 100000 kB\nMemFree: 90000 kB\n")
            self.assertEqual(h.memory(p)["state"], "UNVERIFIED")
            p.write_text("MemTotal: 100000 kB\nMemAvailable: 10000 kB\nSwapTotal: 8388608 kB\nSwapFree: 7340032 kB\n")
            self.assertEqual(h.memory(p)["pressure"], "CRITICAL")
            self.assertGreater(h.memory(p)["swap_used_gib"], 0)

    def test_reserve_invalid_never_assumed_healthy(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self.assertEqual(h.reserve(base)["state"], "UNVERIFIED")
            config = base / ".config/mastermind/fabric-storage-reserve.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"internal_floor_gib": -10}')
            self.assertEqual(h.reserve(base)["state"], "UNVERIFIED")
            config.write_text('{"internal_floor_gib": 315}')
            self.assertEqual(h.reserve(base)["floor_gib"], 315)

    def test_symlink_tree_not_inspected_and_never_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "lanes").mkdir()
            protected = base / "keep"
            protected.mkdir()
            (base / "lanes/wt").symlink_to(protected, target_is_directory=True)
            self.assertEqual(h.candidates(base)["state"], "UNVERIFIED")
            self.assertTrue(protected.is_dir())

    def test_candidate_output_is_observation_only(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            old = base / "lanes/wt/leased-worker"
            old.mkdir(parents=True)
            import os
            import time
            os.utime(old, (time.time()-8*86400, time.time()-8*86400))
            report = h.candidates(base)
            self.assertEqual(report["state"], "OBSERVED_ONLY")
            self.assertEqual(report["count_aged"], 1)
            self.assertTrue(old.exists())

    def test_calm_and_running_package_manager_do_not_run_cache(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self.assertEqual(h.cache_cleanup(base, base, "CALM"), [{"state": "SKIPPED_CALM"}])
            with patch.object(h, "package_busy", return_value=True):
                self.assertEqual(h.cache_cleanup(base, base, "CRITICAL"),
                                 [{"state": "SKIPPED_PACKAGE_ACTIVITY"}])
            with patch.object(h, "package_busy", return_value=False):
                (base / h.HOLD).write_text("unknown effect")
                self.assertEqual(h.cache_cleanup(base, base, "CRITICAL"),
                                 [{"state": "HELD_EFFECT_UNVERIFIED"}])

    def test_explicit_report_only_does_not_trigger_cache_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            snapshot = {"state": "OK", "total_gib": 900, "free_gib": 75,
                        "inodes_free_fraction": 0.5}
            with patch.object(h, "volume", return_value=snapshot), patch.object(
                h, "memory", return_value={"state": "OK"}), patch.object(
                h, "reserve", return_value={"state": "UNVERIFIED"}), patch.object(
                h, "cache_cleanup", side_effect=AssertionError("must not run")):
                row = h.run(Path(d), Path(d), False)
            self.assertEqual(row["mode"], "CRITICAL")
            self.assertEqual(row["cleanup"], [{"state": "REPORT_ONLY"}])

    def test_lock_contention_does_not_run(self):
        with tempfile.TemporaryDirectory() as d, patch.object(
                h.fcntl, "flock", side_effect=BlockingIOError):
            with patch.object(h, "run", side_effect=AssertionError("duplicate pass")):
                self.assertEqual(h.main(["--state-dir", d]), 0)

    def test_timer_keeps_running_and_has_no_end_date(self):
        timer = (SOURCE.parent / "mastermind-linux-hygiene.timer").read_text()
        self.assertIn("Persistent=true", timer)
        self.assertIn("OnCalendar=hourly", timer)
        self.assertIn("WantedBy=timers.target", timer)
        self.assertNotIn("OnActiveSec=0", timer)


if __name__ == "__main__":
    unittest.main()
