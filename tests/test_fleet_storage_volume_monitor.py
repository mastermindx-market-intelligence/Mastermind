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
        complete_scratch = json.dumps({
            "removed": 0, "bundled": 0, "skipped": 0, "partial": False,
            "deadline_s": 2700.0, "elapsed_s": 1,
            "swept_overcap_bundles": 0, "freed_gib": 0.0,
        })
        complete_stale = json.dumps({
            "applied": True, "removed": 0, "freed_bytes": 0,
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
                     ["stale_packs"], 1),
                    ({"stale_packs_rc": 0, "scratch_reap_rc": 0, "scratch_reap": complete_scratch,
                      "stale_packs": complete_stale}, [], 0),
                    ({"stale_packs_rc": 0, "scratch_reap_rc": 0, "scratch_reap": complete_scratch,
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


    def test_stale_pack_zero_exit_partial_discovery_is_degraded(self):
        # Real incumbent M1: exit 0, but find(1) denied /private/tmp subtree.
        receipt = {
            'applied': True, 'removed': 0, 'freed_bytes': 0,
            'scratch_discovery': {'complete': False, 'errors': [
                '/private/tmp: find rc=1: Permission denied']},
        }
        self.assertFalse(self.sweep._stale_pack_inventory_complete(json.dumps(receipt)))
        self.assertFalse(self.sweep._stale_pack_inventory_complete('not json'))
        self.assertTrue(self.sweep._stale_pack_inventory_complete(json.dumps(
            {**receipt, 'scratch_discovery': {'complete': True, 'errors': []}})))
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
            self.assertIn('sparse', executed, 'existing native sparse helper stays eligible')
            self.assertNotIn('fleet_sparse', executed)
            self.assertNotIn('repack', executed)
            self.assertEqual(status, 1)
            for key in ('fleet_sparse', 'repack'):
                with self.subTest(helper=key):
                    self.assertEqual(receipt[key + '_rc'], 78)
                    self.assertEqual(receipt[key + '_effect_state'], 'NOT_APPLIED')
                    self.assertIn(key, receipt['incomplete_substeps'])
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
