"""Regression tests for existing storage-sweeper scripts (no live sweeps)."""
import contextlib
import importlib.util
import io
import json
import pathlib
import queue
import threading
import sys
import tempfile
import time
import unittest
from unittest import mock

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "ops/fleet_storage_cleanup"


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FleetStorageVolumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sweep = load("fleet_test_sweep", SOURCE / "sweep.py")
        cls.fleet = load("fleet_test_driver", SOURCE / "fleet_remote_sweep.py")

    @staticmethod
    def m1_sample(free=71.7):
        return {
            "mount": "/Volumes/STORAGE",
            "state": "OK",
            "free_gib": free,
            "total_gib": 931.3,
            "floor_gib": 130.4,
            "warn_gib": 204.9,
            "used_pct": round(100 * (931.3 - free) / 931.3, 1),
        }

    def test_split_root_external_breach_despite_healthy_system_disk(self):
        row = {
            "host": "m1", "rc": 0,
            "sweep": {
                "free_gib_after": 201.3,
                "floor_gib": 120.0,
                "external_volumes": [self.m1_sample()],
            },
        }
        self.assertIsNone(self.fleet._space_pressure(row))
        alert = self.fleet._external_volume_pressure(row)
        self.assertEqual(len(alert), 1)
        self.assertEqual(alert[0]["severity"], "BREACH")
        self.assertEqual(alert[0]["mount"], "/Volumes/STORAGE")

    def test_healthy_external_mount_does_not_warn(self):
        row = {"host": "m1", "rc": 0,
               "sweep": {"external_volumes": [self.m1_sample(free=400.0)]}}
        self.assertEqual(self.fleet._external_volume_pressure(row), [])

    def test_disconnected_mount_is_unverified_not_root_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            home = pathlib.Path(temp)
            config = home / ".config/mastermind"
            config.mkdir(parents=True)
            (config / "worktree-storage.json").write_text(
                json.dumps({"mount_point": "/Volumes/NOT_MOUNTED_MMX_TEST"}))
            with mock.patch.object(self.sweep.Path, "home", return_value=home):
                records = self.sweep._external_volume_snapshots()
        self.assertIn(
            {"mount": "/Volumes/NOT_MOUNTED_MMX_TEST", "state": "MOUNT_UNAVAILABLE"},
            records,
        )

    def test_invalid_policy_never_masquerades_as_healthy(self):
        with tempfile.TemporaryDirectory() as temp:
            home = pathlib.Path(temp)
            config = home / ".config/mastermind"
            config.mkdir(parents=True)
            (config / "worktree-storage.json").write_text("{")
            with mock.patch.object(self.sweep.Path, "home", return_value=home):
                records = self.sweep._external_volume_snapshots()
        self.assertTrue(any(r["state"] == "POLICY_UNREADABLE" for r in records))

    def test_invalid_metrics_fail_closed(self):
        sample = self.m1_sample()
        sample["floor_gib"] = 999999
        row = {"host": "m1", "rc": 0, "sweep": {"external_volumes": [sample]}}
        alert = self.fleet._external_volume_pressure(row)
        self.assertEqual(len(alert), 1)
        self.assertEqual(alert[0]["severity"], "UNVERIFIED")

    def test_missing_remote_telemetry_is_unverified(self):
        row = {"host": "m1", "rc": 0, "sweep": {"free_gib_after": 201.3,
                                                "floor_gib": 120.0}}
        got = self.fleet._external_volume_pressure(row)
        self.assertEqual(got[0]["severity"], "UNVERIFIED")
        self.assertEqual(got[0]["state"], "TELEMETRY_MISSING")

    def test_bad_remote_policy_is_reported(self):
        row = {"host": "m1", "rc": 0, "sweep": {"external_volumes": [
            {"mount": "/Users/example/.config/mastermind/worktree-storage.json",
             "state": "POLICY_UNREADABLE", "reason": "ValueError"}]}}
        got = self.fleet._external_volume_pressure(row)
        self.assertEqual(got[0]["severity"], "UNVERIFIED")
        self.assertEqual(got[0]["state"], "POLICY_UNREADABLE")

    def test_small_volume_bounds_are_consistent(self):
        row = {"host": "peer", "rc": 0, "sweep": {"external_volumes": [
            {"mount": "/Volumes/SMALL", "state": "OK", "total_gib": 32.0,
             "free_gib": 10.0, "floor_gib": 32.0, "warn_gib": 32.0}]}}
        result = self.fleet._external_volume_pressure(row)
        self.assertEqual(result[0]["severity"], "BREACH")

    def test_repeated_unreachable_carries_last_breach_until_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            fleet = self.fleet
            with mock.patch.object(fleet, "STATE", state), (
                 mock.patch.object(fleet, "LOCK", state / "fleet-remote-sweep.lock")
            ), mock.patch.object(fleet, "SEEN", state / "fleet-host-state.json"), (
                 mock.patch.object(fleet, "sync", return_value="ok")
            ), mock.patch.object(
                sys, "argv", ["fleet", "--hosts", "m1", "--no-sync", "--json"]
            ):
                failing = {
                    "host": "m1", "rc": 0,
                    "sweep": {
                        "free_gib_after": 201.3,
                        "floor_gib": 120.0,
                        "external_volumes": [self.m1_sample()],
                    },
                }
                healed = {
                    "host": "m1", "rc": 0,
                    "sweep": {
                        "free_gib_after": 201.3,
                        "floor_gib": 120.0,
                        "external_volumes": [self.m1_sample(free=400.0)],
                    },
                }
                for index, online in enumerate([True, False, False, False, True]):
                    with mock.patch.object(
                        fleet, "reachable", return_value=online
                    ), mock.patch.object(
                        fleet, "sweep", return_value=failing if index < 4 else healed
                    ), contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(fleet.main(), 0)
                    report = json.loads(output.getvalue())
                    self.assertEqual((state / "FLEET-ALERT").exists(), index < 4)
                    if index == 0:
                        self.assertEqual(
                            report["external_volume_pressure_hosts"][0]["severity"],
                            "BREACH",
                        )
                    if index in (1, 2, 3):
                        self.assertEqual(
                            report["unverified_prior_external_breaches"][0]["state"],
                            "UNVERIFIED",
                        )
                    if index == 4:
                        self.assertFalse(report["external_volume_pressure_hosts"])
                        self.assertFalse(report["unverified_prior_external_breaches"])

    def test_incomplete_substep_never_masquerades_as_green_sweep(self):
        # Does not execute sweep.main or any cleanup helper; finish is a pure
        # receipt and exit-status boundary under a disposable state directory.
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            with mock.patch.object(self.sweep, "STATE", state), mock.patch.object(
                self.sweep, "_external_volume_snapshots", return_value=[]
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=200 * 1024 ** 3)
            ):
                for steps, expected_incomplete, expected_exit in [
                    ({"stale_packs_rc": 2, "scratch_reap_rc": 0,
                      "stale_packs": '{"status":"refused"}'},
                     ["stale_packs"], 1),
                    ({"stale_packs_rc": 0, "scratch_reap_rc": 0,
                      "stale_packs": '{"status":"complete"}'}, [], 0),
                    ({"stale_packs_rc": 0, "scratch_reap_rc": 0,
                      "stale_packs": ""}, ["stale_packs.receipt_unverified"], 1),
                ]:
                    with contextlib.redirect_stdout(io.StringIO()) as stdout:
                        exit_code = self.sweep.finish({"mode": "calm", **steps})
                    receipt = json.loads(stdout.getvalue())
                    self.assertEqual(exit_code, expected_exit)
                    self.assertEqual(receipt["incomplete_substeps"], expected_incomplete)
                    self.assertEqual(receipt["degraded"], bool(expected_incomplete))
                    self.assertEqual(receipt["stale_packs_rc"], steps["stale_packs_rc"])
            recorded = [json.loads(line) for line in
                        (state / "sweep-log.jsonl").read_text().splitlines()]
            self.assertEqual([row["degraded"] for row in recorded], [True, False, True])


    def test_denied_grants_requires_verified_loopback_completion(self):
        # Hermetic receipt classification only: never run ssh or cleanup.
        now = time.time()
        mandatory = ("hung", "stale_packs", "temp_gc",
                     "temp_gc_generic", "reap", "scratch_reap")
        clean_child = {"grants": "ok", "degraded": False, "mode": "calm",
                       "time": now, "free_gib_after": 180.0,
                       "incomplete_substeps": [],
                       **{key + "_rc": 0 for key in mandatory}}
        rows = [
            ({"grants": "denied", "skipped": "grant-requiring passes"},
             ["grant_requiring_passes"], 1),
            ({"grants": "denied", "loopback": "rc=75 busy"},
             ["grant_requiring_passes"], 1),
            ({"grants": "denied", "loopback": {"grants": "ok", "degraded": False}},
             ["grant_requiring_passes"], 1),
            ({"grants": "denied", "loopback": {**clean_child,
                                              "degraded": True,
                                              "incomplete_substeps": ["stale_packs"]}},
             ["grant_requiring_passes"], 1),
            ({"grants": "denied", "loopback": {
                "grants": "ok", "degraded": False, "mode": "calm",
                "time": now, "free_gib_after": 180.0,
                "incomplete_substeps": []}},
             ["grant_requiring_passes"], 1),
            ({"grants": "denied", "loopback": {**clean_child,
                                                "time": now - 60}},
             ["grant_requiring_passes"], 1),
            ({"grants": "denied", "loopback": {**clean_child,
                                                "stale_packs_rc": 2}},
             ["grant_requiring_passes"], 1),
            ({"grants": "denied", "loopback": clean_child}, [], 0),
        ]
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(self.sweep, "STATE", pathlib.Path(temp)), mock.patch.object(
                self.sweep, "_external_volume_snapshots", return_value=[]
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=180 * 1024 ** 3)
            ):
                for data, expected, code in rows:
                    with self.subTest(data=data), contextlib.redirect_stdout(io.StringIO()) as stdout:
                        actual = self.sweep.finish({"mode": "calm", "time": now - 1,
                                                    "hung_rc": 0, "hung": '{"status":"ok"}',
                                                    **data})
                        receipt = json.loads(stdout.getvalue())
                        self.assertEqual(actual, code)
                        self.assertEqual(receipt["incomplete_substeps"], expected)
                        self.assertEqual(receipt["degraded"], bool(expected))


    def test_nested_archive_substep_failure_degrades_top_level_receipt(self):
        # An optional archive pass may run both peer helpers. A refused peer
        # is incomplete even when every other direct helper returned rc=0.
        # Never invokes a remote archive or any cleanup helper.
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(self.sweep, "STATE", pathlib.Path(temp)), (
                mock.patch.object(self.sweep, "_external_volume_snapshots", return_value=[])
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=200 * 1024 ** 3)
            ):
                good_obj = {
                    "status": "REPORT_ONLY_SOURCE_PRESERVED",
                    "eligible_source_less_trees": 0,
                    "eligible_gib": 0.0,
                    "remote_deletions": 0,
                    "dest": "/Volumes/test/fleet-archive",
                }
                good_mb = json.dumps({**good_obj, "host": "mb"})
                good_m1 = json.dumps({**good_obj, "host": "m1"})
                for archive, expected, code in [
                    ({"mb": good_mb, "mb_rc": 2, "m1": good_m1, "m1_rc": 0},
                     ["fleet_archive.mb"], 1),
                    ({"mb": good_mb, "mb_rc": 0, "m1": good_m1, "m1_rc": 124},
                     ["fleet_archive.m1"], 1),
                    ({"mb": good_mb, "mb_rc": 0, "m1": good_m1, "m1_rc": 0}, [], 0),
                ]:
                    with self.subTest(archive=archive), contextlib.redirect_stdout(io.StringIO()) as output:
                        actual = self.sweep.finish({"mode": "calm", "hung_rc": 0,
                                                    "hung": '{"status":"ok"}',
                                                    "fleet_archive_expected_dest": "/Volumes/test/fleet-archive",
                                                    "fleet_archive": archive})
                    receipt = json.loads(output.getvalue())
                    self.assertEqual(actual, code)
                    self.assertEqual(receipt["incomplete_substeps"], expected)
                    self.assertEqual(receipt["degraded"], bool(expected))

    def test_archive_exit_zero_requires_verified_report_only_peer_receipts(self):
        # A helper can exit 0 after output truncation or an invalid JSON report.
        # This tests only the top-level receipt; no archives or cleaners run.
        good = {"status": "REPORT_ONLY_SOURCE_PRESERVED",
                "eligible_source_less_trees": 0, "eligible_gib": 0.0,
                "remote_deletions": 0, "dest": "/Volumes/test/fleet-archive",
                "host": "mb"}
        ok = json.dumps(good)
        ok_m1 = json.dumps({**good, "host": "m1"})
        bad_rows = [
            ("not-json", "invalid JSON"),
            ("", "empty output"),
            ('{"status":', "truncated JSON"),
            (json.dumps({**good, "status": "DONE"}), "wrong status"),
            (json.dumps({**good, "eligible_source_less_trees": -1}), "negative count"),
            (json.dumps({**good, "eligible_gib": "0"}), "wrong metric type"),
            (json.dumps({**good, "remote_deletions": 1}), "remote delete claim"),
            (json.dumps({k: v for k, v in good.items() if k != "dest"}), "missing dest"),
            (json.dumps({**good, "host": "m1"}), "wrong peer identity"),
            (json.dumps({**good, "dest": "/wrong/unverified"}), "wrong destination"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(self.sweep, "STATE", pathlib.Path(temp)), mock.patch.object(
                self.sweep, "_external_volume_snapshots", return_value=[]
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=200 * 1024 ** 3)
            ):
                for body, reason in bad_rows:
                    with self.subTest(reason=reason), contextlib.redirect_stdout(io.StringIO()) as output:
                        code = self.sweep.finish({
                            "mode": "calm", "hung_rc": 0, "hung": '{"status":"ok"}',
                            "fleet_archive_expected_dest": "/Volumes/test/fleet-archive",
                            "fleet_archive": {"mb": body, "mb_rc": 0,
                                              "m1": ok_m1, "m1_rc": 0},
                        })
                    receipt = json.loads(output.getvalue())
                    self.assertEqual(code, 1)
                    self.assertEqual(receipt["incomplete_substeps"],
                                     ["fleet_archive.mb_receipt_unverified"])
                    self.assertTrue(receipt["degraded"])
                for archive, expected in [
                    ({"mb": ok, "mb_rc": 0, "m1": ok_m1, "m1_rc": 0}, []),
                    ({"mb": ok, "mb_rc": 0}, ["fleet_archive.m1_receipt_unverified"]),
                    ("malformed-archive-container", ["fleet_archive.receipt_unverified"]),
                ]:
                    with self.subTest(archive=archive), contextlib.redirect_stdout(io.StringIO()) as output:
                        code = self.sweep.finish({
                            "mode": "calm", "hung_rc": 0, "hung": '{"status":"ok"}',
                            "fleet_archive_expected_dest": "/Volumes/test/fleet-archive",
                            "fleet_archive": archive,
                        })
                    receipt = json.loads(output.getvalue())
                    self.assertEqual(receipt["incomplete_substeps"], expected)
                    self.assertEqual(code, 0 if not expected else 1)


    def test_nonzero_loopback_exit_cannot_return_success_shaped_json(self):
        # No ssh call: hermetic transport-exit fixture under disposable key path.
        clean = {"grants": "ok", "degraded": False, "mode": "calm",
                 "free_gib_after": 180.0, "incomplete_substeps": []}
        with tempfile.TemporaryDirectory() as temp:
            key = pathlib.Path(temp) / "loopback-fixture"
            key.write_text("fixture")
            proc = mock.Mock(returncode=42, stdout=json.dumps(clean),
                             stderr="not for top-level success")
            with mock.patch.object(self.sweep, "LOOPBACK_KEY", key), mock.patch.object(
                self.sweep.subprocess, "run", return_value=proc
            ), mock.patch.dict(self.sweep.os.environ, {"MM_SWEEP_LOOPBACK": "0"}):
                self.assertEqual(self.sweep.via_loopback(),
                                 "loopback transport rc=42")
            # This invalid child must also degrade the original launchd receipt.
            with mock.patch.object(self.sweep, "STATE", pathlib.Path(temp)), (
                mock.patch.object(self.sweep, "_external_volume_snapshots", return_value=[])
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=180 * 1024 ** 3)
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                code = self.sweep.finish({"mode": "calm", "grants": "denied",
                                          "loopback": "loopback transport rc=42"})
            self.assertEqual(code, 1)
            self.assertIn("grant_requiring_passes",
                          json.loads(output.getvalue())["incomplete_substeps"])


    def test_atomic_original_sweep_lock_serializes_two_contenders(self):
        # Disposable lock only. Never calls the sweeper, SSH, launchd or cleanup.
        with tempfile.TemporaryDirectory() as temp:
            lock = pathlib.Path(temp) / 'sweep.lock'
            start = threading.Barrier(2)
            release = threading.Event()
            outcomes = queue.Queue()

            def contender():
                start.wait(timeout=10)
                fd = self.sweep._claim_sweep_lock(lock)
                outcomes.put(fd is not None)
                if fd is not None:
                    try:
                        release.wait(timeout=10)
                    finally:
                        self.sweep.os.close(fd)

            threads = [threading.Thread(target=contender) for _ in range(2)]
            for thread in threads:
                thread.start()
            try:
                values = [outcomes.get(timeout=10) for _ in range(2)]
            finally:
                release.set()
                for thread in threads:
                    thread.join(timeout=10)
            self.assertEqual(sum(values), 1)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertTrue(lock.exists(), 'stable marker must not be unlinked')
            fd = self.sweep._claim_sweep_lock(lock)
            self.assertIsNotNone(fd, 'stale PID text cannot strand kernel lock')
            self.sweep.os.close(fd)
            self.assertTrue(lock.exists())

    def test_original_sweep_lock_symlink_and_busy_main_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            target = state / 'preserve'
            target.write_text('untouched')
            lock = state / 'sweep.lock'
            lock.symlink_to(target)
            with self.assertRaises(OSError):
                self.sweep._claim_sweep_lock(lock)
            self.assertEqual(target.read_text(), 'untouched')
            lock.unlink()
            fd = self.sweep._claim_sweep_lock(lock)
            try:
                with mock.patch.object(self.sweep, 'STATE', state), mock.patch.object(
                    self.sweep, 'LOCK', lock
                ), mock.patch.dict(self.sweep.os.environ, {'MM_SWEEP_NOLOCK': '0'}):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        result = self.sweep.main()
                    self.assertEqual(result, 75)
                    self.assertEqual(json.loads(output.getvalue()),
                                     {'degraded': True, 'lock': 'BUSY'})
            finally:
                self.sweep.os.close(fd)
            self.assertTrue(lock.exists())


if __name__ == "__main__":
    unittest.main()
