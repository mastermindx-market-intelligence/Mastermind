from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import stat
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import control_bundle as bundle


class BundleTests(unittest.TestCase):
    def _prior_digest(self):
        return bundle.verify(
            control_root=self.control, launcher=self.launcher,
        )["bundleDigest"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.control = self.root / "control"
        self.bin = self.root / "bin"
        self.source.mkdir()
        self.control.mkdir(mode=0o700)
        self.bin.mkdir()
        for name in bundle.CONTROL_FILES:
            (self.source / name).write_text(f"new {name}\n", encoding="utf-8")
            (self.control / name).write_text(f"old {name}\n", encoding="utf-8")
            (self.control / name).chmod(0o600)
        self.launcher = self.bin / "studio-direct"
        self.launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.launcher.chmod(0o700)
        old_files = {name: bundle._sha256(self.control / name) for name in bundle.CONTROL_FILES}
        launcher_hash = bundle._sha256(self.launcher)
        manifest = {
            "schema": bundle.SCHEMA,
            "files": old_files,
            "launcher": str(self.launcher),
            "launcherHash": launcher_hash,
            "bundleDigest": bundle._bundle_digest(old_files, launcher_hash),
            "source": "/old/source",
        }
        (self.control / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.control / "manifest.json").chmod(0o600)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_adopts_exact_helpers_and_reseals_manifest(self):
        result = bundle.install(source=self.source, control_root=self.control, launcher=self.launcher, expected_bundle_digest=self._prior_digest())
        self.assertEqual(result["state"], "CONTROL_BUNDLE_INSTALLED")
        verified = bundle.verify(control_root=self.control, launcher=self.launcher)
        self.assertEqual(verified["state"], "CONTROL_BUNDLE_VERIFIED")
        self.assertEqual(verified["source"], str(self.source))
        for name in bundle.CONTROL_FILES:
            self.assertEqual((self.control / name).read_text(), f"new {name}\n")
            self.assertEqual(stat.S_IMODE((self.control / name).stat().st_mode), 0o600)

    def test_verify_detects_stale_manifest_after_helper_drift(self):
        (self.control / "studio_direct_control.py").write_text("drift\n")
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_MISMATCH"):
            bundle.verify(control_root=self.control, launcher=self.launcher)

    def test_malformed_manifest_files_shape_refuses_closed(self):
        manifest_path = self.control / "manifest.json"
        value = json.loads(manifest_path.read_text())
        value["files"] = list(bundle.CONTROL_FILES)
        manifest_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_MANIFEST_INVALID"):
            bundle.verify(control_root=self.control, launcher=self.launcher)

    def test_bundle_digest_binds_helpers_and_launcher(self):
        bundle.install(source=self.source, control_root=self.control, launcher=self.launcher, expected_bundle_digest=self._prior_digest())
        verified = bundle.verify(control_root=self.control, launcher=self.launcher)
        expected = bundle._bundle_digest(verified["files"], verified["launcherHash"])
        self.assertEqual(verified["bundleDigest"], expected)
        manifest_path = self.control / "manifest.json"
        value = json.loads(manifest_path.read_text())
        value["bundleDigest"] = "0" * 64
        manifest_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_MANIFEST_INVALID"):
            bundle.verify(control_root=self.control, launcher=self.launcher)

    def test_install_is_idempotent(self):
        first = bundle.install(source=self.source, control_root=self.control, launcher=self.launcher, expected_bundle_digest=self._prior_digest())
        second = bundle.install(source=self.source, control_root=self.control, launcher=self.launcher, expected_bundle_digest=self._prior_digest())
        self.assertEqual(first["files"], second["files"])
        self.assertEqual(second["state"], "CONTROL_BUNDLE_INSTALLED")

    def test_source_symlink_refuses_before_effect(self):
        real = self.source / "real.py"
        real.write_text("safe\n")
        target = self.source / bundle.CONTROL_FILES[0]
        target.unlink()
        target.symlink_to(real)
        before = (self.control / bundle.CONTROL_FILES[1]).read_bytes()
        with self.assertRaisesRegex(bundle.Refusal, "REGULAR_FILE_REQUIRED"):
            bundle.install(source=self.source, control_root=self.control, launcher=self.launcher, expected_bundle_digest=self._prior_digest())
        self.assertEqual((self.control / bundle.CONTROL_FILES[1]).read_bytes(), before)

    def test_launcher_drift_refuses_verification(self):
        bundle.install(source=self.source, control_root=self.control, launcher=self.launcher, expected_bundle_digest=self._prior_digest())
        self.launcher.write_text("#!/bin/sh\ntrue\n")
        self.launcher.chmod(0o700)
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_MISMATCH"):
            bundle.verify(control_root=self.control, launcher=self.launcher)

    def test_partial_commit_is_effect_unknown(self):
        real_replace = os.replace
        calls = 0
        def fail_second(src, dst):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("forced")
            return real_replace(src, dst)
        with mock.patch.object(bundle.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(bundle.EffectUnknown, "CONTROL_BUNDLE_EFFECT_UNKNOWN"):
                bundle.install(source=self.source, control_root=self.control, launcher=self.launcher, expected_bundle_digest=self._prior_digest())

    def test_lock_contention_refuses(self):
        with bundle._lock(self.control):
            with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_BUSY"):
                bundle.install(source=self.source, control_root=self.control, launcher=self.launcher, expected_bundle_digest=self._prior_digest())

    def test_existing_bundle_requires_exact_original_digest_before_any_replace(self):
        before = {n:(self.control/n).read_bytes() for n in bundle.CONTROL_FILES}
        manifest = (self.control/"manifest.json").read_bytes()
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_CAS_REQUIRED"):
            bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_CAS_MISMATCH"):
            bundle.install(
                source=self.source, control_root=self.control,
                launcher=self.launcher, expected_bundle_digest="0" * 64,
            )
        self.assertEqual(before, {n:(self.control/n).read_bytes() for n in bundle.CONTROL_FILES})
        self.assertEqual(manifest, (self.control/"manifest.json").read_bytes())

    def test_original_helper_drift_refuses_upgrade_before_replace(self):
        original_cas = self._prior_digest()
        preserved = (self.control/"private_service.py").read_bytes()
        (self.control/"private_tunnel_service.py").write_text("unexpected drift\\n")
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_MISMATCH"):
            bundle.install(
                source=self.source, control_root=self.control,
                launcher=self.launcher, expected_bundle_digest=original_cas,
            )
        self.assertEqual((self.control/"private_service.py").read_bytes(), preserved)

    def test_initial_install_only_into_truly_empty_control_directory(self):
        for name in (*bundle.CONTROL_FILES, "manifest.json"):
            (self.control/name).unlink()
        result = bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)
        self.assertEqual(result["state"], "CONTROL_BUNDLE_INSTALLED")
        self.assertEqual(self._prior_digest(), result["bundleDigest"])

    def test_unmanifested_partial_existing_helpers_refuse_first_install(self):
        (self.control/"manifest.json").unlink()
        before = (self.control/"private_service.py").read_bytes()
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_UNMANIFESTED"):
            bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)
        self.assertEqual((self.control/"private_service.py").read_bytes(), before)

    def test_precommit_manifest_change_refuses_without_overwriting_old_helpers(self):
        expected = self._prior_digest()
        original_old = {name:(self.control/name).read_bytes() for name in bundle.CONTROL_FILES}
        original_writer = bundle._write_private
        changed = False
        def mutate_original_after_staging(path, data):
            nonlocal changed
            original_writer(path, data)
            if not changed and path.name == bundle.CONTROL_FILES[0]:
                path_to_old = self.control/"manifest.json"
                manifest = json.loads(path_to_old.read_text())
                manifest["source"] = "/altered/original/provenance"
                path_to_old.write_text(json.dumps(manifest), encoding="utf-8")
                path_to_old.chmod(0o600)
                changed = True
        with mock.patch.object(bundle, "_write_private", side_effect=mutate_original_after_staging):
            with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_ORIGINAL_CHANGED"):
                bundle.install(
                    source=self.source, control_root=self.control,
                    launcher=self.launcher, expected_bundle_digest=expected,
                )
        self.assertTrue(changed)
        self.assertEqual(original_old, {name:(self.control/name).read_bytes() for name in bundle.CONTROL_FILES})

    def test_cli_upgrade_must_supply_current_bundle_digest(self):
        with mock.patch.object(bundle, "_default_paths", return_value=(self.source, self.control, self.launcher)), mock.patch("builtins.print") as printer:
            self.assertEqual(bundle.main(["install"]), 2)
            self.assertEqual(json.loads(printer.call_args.args[0])["state"], "CONTROL_BUNDLE_CAS_REQUIRED")
            self.assertEqual(bundle.main(["verify", "--expected-bundle-digest", self._prior_digest()]), 2)
            self.assertEqual(json.loads(printer.call_args.args[0])["state"], "CONTROL_BUNDLE_EXPECTATION_UNSUPPORTED_FOR_VERIFY")

    def test_cli_effect_unknown_is_nonretryable(self):
        with mock.patch.object(bundle, "_default_paths", return_value=(self.source, self.control, self.launcher)), mock.patch.object(bundle, "install", side_effect=bundle.EffectUnknown("x")), mock.patch("builtins.print") as printer:
            self.assertEqual(bundle.main(["install"]), 3)
        payload = json.loads(printer.call_args.args[0])
        self.assertEqual(payload["state"], "EFFECT_UNKNOWN")
        self.assertFalse(payload["retry_allowed"])
        self.assertEqual(payload["reconcile_action"], "verify")


if __name__ == "__main__":
    unittest.main()
