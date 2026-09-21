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
        manifest = {
            "schema": bundle.SCHEMA,
            "files": old_files,
            "launcher": str(self.launcher),
            "launcherHash": bundle._sha256(self.launcher),
            "source": "/old/source",
        }
        (self.control / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.control / "manifest.json").chmod(0o600)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_adopts_exact_helpers_and_reseals_manifest(self):
        result = bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)
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

    def test_install_is_idempotent(self):
        first = bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)
        second = bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)
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
            bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)
        self.assertEqual((self.control / bundle.CONTROL_FILES[1]).read_bytes(), before)

    def test_launcher_drift_refuses_verification(self):
        bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)
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
                bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)

    def test_lock_contention_refuses(self):
        with bundle._lock(self.control):
            with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_BUSY"):
                bundle.install(source=self.source, control_root=self.control, launcher=self.launcher)

    def test_cli_effect_unknown_is_nonretryable(self):
        with mock.patch.object(bundle, "_default_paths", return_value=(self.source, self.control, self.launcher)), mock.patch.object(bundle, "install", side_effect=bundle.EffectUnknown("x")), mock.patch("builtins.print") as printer:
            self.assertEqual(bundle.main(["install"]), 3)
        payload = json.loads(printer.call_args.args[0])
        self.assertEqual(payload["state"], "EFFECT_UNKNOWN")
        self.assertFalse(payload["retry_allowed"])
        self.assertEqual(payload["reconcile_action"], "verify")


if __name__ == "__main__":
    unittest.main()
