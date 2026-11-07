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

    def test_nonpositive_nonfinite_or_boolean_floor_cannot_disable_guard(self):
        # A malformed or invalid installed override must not silently erase
        # the absolute storage floor. Valid M1 120 GiB remains authoritative.
        with tempfile.TemporaryDirectory() as directory:
            config = pathlib.Path(directory) / "storage-floor.json"
            with mock.patch.object(self.sweep, "FLOOR_CONF", config):
                self.assertEqual(
                    self.sweep.floor_for_host(),
                    self.sweep.GUARD_DEFAULT_FLOOR_GIB,
                )
                for value in (0, -1, True, False, "nan", "inf", "-inf", "bad"):
                    with self.subTest(value=value):
                        config.write_text(json.dumps({"internal_floor_gib": value}))
                        self.assertEqual(
                            self.sweep.floor_for_host(),
                            self.sweep.GUARD_DEFAULT_FLOOR_GIB,
                        )
                config.write_text(json.dumps({"internal_floor_gib": 120}))
                self.assertEqual(self.sweep.floor_for_host(), 120.0)

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
        complete_scratch = json.dumps({
            "removed": 0, "bundled": 0, "skipped": 0, "partial": False,
            "deadline_s": 2700.0, "elapsed_s": 1,
            "swept_overcap_bundles": 0, "freed_gib": 0.0,
        })
        # The stale-pack pass runs as a never-apply INVENTORY, so the only
        # receipt that can complete it is a complete, error-free discovery
        # that declares applied=false and zero removed/freed bytes.
        complete_stale = json.dumps({
            "applied": False, "removed": 0, "freed_bytes": 0,
            "scratch_discovery": {"complete": True, "errors": []},
        })
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            with mock.patch.object(self.sweep, "STATE", state), mock.patch.object(
                self.sweep, "_external_volume_snapshots", return_value=[]
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=200 * 1024 ** 3)
            ):
                for steps, expected_incomplete, expected_exit in [
                    ({"stale_packs_rc": 2, "scratch_reap_rc": 0, "scratch_reap": complete_scratch,
                      "stale_packs": '{"status":"refused"}'},
                     ["stale_packs", "stale_packs.unexpected_effect"], 1),
                    ({"stale_packs_rc": 0, "scratch_reap_rc": 0, "scratch_reap": complete_scratch,
                      "stale_packs": complete_stale}, [], 0),
                    ({"stale_packs_rc": 0, "scratch_reap_rc": 0, "scratch_reap": complete_scratch,
                      "stale_packs": ""},
                     ["stale_packs.receipt_unverified",
                      "stale_packs.unexpected_effect"], 1),
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



    def test_scratch_reap_zero_exit_requires_complete_final_ledger(self):
        # Pure finish() classification: no cleanup script or remote host runs.
        complete = {
            "removed": 0, "bundled": 0, "skipped": 0, "partial": False,
            "deadline_s": 2700.0, "elapsed_s": 1,
            "swept_overcap_bundles": 0, "freed_gib": 0.0,
        }
        invalid = dict(complete, removed=-1)
        missing_partial = {key: value for key, value in complete.items()
                           if key != "partial"}
        cases = [
            (None, ["scratch_reap.receipt_unverified"], 1),
            ("", ["scratch_reap.receipt_unverified"], 1),
            ("SKIP now-busy /somewhere", ["scratch_reap.receipt_unverified"], 1),
            ("{broken", ["scratch_reap.receipt_unverified"], 1),
            (json.dumps(missing_partial), ["scratch_reap.receipt_unverified"], 1),
            (json.dumps(invalid), ["scratch_reap.receipt_unverified"], 1),
            (json.dumps(dict(complete, partial=True)),
             ["scratch_reap.partial"], 1),
            (json.dumps(complete), [], 0),
        ]
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            with mock.patch.object(self.sweep, "STATE", state), mock.patch.object(
                self.sweep, "_external_volume_snapshots", return_value=[]
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=200 * 1024 ** 3)
            ):
                for raw, expected, exit_status in cases:
                    with self.subTest(raw=raw), contextlib.redirect_stdout(
                        io.StringIO()
                    ) as output:
                        status = self.sweep.finish({
                            "mode": "calm", "scratch_reap_rc": 0,
                            "scratch_reap": raw,
                        })
                    receipt = json.loads(output.getvalue())
                    self.assertEqual(status, exit_status)
                    self.assertEqual(receipt["incomplete_substeps"], expected)
                    self.assertEqual(receipt["degraded"], bool(expected))

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
                self.assertEqual(self.sweep.via_loopback(parent_nonce='a' * 64),
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


    def test_stale_pack_zero_exit_partial_discovery_is_degraded(self):
        # Real incumbent M1: exit 0, but find(1) denied /private/tmp subtree.
        # The pass is a never-apply INVENTORY: applied=false, zero removed,
        # zero freed bytes, complete error-free discovery.
        receipt = {
            'applied': False, 'removed': 0, 'freed_bytes': 0,
            'scratch_discovery': {'complete': False, 'errors': [
                '/private/tmp: find rc=1: Permission denied']},
        }
        self.assertFalse(self.sweep._stale_pack_inventory_complete(json.dumps(receipt)))
        self.assertFalse(self.sweep._stale_pack_inventory_complete('not json'))
        self.assertTrue(self.sweep._stale_pack_inventory_complete(json.dumps(
            {**receipt, 'scratch_discovery': {'complete': True, 'errors': []}})))
        # A receipt that claims it APPLIED is not an inventory of a
        # never-apply pass, whatever its counters say.
        self.assertFalse(self.sweep._stale_pack_inventory_complete(json.dumps(
            {**receipt, 'applied': True,
             'scratch_discovery': {'complete': True, 'errors': []}})))
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            self.sweep, 'STATE', pathlib.Path(temp)
        ), mock.patch.object(
            self.sweep, '_external_volume_snapshots', return_value=[]
        ), mock.patch.object(
            self.sweep.shutil, 'disk_usage',
            return_value=mock.Mock(free=200 * 1024 ** 3)
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            code = self.sweep.finish({'mode': 'calm', 'stale_packs_rc': 0,
                                      'stale_packs': json.dumps(receipt)})
        self.assertEqual(code, 1)
        self.assertIn('stale_packs.inventory_unverified',
                      json.loads(output.getvalue())['incomplete_substeps'])

    def test_archive_cooldown_fails_closed_on_partial_or_invalid_peer(self):
        dest = '/Volumes/test/fleet-archive'
        base = {'status': 'REPORT_ONLY_SOURCE_PRESERVED',
                'eligible_source_less_trees': 0, 'eligible_gib': 0.0,
                'remote_deletions': 0, 'dest': dest}
        valid = {peer: json.dumps({**base, 'host': peer}) for peer in ('mb', 'm1')}
        self.assertTrue(self.sweep._archive_cooldown_ready({
            'mb': valid['mb'], 'mb_rc': 0, 'm1': valid['m1'], 'm1_rc': 0}, dest))
        for bad_m1, bad_rc in [(valid['m1'], 124), (valid['m1'], 1),
                               (valid['m1'], 2), ('', 0), ('truncated {', 0),
                               (json.dumps({**base, 'host': 'm1',
                                            'remote_deletions': 1}), 0),
                               (json.dumps({**base, 'host': 'm1',
                                            'eligible_gib': '0'}), 0)]:
            with self.subTest(rc=bad_rc, receipt=bad_m1):
                self.assertFalse(self.sweep._archive_cooldown_ready({
                    'mb': valid['mb'], 'mb_rc': 0, 'm1': bad_m1, 'm1_rc': bad_rc}, dest))
        import inspect
        source = inspect.getsource(self.sweep.main)
        self.assertIn('if _archive_cooldown_ready(pulled, str(archive_dest)):', source)
        self.assertIn('item = _qualified_archive_peer(', source)

    def test_b10_helper_success_requires_complete_structured_receipts(self):
        # Pure finish() classification, no live cleanup/archive/SSH/host effects.
        cache = {'mode': 'APPLY', 'selected': [], 'verified': [], 'held': {},
                 'held_count': 0, 'recovered_bytes': 0, 'scanned': 0}
        sparse = {'applied': True, 'sparsified': 0, 'skipped': 0,
                  'conversion_failures': 0, 'freed_gib': 0.0,
                  'discovery_complete': True, 'scan_failures': []}
        repack = {'repacked': 0, 'attempts_failed': 0, 'total_freed_gib': 0.0,
                  'free_after': 200.0, 'discovery_complete': True,
                  'scan_failures': [], 'discovery_scope':
                  {'durable_clones_checked': 0, 'object_stores_identified': 0}}
        chain = {'applied': True, 'src': '/tmp/test-chain', 'dst': '/tmp/test-archive',
                 'manifest': '/tmp/test-archive/_manifests/archive-TEST.json',
                 'candidates': 0, 'archived': 0, 'errors': 0, 'bytes': 0,
                 'archived_gib': 0.0, 'time': 1.0}
        fixtures = {'generated_cache_trim': cache, 'fleet_sparse': sparse,
                    'repack': repack, 'chain_archive': chain}
        for key, valid in fixtures.items():
            with self.subTest(helper=key):
                self.assertTrue(self.sweep._helper_receipt_qualified(key, json.dumps(valid)))
                for bad in ('', '{truncated', '{"status":"ok"}'):
                    self.assertFalse(self.sweep._helper_receipt_qualified(key, bad))
                with tempfile.TemporaryDirectory() as temp, mock.patch.object(
                    self.sweep, 'STATE', pathlib.Path(temp)
                ), mock.patch.object(
                    self.sweep, '_external_volume_snapshots', return_value=[]
                ), mock.patch.object(
                    self.sweep.shutil, 'disk_usage',
                    return_value=mock.Mock(free=200 * 1024 ** 3)
                ):
                    for raw, expected in [(json.dumps(valid), []),
                                          ('', [key + '.receipt_unverified']),
                                          ('{"status":"ok"}', [key + '.receipt_unverified'])]:
                        with contextlib.redirect_stdout(io.StringIO()) as output:
                            status = self.sweep.finish({'mode': 'calm', key + '_rc': 0, key: raw})
                        row = json.loads(output.getvalue())
                        self.assertEqual(row['incomplete_substeps'], expected)
                        self.assertEqual(status, 0 if not expected else 1)

        for key, invalid in [
            ('generated_cache_trim', {**cache, 'refused': 'unresolved_action'}),
            ('generated_cache_trim', {**cache, 'bounded': 'time_budget'}),
            ('fleet_sparse', {**sparse, 'discovery_complete': False}),
            ('fleet_sparse', {**sparse, 'scan_failures': ['denied']}),
            ('fleet_sparse', {**sparse, 'conversion_failures': 1}),
            ('repack', {**repack, 'attempts_failed': 1}),
            ('repack', {**repack, 'discovery_complete': False}),
            ('chain_archive', {**chain, 'archived': 1}),
            ('chain_archive', {**chain, 'errors': 1}),
            ('chain_archive', {**chain, 'manifest': '/tmp/other/archive-TEST.json'}),
        ]:
            with self.subTest(helper=key, case=invalid):
                self.assertFalse(self.sweep._helper_receipt_qualified(key, json.dumps(invalid)))

        # The existing fleet_sparse and fleet_repack producers currently omit
        # these proof fields. No false assertion that a matching producer is installed.
        self.assertFalse(self.sweep._helper_receipt_qualified(
            'fleet_sparse', json.dumps({'sparsified': 0, 'skipped': 0, 'freed_gib': 0.0})))
        self.assertFalse(self.sweep._helper_receipt_qualified(
            'repack', json.dumps({k: v for k, v in repack.items()
                                  if k != 'attempts_failed'})))
        import inspect
        main_source = inspect.getsource(self.sweep.main)
        self.assertIn("_helper_receipt_qualified('chain_archive', out.get('chain_archive'))",
                      main_source)


    def test_b10_unqualified_sparse_and_repack_hold_before_any_apply(self):
        # Execute only the sweep coordinator with every executable child mocked.
        # This ensures an eligible caution/under-floor pass cannot invoke either
        # unqualified producer; no installed cleaner/host/process is touched.
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            executed = []

            def fake_guarded(out, key, *args, **kwargs):
                executed.append(key)
                out[key + '_rc'] = 0
                out[key] = '{"status":"ok"}'

            usage = mock.Mock(free=180 * self.sweep.GIB,
                              total=460 * self.sweep.GIB)
            with mock.patch.object(self.sweep, 'STATE', state), (
                mock.patch.object(self.sweep, 'LOCK', state / 'sweep.lock')
            ), mock.patch.object(self.sweep, 'ssd_receipts', return_value=[]), (
                mock.patch.object(self.sweep, 'grants', return_value='ok')
            ), mock.patch.object(self.sweep, 'guarded', side_effect=fake_guarded), (
                mock.patch.object(self.sweep, '_pool_archive_mount', return_value=None)
            ), mock.patch.object(self.sweep, 'floor_for_host', return_value=200.0), (
                mock.patch.object(self.sweep.shutil, 'disk_usage', return_value=usage)
            ), mock.patch.object(self.sweep, '_external_volume_snapshots', return_value=[]), (
                mock.patch.object(self.sweep.Path, 'home', return_value=state)
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                status = self.sweep.main()
            receipt = json.loads(output.getvalue())
            # The installed sparse producer is held pre-effect too: its
            # --apply mode is never launched. The unenrolled stale-pack helper
            # is held BEFORE any helper subprocess as well, so it is not
            # launched either: no child runs at all.
            self.assertNotIn('sparse', executed,
                             'the unqualified sparse helper must not be launched')
            self.assertNotIn('fleet_sparse', executed)
            self.assertNotIn('repack', executed)
            self.assertNotIn('stale_packs', executed,
                             'the unenrolled stale-pack helper must not be launched')
            self.assertEqual(status, 1)
            for key in ('sparse', 'fleet_sparse', 'repack'):
                with self.subTest(helper=key):
                    self.assertEqual(receipt[key + '_rc'], 78)
                    self.assertEqual(receipt[key + '_effect_state'], 'NOT_APPLIED')
                    self.assertIn(key, receipt['incomplete_substeps'])
            # The held sparse pass is degraded by the hold itself, so a later
            # success-shaped receipt cannot rearm it.
            self.assertIn('sparse.held_unqualified_helper',
                          receipt['incomplete_substeps'])
            self.assertTrue(receipt['degraded'])
            self.assertEqual(self.sweep.hold_unqualified_apply.__name__,
                             'hold_unqualified_apply')

    def test_installed_sparse_scan_headroom_behavior_survives_source_release(self):
        # Source-only contract: neither main() nor any cleanup helper is run.
        allow = self.sweep.sparse_scan_allowed
        self.assertFalse(allow(260.0, 200.0), '60-GiB reserve defers 5400s scan')
        self.assertFalse(allow(300.0, 200.0))
        self.assertTrue(allow(259.99, 200.0))
        self.assertTrue(allow(200.0, 200.0), 'never defer at the floor')
        self.assertTrue(allow(199.0, 200.0), 'never weaken pressure floor')
        self.assertTrue(allow(300.0, None), 'unknown floor does not skip')
        self.assertTrue(allow(300.0, 0.0), 'unconfigured floor does not skip')
        import inspect
        main_source = inspect.getsource(self.sweep.main)
        self.assertIn('sparse_scan_allowed(free / GIB, floor_gib)', main_source)
        self.assertIn("out['sparse_deferred']", main_source)

    def test_b3_unbound_loopback_refuses_before_any_cleanup_helper(self):
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            with mock.patch.object(self.sweep, 'STATE', state), mock.patch.object(
                self.sweep, 'LOCK', state / 'sweep.lock'
            ), mock.patch.dict(self.sweep.os.environ, {
                'MM_SWEEP_NOLOCK': '1', 'MM_SWEEP_LOOPBACK': '1',
                'SSH_ORIGINAL_COMMAND': 'sweep ' + 'a' * 64,
            }), mock.patch.object(
                self.sweep, 'guarded', side_effect=AssertionError('helper dispatched')
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(self.sweep.main(), 78)
            self.assertEqual(json.loads(output.getvalue())['lock'], 'UNBOUND_CHILD')
            self.assertFalse((state / 'sweep-loopback.lock').exists())

    def test_b3_binding_needs_live_parent_matching_nonce_and_fresh_epoch(self):
        # Disposable kernel locks and synthetic child identity, never SSH/cleanup.
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            lock = state / 'sweep.lock'
            with mock.patch.object(self.sweep, 'LOCK', lock):
                parent_fd = self.sweep._claim_sweep_lock(lock)
                self.assertIsNotNone(parent_fd)
                parent_pid = self.sweep.os.getpid()
                nonce = self.sweep._read_lock_nonce(parent_fd)
                try:
                    with mock.patch.dict(self.sweep.os.environ, {
                        'MM_SWEEP_LOOPBACK': '1',
                        'SSH_ORIGINAL_COMMAND': 'sweep ' + nonce,
                    }), mock.patch.object(self.sweep.os, 'getpid',
                                          return_value=parent_pid + 10000):
                        self.assertTrue(self.sweep._bound_loopback_parent())
                        # The bound child acquires secondary while parent owns
                        # canonical. Its own flock prevents later parent overlap.
                        child_fd = self.sweep._claim_sweep_lock(
                            state / 'sweep-loopback.lock')
                        self.assertIsNotNone(child_fd)
                        try:
                            with mock.patch.dict(self.sweep.os.environ, {
                                'SSH_ORIGINAL_COMMAND': 'sweep ' + 'b' * 64,
                            }):
                                self.assertFalse(self.sweep._bound_loopback_parent())
                            old = {'pid': parent_pid, 'time': time.time() - 3600,
                                   'nonce': nonce}
                            self.sweep.os.ftruncate(parent_fd, 0)
                            self.sweep.os.lseek(parent_fd, 0, self.sweep.os.SEEK_SET)
                            self.sweep.os.write(parent_fd,
                                                 json.dumps(old).encode('ascii'))
                            self.sweep.os.fsync(parent_fd)
                            self.assertFalse(self.sweep._bound_loopback_parent())
                        finally:
                            self.sweep.os.close(child_fd)
                finally:
                    self.sweep.os.close(parent_fd)
                with mock.patch.dict(self.sweep.os.environ, {
                    'MM_SWEEP_LOOPBACK': '1',
                    'SSH_ORIGINAL_COMMAND': 'sweep ' + nonce,
                }), mock.patch.object(self.sweep.os, 'getpid',
                                      return_value=parent_pid + 10000):
                    self.assertFalse(self.sweep._bound_loopback_parent())

    def test_b3_ordinary_sweep_refuses_while_child_owns_helper_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            child_fd = self.sweep._claim_sweep_lock(state / 'sweep-loopback.lock')
            try:
                with mock.patch.object(self.sweep, 'STATE', state), mock.patch.object(
                    self.sweep, 'LOCK', state / 'sweep.lock'
                ), mock.patch.dict(self.sweep.os.environ, {
                    'MM_SWEEP_NOLOCK': '0', 'MM_SWEEP_LOOPBACK': '0',
                }), mock.patch.object(
                    self.sweep, 'guarded',
                    side_effect=AssertionError('helper must not dispatch'),
                ), contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(self.sweep.main(), 75)
                self.assertEqual(json.loads(output.getvalue())['lock'], 'BUSY')
            finally:
                self.sweep.os.close(child_fd)

    def test_b8_legacy_pid_lock_refuses_without_rewriting_unfenced_marker(self):
        # Disposable preimage only. A former sweeper writes bare PID text with
        # NO kernel flock, so a new flock is NOT evidence of exclusive custody.
        with tempfile.TemporaryDirectory() as directory:
            lock = pathlib.Path(directory) / "sweep.lock"
            legacy = f"{self.sweep.os.getpid()}\\n".encode("ascii")
            lock.write_bytes(legacy)
            with self.assertRaises(OSError) as failure:
                self.sweep._claim_sweep_lock(lock)
            self.assertEqual(failure.exception.errno, self.sweep.errno.EPERM)
            self.assertEqual(lock.read_bytes(), legacy,
                             "refusal must preserve legacy publisher evidence")
            with mock.patch.object(self.sweep, 'STATE', pathlib.Path(directory)), \
                 mock.patch.object(self.sweep, 'LOCK', lock), \
                 mock.patch.dict(self.sweep.os.environ, {'MM_SWEEP_NOLOCK': '0'}), \
                 mock.patch.object(self.sweep, 'guarded',
                                   side_effect=AssertionError('cleanup helper started')), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(self.sweep.main(), 78)
            self.assertEqual(json.loads(output.getvalue())['lock'], 'UNVERIFIED')
            self.assertEqual(lock.read_bytes(), legacy)

            # Only the test's simulated completed old epoch removes its marker;
            # source cannot grant itself that production migration authority.
            lock.unlink()
            fd = self.sweep._claim_sweep_lock(lock)
            self.assertIsNotNone(fd)
            try:
                inode = self.sweep.os.fstat(fd).st_ino
                self.assertIsNone(self.sweep._claim_sweep_lock(lock))
                current = lock.read_bytes()
                self.assertIn(b'"nonce"', current)
            finally:
                self.sweep.os.close(fd)
            fd = self.sweep._claim_sweep_lock(lock)
            self.assertIsNotNone(fd)
            self.assertEqual(self.sweep.os.fstat(fd).st_ino, inode)
            self.sweep.os.close(fd)
            # A new qualified current owner rotates its nonce on the SAME
            # persistent inode; it must never preserve the old lease secret.
            self.assertNotEqual(lock.read_bytes(), current)
            self.assertIn(b'"nonce"', lock.read_bytes())

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



    def test_malformed_helper_return_codes_cannot_report_clean(self):
        """Pure finish() contract: false-green is forbidden even for corrupt rc.

        No real sweeper, package cache cleaner, SSH, launchctl or deletion path
        runs. Disk and receipt paths are replaced by disposable fixtures.
        """
        # The stale-pack pass runs as a never-apply INVENTORY, so the only
        # receipt that can complete it is a complete, error-free discovery
        # that declares applied=false and zero removed/freed bytes.
        complete_stale = json.dumps({
            "applied": False, "removed": 0, "freed_bytes": 0,
            "scratch_discovery": {"complete": True, "errors": []},
        })
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(self.sweep, "STATE", pathlib.Path(temp)), (
                mock.patch.object(self.sweep, "_external_volume_snapshots", return_value=[])
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=200 * 1024 ** 3)
            ):
                # Python True == 0 is false, but False == 0 and 0.0 == 0
                # are true. None/"2" previously bypassed the rc scanner.
                for raw in ("2", True, False, 0.0, 2.0, None):
                    with self.subTest(raw=raw), contextlib.redirect_stdout(
                        io.StringIO()
                    ) as output:
                        status = self.sweep.finish({
                            "mode": "calm", "stale_packs_rc": raw,
                            "stale_packs": complete_stale,
                        })
                    row = json.loads(output.getvalue())
                    self.assertEqual(status, 1)
                    self.assertTrue(row["degraded"])
                    self.assertIn("stale_packs", row["incomplete_substeps"])
                    self.assertEqual(row["stale_packs_rc"], raw)

                # Int-valued 0 still proves a complete helper receipt.
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    status = self.sweep.finish({
                        "mode": "calm", "stale_packs_rc": 0,
                        "stale_packs": complete_stale,
                    })
                row = json.loads(output.getvalue())
                self.assertEqual(status, 0)
                self.assertEqual(row["incomplete_substeps"], [])

    def test_granted_sweep_missing_mandatory_return_code_is_degraded(self):
        """A granted pass missing even its helper status is not green."""
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            self.sweep, "STATE", pathlib.Path(temp)
        ), mock.patch.object(
            self.sweep, "_external_volume_snapshots", return_value=[]
        ), mock.patch.object(
            self.sweep.shutil, "disk_usage",
            return_value=mock.Mock(free=200 * 1024 ** 3)
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            code = self.sweep.finish({"mode": "calm", "grants": "ok"})
        receipt = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertTrue(receipt["degraded"])
        for name in ("hung", "stale_packs", "temp_gc",
                     "temp_gc_generic", "reap", "scratch_reap"):
            self.assertIn(name + ".rc_missing", receipt["incomplete_substeps"])

    # -- B11: the unenrolled stale-pack reaper is never invoked apply-capable.

    @staticmethod
    def _tree_snapshot(root):
        """Content-addressed snapshot of a directory tree, or None if absent."""
        if not root.exists():
            return None
        rows = []
        for path in sorted(root.rglob("*")):
            try:
                info = path.lstat()
            except OSError:
                continue
            rows.append((str(path), info.st_size, info.st_mtime_ns, info.st_mode))
        return rows

    # Two argv shapes a later edit could smuggle into the stale-pack builder.
    # Each is applied to a throwaway copy of the REAL sweep source, so the
    # mutation is proved against the production code path and not against a
    # re-implementation of it.
    _STALE_PACK_MUTATIONS = (
        # An apply abbreviation inside the argv literal, before the guard.
        ("apply-abbreviation-in-the-builder-literal",
         "    argv = [sys.executable, helper_text, '--json',\n"
         "            '--min-age-minutes', str(min_age_minutes)]",
         "    argv = [sys.executable, helper_text, '--json', '--app',\n"
         "            '--min-age-minutes', str(min_age_minutes)]"),
        # An apply abbreviation appended after the builder's own guard.
        ("apply-abbreviation-appended-after-the-guard",
         "    _assert_stale_pack_argv_allowed(argv)\n    return argv",
         "    _assert_stale_pack_argv_allowed(argv)\n"
         "    argv.append('--app')\n    return argv"),
    )

    def _load_mutated_sweep(self, old, new):
        """Load a throwaway copy of the real sweep source with one edit applied."""
        source = (SOURCE / "sweep.py").read_text()
        self.assertEqual(source.count(old), 1,
                         "the mutation anchor must exist exactly once")
        mutated_source = source.replace(old, new, 1)
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sweep_mutated.py"
            path.write_text(mutated_source)
            return load("fleet_test_sweep_mutated", path)

    def _run_sweep(self, sweep_module, stale_rc=0,
                   stale_receipt='{"status":"ok"}'):
        """Run main() with every executable child mocked.

        Returns (exit status, receipt, calls, created) where calls is the
        ORDERED list of (key, argv) the sweep handed to its children, and
        created lists the files the sweep wrote into the disposable state
        directory. No helper, host, network or native file is touched.
        """
        calls = []

        def fake_guarded(out, key, argv, timeout, env=None, limit=600):
            calls.append((key, list(argv)))
            out[key + "_rc"] = stale_rc if key == "stale_packs" else 0
            out[key] = (stale_receipt if key == "stale_packs"
                        else '{"status":"ok"}')
            return None

        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            usage = mock.Mock(free=180 * sweep_module.GIB,
                              total=460 * sweep_module.GIB)
            with mock.patch.object(sweep_module, "STATE", state), (
                mock.patch.object(sweep_module, "LOCK", state / "sweep.lock")
            ), mock.patch.object(sweep_module, "ssd_receipts", return_value=[]), (
                mock.patch.object(sweep_module, "grants", return_value="ok")
            ), mock.patch.object(sweep_module, "guarded",
                                 side_effect=fake_guarded), (
                mock.patch.object(sweep_module, "_pool_archive_mount",
                                  return_value=None)
            ), mock.patch.object(sweep_module, "floor_for_host",
                                 return_value=200.0), (
                mock.patch.object(sweep_module.shutil, "disk_usage",
                                  return_value=usage)
            ), mock.patch.object(sweep_module, "_external_volume_snapshots",
                                 return_value=[]), (
                mock.patch.object(sweep_module.Path, "home", return_value=state)
            ), mock.patch.object(sweep_module.os, "uname",
                                 return_value=mock.Mock(nodename="m2studio.local")), (
                contextlib.redirect_stdout(io.StringIO())
            ) as output:
                status = sweep_module.main()
            receipt = json.loads(output.getvalue())
            created = sorted(path.name for path in state.iterdir())
        return status, receipt, calls, created

    def _expected_stale_pack_argv(self, sweep_module, helper):
        """The one argv shape the stale-pack pass is allowed to emit."""
        return [sys.executable, str(helper), "--json", "--min-age-minutes", "120"]

    def test_stale_pack_invocation_is_never_apply_capable(self):
        # Pure argv construction. No helper, host, file or process is touched.
        helper = pathlib.Path("/nonexistent/stale_pack_reaper.py")
        argv = self.sweep.stale_pack_argv(helper)
        # EXACT argv equality. The contract is not "no --apply somewhere in
        # there"; it is precisely this one shape and nothing else.
        self.assertEqual(argv, [sys.executable, str(helper), "--json",
                                "--min-age-minutes", "120"])
        self.assertEqual(argv, self._expected_stale_pack_argv(self.sweep, helper))
        self.assertNotIn("--apply", argv)
        self.assertEqual(
            [token for token in argv if self.sweep._is_apply_capable(token)], [])
        self.assertIn("--json", argv)
        self.assertEqual(argv[-2:], ["--min-age-minutes", "120"])
        # The incumbent age is preserved.
        self.assertEqual(self.sweep.stale_pack_argv(helper)[-1], "120")
        # The guard is fail closed: an apply-capable spelling is refused, not
        # passed through to the unenrolled helper.
        for token in ("--apply", "--apply-now", "--force-apply", "--mode=apply"):
            with self.subTest(token=token):
                self.assertTrue(self.sweep._is_apply_capable(token))
                with self.assertRaises(ValueError):
                    self.sweep._assert_not_apply_capable(
                        ["python3", "/x/stale_pack_reaper.py", token])

    def test_apply_abbreviations_are_what_argparse_really_accepts(self):
        # The premise of the prefix rule, proved against argparse itself. The
        # installed helper is never read and never executed: this replicates
        # ONLY its parser, whose default ArgumentParser() sets allow_abbrev.
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--min-age-minutes", type=int, default=120)
        for token in ("--a", "--ap", "--app", "--appl"):
            with self.subTest(token=token):
                namespace = parser.parse_args(
                    ["--json", token, "--min-age-minutes", "120"])
                self.assertTrue(namespace.apply,
                                "argparse accepted " + token + " as --apply")
                # The guard must see what argparse actually accepts.
                self.assertTrue(self.sweep._is_apply_capable(token))

    def test_stale_pack_argv_refuses_apply_abbreviation_attacks(self):
        # The abbreviations a denylist of whole tokens misses. Each of these
        # arms the helper's --apply branch, and each must be refused.
        helper = pathlib.Path("/nonexistent/stale_pack_reaper.py")
        for token in ("--a", "--ap", "--app", "--appl", "--apply"):
            with self.subTest(token=token):
                self.assertTrue(self.sweep._is_apply_capable(token))
                with self.assertRaises(ValueError):
                    self.sweep._assert_not_apply_capable(
                        ["python3", "/x/stale_pack_reaper.py", token])
                # The allowlist refuses the abbreviation in either option slot
                # and as an extra trailing token.
                for argv in (
                        [sys.executable, str(helper), token,
                         "--min-age-minutes", "120"],
                        [sys.executable, str(helper), "--json",
                         "--min-age-minutes", "120", token],
                        [sys.executable, str(helper), "--json", token, "120"]):
                    with self.assertRaises(ValueError):
                        self.sweep._assert_stale_pack_argv_allowed(argv)

    def test_stale_pack_argv_refuses_hostile_min_age_minutes(self):
        # An adversarial age must never reach the helper as a token: a bool
        # is not an int here, a string is not an int here, and an option-like
        # value is not an int here either.
        helper = pathlib.Path("/nonexistent/stale_pack_reaper.py")
        hostile = (0, -1, -120, True, False, None, 120.0, 12.5,
                   "--app", "--apply", "5 --apply", "", " ", "120\n",
                   "0x10", "1e3", "120 ", [120], {"minutes": 120})
        for value in hostile:
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    self.sweep.stale_pack_argv(helper, value)
        # The BUILDER refuses these on its own, with the argv allowlist
        # stubbed out. The builder's own type/range contract must not depend
        # on a second layer that happens to catch the same value.
        with mock.patch.object(self.sweep, "_assert_stale_pack_argv_allowed",
                               return_value=None):
            for value in hostile:
                with self.subTest(value=repr(value), layer="builder-only"):
                    with self.assertRaises(ValueError):
                        self.sweep.stale_pack_argv(helper, value)
        # The age token itself is canonical and positive.
        for minutes_text in ("0120", "+120", "-120", " 120", "120 ", "0",
                             "", "120\n", "abc"):
            with self.subTest(minutes=repr(minutes_text)):
                with self.assertRaises(ValueError):
                    self.sweep._assert_stale_pack_argv_allowed(
                        [sys.executable, str(helper), "--json",
                         "--min-age-minutes", minutes_text])
        # The incumbent value still works.
        self.assertEqual(self.sweep.stale_pack_argv(helper, 120)[-1], "120")
        self.assertEqual(self.sweep.stale_pack_argv(helper)[-1], "120")

    def test_stale_pack_argv_refuses_an_option_like_helper_path(self):
        # The helper path is an argv token too: an option-like path would be
        # parsed by the helper's own parser, not treated as a script.
        for helper in ("--apply", "--app", "-a", "--json", ""):
            with self.subTest(helper=helper):
                with self.assertRaises(ValueError):
                    self.sweep.stale_pack_argv(helper)
        # The BUILDER refuses an option-like path on its own, with the argv
        # allowlist stubbed out.
        with mock.patch.object(self.sweep, "_assert_stale_pack_argv_allowed",
                               return_value=None):
            for helper in ("--apply", "--app", "-a", "--json"):
                with self.subTest(helper=helper, layer="builder-only"):
                    with self.assertRaises(ValueError):
                        self.sweep.stale_pack_argv(helper)
        # A real path is fine.
        self.assertEqual(
            self.sweep.stale_pack_argv(
                pathlib.Path("/x/stale_pack_reaper.py"))[1],
            "/x/stale_pack_reaper.py")

    def test_no_apply_capable_stale_pack_invocation_exists_in_the_module(self):
        # The oracle must be the REAL builder, not a literal scan. The builder
        # assembles the argv from str(helper) and the STALE_PACK_HELPER
        # constant, so a scan of string literals never inspects the argv that
        # is actually executed. A literal scan cannot even see a new direct
        # guarded(..., [..., str(HERE / STALE_PACK_HELPER), '--apply']).
        import ast
        import inspect

        # 1. Guard invocation capture: the builder hands its own argv to the
        #    allowlist guard, exactly once.
        helper = pathlib.Path("/nonexistent/stale_pack_reaper.py")
        captured = []
        real_guard = self.sweep._assert_stale_pack_argv_allowed

        def spy(argv):
            captured.append(list(argv))
            return real_guard(argv)

        with mock.patch.object(self.sweep, "_assert_stale_pack_argv_allowed",
                               side_effect=spy):
            argv = self.sweep.stale_pack_argv(helper)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0], argv)
        self.assertEqual(captured[0],
                         self._expected_stale_pack_argv(self.sweep, helper))

        # 2. Real builder identity, and the corrected runtime contract: the
        #    builder still produces exactly the one never-apply argv, but the
        #    coordinator NO LONGER dispatches the unenrolled helper at all.
        #    The proof is at the PROCESS boundary: subprocess.run itself is
        #    captured, so every argv the coordinator would have handed to a
        #    child is visible. A mocked helper could not prove this.
        run = self._run_sweep_spawning_children(self.sweep)
        self.assertEqual(run["spawned"], [], run["spawned"])
        self.assertFalse(any(
            "stale_pack_reaper.py" in token
            for argv in run["spawned"] for token in argv))
        self.assertEqual(
            self.sweep.stale_pack_argv(
                self.sweep.HERE / self.sweep.STALE_PACK_HELPER),
            self._expected_stale_pack_argv(
                self.sweep, self.sweep.HERE / self.sweep.STALE_PACK_HELPER))

        # 3. Exactly one stale-pack invocation site, and it is the guarded
        #    pass. The marker is the SOURCE IDENTITY of the unenrolled helper
        #    (the STALE_PACK_HELPER constant, or a stale-pack literal), which
        #    a direct new call site would have to use.
        tree = ast.parse(inspect.getsource(self.sweep))
        stale_functions = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            has_marker = False
            guarded_calls = []
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id == "STALE_PACK_HELPER":
                    has_marker = True
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    if "stale_pack_reaper" in sub.value:
                        has_marker = True
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "guarded"):
                    guarded_calls.append(sub)
            if has_marker:
                stale_functions.append((node.name, guarded_calls))
        self.assertEqual(len(stale_functions), 1,
                         "exactly one function may name the unenrolled helper")
        name, guarded_calls = stale_functions[0]
        self.assertEqual(name, "stale_pack_discovery_pass")
        # The corrected contract: the one function that names the unenrolled
        # helper dispatches it NOWHERE. It builds and validates the argv and
        # then holds, so no child process is ever started for this helper.
        self.assertEqual(guarded_calls, [])

        # 4. Neither the builder nor the pass carries an apply-capable literal.
        for function in (self.sweep.stale_pack_argv,
                         self.sweep.stale_pack_discovery_pass):
            for node in ast.walk(ast.parse(inspect.getsource(function))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertFalse(
                        self.sweep._is_apply_capable(node.value),
                        function.__name__ + " contains " + repr(node.value))

        # Exactly one stale-pack call site in main(), and it is the guarded pass.
        main_source = inspect.getsource(self.sweep.main)
        self.assertIn("stale_pack_discovery_pass(out, 'stale_packs'", main_source)
        self.assertNotIn("stale_pack_reaper.py", main_source)
        # The unenrolled helper itself is not shipped by this source tree.
        self.assertFalse(
            (self.sweep.HERE / "stale_pack_reaper.py").exists())

    def test_stale_pack_pass_holds_unapplied_on_the_eligible_mac_path(self):
        # Execute only the sweep coordinator with the PROCESS launcher
        # captured and the host presented as an eligible Mac. The captured
        # argv list is the proof: the stale-pack helper is not dispatched at
        # all, the receipt names the hold, and no native file is created,
        # changed or removed.
        native_state = pathlib.Path.home() / ".local/state/mastermind/storage-cleanup"
        native_before = self._tree_snapshot(native_state)
        run = self._run_sweep_spawning_children(self.sweep)
        receipt = run["receipt"]
        status = run["status"]

        # No child process is started for the stale-pack helper. The
        # coordinator builds and validates the never-apply argv and then
        # holds, before any helper subprocess could run.
        self.assertEqual(run["spawned"], [], run["spawned"])
        self.assertFalse(any(
            "stale_pack_reaper.py" in token
            for argv in run["spawned"] for token in argv))

        # The builder still produces exactly the one never-apply argv.
        argv = self.sweep.stale_pack_argv(
            self.sweep.HERE / self.sweep.STALE_PACK_HELPER)
        self.assertEqual(argv,
                         self._expected_stale_pack_argv(
                             self.sweep,
                             self.sweep.HERE / self.sweep.STALE_PACK_HELPER))
        self.assertNotIn("--apply", argv)
        self.assertEqual(
            [token for token in argv
             if self.sweep._is_apply_capable(token)], [])

        self.assertEqual(receipt["stale_packs_hold"],
                         "HELD_UNQUALIFIED_STALE_PACK_HELPER")
        self.assertEqual(receipt["stale_packs_effect_state"], "NOT_APPLIED")
        self.assertEqual(receipt["stale_packs_rc"], 78)
        self.assertEqual(receipt["stale_packs_verified_reclaimed_bytes"], 0)
        self.assertIn("stale_packs.held_unqualified_helper",
                      receipt["incomplete_substeps"])
        self.assertTrue(receipt["degraded"])
        self.assertNotEqual(status, 0)

        # The sweep's INDEPENDENT telemetry survives the hold: the free-space
        # sample and the recurring sweep-log row are still there.
        self.assertIn("free_gib_before", receipt)
        self.assertIn("free_gib_after", receipt)
        self.assertIn("sweep-log.jsonl", run["created"])
        self.assertEqual(native_before, self._tree_snapshot(native_state),
                         "no native storage-cleanup file was created or changed")

    def test_stale_pack_hold_survives_helper_failures(self):
        # The hold is a property of the PASS, not of one lucky exit code. No
        # helper runs at all, so no helper outcome -- a partial census, a
        # timeout, a launch error -- can change the hold, the NOT_APPLIED
        # effect state, the degraded receipt or the nonzero exit.
        run = self._run_sweep_spawning_children(self.sweep)
        receipt = run["receipt"]
        self.assertEqual(receipt["stale_packs_rc"], 78)
        self.assertEqual(receipt["stale_packs_hold"],
                         "HELD_UNQUALIFIED_STALE_PACK_HELPER")
        self.assertEqual(receipt["stale_packs_effect_state"], "NOT_APPLIED")
        self.assertEqual(receipt["stale_packs_verified_reclaimed_bytes"], 0)
        self.assertIn("stale_packs.held_unqualified_helper",
                      receipt["incomplete_substeps"])
        self.assertTrue(receipt["degraded"])
        self.assertNotEqual(run["status"], 0)
        self.assertEqual(run["spawned"], [], run["spawned"])
        # A refused argv is still a known non-dispatch, never an unknown
        # effect: the refusal the coordinator writes is recognised by the
        # receipt reconciler through the structured hold metadata it emits
        # together with the incumbent refusal rc. That provenance is the
        # producer's own report, so it is carried here exactly as the
        # producer emits it; a receipt without it is missing provenance, not
        # provenance.
        produced = {}
        self.sweep.stale_pack_discovery_pass(produced, "stale_packs")
        out = {"stale_packs": self.sweep.STALE_PACK_HOLD_REFUSAL,
               "stale_packs_rc": 78,
               "stale_packs_hold": self.sweep.STALE_PACK_HOLD,
               "stale_packs_effect_report": produced["stale_packs_effect_report"]}
        self.sweep._record_stale_pack_receipt_truth(out, "stale_packs")
        self.assertEqual(out["stale_packs_effect_state"], "NOT_APPLIED")
        self.assertEqual(out["stale_packs_effect_report"]["kind"],
                         "runtime_pre_dispatch_hold")

    def test_stale_pack_allowlist_kills_an_apply_abbreviation_mutation(self):
        # A later edit that smuggles an apply abbreviation into the builder
        # must fail closed BEFORE the guarded child executes. The mutation is
        # applied to a throwaway copy of the REAL sweep source, so the proof
        # is against the production code path.
        helper = pathlib.Path("/nonexistent/stale_pack_reaper.py")
        expected = self._expected_stale_pack_argv(self.sweep, helper)
        for label, old, new in self._STALE_PACK_MUTATIONS:
            with self.subTest(mutation=label):
                mutated = self._load_mutated_sweep(old, new)

                # 1. The mutated builder cannot ship a compliant argv: the
                #    exact-argv regression fails against the mutant.
                try:
                    shipped = mutated.stale_pack_argv(helper)
                except ValueError:
                    shipped = None
                self.assertNotEqual(shipped, expected)

                # 2. The allowlist itself refuses the smuggled shape.
                with self.assertRaises(ValueError):
                    mutated._assert_stale_pack_argv_allowed(
                        [sys.executable, str(helper), "--json", "--app",
                         "--min-age-minutes", "120"])

                # 3. The production path never hands an apply-capable argv to
                #    a child: the stale-pack child is not executed at all.
                status, receipt, calls, _ = self._run_sweep(mutated)
                self.assertEqual([argv for key, argv in calls
                                  if key == "stale_packs"], [])
                for key, argv in calls:
                    if any("stale_pack_reaper" in token for token in argv):
                        for token in argv:
                            self.assertFalse(
                                mutated._is_apply_capable(token),
                                "an apply-capable token reached a child")

                # 4. The refusal is receipted, not swallowed: the sweep stays
                #    degraded and the hold is still named.
                self.assertEqual(receipt["stale_packs_hold"],
                                 "HELD_UNQUALIFIED_STALE_PACK_HELPER")
                self.assertEqual(receipt["stale_packs_effect_state"], "NOT_APPLIED")
                self.assertEqual(receipt["stale_packs_rc"], 78)
                self.assertTrue(receipt["degraded"])
                self.assertNotEqual(status, 0)

    def test_stale_pack_hold_marker_degrades_the_sweep_receipt(self):
        # Pure finish() classification: no helper, host or file is touched.
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            with mock.patch.object(self.sweep, "STATE", state), mock.patch.object(
                self.sweep, "_external_volume_snapshots", return_value=[]
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=200 * 1024 ** 3)
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                code = self.sweep.finish({
                    "mode": "calm",
                    "stale_packs_rc": 0,
                    "stale_packs": '{"applied": false, "removed": 0, "freed_bytes": 0}',
                    "stale_packs_hold": "HELD_UNQUALIFIED_STALE_PACK_HELPER",
                    "stale_packs_effect_state": "NOT_APPLIED",
                })
            receipt = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertTrue(receipt["degraded"])
        self.assertIn("stale_packs.held_unqualified_helper",
                      receipt["incomplete_substeps"])
        self.assertEqual(receipt["stale_packs_effect_state"], "NOT_APPLIED")
        self.assertEqual(receipt["stale_packs_hold"],
                         "HELD_UNQUALIFIED_STALE_PACK_HELPER")


    def test_unenrolled_m2_cache_trim_is_held_before_helper_dispatch(self):
        # Drive the real coordinator on the eligible M2 path with all child
        # launches mocked. The missing source enrollment is a pre-effect hold,
        # not merely a post-hoc warning after an apply-capable subprocess.
        self.assertFalse((self.sweep.HERE / "generated_cache_trim.py").exists())
        status, receipt, calls, created = self._run_sweep(self.sweep)
        self.assertNotIn("generated_cache_trim", [key for key, _ in calls])
        self.assertFalse(any(
            "generated_cache_trim.py" in token
            for _, argv in calls for token in argv
        ))
        self.assertEqual(receipt["generated_cache_trim_hold"],
                         "HELD_UNQUALIFIED_GENERATED_CACHE_HELPER")
        self.assertEqual(receipt["generated_cache_trim_effect_state"],
                         "NOT_APPLIED")
        self.assertEqual(receipt["generated_cache_trim_rc"], 78)
        self.assertIn("PRE_EFFECT_HOLD", receipt["generated_cache_trim"])
        self.assertIn("generated_cache_trim",
                      receipt["incomplete_substeps"])
        self.assertIn("generated_cache_trim.held_unqualified_helper",
                      receipt["incomplete_substeps"])
        self.assertTrue(receipt["degraded"])
        self.assertEqual(status, 1)
        self.assertIn("sweep-log.jsonl", created)
        # The generic admission helper remains deliberately key-closed: an
        # unknown key is refused, and only the enumerated unqualified apply
        # call sites are admitted.
        with self.assertRaises(ValueError):
            self.sweep.hold_unqualified_apply({}, "not_an_enrolled_helper")
        for key in ("fleet_sparse", "repack", "generated_cache_trim", "hung",
                    "temp_gc", "temp_gc_generic", "reap", "sparse",
                    "scratch_reap", "chain_archive"):
            with self.subTest(key=key):
                out = {}
                self.sweep.hold_unqualified_apply(out, key)
                self.assertEqual(out[key + "_rc"], 78)
                self.assertEqual(out[key + "_effect_state"], "NOT_APPLIED")
                self.assertIn("PRE_EFFECT_HOLD", out[key])

    def test_cache_trim_hold_beats_a_success_shaped_helper_receipt(self):
        # Even a future regression that writes rc=0 and a plausible JSON
        # cannot turn an explicit pre-effect hold into a green sweep.
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            with mock.patch.object(self.sweep, "STATE", state), mock.patch.object(
                self.sweep, "_external_volume_snapshots", return_value=[]
            ), mock.patch.object(
                self.sweep.shutil, "disk_usage",
                return_value=mock.Mock(free=200 * 1024 ** 3)
            ), mock.patch.object(
                self.sweep, "_helper_receipt_qualified", return_value=True
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                status = self.sweep.finish({
                    "mode": "calm",
                    "generated_cache_trim_rc": 0,
                    "generated_cache_trim": '{"mode":"APPLY","verified":[]}',
                    "generated_cache_trim_hold":
                        "HELD_UNQUALIFIED_GENERATED_CACHE_HELPER",
                    "generated_cache_trim_effect_state": "NOT_APPLIED",
                })
            receipt = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertTrue(receipt["degraded"])
        self.assertIn("generated_cache_trim.held_unqualified_helper",
                      receipt["incomplete_substeps"])
        self.assertEqual(receipt["generated_cache_trim_effect_state"],
                         "NOT_APPLIED")


    # -- S5: stale-pack inventory truth, effect truth, and the pre-effect holds.

    @staticmethod
    def _zero_effect_inventory(**overrides):
        """A complete, error-free, zero-effect stale-pack inventory receipt."""
        receipt = {
            'applied': False, 'removed': 0, 'freed_bytes': 0,
            'scratch_discovery': {'complete': True, 'errors': []},
        }
        receipt.update(overrides)
        return receipt

    @contextlib.contextmanager
    def _disposable_state(self):
        """A disposable sweep state directory. Nothing native is written."""
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(self.sweep, "STATE", pathlib.Path(temp)), \
                 mock.patch.object(self.sweep, "_external_volume_snapshots",
                                   return_value=[]), \
                 mock.patch.object(self.sweep.shutil, "disk_usage",
                                   return_value=mock.Mock(free=200 * 1024 ** 3)):
                yield pathlib.Path(temp)

    def _run_sweep_spawning_children(self, sweep_module, free_gib=180.0,
                                     stale_receipt='{"status":"ok"}',
                                     grants_result='ok', make_chain=False):
        """Run main() with subprocess.run itself captured.

        The captured list is every argv the coordinator handed to a child
        PROCESS. The launcher is replaced, not the helper: no helper, host,
        network or native file is touched.
        """
        spawned = []
        ssd_calls = []

        def fake_run(argv, *args, **kwargs):
            spawned.append([str(token) for token in argv])
            return mock.Mock(returncode=0, stdout=stale_receipt, stderr='')

        def fake_ssd_receipts(sub):
            ssd_calls.append(sub)
            return ['--receipts', str(sweep_module.STATE / 'never')]

        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            if make_chain:
                (state / 'flow-ops-wt' / 'data' / 'chain_snapshots').mkdir(
                    parents=True)
            usage = mock.Mock(free=int(free_gib * sweep_module.GIB),
                              total=int(460 * sweep_module.GIB))
            with mock.patch.object(sweep_module, 'STATE', state), (
                mock.patch.object(sweep_module, 'LOCK', state / 'sweep.lock')
            ), mock.patch.object(sweep_module, 'ssd_receipts',
                                 side_effect=fake_ssd_receipts), (
                mock.patch.object(sweep_module, 'grants', return_value=grants_result)
            ), mock.patch.object(sweep_module, 'via_loopback', return_value=None), (
                mock.patch.object(sweep_module, '_pool_archive_mount',
                                  return_value=None)
            ), mock.patch.object(sweep_module, 'floor_for_host',
                                 return_value=200.0), (
                mock.patch.object(sweep_module.shutil, 'disk_usage',
                                  return_value=usage)
            ), mock.patch.object(sweep_module, '_external_volume_snapshots',
                                 return_value=[]), (
                mock.patch.object(sweep_module.Path, 'home', return_value=state)
            ), mock.patch.object(sweep_module.os, 'uname',
                                 return_value=mock.Mock(nodename='m2studio.local')), (
                mock.patch.object(sweep_module.subprocess, 'run',
                                  side_effect=fake_run)
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                status = sweep_module.main()
            receipt = json.loads(output.getvalue())
            created = sorted(path.name for path in state.iterdir())
            chain_stamp = (state / 'chain-archive.last').exists()
        return {'status': status, 'receipt': receipt, 'spawned': spawned,
                'ssd_calls': ssd_calls, 'created': created,
                'chain_stamp': chain_stamp}

    # -- A: the inventory contract.

    def test_stale_pack_inventory_requires_exact_zero_effect_and_complete_discovery(self):
        # A complete zero-effect inventory is the ONLY receipt that qualifies.
        # applied=1 is not applied=False, and 0.0/False/'0' are not exact-int
        # zeros. The exit code is never part of this contract.
        base = self._zero_effect_inventory()
        self.assertTrue(self.sweep._stale_pack_inventory_complete(json.dumps(base)))
        bad_cases = [
            ('applied_true', {**base, 'applied': True}),
            ('applied_int_zero', {**base, 'applied': 0}),
            ('applied_float', {**base, 'applied': 0.0}),
            ('applied_string', {**base, 'applied': 'false'}),
            ('applied_null', {**base, 'applied': None}),
            ('applied_missing', {k: v for k, v in base.items() if k != 'applied'}),
            ('removed_positive', {**base, 'removed': 1}),
            ('removed_float', {**base, 'removed': 0.0}),
            ('removed_bool', {**base, 'removed': False}),
            ('removed_string', {**base, 'removed': '0'}),
            ('removed_missing', {k: v for k, v in base.items() if k != 'removed'}),
            ('freed_positive', {**base, 'freed_bytes': 1}),
            ('freed_float', {**base, 'freed_bytes': 0.0}),
            ('freed_bool', {**base, 'freed_bytes': True}),
            ('freed_string', {**base, 'freed_bytes': '0'}),
            ('freed_missing', {k: v for k, v in base.items() if k != 'freed_bytes'}),
            ('census_incomplete',
             {**base, 'scratch_discovery': {'complete': False, 'errors': []}}),
            ('census_errors',
             {**base, 'scratch_discovery': {'complete': True, 'errors': ['denied']}}),
            ('census_missing', {k: v for k, v in base.items() if k != 'scratch_discovery'}),
            ('census_not_dict', {**base, 'scratch_discovery': 'complete'}),
        ]
        for label, bad in bad_cases:
            with self.subTest(case=label):
                self.assertFalse(
                    self.sweep._stale_pack_inventory_complete(json.dumps(bad)))
        for raw in ('', '   ', 'not json', '[]', '5', 'null', '{"status":"ok"}'):
            with self.subTest(raw=raw):
                self.assertFalse(self.sweep._stale_pack_inventory_complete(raw))

    def test_stale_packs_inventory_complete_is_explicit_and_exact(self):
        # The receipt carries an EXPLICIT inventory verdict. It is true only
        # for an exact-int rc 0 with a present stdout that satisfies the
        # inventory contract.
        complete = json.dumps(self._zero_effect_inventory())
        cases = [
            (0, complete, True),
            (0, '', False),
            (0, '   ', False),
            (0, None, False),
            ('0', complete, False),
            (0.0, complete, False),
            (False, complete, False),
            (2, complete, False),
            (124, complete, False),
            (0, json.dumps(self._zero_effect_inventory(applied=True)), False),
            (0, json.dumps(self._zero_effect_inventory(removed=1)), False),
        ]
        for rc, raw, expected in cases:
            with self.subTest(rc=rc, raw=raw), self._disposable_state(), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.sweep.finish({'mode': 'calm', 'stale_packs_rc': rc,
                                   'stale_packs': raw})
                receipt = json.loads(output.getvalue())
            self.assertIs(receipt['stale_packs_inventory_complete'], expected)

    def test_missing_and_invalid_stale_pack_receipts_stay_degraded(self):
        # Missing or blank stdout is an unverified receipt; an invalid but
        # present rc-0 receipt is an unverified INVENTORY; a failed rc keeps
        # the existing failure semantics. None of them is green.
        invalid = json.dumps(self._zero_effect_inventory(removed=2))
        cases = [
            (0, '', ['stale_packs.receipt_unverified']),
            (0, None, ['stale_packs.receipt_unverified']),
            (0, invalid, ['stale_packs.inventory_unverified']),
            (2, '{"status":"ok"}', ['stale_packs']),
        ]
        for rc, raw, expected in cases:
            with self.subTest(rc=rc, raw=raw), self._disposable_state(), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                status = self.sweep.finish({'mode': 'calm', 'stale_packs_rc': rc,
                                            'stale_packs': raw})
                receipt = json.loads(output.getvalue())
            self.assertEqual(status, 1)
            self.assertTrue(receipt['degraded'])
            for step in expected:
                self.assertIn(step, receipt['incomplete_substeps'])
            self.assertIs(receipt['stale_packs_inventory_complete'], False)

    # -- B: effect truth.

    def test_stale_pack_adverse_receipt_is_effect_unknown_not_not_applied(self):
        # The allowlisted argv proves the REQUEST was never-apply; it does not
        # prove the helper honoured it. A contradictory receipt is retained
        # verbatim, reported as EFFECT_UNKNOWN, and verifies no reclaimed
        # bytes. It is never softened back to NOT_APPLIED.
        adverse = [
            ('applied_true', self._zero_effect_inventory(applied=True)),
            ('removed_positive', self._zero_effect_inventory(removed=3)),
            ('freed_positive', self._zero_effect_inventory(freed_bytes=4096)),
            ('applied_int_one', self._zero_effect_inventory(applied=1)),
            ('applied_int_zero', self._zero_effect_inventory(applied=0)),
            ('applied_string', self._zero_effect_inventory(applied='false')),
            ('applied_null', self._zero_effect_inventory(applied=None)),
            ('removed_float', self._zero_effect_inventory(removed=0.0)),
            ('removed_bool', self._zero_effect_inventory(removed=False)),
            ('freed_string', self._zero_effect_inventory(freed_bytes='0')),
            ('freed_negative', self._zero_effect_inventory(freed_bytes=-1)),
        ]
        for label, receipt in adverse:
            with self.subTest(case=label):
                raw = json.dumps(receipt)
                verdict = self.sweep._stale_pack_retained_verdict(raw, 0)
                self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')
                self.assertNotEqual(verdict['state'], 'NOT_APPLIED')
                self.assertEqual(verdict['verified_reclaimed_bytes'], 0)
                # The contradictory raw receipt is retained verbatim.
                self.assertEqual(verdict['raw_receipt'], raw)
                self.assertTrue(verdict['signals'])
                # The same receipt, reconciled into a sweep receipt, degrades
                # the sweep and verifies no reclaimed bytes.
                with self._disposable_state(), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    status = self.sweep.finish({'mode': 'calm',
                                                'stale_packs_rc': 0,
                                                'stale_packs': raw})
                    out_receipt = json.loads(output.getvalue())
                self.assertEqual(status, 1)
                self.assertTrue(out_receipt['degraded'])
                self.assertEqual(out_receipt['stale_packs_effect_state'],
                                 'EFFECT_UNKNOWN')
                self.assertEqual(out_receipt['stale_packs_verified_reclaimed_bytes'],
                                 0)
                report = out_receipt['stale_packs_effect_report']
                self.assertEqual(report['state'], 'EFFECT_UNKNOWN')
                self.assertTrue(report['signals'])
                self.assertEqual(report['raw_receipt'], raw)
                self.assertEqual(report['verified_reclaimed_bytes'], 0)
                self.assertIn('stale_packs.unexpected_effect',
                              out_receipt['incomplete_substeps'])
                # No retry and no compensation: nothing is dispatched at all.
                run = self._run_sweep_spawning_children(self.sweep)
                self.assertEqual(run['spawned'], [], run['spawned'])

    def test_normal_zero_effect_inventory_stays_held_inventory_only(self):
        # A complete zero-effect receipt is a PRODUCER CLAIM that the
        # never-apply request was honoured. It is not proof of an enrolled
        # implementation: the hold stays, the sweep stays degraded, and no
        # apply capability is armed.
        raw = json.dumps(self._zero_effect_inventory())
        verdict = self.sweep._stale_pack_retained_verdict(raw, 0)
        self.assertEqual(verdict['state'], 'NOT_APPLIED')
        self.assertEqual(verdict['kind'], 'zero_effect_producer_claim')
        self.assertIs(verdict['inventory_claim'], True)
        self.assertEqual(verdict['verified_reclaimed_bytes'], 0)
        # The inventory predicate still qualifies it -- and only it.
        self.assertTrue(self.sweep._stale_pack_inventory_complete(raw))
        with self._disposable_state(), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            status = self.sweep.finish({
                'mode': 'calm',
                'stale_packs_rc': 0,
                'stale_packs': raw,
                'stale_packs_hold': 'HELD_UNQUALIFIED_STALE_PACK_HELPER',
            })
            out_receipt = json.loads(output.getvalue())
        self.assertEqual(out_receipt['stale_packs_effect_state'], 'NOT_APPLIED')
        self.assertIs(out_receipt['stale_packs_inventory_complete'], True)
        self.assertEqual(out_receipt['stale_packs_verified_reclaimed_bytes'], 0)
        self.assertEqual(out_receipt['stale_packs_hold'],
                         'HELD_UNQUALIFIED_STALE_PACK_HELPER')
        self.assertIn('stale_packs.held_unqualified_helper',
                      out_receipt['incomplete_substeps'])
        self.assertNotIn('stale_packs.unexpected_effect',
                         out_receipt['incomplete_substeps'])
        self.assertTrue(out_receipt['degraded'])
        self.assertNotEqual(status, 0)
        # The live pass holds regardless: no helper is dispatched, so the
        # sweep's independent telemetry survives and its deletion capability
        # does not.
        run = self._run_sweep_spawning_children(self.sweep)
        self.assertEqual(run['spawned'], [], run['spawned'])
        self.assertEqual(run['receipt']['stale_packs_hold'],
                         'HELD_UNQUALIFIED_STALE_PACK_HELPER')
        self.assertEqual(run['receipt']['stale_packs_effect_state'], 'NOT_APPLIED')
        self.assertTrue(run['receipt']['degraded'])
        self.assertNotEqual(run['status'], 0)

    # -- C: the pre-effect holds.

    def test_seven_unqualified_apply_helpers_never_spawn(self):
        # The real coordinator, with the PROCESS launcher captured. On the
        # applicable paths none of the seven held helpers is ever spawned,
        # and every one of them is receipted as a held pass.
        held = {
            'hung': 'hung_process_reaper.py',
            'temp_gc': 'temp_worktree_gc.py',
            'temp_gc_generic': 'temp_worktree_gc.py',
            'reap': 'reap_incomplete_temp_worktrees.py',
            'sparse': 'sparse_idle_worktrees.py',
            'scratch_reap': 'scratch_reap.py',
            'chain_archive': 'chain_snapshot_archive.py',
        }
        run = self._run_sweep_spawning_children(self.sweep, make_chain=True)
        receipt = run['receipt']
        for key, helper in held.items():
            with self.subTest(helper=key):
                self.assertFalse(
                    any(helper in token for argv in run['spawned'] for token in argv),
                    helper + ' must not be spawned')
                self.assertEqual(receipt[key + '_rc'], 78)
                self.assertEqual(receipt[key + '_effect_state'], 'NOT_APPLIED')
                self.assertIn('PRE_EFFECT_HOLD', receipt[key])
                self.assertIn(key, receipt['incomplete_substeps'])
                self.assertIn(key + '.held_unqualified_helper',
                              receipt['incomplete_substeps'])
        # No child runs at all. The stale-pack helper is held before any
        # helper subprocess too, so it is no longer the one remaining child.
        self.assertEqual(run['spawned'], [], run['spawned'])
        self.assertTrue(receipt['degraded'])
        self.assertNotEqual(run['status'], 0)
        # The unused removable-volume receipt probe is never prepared.
        self.assertEqual(run['ssd_calls'], [])
        # A hold is an abstention: the chain archive success stamp is never
        # advanced by a pass that never ran.
        self.assertFalse(run['chain_stamp'])

    def test_held_apply_passes_cannot_be_rearmed_by_success_shaped_receipts(self):
        # Pure finish() classification: a zero exit code and a plausible
        # stdout injected after the fact cannot rearm a held pass.
        held = ('hung', 'temp_gc', 'temp_gc_generic', 'reap', 'sparse',
                'scratch_reap', 'chain_archive')
        with self._disposable_state(), contextlib.redirect_stdout(io.StringIO()) as output:
            status = self.sweep.finish({
                'mode': 'calm',
                **{key + '_rc': 0 for key in held},
                **{key: '{"status":"ok"}' for key in held},
                **{key + '_effect_state': 'NOT_APPLIED' for key in held},
            })
            receipt = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertTrue(receipt['degraded'])
        for key in held:
            with self.subTest(helper=key):
                self.assertIn(key + '.held_unqualified_helper',
                              receipt['incomplete_substeps'])

    def test_conditional_holds_stay_conditional(self):
        # The applicability conditions of the incumbent sweep are preserved:
        # a calm host with headroom defers the sparse census and the repack,
        # so those two passes are neither held nor launched there.
        run = self._run_sweep_spawning_children(self.sweep, free_gib=300.0)
        receipt = run['receipt']
        self.assertNotIn('sparse_rc', receipt)
        self.assertNotIn('fleet_sparse_rc', receipt)
        self.assertNotIn('repack_rc', receipt)
        # The always-eligible holds are still recorded.
        for key in ('hung', 'temp_gc', 'temp_gc_generic', 'reap', 'scratch_reap'):
            with self.subTest(helper=key):
                self.assertEqual(receipt[key + '_rc'], 78)
        self.assertFalse(any(
            'sparse_idle_worktrees.py' in token
            for argv in run['spawned'] for token in argv))
        self.assertFalse(any(
            'fleet_repack.py' in token
            for argv in run['spawned'] for token in argv))

    def test_hung_pass_is_held_before_the_grant_gate(self):
        # The process reaper is held BEFORE the grant gate, so a host without
        # file grants still names the hold instead of an applied pass, and no
        # reaper is spawned on either path.
        run = self._run_sweep_spawning_children(self.sweep,
                                                grants_result='denied')
        receipt = run['receipt']
        self.assertEqual(receipt['hung_rc'], 78)
        self.assertEqual(receipt['hung_effect_state'], 'NOT_APPLIED')
        self.assertIn('hung', receipt['incomplete_substeps'])
        self.assertFalse(any(
            'hung_process_reaper.py' in token
            for argv in run['spawned'] for token in argv))
        self.assertTrue(receipt['degraded'])
        self.assertNotEqual(run['status'], 0)
        self.assertEqual(run['ssd_calls'], [])

    # -- S5 corrections: the pre-dispatch hold, the delegation hold, and the
    #    strict retrospective classification of retained receipts.

    def _run_two_passes_sharing_state(self, sweep_module,
                                      grants_results=('ok', 'denied')):
        """Two ordinary main() passes over ONE state directory.

        subprocess.run itself is captured, so `spawned` is every argv the
        coordinator would have handed to a child PROCESS. A loopback key
        EXISTS, so the delegation would really proceed if it were not held.
        No helper, host, network or native file is touched.
        """
        spawned = []
        ssd_calls = []

        def fake_run(argv, *args, **kwargs):
            spawned.append([str(token) for token in argv])
            return mock.Mock(returncode=0, stdout='{"status":"ok"}', stderr='')

        def fake_ssd_receipts(sub):
            ssd_calls.append(sub)
            return ['--receipts', str(sweep_module.STATE / 'never')]

        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            (state / 'flow-ops-wt' / 'data' / 'chain_snapshots').mkdir(
                parents=True)
            (state / 'id_mm_loopback').write_text('fixture')
            receipts = []
            statuses = []
            for grants_result in grants_results:
                usage = mock.Mock(free=180 * sweep_module.GIB,
                                  total=460 * sweep_module.GIB)
                with mock.patch.object(sweep_module, 'STATE', state), (
                    mock.patch.object(sweep_module, 'LOCK', state / 'sweep.lock')
                ), mock.patch.object(sweep_module, 'ssd_receipts',
                                     side_effect=fake_ssd_receipts), (
                    mock.patch.object(sweep_module, 'grants',
                                      return_value=grants_result)
                ), mock.patch.object(sweep_module, 'LOOPBACK_KEY',
                                     state / 'id_mm_loopback'), (
                    mock.patch.object(sweep_module, '_pool_archive_mount',
                                      return_value=None)
                ), mock.patch.object(sweep_module, 'floor_for_host',
                                     return_value=200.0), (
                    mock.patch.object(sweep_module.shutil, 'disk_usage',
                                      return_value=usage)
                ), mock.patch.object(sweep_module, '_external_volume_snapshots',
                                     return_value=[]), (
                    mock.patch.object(sweep_module.Path, 'home',
                                      return_value=state)
                ), mock.patch.object(sweep_module.os, 'uname',
                                     return_value=mock.Mock(nodename="m2studio.local")), (
                    mock.patch.object(sweep_module.subprocess, 'run',
                                      side_effect=fake_run)
                ), contextlib.redirect_stdout(io.StringIO()) as output:
                    statuses.append(sweep_module.main())
                receipts.append(json.loads(output.getvalue()))
            created = sorted(path.name for path in state.iterdir())
            log = (state / 'sweep-log.jsonl').read_text()
            chain_stamp = (state / 'chain-archive.last').exists()
        return {'statuses': statuses, 'receipts': receipts, 'spawned': spawned,
                'ssd_calls': ssd_calls, 'created': created, 'log': log,
                'chain_stamp': chain_stamp}

    def test_two_natural_passes_sharing_one_state_never_dispatch_a_helper(self):
        # Two ordinary main() passes over the SAME state directory: a granted
        # pass and a denied-grant pass. The proof is at the PROCESS boundary,
        # not a mock of the guarded helper: subprocess.run itself is
        # captured, so every argv the coordinator would have handed to a child
        # is visible. A mocked helper could not prove this.
        run = self._run_two_passes_sharing_state(self.sweep)
        self.assertEqual(len(run['receipts']), 2)
        self.assertEqual(run['spawned'], [], run['spawned'])
        # Neither the stale-pack helper nor any held helper appears in a
        # child argv, and no ssh is ever started.
        for name in ('stale_pack_reaper.py', 'hung_process_reaper.py',
                     'temp_worktree_gc.py', 'reap_incomplete_temp_worktrees.py',
                     'sparse_idle_worktrees.py', 'scratch_reap.py',
                     'chain_snapshot_archive.py'):
            with self.subTest(helper=name):
                self.assertFalse(any(
                    name in token for argv in run['spawned'] for token in argv))
        self.assertFalse(any(
            argv and argv[0] == 'ssh' for argv in run['spawned']))
        # The independent telemetry survives both passes: two sweep-log rows.
        # The append-only JSONL is the owner of the retained evidence, and it
        # is read DIRECTLY here -- no history reader function is mocked.
        rows = [json.loads(item) for item in run['log'].strip().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertIn('sweep-log.jsonl', run['created'])
        granted_row, denied_row = rows
        # The granted pass records its OWN pre-dispatch hold, and claims
        # nothing about any other row.
        self.assertEqual(granted_row['stale_packs_rc'], 78)
        self.assertEqual(granted_row['stale_packs_hold'],
                         'HELD_UNQUALIFIED_STALE_PACK_HELPER')
        self.assertEqual(granted_row['stale_packs_effect_state'], 'NOT_APPLIED')
        self.assertEqual(granted_row['stale_packs_effect_report']['kind'],
                         'runtime_pre_dispatch_hold')
        self.assertIs(granted_row['stale_packs_inventory_complete'], False)
        self.assertEqual(granted_row['stale_packs_verified_reclaimed_bytes'], 0)
        # The denied pass never reached the stale-pack pass at all: it holds
        # the delegation instead, and records no stale-pack evidence.
        self.assertNotIn('stale_packs', denied_row)
        self.assertNotIn('stale_packs_rc', denied_row)
        self.assertEqual(denied_row['loopback_rc'], 78)
        for row in rows:
            # Neither row claims that any prior unknown was reconciled.
            self.assertNotIn('stale_packs_reconciled', row)
            self.assertNotIn('stale_packs_resolved', row)
        # The unused removable-volume receipt probe is never prepared.
        self.assertEqual(run['ssd_calls'], [])
        # A hold is an abstention: the chain archive success stamp is never
        # advanced by a pass that never ran.
        self.assertFalse(run['chain_stamp'])
        granted, denied = run['receipts']
        self.assertNotEqual(run['statuses'][0], 0)
        self.assertNotEqual(run['statuses'][1], 0)
        self.assertTrue(granted['degraded'])
        self.assertTrue(denied['degraded'])
        # The granted pass names the stale-pack hold and every direct hold.
        self.assertEqual(granted['stale_packs_hold'],
                         'HELD_UNQUALIFIED_STALE_PACK_HELPER')
        self.assertEqual(granted['stale_packs_effect_state'], 'NOT_APPLIED')
        self.assertEqual(granted['stale_packs_verified_reclaimed_bytes'], 0)
        for key in ('hung', 'temp_gc', 'temp_gc_generic', 'reap',
                    'scratch_reap', 'chain_archive'):
            with self.subTest(held=key):
                self.assertEqual(granted[key + '_rc'], 78)
                self.assertEqual(granted[key + '_effect_state'], 'NOT_APPLIED')
                self.assertIn(key + '.held_unqualified_helper',
                              granted['incomplete_substeps'])
        # The denied-grant pass names the delegation hold.
        self.assertEqual(denied['loopback_hold'],
                         'HELD_UNBOUND_LOOPBACK_CHILD_SOURCE')
        self.assertEqual(denied['loopback_effect_state'], 'NOT_APPLIED')
        self.assertIn('loopback.held_unqualified_child_source',
                      denied['incomplete_substeps'])
        self.assertIn('grant_requiring_passes', denied['incomplete_substeps'])

    def test_denied_grant_delegation_is_held_before_any_forced_child(self):
        # The delegation is held BEFORE any ssh. The proof is at the process
        # boundary: subprocess.run is captured and a loopback key EXISTS, so
        # the delegation would really proceed if it were not held.
        run = self._run_two_passes_sharing_state(self.sweep,
                                                  grants_results=('denied',))
        receipt = run['receipts'][0]
        self.assertEqual(run['spawned'], [], run['spawned'])
        self.assertFalse(any(
            argv and argv[0] == 'ssh' for argv in run['spawned']))
        self.assertEqual(receipt['loopback_hold'],
                         'HELD_UNBOUND_LOOPBACK_CHILD_SOURCE')
        self.assertEqual(receipt['loopback_effect_state'], 'NOT_APPLIED')
        self.assertEqual(receipt['loopback_rc'], 78)
        self.assertIn('loopback.held_unqualified_child_source',
                      receipt['incomplete_substeps'])
        self.assertTrue(receipt['degraded'])
        self.assertNotEqual(run['statuses'][0], 0)
        # No qualification flag was invented to carry the hold: the only
        # loopback constants are the pre-existing key path and the hold
        # marker itself. The delegation is held by control flow, not by a
        # boolean that could be flipped.
        self.assertEqual(
            sorted(name for name in dir(self.sweep)
                   if name.isupper() and name.startswith('LOOPBACK_')),
            ['LOOPBACK_HOLD', 'LOOPBACK_KEY'])

    def test_false_live_transfer_claim_is_corrected_in_the_source(self):
        # The stale-pack pass comment used to claim that the helper "refuses
        # any file a process still holds open, so a live transfer is never
        # interrupted". That claim is false: stat+lsof is a PATH check, not an
        # owner/inode binding, so a writer that replaces the pathname in
        # between can still be hit. The source must not carry the claim.
        import inspect
        source = inspect.getsource(self.sweep)
        self.assertNotIn('live transfer is never interrupted', source)
        self.assertIn('owner/inode binding', source)

    def test_sparse_hold_rationale_is_a_missing_qualification(self):
        # The hold on the sparse_idle_worktrees.py producer states a MISSING
        # QUALIFICATION. It does not assert an unproven internal defect of the
        # held helper. The pre-existing B10 fleet_sparse hold is a DIFFERENT
        # helper and keeps its own original rationale.
        import inspect
        source = inspect.getsource(self.sweep.main)
        marker = "hold_unqualified_apply(out, 'sparse')"
        index = source.index(marker)
        rationale = source[max(0, index - 900):index]
        self.assertNotIn('lacks complete', rationale)
        self.assertNotIn('conversion-attempt receipts', rationale)
        self.assertIn('source/preimage-qualified for apply', rationale)
        self.assertIn('not a proven internal defect of the', rationale)

    def test_runtime_pre_dispatch_hold_is_not_an_unknown_effect(self):
        # The coordinator's own pre-dispatch refusal is a KNOWN non-dispatch,
        # not an unknown effect. The reconciler recognises it exactly.
        out = {}
        self.sweep.stale_pack_discovery_pass(out, 'stale_packs')
        self.assertEqual(out['stale_packs_hold'], self.sweep.STALE_PACK_HOLD)
        self.assertEqual(out['stale_packs_rc'], 78)
        self.assertEqual(out['stale_packs_effect_state'], 'NOT_APPLIED')
        self.assertEqual(out['stale_packs_verified_reclaimed_bytes'], 0)
        self.assertEqual(out['stale_packs'], self.sweep.STALE_PACK_HOLD_REFUSAL)
        self.assertIn('this invocation only',
                      out['stale_packs_effect_report']['scope'])
        self.sweep._record_stale_pack_receipt_truth(out, 'stale_packs')
        self.assertEqual(out['stale_packs_effect_state'], 'NOT_APPLIED')
        self.assertEqual(out['stale_packs_effect_report']['kind'],
                         'runtime_pre_dispatch_hold')
        self.assertIs(out['stale_packs_inventory_complete'], False)
        # Anything that is NOT the exact refusal is classified strictly, so a
        # receipt that merely resembles the refusal cannot hide an effect.
        lookalike = self.sweep.STALE_PACK_HOLD_REFUSAL + ' applied=true'
        verdict = self.sweep._stale_pack_retained_verdict(lookalike, 0)
        self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')

    def test_missing_null_and_non_int_rc_cannot_carry_a_zero_effect_claim(self):
        # A completed producer claim needs an EXACT int rc of 0. A missing or
        # null rc, and an rc that is a bool, a float or a string, are not exit
        # codes: they are missing evidence, so the receipt stays
        # EFFECT_UNKNOWN even when its effect fields read as zero.
        raw = json.dumps(self._zero_effect_inventory())
        for label, rc in (('null', None), ('true', True), ('false', False),
                          ('float', 0.0), ('string', '0'), ('nonzero', 1),
                          ('timeout', 124)):
            with self.subTest(rc=label):
                verdict = self.sweep._stale_pack_retained_verdict(raw, rc)
                self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')
                self.assertNotEqual(verdict['state'], 'NOT_APPLIED')
                self.assertIs(verdict['inventory_claim'], False)
                self.assertEqual(verdict['verified_reclaimed_bytes'], 0)
                self.assertEqual(verdict['raw_receipt'], raw)
        # The omitted rc is the same case: the classifier's own default is
        # missing evidence, not a completed dispatch.
        verdict = self.sweep._stale_pack_retained_verdict(raw)
        self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')
        self.assertEqual(verdict['kind'], 'evidence_missing')
        # The sweep records the same truth: an unknown effect degrades the
        # pass and is never softened into NOT_APPLIED.
        for label, rc in (('null', None), ('true', True), ('float', 0.0)):
            with self.subTest(rc=label):
                out = {'stale_packs': raw, 'stale_packs_rc': rc}
                self.sweep._record_stale_pack_receipt_truth(out, 'stale_packs')
                self.assertEqual(out['stale_packs_effect_state'],
                                 'EFFECT_UNKNOWN')
                self.assertIs(out['stale_packs_inventory_complete'], False)
                self.assertEqual(out['stale_packs_verified_reclaimed_bytes'], 0)

    def test_incomplete_discovery_is_not_a_complete_inventory_claim(self):
        # applied=false with exact int zero counters is a zero-effect
        # PRODUCER CLAIM. It is a COMPLETE INVENTORY only when the retained
        # discovery census is complete and error-free.
        complete = json.dumps(self._zero_effect_inventory())
        verdict = self.sweep._stale_pack_retained_verdict(complete, 0)
        self.assertEqual(verdict['state'], 'NOT_APPLIED')
        self.assertEqual(verdict['kind'], 'zero_effect_producer_claim')
        self.assertIs(verdict['inventory_claim'], True)
        # A census that did not bind what it claims to have inventoried stays
        # incomplete: it reports complete=false, it carries a binding error,
        # or it never asserts a binding at all.
        for label, census in (
                ('incomplete', {'complete': False, 'errors': []}),
                ('binding_error', {'complete': False, 'errors': [
                    '/private/tmp: find rc=1: Permission denied']}),
                ('no_binding_asserted', {'errors': []}),
                ('errors_present', {'complete': True, 'errors': ['denied']}),
                ('not_a_dict', 'complete')):
            with self.subTest(census=label):
                raw = json.dumps({**self._zero_effect_inventory(),
                                  'scratch_discovery': census})
                verdict = self.sweep._stale_pack_retained_verdict(raw, 0)
                self.assertEqual(verdict['state'], 'NOT_APPLIED')
                self.assertEqual(verdict['kind'],
                                 'zero_effect_producer_claim')
                self.assertIs(verdict['inventory_claim'], False)
                self.assertIn('no complete inventory is claimed',
                              verdict['reason'])
                self.assertIn('producer claim', verdict['reason'])
        # An omitted census is the same case.
        raw = json.dumps({k: v for k, v in self._zero_effect_inventory().items()
                          if k != 'scratch_discovery'})
        verdict = self.sweep._stale_pack_retained_verdict(raw, 0)
        self.assertEqual(verdict['state'], 'NOT_APPLIED')
        self.assertIs(verdict['inventory_claim'], False)
        # The reason never claims a complete inventory when it is unproven.
        self.assertNotIn('complete zero-effect inventory', verdict['reason'])
        # The sweep keeps the two dimensions apart: the inventory verdict is
        # incomplete while the zero-effect producer claim stands.
        with self._disposable_state(), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            status = self.sweep.finish({
                'mode': 'calm',
                'stale_packs_rc': 0,
                'stale_packs': json.dumps(self._zero_effect_inventory(
                    scratch_discovery={'complete': False, 'errors': []})),
            })
            out_receipt = json.loads(output.getvalue())
        self.assertEqual(out_receipt['stale_packs_effect_state'], 'NOT_APPLIED')
        self.assertIs(out_receipt['stale_packs_inventory_complete'], False)
        self.assertIn('stale_packs.inventory_unverified',
                      out_receipt['incomplete_substeps'])
        self.assertNotEqual(status, 0)

    def test_refusal_text_alone_cannot_prove_a_coordinator_no_dispatch(self):
        # The refusal TEXT is a plain string, so a retained receipt, a copied
        # row or an injected value can carry it verbatim. The provenance of a
        # coordinator no-dispatch is the structured hold metadata the current
        # stale-pack pass emits, together with the incumbent refusal rc 78.
        refusal = self.sweep.STALE_PACK_HOLD_REFUSAL
        # The exact text, rc 78 and the incumbent hold marker: everything the
        # coordinator's own refusal carries EXCEPT its structured report.
        held = {
            'stale_packs': refusal,
            'stale_packs_rc': 78,
            'stale_packs_hold': self.sweep.STALE_PACK_HOLD,
        }
        lookalikes = (
            # The exact text, but the dispatch did not exit 78.
            {'stale_packs': refusal, 'stale_packs_rc': 0},
            # The exact text, but no exit code was retained at all.
            {'stale_packs': refusal},
            # The exact text and rc 78, but no structured hold metadata.
            {'stale_packs': refusal, 'stale_packs_rc': 78},
            # The exact text, rc 78 and a hold marker, but a report that
            # says something else.
            {'stale_packs': refusal, 'stale_packs_rc': 78,
             'stale_packs_hold': self.sweep.STALE_PACK_HOLD,
             'stale_packs_effect_report': {'kind': 'contradiction'}},
            # The exact text, rc 78 and the hold marker, but NO report at
            # all. The current producer emits the complete report before any
            # argv work, so an ABSENT report is absent provenance, not a
            # proven no-dispatch.
            dict(held),
            # The same, with a NULL report.
            {**held, 'stale_packs_effect_report': None},
            # A bare STRING that names the kind is not the producer's
            # structured report.
            {**held, 'stale_packs_effect_report': 'runtime_pre_dispatch_hold'},
            # Nor is a LIST that names the kind.
            {**held,
             'stale_packs_effect_report': ['runtime_pre_dispatch_hold']},
            # Nor is a BOOLEAN: it is not a report at all.
            {**held, 'stale_packs_effect_report': True},
            # Nor is a dictionary that names a different kind.
            {**held,
             'stale_packs_effect_report': {
                 'kind': 'zero_effect_producer_claim'}},
        )
        for index, out in enumerate(lookalikes):
            with self.subTest(lookalike=index):
                self.sweep._record_stale_pack_receipt_truth(out, 'stale_packs')
                self.assertEqual(out['stale_packs_effect_state'],
                                 'EFFECT_UNKNOWN')
                self.assertNotEqual(out['stale_packs_effect_state'],
                                    'NOT_APPLIED')
                self.assertEqual(out['stale_packs_verified_reclaimed_bytes'], 0)
                # The exact source raw text is retained verbatim, and the
                # report that carries it states the unknown.
                report = out['stale_packs_effect_report']
                self.assertEqual(report['state'], 'EFFECT_UNKNOWN')
                self.assertEqual(report['raw_receipt'], refusal)
        # The GENUINE coordinator hold is still a known non-dispatch for THIS
        # invocation: the real pass emits the structured metadata itself.
        genuine = {}
        self.sweep.stale_pack_discovery_pass(genuine, 'stale_packs')
        self.assertEqual(genuine['stale_packs'], refusal)
        self.assertEqual(genuine['stale_packs_rc'], 78)
        self.assertEqual(genuine['stale_packs_hold'],
                         self.sweep.STALE_PACK_HOLD)
        # The producer's own report IS the provenance, and it is retained
        # EXACTLY: the classifier does not replace it with a synthesized one.
        produced = genuine['stale_packs_effect_report']
        self.assertEqual(produced['kind'], 'runtime_pre_dispatch_hold')
        self.sweep._record_stale_pack_receipt_truth(genuine, 'stale_packs')
        self.assertIs(genuine['stale_packs_effect_report'], produced)
        self.assertEqual(genuine['stale_packs_effect_state'], 'NOT_APPLIED')
        self.assertEqual(genuine['stale_packs_effect_report']['kind'],
                         'runtime_pre_dispatch_hold')
        self.assertIs(genuine['stale_packs_inventory_complete'], False)
        self.assertEqual(genuine['stale_packs_verified_reclaimed_bytes'], 0)
        # A PRIOR unknown classification is not downgraded by this
        # invocation's own hold: the unknown state stays unknown.
        prior = {}
        self.sweep.stale_pack_discovery_pass(prior, 'stale_packs')
        prior['stale_packs_effect_state'] = 'EFFECT_UNKNOWN'
        self.sweep._record_stale_pack_receipt_truth(prior, 'stale_packs')
        self.assertEqual(prior['stale_packs_effect_state'], 'EFFECT_UNKNOWN')

    def test_retained_receipt_cases_are_classified_truthfully(self):
        # Pure classification of RETAINED receipts. Nothing is spawned, no
        # file is written, and no history is rewritten.
        # 1. A complete exact zero-effect receipt is a PRODUCER CLAIM.
        complete = json.dumps(self._zero_effect_inventory())
        verdict = self.sweep._stale_pack_retained_verdict(complete, 0)
        self.assertEqual(verdict['state'], 'NOT_APPLIED')
        self.assertEqual(verdict['kind'], 'zero_effect_producer_claim')
        self.assertIs(verdict['inventory_claim'], True)
        self.assertEqual(verdict['verified_reclaimed_bytes'], 0)
        # 2. A contradiction is EFFECT_UNKNOWN and its raw text is retained.
        adverse = json.dumps(self._zero_effect_inventory(applied=True))
        verdict = self.sweep._stale_pack_retained_verdict(adverse, 0)
        self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')
        self.assertEqual(verdict['kind'], 'contradiction')
        self.assertTrue(verdict['signals'])
        self.assertEqual(verdict['raw_receipt'], adverse)
        # 3. An OMITTED effect field is missing evidence, not evidence of no
        #    effect. This is the correction: it used to leave NOT_APPLIED.
        for omitted in ('applied', 'removed', 'freed_bytes'):
            raw = json.dumps({k: v for k, v in self._zero_effect_inventory().items()
                              if k != omitted})
            with self.subTest(omitted=omitted):
                verdict = self.sweep._stale_pack_retained_verdict(raw, 0)
                self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')
                self.assertEqual(verdict['kind'], 'evidence_missing')
                self.assertIn('omitted:' + omitted, verdict['signals'])
        # 4. A MALFORMED receipt that shows a positive deletion keeps its raw
        #    text and is never read as a complete zero.
        malformed = '{"applied": true, "removed": 12, "freed_bytes": 4096'
        verdict = self.sweep._stale_pack_retained_verdict(malformed, 0)
        self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')
        self.assertEqual(verdict['kind'], 'unparsable')
        self.assertEqual(verdict['raw_receipt'], malformed)
        # 5. CAPTURE LOSS: a receipt longer than the capture limit is retained
        #    truncated, and the truncated text is lost evidence.
        long_receipt = json.dumps({**self._zero_effect_inventory(),
                                   'note': 'x' * 2500})
        self.assertGreater(len(long_receipt), self.sweep.STALE_PACK_CAPTURE_LIMIT)
        truncated = long_receipt[:self.sweep.STALE_PACK_CAPTURE_LIMIT]
        verdict = self.sweep._stale_pack_retained_verdict(truncated, 0)
        self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')
        self.assertEqual(verdict['kind'], 'unparsable')
        self.assertEqual(verdict['receipt_scope'], 'captured_excerpt')
        self.assertEqual(verdict['capture_limit'],
                         self.sweep.STALE_PACK_CAPTURE_LIMIT)
        # Only the CAPTURE lost the evidence: the full text is a complete
        # zero-effect receipt.
        self.assertEqual(
            self.sweep._stale_pack_retained_verdict(long_receipt, 0)['state'],
            'NOT_APPLIED')
        # 6. A TIMEOUT or a partial capture is interrupted evidence.
        for rc, raw in ((124, 'TIMEOUT after 1800s'),
                        (125, 'ERROR OSError: helper absent')):
            with self.subTest(rc=rc):
                verdict = self.sweep._stale_pack_retained_verdict(raw, rc)
                self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')
                self.assertEqual(verdict['kind'], 'interrupted')
        # A broken-JSON parser never proves NOT_APPLIED, whatever it is fed.
        for raw in ('', '   ', 'not json', '[]', '5', 'null',
                    '{"status":"ok"}', '{"removed": 0'):
            with self.subTest(raw=raw):
                verdict = self.sweep._stale_pack_retained_verdict(raw, 0)
                self.assertEqual(verdict['state'], 'EFFECT_UNKNOWN')

    def test_unknown_classification_is_monotonic_against_a_later_zero(self):
        # An observation already classified unknown is not downgraded by a
        # later zero or blank value for the same key.
        out = {'stale_packs': json.dumps(self._zero_effect_inventory(applied=True)),
               'stale_packs_rc': 0}
        self.sweep._record_stale_pack_receipt_truth(out, 'stale_packs')
        self.assertEqual(out['stale_packs_effect_state'], 'EFFECT_UNKNOWN')
        self.assertEqual(out['stale_packs_effect_report']['kind'], 'contradiction')
        # A later, weaker reading of the same observation.
        out['stale_packs'] = json.dumps(self._zero_effect_inventory())
        self.sweep._record_stale_pack_receipt_truth(out, 'stale_packs')
        self.assertEqual(out['stale_packs_effect_state'], 'EFFECT_UNKNOWN')
        self.assertEqual(out['stale_packs_effect_report']['kind'],
                         'unknown_monotonic')
        # And a later blank value does not clear it either.
        out['stale_packs'] = ''
        self.sweep._record_stale_pack_receipt_truth(out, 'stale_packs')
        self.assertEqual(out['stale_packs_effect_state'], 'EFFECT_UNKNOWN')
        self.assertEqual(out['stale_packs_verified_reclaimed_bytes'], 0)

    def test_injected_earlier_unknown_row_is_preserved_and_never_reconciled(self):
        # An earlier sweep-log row that already carries an unknown effect is
        # APPEND-ONLY history. A later pass must not rewrite it, and nothing
        # may claim that it is reconciled or resolved.
        injected = {
            'time': 1000.0,
            'mode': 'calm',
            'grants': 'ok',
            'stale_packs_rc': 0,
            'stale_packs': json.dumps(self._zero_effect_inventory(applied=True)),
            'stale_packs_effect_state': 'EFFECT_UNKNOWN',
            'stale_packs_verified_reclaimed_bytes': 0,
        }
        line = json.dumps(injected, sort_keys=True)
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            log = state / 'sweep-log.jsonl'
            log.write_text(line + '\n')
            usage = mock.Mock(free=180 * self.sweep.GIB,
                              total=460 * self.sweep.GIB)
            patches = (
                mock.patch.object(self.sweep, 'STATE', state),
                mock.patch.object(self.sweep, 'LOCK', state / 'sweep.lock'),
                mock.patch.object(self.sweep, 'ssd_receipts', return_value=[]),
                mock.patch.object(self.sweep, 'grants', return_value='ok'),
                mock.patch.object(self.sweep, '_pool_archive_mount',
                                  return_value=None),
                mock.patch.object(self.sweep, 'floor_for_host', return_value=200.0),
                mock.patch.object(self.sweep.shutil, 'disk_usage',
                                  return_value=usage),
                mock.patch.object(self.sweep, '_external_volume_snapshots',
                                  return_value=[]),
                mock.patch.object(self.sweep.Path, 'home', return_value=state),
                mock.patch.object(self.sweep.os, 'uname',
                                  return_value=mock.Mock(nodename="m2studio.local")),
                mock.patch.object(self.sweep.subprocess, 'run',
                                  side_effect=AssertionError('no child may be spawned')),
            )
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                status = self.sweep.main()
                receipt = json.loads(output.getvalue())
            # The append-only log is the owner of history, and it is read
            # DIRECTLY here. No history reader function is mocked, so this
            # preservation proof cannot depend on one existing.
            after = log.read_text()
            rows = [json.loads(item) for item in after.splitlines()]
        self.assertNotEqual(status, 0)
        self.assertTrue(receipt['degraded'])
        # The earlier row is preserved byte for byte: the log is append-only.
        self.assertEqual(after.splitlines()[0], line)
        self.assertEqual(len(after.splitlines()), 2)
        # It is still reported as unknown, and nothing calls it reconciled.
        self.assertEqual(rows[0]['stale_packs_effect_state'], 'EFFECT_UNKNOWN')
        self.assertEqual(rows[0]['stale_packs_verified_reclaimed_bytes'], 0)
        # The earlier row keeps its own contradictory receipt verbatim: the
        # history is not rewritten, and it is not silently cleared either.
        self.assertEqual(rows[0]['stale_packs'], injected['stale_packs'])
        self.assertNotIn('stale_packs_reconciled', receipt)
        self.assertNotIn('stale_packs_resolved', receipt)
        # The new row records its own pre-dispatch hold, and makes no claim
        # about the earlier row.
        self.assertEqual(rows[1]['stale_packs_effect_state'], 'NOT_APPLIED')
        self.assertEqual(rows[1]['stale_packs_effect_report']['kind'],
                         'runtime_pre_dispatch_hold')
        self.assertEqual(rows[1]['stale_packs_verified_reclaimed_bytes'], 0)


if __name__ == "__main__":
    unittest.main()
