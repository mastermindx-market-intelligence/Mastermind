"""Hermetic existing-owner cache preview; never invoke a remote or real cache."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1] / "ops/fleet_storage_cleanup"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LinuxCachePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview = load("fixture_cache_preview", "linux_cache_preview.py")
        cls.fleet = load("fixture_cache_driver", "fleet_remote_sweep.py")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.home.chmod(0o700)
        self.active = self.home / "lanes/ext/active"
        self.active.mkdir(parents=True, mode=0o700)
        (self.active / ".admission.lock").touch(mode=0o600)
        self.cache = self.home / ".cache/pip"
        (self.cache / "http-v2/aa").mkdir(parents=True, mode=0o700)
        (self.cache / "http-v2/aa/object.body").write_bytes(b"regenerable cached fixture")
        self.uid = os.getuid()

    def run_preview(self, **kwargs):
        return self.preview.preview(home=self.home, uid=self.uid, platform="linux",
                                    live_reader=kwargs.pop("live_reader", lambda: set()), **kwargs)

    def pip(self, result):
        return next(r for r in result["caches"] if r["cache"] == "pip")

    def state_dir(self):
        path = self.home / ".local/state/mastermind/storage-cleanup"
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        return path

    def test_preview_counts_only_metadata_and_never_authorizes_or_deletes(self):
        before = (self.cache / "http-v2/aa/object.body").read_bytes()
        result = self.run_preview()
        self.assertEqual(result["status"], "PREVIEWED")
        self.assertTrue(result["preview_only"])
        self.assertFalse(result["cleanup_authorized"])
        self.assertEqual(self.pip(result)["logical_bytes"], len(before))
        self.assertEqual((self.cache / "http-v2/aa/object.body").read_bytes(), before)
        self.assertNotIn(str(self.home), json.dumps(result))
        self.assertFalse((self.home / ".local").exists())

    def test_same_existing_lock_is_nonblocking_and_never_replaced(self):
        path = self.active / ".admission.lock"
        before = path.stat().st_ino
        with path.open("r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_preview()
        self.assertEqual(result["reasons"], ["admission_busy"])
        self.assertEqual(before, path.stat().st_ino)

    def test_absent_admission_lock_never_created(self):
        (self.active / ".admission.lock").unlink()
        self.assertEqual(self.run_preview()["status"], "HELD")
        self.assertFalse((self.active / ".admission.lock").exists())

    def test_any_active_or_unknown_reconciliation_marker_holds(self):
        for name in ["worker", ".reconciliation", "unknown-marker"]:
            p = self.active / name
            p.write_text("original metadata")
            self.assertEqual(self.run_preview()["reasons"], ["active_lane_or_reconciliation_hold"])
            self.assertEqual(p.read_text(), "original metadata")
            p.unlink()

    def assert_admission_withheld(self, result):
        self.assertEqual(result["status"], "HELD")
        self.assertFalse(result["cleanup_authorized"])
        for row in result["caches"]:
            self.assertEqual(row["status"], "HELD")
            self.assertNotIn("logical_bytes", row)
            self.assertNotIn("inventory_sha256", row)

    def test_marker_inserted_during_live_read_withholds_completed_inventory(self):
        calls = 0
        def insert():
            nonlocal calls
            calls += 1
            if calls == 2:  # After pip inventory, before publication.
                (self.active / "unknown-marker").write_text("held original")
            return set()
        result = self.run_preview(live_reader=insert)
        self.assert_admission_withheld(result)
        self.assertEqual(result["reasons"], ["active_lane_or_reconciliation_hold"])
        self.assertEqual((self.active / "unknown-marker").read_text(), "held original")

    def test_replaced_independently_lockable_admission_lock_withholds_preview(self):
        original = (self.active / ".admission.lock").stat().st_ino
        calls = 0
        def replace():
            nonlocal calls
            calls += 1
            if calls == 1:
                path = self.active / ".admission.lock"
                path.unlink()
                path.touch(mode=0o600)
                self.assertNotEqual(path.stat().st_ino, original)
                with path.open("r+") as stream:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return set()
        result = self.run_preview(live_reader=replace)
        self.assert_admission_withheld(result)
        self.assertEqual(result["reasons"], ["admission_lock_identity"])

    def test_active_directory_replacement_withholds_preview_of_old_namespace(self):
        calls = 0
        def replace():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.active.rename(self.active.with_name("original-active"))
                self.active.mkdir(mode=0o700)
                (self.active / ".admission.lock").touch(mode=0o600)
            return set()
        result = self.run_preview(live_reader=replace)
        self.assert_admission_withheld(result)
        self.assertEqual(result["reasons"], ["directory_identity"])

    def test_live_cwd_or_fd_under_cache_holds(self):
        for path in [str(self.cache), str(self.cache / "http-v2/aa/object.body")]:
            result = self.run_preview(live_reader=lambda: {path})
            self.assertEqual(self.pip(result)["reason"], "live_use")

    def test_incomplete_live_census_holds_without_inventory(self):
        def unknown():
            raise self.preview.PreviewHeld("live_use_unknown")
        result = self.run_preview(live_reader=unknown)
        self.assertEqual(result["reasons"], ["live_use_unknown"])
        self.assertEqual(result["caches"], [])

    def test_live_use_appearing_after_inventory_withholds_metadata(self):
        calls = 0
        def live():
            nonlocal calls
            calls += 1
            return set() if calls == 1 else {str(self.cache)}
        result = self.run_preview(live_reader=live)
        self.assertEqual(self.pip(result)["reason"], "live_use")
        self.assertNotIn("logical_bytes", self.pip(result))

    def test_pending_original_maintenance_prepare_holds_until_verified(self):
        journal = self.state_dir() / "generated-cache-trim.jsonl"
        row = {"event": "PREPARE", "path": str(self.cache)}
        journal.write_text(json.dumps(row) + "\n")
        self.assertEqual(self.pip(self.run_preview())["reason"], "maintenance_effect_unknown")
        with journal.open("a") as out:
            out.write(json.dumps(dict(row, event="VERIFIED")) + "\n")
        self.assertEqual(self.pip(self.run_preview())["status"], "PREVIEWED")

    def test_corrupt_or_symlinked_journal_holds(self):
        path = self.state_dir() / "generated-cache-trim.jsonl"
        path.write_text("not-json\n")
        self.assertEqual(self.run_preview()["reasons"], ["maintenance_journal_unknown"])
        path.unlink()
        path.symlink_to(self.cache / "http-v2/aa/object.body")
        self.assertEqual(self.run_preview()["status"], "HELD")

    def test_unknown_top_level_data_is_not_called_disposable(self):
        (self.cache / "my-work.txt").write_text("private source")
        self.assertEqual(self.pip(self.run_preview())["reason"], "unrecognized_cache_layout")

    def test_symlink_special_or_hardlink_inside_cache_holds(self):
        p = self.cache / "http-v2/aa/danger"
        outside = self.home / "outside"
        outside.write_bytes(b"not cache data")
        p.symlink_to(outside)
        row = self.pip(self.run_preview())
        # Linux reports symlink mode0777: the unchanged ownership/mode guard
        # refuses it before the special-node guard reached on macOS.
        self.assertIn(row["reason"], {"ownership_or_write_mode", "symlink_hardlink_or_special"})
        self.assertEqual(row["status"], "HELD")
        self.assertNotIn("logical_bytes", row)
        self.assertNotIn("inventory_sha256", row)
        self.assertEqual(outside.read_bytes(), b"not cache data")
        p.unlink()
        os.link(self.cache / "http-v2/aa/object.body", p)
        self.assertEqual(self.pip(self.run_preview())["reason"], "symlink_hardlink_or_special")

    def test_symlinked_cache_parent_or_cache_is_never_followed(self):
        moved = self.home / "not-a-cache"
        self.cache.rename(moved)
        self.cache.symlink_to(moved, target_is_directory=True)
        with mock.patch.object(self.preview, "_inventory", side_effect=AssertionError("must not follow cache symlink")):
            row = self.pip(self.run_preview())
        self.assertEqual(row["status"], "HELD")
        self.assertNotIn("inventory_sha256", row)
        self.cache.unlink()
        parent = self.cache.parent
        parent.rmdir()
        parent.symlink_to(moved, target_is_directory=True)
        with mock.patch.object(self.preview, "_inventory", side_effect=AssertionError("must not follow parent symlink")):
            row = self.pip(self.run_preview())
        self.assertIn(row["reason"], {"ownership_or_write_mode", "directory_identity"})
        self.assertEqual(row["status"], "HELD")
        self.assertNotIn("logical_bytes", row)
        self.assertNotIn("inventory_sha256", row)
        self.assertEqual((moved / "http-v2/aa/object.body").read_bytes(), b"regenerable cached fixture")

    def test_linux_0777_symlink_stat_is_refused_by_unchanged_mode_guard(self):
        original_owned = self.preview._owned
        seen = []
        def linux_symlink_stat(s, uid, *, directory=False):
            if stat.S_ISLNK(s.st_mode):
                seen.append(directory)
                s = SimpleNamespace(st_uid=s.st_uid, st_mode=stat.S_IFLNK | 0o777)
            return original_owned(s, uid, directory=directory)
        p = self.cache / "http-v2/aa/danger"
        p.symlink_to(self.home / "outside")
        with mock.patch.object(self.preview, "_owned", side_effect=linux_symlink_stat):
            row = self.pip(self.run_preview())
            self.assertEqual(row["reason"], "ownership_or_write_mode")
            self.assertNotIn("inventory_sha256", row)
            p.unlink()
            moved = self.home / "not-a-cache"
            self.cache.rename(moved)
            self.cache.parent.rmdir()
            self.cache.parent.symlink_to(moved, target_is_directory=True)
            with mock.patch.object(self.preview, "_inventory", side_effect=AssertionError("must not follow Linux symlink")):
                row = self.pip(self.run_preview())
            self.assertEqual(row["reason"], "ownership_or_write_mode")
            self.assertNotIn("logical_bytes", row)
        self.assertEqual(seen, [False, True])

    def test_foreign_owner_or_writable_cache_holds(self):
        self.cache.chmod(0o777)
        self.assertEqual(self.pip(self.run_preview())["reason"], "ownership_or_write_mode")
        self.cache.chmod(0o700)
        with mock.patch.object(self.preview, "_owned", side_effect=self.preview.PreviewHeld("ownership_or_write_mode")):
            self.assertEqual(self.run_preview()["reasons"], ["ownership_or_write_mode"])

    def test_lock_named_file_holds(self):
        (self.cache / "http-v2/cache.lock").touch()
        self.assertEqual(self.pip(self.run_preview())["reason"], "cache_lock_or_unknown_entry")

    def test_entry_and_depth_budgets_hold_without_partial_candidate(self):
        with mock.patch.object(self.preview, "MAX_ENTRIES", 1):
            self.assertEqual(self.pip(self.run_preview())["reason"], "inventory_bound")
        with mock.patch.object(self.preview, "MAX_DEPTH", 0):
            self.assertEqual(self.pip(self.run_preview())["reason"], "inventory_bound")

    def test_cache_replaced_after_inventory_does_not_return_old_bytes(self):
        calls = 0
        def mutate():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.cache.rename(self.home / "old-cache")
                self.cache.mkdir()
            return set()
        self.assertEqual(self.pip(self.run_preview(live_reader=mutate))["reason"], "inventory_changed")

    def test_non_linux_and_root_owner_do_not_inspect(self):
        with mock.patch.object(self.preview, "_directory", side_effect=AssertionError("must not inspect")):
            for platform, uid in [("darwin", self.uid), ("linux", 0)]:
                result = self.preview.preview(home=self.home, uid=uid, platform=platform)
                self.assertEqual(result["reasons"], ["linux_nonroot_owner_required"])

    def test_retains_new_preview_only_receipt_in_existing_owner_directory(self):
        result = self.run_preview()
        receipt = self.preview.retain_preview(result, home=self.home, uid=self.uid)
        raw = (self.state_dir() / receipt["receipt"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt["sha256"])
        self.assertEqual(json.loads(raw), result)
        self.assertEqual((self.state_dir() / receipt["receipt"]).stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.state_dir() / "generated-cache-trim.jsonl").exists())

    def test_receipt_parent_symlink_does_not_write_through_it(self):
        outside = self.home / "outside"
        outside.mkdir()
        (self.home / ".local").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.preview.retain_preview(self.run_preview(), home=self.home, uid=self.uid)
        self.assertEqual(list(outside.iterdir()), [])

    def test_actual_proc_census_tracks_paths_and_refuses_missing_owned_fd(self):
        proc = self.home / "fixture-proc"
        pid = proc / "99999999"
        (pid / "fd").mkdir(parents=True)
        (pid / "stat").write_text("99999999 (fixture) S " + "0 " * 18 + "123")
        (pid / "cwd").symlink_to(self.cache, target_is_directory=True)
        (pid / "exe").symlink_to("/usr/bin/inert-fixture")
        (pid / "fd/7").symlink_to(self.cache / "http-v2/aa/object.body")
        paths = self.preview._live_paths(self.uid, proc=proc)
        self.assertIn(str(self.cache), paths)
        self.assertIn(str(self.cache / "http-v2/aa/object.body"), paths)
        (pid / "exe").unlink()
        with self.assertRaises(self.preview.PreviewHeld):
            self.preview._live_paths(self.uid, proc=proc)

    def test_logical_and_allocated_size_budget_is_not_partial_success(self):
        with mock.patch.object(self.preview, "MAX_BYTES", 1):
            self.assertEqual(self.pip(self.run_preview())["reason"], "inventory_bound")

    def test_cache_on_other_filesystem_cannot_claim_worker_disk_relief(self):
        original_open = self.preview._directory
        original_stat = os.fstat
        target_fd = None
        def directory(path, uid):
            nonlocal target_fd
            fd = original_open(path, uid)
            if Path(path) == self.cache:
                target_fd = fd
            return fd
        def stat_fd(fd):
            value = original_stat(fd)
            if fd == target_fd:
                attrs = {k: getattr(value, k) for k in dir(value) if k.startswith("st_")}
                attrs["st_dev"] += 1
                return SimpleNamespace(**attrs)
            return value
        with mock.patch.object(self.preview, "_directory", side_effect=directory), \
             mock.patch.object(self.preview.os, "fstat", side_effect=stat_fd):
            self.assertEqual(self.pip(self.run_preview())["reason"], "different_worker_filesystem")

    def test_absent_fixed_cache_is_absent_not_an_empty_inventory(self):
        import shutil
        shutil.rmtree(self.cache)
        self.cache.parent.rmdir()
        result = self.run_preview()
        self.assertEqual(self.pip(result)["status"], "ABSENT")
        self.assertNotIn("logical_bytes", self.pip(result))

    def test_source_mismatch_refuses_before_preview_or_receipt(self):
        with mock.patch.object(self.preview, "preview", side_effect=AssertionError("no inventory")):
            with self.assertRaises(SystemExit):
                self.preview.main(["--expected-source-sha", "0" * 64])

    def test_existing_driver_calls_once_no_sync_probe_sweep_or_fallback(self):
        body = self.run_preview()
        body.update(self.preview.retain_preview(body, home=self.home, uid=self.uid))
        with mock.patch.object(self.fleet, "run", return_value=(0, json.dumps(body), "")) as run:
            result = self.fleet.preview_linux_caches("ubuntu0")
        self.assertEqual(result["state"], "PREVIEWED")
        run.assert_called_once()
        argv = run.call_args.args[0]
        self.assertEqual(argv[:-1], self.fleet.SSH + ["ubuntu0"])
        self.assertIn("linux_cache_preview.py", argv[-1])
        self.assertNotIn("sweep.py", argv[-1])
        self.assertNotIn("--apply", argv[-1])
        self.assertFalse(result["preview"]["cleanup_authorized"])

    def test_missing_old_remote_source_is_unavailable_without_retry(self):
        with mock.patch.object(self.fleet, "run", return_value=(2, "", "missing")) as run:
            self.assertEqual(self.fleet.preview_linux_caches("ubuntu0")["state"], "UNAVAILABLE")
        run.assert_called_once()

    def test_transport_target_timeout_and_body_are_closed(self):
        with mock.patch.object(self.fleet, "run", side_effect=AssertionError("no transport")):
            for host in ["m1", "ubuntu0;echo bad", "elsewhere"]:
                with self.assertRaises(ValueError):
                    self.fleet.preview_linux_caches(host)
            with self.assertRaises(ValueError):
                self.fleet.preview_linux_caches("ubuntu0", timeout=21)
        for body in [{}, {"schema": self.preview.SCHEMA, "cleanup_authorized": True}]:
            with mock.patch.object(self.fleet, "run", return_value=(0, json.dumps(body), "")):
                self.assertEqual(self.fleet.preview_linux_caches("ubuntu0")["state"], "UNAVAILABLE")

    def test_driver_rejects_receipt_drift_unknown_fields_and_authority_claim(self):
        original = self.run_preview()
        original.update(self.preview.retain_preview(original, home=self.home, uid=self.uid))
        for mutate in [lambda b: b.update(cleanup_authorized=True),
                       lambda b: b.update(private_payload="not allowed"),
                       lambda b: b.update(sha256="0" * 64),
                       lambda b: b.update(caches=[{"cache": "arbitrary", "relative_root": "../../source"}])]:
            body = json.loads(json.dumps(original))
            mutate(body)
            with mock.patch.object(self.fleet, "run", return_value=(0, json.dumps(body), "")):
                self.assertEqual(self.fleet.preview_linux_caches("ubuntu0")["state"], "UNAVAILABLE")

    def test_preview_cli_never_enters_old_sweep_probe_sync_or_lock(self):
        with mock.patch("sys.argv", ["fleet_remote_sweep.py", "--linux-cache-preview", "--no-sync", "--hosts", "ubuntu0"]), \
             mock.patch.object(self.fleet, "preview_linux_caches", return_value={"state": "HELD"}) as preview, \
             mock.patch.object(self.fleet, "reachable", side_effect=AssertionError("no probe")), \
             mock.patch.object(self.fleet, "sweep", side_effect=AssertionError("no sweep")), \
             mock.patch.object(self.fleet, "sync", side_effect=AssertionError("no sync")), \
             mock.patch.object(self.fleet, "STATE", self.home / "not-created"), \
             mock.patch("builtins.print"):
            self.assertEqual(self.fleet.main(), 3)
            preview.assert_called_once_with("ubuntu0", timeout=20)
            self.assertFalse((self.home / "not-created").exists())

    def test_preview_cli_requires_explicit_single_target_no_sync(self):
        for args in [["--linux-cache-preview"],
                     ["--linux-cache-preview", "--no-sync", "--hosts", "ubuntu0,ubuntu1"]]:
            with mock.patch("sys.argv", ["fleet_remote_sweep.py", *args]), \
                 mock.patch.object(self.fleet, "preview_linux_caches", side_effect=AssertionError("no call")), \
                 mock.patch("sys.stderr"):
                with self.assertRaises(SystemExit):
                    self.fleet.main()

    def test_fixed_bootstrap_does_not_execute_wrong_remote_module(self):
        import subprocess
        installed = self.home / ".local/lib/mastermind/storage-cleanup"
        installed.mkdir(parents=True)
        marker = self.home / "must-not-execute"
        source = installed / "linux_cache_preview.py"
        source.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('bad')\n")
        env = dict(os.environ, HOME=str(self.home))
        result = subprocess.run([sys.executable, "-c", self.fleet.LINUX_PREVIEW_BOOTSTRAP, "0" * 64],
                                env=env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 78)
        self.assertFalse(marker.exists())



if __name__ == "__main__":
    unittest.main()
