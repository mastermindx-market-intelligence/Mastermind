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

    def test_nonzero_package_cache_effect_is_held_for_owner(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / ".cache/pip").mkdir(parents=True)
            with patch.object(h, "package_busy", return_value=False), patch.object(
                    h.shutil, "which", return_value="/usr/bin/python3"), patch.object(
                    h.subprocess, "run",
                    return_value=SimpleNamespace(returncode=17,
                                           stderr="pip auth failed https://u:SECRET_DO_NOT_LOG@example.invalid/")):
                results = h.cache_cleanup(base, base, "CAUTION")
            self.assertEqual(results[0]["state"], "EFFECT_UNVERIFIED")
            self.assertEqual(results[0]["exit_code"], 17)
            self.assertEqual(results[0]["error_class"], "MANAGER_EXIT_NONZERO")
            self.assertTrue(results[0]["stderr_redacted"])
            self.assertNotIn("SECRET_DO_NOT_LOG", __import__("json").dumps(results))
            self.assertTrue((base / h.HOLD).exists())
            self.assertEqual(h.cache_cleanup(base, base, "CRITICAL"),
                             [{"state": "HELD_EFFECT_UNVERIFIED"}])

    def test_cache_intent_is_durable_before_command_and_cleared_on_success(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / ".cache/pip").mkdir(parents=True)
            def checked_package_call(*args, **kwargs):
                self.assertTrue((base / h.HOLD).exists())
                self.assertIn("PRE_EFFECT cache=pip", (base / h.HOLD).read_text())
                return SimpleNamespace(returncode=0, stderr="")
            with patch.object(h, "package_busy", return_value=False), patch.object(
                    h.shutil, "which", return_value="/usr/bin/python3"), patch.object(
                    h.subprocess, "run", side_effect=checked_package_call):
                results = h.cache_cleanup(base, base, "CAUTION")
            self.assertEqual(results[0]["state"], "OK")
            self.assertFalse((base / h.HOLD).exists())

    def test_success_settlement_is_durable_before_hold_release(self):
        from types import SimpleNamespace
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".cache/pip").mkdir(parents=True)
            real_append = h.append_receipt
            receipts = []
            def record_while_held(state, report):
                self.assertTrue((state / h.HOLD).exists())
                self.assertEqual(report["state"], "POST_EFFECT_VERIFIED")
                self.assertIn(report["effect_id"], (state / h.HOLD).read_text())
                receipts.append(report)
                return real_append(state, report)
            with patch.object(h, "package_busy", return_value=False), patch.object(
                    h.shutil, "which", return_value="/usr/bin/python3"), patch.object(
                    h.subprocess, "run", return_value=SimpleNamespace(returncode=0, stderr="")), patch.object(
                    h, "append_receipt", side_effect=record_while_held):
                rows = h.cache_cleanup(root, root, "CAUTION")
            self.assertEqual(rows[0]["state"], "OK")
            self.assertFalse((root / h.HOLD).exists())
            self.assertEqual(len(receipts), 1)
            recorded = json.loads((root / h.LEDGER).read_text().splitlines()[0])
            self.assertEqual(recorded["effect_id"], receipts[0]["effect_id"])
            self.assertEqual(recorded["attributable_reclaimed_bytes"], 0)
            self.assertEqual(recorded["state"], "POST_EFFECT_VERIFIED")

    def test_settlement_write_failure_keeps_pre_effect_and_refuses_replay(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".cache/pip").mkdir(parents=True)
            with patch.object(h, "package_busy", return_value=False), patch.object(
                    h.shutil, "which", return_value="/usr/bin/python3"), patch.object(
                    h.subprocess, "run", return_value=SimpleNamespace(returncode=0, stderr="")) as manager, patch.object(
                    h, "append_receipt", return_value=False):
                rows = h.cache_cleanup(root, root, "CAUTION")
                self.assertEqual(manager.call_count, 1)
            self.assertEqual(rows[0]["state"], "EFFECT_UNVERIFIED")
            self.assertEqual(rows[0]["reason"], "settlement_receipt_unavailable")
            self.assertTrue((root / h.HOLD).exists())
            self.assertEqual(h.cache_cleanup(root, root, "CRITICAL"),
                             [{"state": "HELD_EFFECT_UNVERIFIED"}])

    def test_degraded_receipt_returns_nonzero_without_disarming_timer(self):
        with tempfile.TemporaryDirectory() as d, patch.object(
                h, "run", return_value={"schema": "mastermind.fleet_linux_hygiene.v1",
                                        "degraded": True,
                                        "cleanup": [{"state": "EFFECT_UNVERIFIED"}]}):
            self.assertEqual(h.main(["--state-dir", d]), 1)
            rows = (Path(d) / h.LEDGER).read_text().splitlines()
            self.assertEqual(len(rows), 1)
            self.assertIn('"degraded": true', rows[0])
        timer = (SOURCE.parent / "mastermind-linux-hygiene.timer").read_text()
        self.assertIn("Persistent=true", timer)

    def test_lock_contention_does_not_run(self):
        with tempfile.TemporaryDirectory() as d, patch.object(
                h.fcntl, "flock", side_effect=BlockingIOError):
            with patch.object(h, "run", side_effect=AssertionError("duplicate pass")):
                self.assertEqual(h.main(["--state-dir", d]), 75)
            rows = (Path(d) / h.LEDGER).read_text().splitlines()
            self.assertEqual(len(rows), 1)
            self.assertEqual(__import__("json").loads(rows[0])["state"],
                             "DEFERRED_ALREADY_RUNNING")

    def test_manager_argv_variants_are_detected_not_just_install_substrings(self):
        for arguments in (
            [b"python3", b"-m", b"pip", b"wheel", b"."],
            [b"python3", b"-I", b"-m", b"pip", b"download", b"pkg"],
            [b"uv", b"tool", b"install", b"pkg"],
            [b"npm", b"--prefix", b"/tmp/build", b"install"],
            [b"/usr/local/bin/node", b"/usr/lib/node_modules/npm/bin/npm-cli.js",
             b"install"],
            [b"pnpm", b"--config.foo=x", b"add", b"pkg"],
            [b"yarn", b"--cwd", b"/tmp/build", b"add", b"pkg"],
        ):
            self.assertTrue(h.package_command(b"\x00".join(arguments) + b"\x00"),
                            arguments)
        self.assertFalse(h.package_command(b"python3\x00-c\x00print(3)\x00"))

    def test_redirected_or_symlink_parent_never_calls_cache_api(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "home"
            base.mkdir()
            (base / ".cache/pip").mkdir(parents=True)
            external = Path(d) / "external"
            external.mkdir()
            with patch.dict(h.os.environ, {"XDG_CACHE_HOME": str(external)}):
                with patch.object(h.subprocess, "run", side_effect=AssertionError("redirected purge")):
                    result = h.cache_cleanup(base, base, "CAUTION")
            self.assertEqual(result[0]["state"], "SKIPPED_CUSTOM_CACHE_PATH")
            (base / ".cache/pip").rmdir()
            (base / ".cache").rmdir()
            (base / ".cache").symlink_to(external, target_is_directory=True)
            (external / "pip").mkdir()
            with patch.object(h.subprocess, "run", side_effect=AssertionError("symlink purge")):
                result = h.cache_cleanup(base, base, "CAUTION")
            self.assertEqual(result[0]["state"], "SKIPPED_UNTRUSTED_CACHE_PATH")
            self.assertTrue((external / "pip").exists())

    def test_pip_cache_target_pinned_on_command_line_before_intent_cleared(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cache = root / ".cache/pip"
            cache.mkdir(parents=True)
            def inspect(argv, **kwargs):
                self.assertIn("--isolated", argv)
                self.assertIn("--cache-dir", argv)
                self.assertEqual(argv[argv.index("--cache-dir") + 1], str(cache))
                self.assertTrue((root / h.HOLD).exists())
                return SimpleNamespace(returncode=0, stderr="")
            with patch.object(h, "package_busy", return_value=False), patch.object(
                    h.shutil, "which", return_value="/usr/bin/python3"), patch.object(
                    h.subprocess, "run", side_effect=inspect):
                result = h.cache_cleanup(root, root, "CAUTION")
            self.assertEqual(result[0]["state"], "OK")
            self.assertFalse((root / h.HOLD).exists())

    def test_writer_activity_rescanned_before_every_manager_effect(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".cache/pip").mkdir(parents=True)
            (root / ".cache/uv").mkdir(parents=True)
            with patch.object(h, "package_busy", side_effect=[False, False, True]) as busy, patch.object(
                    h.shutil, "which", return_value="/usr/bin/uv"), patch.object(
                    h.subprocess, "run",
                    return_value=SimpleNamespace(returncode=0, stderr="")) as purge:
                result = h.cache_cleanup(root, root, "CAUTION")
            self.assertEqual([row["state"] for row in result],
                             ["OK", "SKIPPED_PACKAGE_ACTIVITY"])
            self.assertEqual(busy.call_count, 3)
            self.assertEqual(purge.call_count, 1)

    def test_unverified_reserve_lanes_worktrees_or_after_volume_degrades(self):
        good = {"state": "OK", "total_gib": 900, "free_gib": 700,
                "inodes_free_fraction": 0.5, "device": 2}
        missing = {"state": "UNAVAILABLE"}
        with tempfile.TemporaryDirectory() as d, patch.object(
                h, "memory", return_value={"state": "OK"}), patch.object(
                h, "candidates", return_value={"state": "OBSERVED_ONLY"}):
            for snapshots, reserve in (
                ([good, good, good], {"state": "UNVERIFIED"}),
                ([good, missing, good], {"state": "CONFIGURED", "floor_gib": 75}),
                ([good, good, missing], {"state": "CONFIGURED", "floor_gib": 75}),
            ):
                with patch.object(h, "volume", side_effect=snapshots), patch.object(
                        h, "reserve", return_value=reserve), patch.object(
                        h, "cache_cleanup", side_effect=AssertionError("must not purge")):
                    result = h.run(Path(d), Path(d), True)
                self.assertTrue(result["degraded"])
                self.assertNotEqual(result["fabric_admission"], "ELIGIBLE")

    def test_ledger_symlink_does_not_modify_target(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            outside = state / "outside"
            outside.write_text("keep")
            (state / h.LEDGER).symlink_to(outside)
            self.assertFalse(h.append_receipt(state, {"schema": "test"}))
            self.assertEqual(outside.read_text(), "keep")

    def test_volume_exact_integer_bytes_and_inodes_not_rounded(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            sample = SimpleNamespace(f_blocks=2000000, f_frsize=4096,
                                     f_bavail=1234567, f_files=100000,
                                     f_favail=54321)
            with patch.object(h.os, "statvfs", return_value=sample):
                result = h.volume(Path(d))
            self.assertEqual(result["available_bytes"], 1234567 * 4096)
            self.assertEqual(result["total_bytes"], 2000000 * 4096)
            self.assertEqual(result["inodes_available"], 54321)
            self.assertEqual(result["inodes_total"], 100000)
            self.assertIsInstance(result["available_bytes"], int)

    def test_manager_effect_records_byte_exact_drift_without_fake_reclamation(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".cache/pip").mkdir(parents=True)
            def snapshot(available, inodes, device=5):
                return {"state": "OK", "device": device,
                        "total_bytes": 1000000, "available_bytes": available,
                        "inodes_total": 1000, "inodes_available": inodes}
            pre_root, pre_cache = snapshot(300000, 500), snapshot(300000, 500)
            post_root, post_cache = snapshot(312345, 505), snapshot(312345, 505)
            def run_manager(*args, **kwargs):
                marker = (root / h.HOLD).read_text()
                self.assertIn("PRE_EFFECT cache=pip", marker)
                self.assertIn('"available_bytes": 300000', marker)
                return SimpleNamespace(returncode=0, stderr="")
            with patch.object(h, "package_busy", return_value=False), patch.object(
                    h.shutil, "which", return_value="/usr/bin/python3"), patch.object(
                    h, "volume", side_effect=[pre_root, pre_cache, post_root, post_cache]), patch.object(
                    h.subprocess, "run", side_effect=run_manager):
                rows = h.cache_cleanup(root, root, "CAUTION")
            self.assertEqual(rows[0]["state"], "OK")
            self.assertEqual(rows[0]["observed_available_delta_bytes"], 12345)
            self.assertEqual(rows[0]["observed_free_inodes_delta"], 5)
            self.assertEqual(rows[0]["attributable_reclaimed_bytes"], 0)
            self.assertEqual(rows[0]["reclaim_attribution"],
                             "NOT_ESTABLISHED_BY_MANAGER")
            self.assertFalse((root / h.HOLD).exists())

    def test_effect_volume_device_drift_preserves_hold_without_replay(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".cache/pip").mkdir(parents=True)
            def snapshot(device):
                return {"state": "OK", "device": device,
                        "total_bytes": 1000000, "available_bytes": 300000,
                        "inodes_total": 1000, "inodes_available": 500}
            with patch.object(h, "package_busy", return_value=False), patch.object(
                    h.shutil, "which", return_value="/usr/bin/python3"), patch.object(
                    h, "volume", side_effect=[snapshot(5), snapshot(5),
                                             snapshot(6), snapshot(5)]), patch.object(
                    h.subprocess, "run",
                    return_value=SimpleNamespace(returncode=0, stderr="")) as manager:
                rows = h.cache_cleanup(root, root, "CAUTION")
            self.assertEqual(rows[0]["state"], "EFFECT_UNVERIFIED")
            self.assertEqual(rows[0]["reason"], "post_effect_volume_or_target_unverified")
            self.assertEqual(manager.call_count, 1)
            self.assertTrue((root / h.HOLD).exists())
            self.assertEqual(h.cache_cleanup(root, root, "CRITICAL"),
                             [{"state": "HELD_EFFECT_UNVERIFIED"}])

    def test_timer_keeps_running_and_has_no_end_date(self):
        timer = (SOURCE.parent / "mastermind-linux-hygiene.timer").read_text()
        self.assertIn("Persistent=true", timer)
        self.assertIn("OnCalendar=hourly", timer)
        self.assertIn("WantedBy=timers.target", timer)
        self.assertNotIn("OnActiveSec=0", timer)


if __name__ == "__main__":
    unittest.main()
