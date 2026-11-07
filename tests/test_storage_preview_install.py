"""Hermetic fixed-target installer; no real owner state or transport invocation."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[1] / "ops/fleet_storage_cleanup"


class PreviewInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("fixture_preview_install", ROOT / "preview_install.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.home.chmod(0o700)
        self.toolkit = self.home / ".local/lib/mastermind/storage-cleanup"
        self.state = self.home / ".local/state/mastermind/storage-cleanup"
        self.active = self.home / "lanes/ext/active"
        for path in (self.toolkit, self.state, self.active):
            path.mkdir(parents=True, mode=0o700)
        (self.active / ".admission.lock").touch(mode=0o600)
        self.payload = (ROOT / "linux_cache_preview.py").read_bytes()
        self.binding = {"account": "fixture-user", "hostnames": ["fixture-linux"]}
        self.target = self.toolkit / "linux_cache_preview.py"
        self.kw = dict(home=self.home, uid=os.getuid(), platform="linux", account="fixture-user", hostname="fixture-linux")

    def install(self, before="ABSENT", operation=None):
        return self.mod.install("linux-preview", self.binding, self.payload, before,
                                self.mod.digest(self.payload), operation or uuid.uuid4().hex, **self.kw)

    def test_absent_install_is_verified_without_running_preview(self):
        with mock.patch("subprocess.run", side_effect=AssertionError("no transport")):
            result = self.install()
        self.assertEqual(result["state"], "VERIFIED")
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertIsNone(result["backup"])
        self.assertFalse((self.state / "generated-cache-trim.jsonl").exists())
        self.assertEqual(len(list(self.state.glob("*.json.verified"))), 1)

    def test_exact_replacement_retains_original_bytes(self):
        self.target.write_bytes(b"# original installed source\n")
        old = self.target.read_bytes()
        result = self.install(self.mod.digest(old))
        self.assertEqual((self.toolkit / result["backup"]).read_bytes(), old)
        self.assertEqual(self.target.read_bytes(), self.payload)

    def test_preimage_and_payload_drift_never_replace(self):
        self.target.write_bytes(b"foreign current source")
        with self.assertRaisesRegex(self.mod.InstallHeld, "preimage_changed"):
            self.install()
        self.assertEqual(self.target.read_bytes(), b"foreign current source")
        with self.assertRaisesRegex(self.mod.InstallHeld, "source_or_operation_binding"):
            self.mod.install("linux-preview", self.binding, self.payload, "ABSENT", "0" * 64, uuid.uuid4().hex, **self.kw)
        self.assertEqual(list(self.state.iterdir()), [])

    def test_host_account_and_platform_mismatch_refuse_before_writes(self):
        for key, value in [("hostname", "other-host"), ("account", "other-user"), ("platform", "darwin"), ("uid", 0)]:
            with self.subTest(key=key), self.assertRaises(self.mod.InstallHeld):
                self.mod.install("linux-preview", self.binding, self.payload, "ABSENT", self.mod.digest(self.payload), uuid.uuid4().hex,
                                 **dict(self.kw, **{key: value}))
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.state.iterdir()), [])

    def test_marker_and_existing_lock_contention_refuse(self):
        (self.active / "unknown").touch()
        with self.assertRaises(ValueError):
            self.install()
        (self.active / "unknown").unlink()
        import fcntl
        with (self.active / ".admission.lock").open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.install()
        self.assertFalse(self.target.exists())

    def test_symlink_hardlink_and_writable_target_are_not_replaced(self):
        external = self.home / "external"
        external.write_bytes(b"untouched")
        self.target.symlink_to(external)
        with self.assertRaises(OSError):
            self.install()
        self.target.unlink()
        os.link(external, self.target)
        with self.assertRaises(self.mod.InstallHeld):
            self.install()
        self.target.unlink()
        self.target.write_bytes(b"writable")
        self.target.chmod(0o666)
        with self.assertRaises(self.mod.InstallHeld):
            self.install()
        self.assertEqual(external.read_bytes(), b"untouched")

    def test_pending_prior_operation_forbids_new_id(self):
        (self.state / ("preview-install-" + uuid.uuid4().hex + ".json")).write_text('{"state":"PREPARED"}')
        with self.assertRaisesRegex(self.mod.InstallHeld, "prior_install_unknown_no_replay"):
            self.install()
        self.assertFalse(self.target.exists())

    def test_absent_target_appearing_at_commit_is_never_overwritten(self):
        original = os.link
        def collision(*args, **kw):
            self.target.write_bytes(b"new independent source")
            return original(*args, **kw)
        with mock.patch.object(self.mod.os, "link", side_effect=collision):
            with self.assertRaisesRegex(self.mod.InstallHeld, "install_effect_unknown_no_replay"):
                self.install()
        self.assertEqual(self.target.read_bytes(), b"new independent source")
        with self.assertRaisesRegex(self.mod.InstallHeld, "prior_install_unknown_no_replay"):
            self.install()

    def test_late_active_marker_withholds_install_before_commit(self):
        original = self.mod._write_new
        def stage(fd, name, raw):
            original(fd, name, raw)
            if ".stage-" in name:
                (self.active / "new-reconciliation-hold").touch()
        with mock.patch.object(self.mod, "_write_new", side_effect=stage):
            with self.assertRaises(ValueError):
                self.install()
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.state.glob("*.verified")), [])

    def test_late_toolkit_namespace_replacement_cannot_install_old_directory(self):
        original = self.mod._write_new
        def stage(fd, name, raw):
            original(fd, name, raw)
            if ".stage-" in name:
                self.toolkit.rename(self.toolkit.with_name("original-toolkit"))
                self.toolkit.mkdir(mode=0o700)
        with mock.patch.object(self.mod, "_write_new", side_effect=stage):
            with self.assertRaisesRegex(self.mod.InstallHeld, "directory_identity"):
                self.install()
        self.assertFalse(self.target.exists())
        self.assertFalse((self.toolkit.with_name("original-toolkit") / self.target.name).exists())

    def test_state_directory_replacement_cannot_detach_install_receipts(self):
        original = self.mod._write_new
        def replace_state(fd, name, raw):
            original(fd, name, raw)
            if name.endswith(".json"):
                self.state.rename(self.state.with_name("original-state"))
                self.state.mkdir(mode=0o700)
        with mock.patch.object(self.mod, "_write_new", side_effect=replace_state):
            with self.assertRaisesRegex(self.mod.InstallHeld, "directory_identity"):
                self.install()
        self.assertFalse(self.target.exists())

    def test_late_postimage_import_scope_drift_cannot_return_verified(self):
        original = self.mod._import_only
        calls = 0
        def late_import(*args):
            nonlocal calls
            module = original(*args)
            calls += 1
            if calls == 2:
                (self.active / "new-hold").touch()
            return module
        with mock.patch.object(self.mod, "_import_only", side_effect=late_import):
            with self.assertRaisesRegex(self.mod.InstallHeld, "install_effect_unknown_no_replay"):
                self.install()
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertEqual(list(self.state.glob("*.verified")), [])

    def test_failed_postimage_retains_backup_and_write_ahead_receipt(self):
        self.target.write_bytes(b"original")
        original = self.mod._import_only
        count = 0
        def check(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise ValueError("inert postimage failure")
            return original(*args)
        with mock.patch.object(self.mod, "_import_only", side_effect=check):
            with self.assertRaisesRegex(self.mod.InstallHeld, "install_effect_unknown_no_replay"):
                self.install(self.mod.digest(b"original"))
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertEqual(next(self.toolkit.glob("*.before-*")).read_bytes(), b"original")
        self.assertEqual(len(list(self.state.glob("*.json"))), 1)
        self.assertEqual(list(self.state.glob("*.verified")), [])

    def test_inspection_is_fixed_read_only_and_no_import(self):
        with mock.patch.object(self.mod, "_import_only", side_effect=AssertionError("inspect cannot import")):
            result = self.mod.inspect_target("linux-preview", self.binding, **self.kw)
        self.assertEqual(result, {"role": "linux-preview", "preimage": "ABSENT"})
        self.assertEqual(list(self.toolkit.iterdir()), [])
        self.assertEqual(list(self.state.iterdir()), [])

    def test_m2_driver_uses_existing_lock_and_does_not_sweep(self):
        payload = (ROOT / "fleet_remote_sweep.py").read_bytes()
        kwargs = dict(self.kw, platform="darwin")
        (self.state / "fleet-remote-sweep.lock").write_text('{"pid":123}')
        with self.assertRaises(FileExistsError):
            self.mod.install("m2-driver", self.binding, payload, "ABSENT", self.mod.digest(payload), uuid.uuid4().hex, **kwargs)
        (self.state / "fleet-remote-sweep.lock").unlink()
        with mock.patch("subprocess.run", side_effect=AssertionError("never sweep or transport")):
            result = self.mod.install("m2-driver", self.binding, payload, "ABSENT", self.mod.digest(payload), uuid.uuid4().hex, **kwargs)
        self.assertEqual(result["state"], "VERIFIED")
        self.assertFalse((self.state / "fleet-remote-sweep.lock").exists())

    def configs(self):
        registry = json.dumps({"ubuntu0": {"ssh_alias": "mmx-ubuntu0", "platform": "linux", "hostnames": ["fixture-linux"]}}).encode()
        config = b"Host mmx-ubuntu0\n HostName 192.0.2.1\n User fixture-user\n"
        return registry, config

    def test_transport_plan_resolves_actual_enrolled_alias_never_dispatches(self):
        driver = SimpleNamespace(SSH=["ssh", "-o", "BatchMode=yes"])
        registry, config = self.configs()
        with mock.patch("subprocess.run", side_effect=AssertionError("planning only")):
            plan = self.mod.transport_plan(driver, "ubuntu0", registry, config, kind="inspect",
                                           expected_installer_sha=self.mod.digest((ROOT / "preview_install.py").read_bytes()))
        self.assertEqual(plan["argv"][-2], "mmx-ubuntu0")
        self.assertEqual(plan["target"]["binding"], self.binding)
        self.assertFalse(plan["dispatch_authorized"])
        self.assertIsNone(plan["remote_preimage"])
        with self.assertRaisesRegex(self.mod.InstallHeld, "remote_preimage_unknown"):
            self.mod.transport_plan(driver, "ubuntu0", registry, config, kind="install", payload=self.payload)

    def test_preview_plan_has_same_user_host_and_source_fence(self):
        driver = SimpleNamespace(SSH=["ssh"], linux_cache_preview_command=lambda: "python3 -c 'pass' " + "a" * 64)
        registry, config = self.configs()
        plan = self.mod.transport_plan(driver, "ubuntu0", registry, config, kind="preview")
        self.assertEqual(plan["argv"][-2], "mmx-ubuntu0")
        self.assertIn("pwd.getpwuid", plan["argv"][-1])
        self.assertIn("socket.gethostname", plan["argv"][-1])
        self.assertIn("a" * 64, plan["argv"][-1])
        self.assertFalse(plan["dispatch_authorized"])

    def test_unknown_role_cannot_inspect_arbitrary_file(self):
        with self.assertRaisesRegex(self.mod.InstallHeld, "platform_or_role"):
            self.mod.inspect_target("/etc/passwd", self.binding, **self.kw)

    def test_bootstrap_source_substitution_cannot_self_bless(self):
        original = (ROOT / "preview_install.py").read_bytes()
        substituted = self.home / "preview_install.py"
        substituted.write_bytes(b"raise RuntimeError('must never execute')\n")
        registry, config = self.configs()
        driver = SimpleNamespace(SSH=["ssh"])
        with mock.patch.object(self.mod, "__file__", str(substituted)):
            with self.assertRaisesRegex(self.mod.InstallHeld, "installer_source_pin"):
                self.mod.transport_plan(driver, "ubuntu0", registry, config, kind="inspect",
                                        expected_installer_sha=self.mod.digest(original))

    def test_missing_independent_installer_pin_never_prepares_bootstrap(self):
        registry, config = self.configs()
        with self.assertRaisesRegex(self.mod.InstallHeld, "installer_source_pin"):
            self.mod.transport_plan(SimpleNamespace(SSH=["ssh"]), "ubuntu0", registry, config, kind="inspect")

    def test_drift_during_terminal_write_cannot_return_verified(self):
        original = self.mod._write_new
        def late_marker(fd, name, raw):
            original(fd, name, raw)
            if name.endswith(".verified"):
                (self.active / "terminal-time-hold").touch()
        with mock.patch.object(self.mod, "_write_new", side_effect=late_marker):
            with self.assertRaisesRegex(self.mod.InstallHeld, "install_effect_unknown_no_replay"):
                self.install()
        self.assertEqual(len(list(self.state.glob("*.verified"))), 1)
        self.assertEqual(len(list(self.state.glob("*.unknown"))), 1)
        (self.active / "terminal-time-hold").unlink()
        with self.assertRaisesRegex(self.mod.InstallHeld, "prior_install_unknown_no_replay"):
            self.install(self.mod.digest(self.payload))

    def test_failed_unknown_companion_cannot_turn_verified_into_reinstall_grant(self):
        original = self.mod._write_new
        def late_marker_and_full_disk(fd, name, raw):
            if name.endswith(".unknown"):
                raise OSError("inert disk pressure")
            original(fd, name, raw)
            if name.endswith(".verified"):
                (self.active / "late-hold").touch()
        with mock.patch.object(self.mod, "_write_new", side_effect=late_marker_and_full_disk):
            with self.assertRaisesRegex(self.mod.InstallHeld, "install_effect_unknown_no_replay"):
                self.install()
        self.assertEqual(len(list(self.state.glob("*.verified"))), 1)
        self.assertEqual(list(self.state.glob("*.unknown")), [])
        (self.active / "late-hold").unlink()
        before = self.mod.digest(self.payload)
        self.payload += b"\n# independent next fixture version\n"
        with self.assertRaisesRegex(self.mod.InstallHeld, "prior_install_record_requires_reconciliation"):
            self.install(before)

    def test_verified_history_also_requires_owner_reconciliation_before_new_id(self):
        self.install()
        before = self.mod.digest(self.payload)
        self.payload += b"\n# independent next fixture version\n"
        with self.assertRaisesRegex(self.mod.InstallHeld, "prior_install_record_requires_reconciliation"):
            self.install(before)
        observed = self.mod.inspect_target("linux-preview", self.binding, **self.kw)
        self.assertEqual(observed["preimage"], before)

    def test_unknown_dynamic_or_accountless_mapping_never_falls_back(self):
        registry, config = self.configs()
        for bad in [b"", config + b"Include dynamic.conf\n", config.replace(b"fixture-user", b"root")]:
            with self.subTest(config=bad), self.assertRaises(self.mod.InstallHeld):
                self.mod.enrolled_binding("ubuntu0", registry, bad)
        with self.assertRaises(self.mod.InstallHeld):
            self.mod.enrolled_binding("other-host", registry, config)
