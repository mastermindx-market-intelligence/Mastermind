import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_local(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


stage = load_local("paper_runtime_stage", ROOT / "integrations/paper_desktop/runtime_stage.py")


class RuntimeStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "runtime"
        self.source = Path(self.tmp.name) / "source"
        self.source.mkdir()
        bridge_bytes = b"import argparse\nargparse.ArgumentParser().parse_args()\n"
        (self.source / "bridge.py").write_bytes(bridge_bytes)
        self.reviewed_patch = mock.patch.object(
            stage,
            "REVIEWED_GENERATIONS",
            {"v2": {"bridge.py": stage._sha256(bridge_bytes)}},
        )
        self.reviewed_patch.start()

    def tearDown(self):
        self.reviewed_patch.stop()
        self.tmp.cleanup()

    def test_stage_creates_offline_versioned_runtime_and_verifies(self):
        result = stage.stage("v2", root=self.root, _source_dir=self.source)
        self.assertEqual(result["state"], "RUNTIME_STAGED")
        self.assertFalse(result["production_acceptance"])
        target = self.root / "v2"
        receipt = json.loads((target / "RUNTIME.json").read_text())
        self.assertFalse(receipt["network_install_performed"])
        self.assertEqual(receipt["bridge_sha256"], result["bridge_sha256"])
        self.assertTrue((target / "venv" / "bin" / "python").exists())
        self.assertEqual(stage.verify("v2", root=self.root, _source_dir=self.source)["state"], "RUNTIME_VERIFIED")

    def test_exact_replay_reconciles_without_overwrite(self):
        first = stage.stage("v2", root=self.root, _source_dir=self.source)
        bridge = self.root / "v2" / "source" / "bridge.py"
        before = bridge.stat().st_mtime_ns
        second = stage.stage("v2", root=self.root, _source_dir=self.source)
        self.assertEqual(first["bridge_sha256"], second["bridge_sha256"])
        self.assertEqual(second["state"], "RUNTIME_ALREADY_PRESENT")
        self.assertEqual(bridge.stat().st_mtime_ns, before)

    def test_modified_existing_generation_refuses_collision(self):
        stage.stage("v2", root=self.root, _source_dir=self.source)
        bridge = self.root / "v2" / "source" / "bridge.py"
        bridge.write_text("changed")
        with self.assertRaisesRegex(stage.Refusal, "GENERATION_COLLISION"):
            stage.stage("v2", root=self.root, _source_dir=self.source)

    def test_generation_name_is_closed(self):
        for value in ["v0", "2", "v2/other", "latest", "v10000"]:
            with self.subTest(value=value), self.assertRaisesRegex(stage.Refusal, "GENERATION_INVALID"):
                stage.stage(value, root=self.root, _source_dir=self.source)

    def test_valid_but_unreviewed_generation_refuses(self):
        with self.assertRaisesRegex(stage.Refusal, "GENERATION_UNSUPPORTED"):
            stage.stage("v3", root=self.root, _source_dir=self.source)

    def test_source_hash_must_match_reviewed_generation(self):
        with mock.patch.object(
            stage,
            "REVIEWED_GENERATIONS",
            {"v2": {"bridge.py": "0" * 64}},
        ):
            with self.assertRaisesRegex(stage.Refusal, "SOURCE_HASH_MISMATCH"):
                stage.stage("v2", root=self.root, _source_dir=self.source)
        self.assertFalse((self.root / "v2").exists())

    def test_verify_uses_generation_pin_not_current_source(self):
        stage.stage("v2", root=self.root, _source_dir=self.source)
        (self.source / "bridge.py").write_text("different protected source later\n", encoding="utf-8")
        self.assertEqual(
            stage.verify("v2", root=self.root, _source_dir=self.source)["state"],
            "RUNTIME_VERIFIED",
        )

    def test_unsafe_existing_runtime_root_refuses(self):
        self.root.mkdir(parents=True, mode=0o700)
        self.root.chmod(0o755)
        with self.assertRaisesRegex(stage.Refusal, "PRIVATE_DIRECTORY_REQUIRED"):
            stage.stage("v2", root=self.root, _source_dir=self.source)

    def test_source_symlink_refuses(self):
        real = self.source / "real.py"
        real.write_text("print('safe')\n")
        (self.source / "bridge.py").unlink()
        (self.source / "bridge.py").symlink_to(real)
        with self.assertRaisesRegex(stage.Refusal, "SOURCE_FILE_UNSAFE"):
            stage.stage("v2", root=self.root, _source_dir=self.source)

    def test_existing_generation_symlink_refuses(self):
        self.root.mkdir(mode=0o700)
        elsewhere = Path(self.tmp.name) / "elsewhere"
        elsewhere.mkdir()
        (self.root / "v2").symlink_to(elsewhere)
        with self.assertRaisesRegex(stage.Refusal, "RUNTIME_DIRECTORY_UNSAFE"):
            stage.stage("v2", root=self.root, _source_dir=self.source)

    def test_stage_lock_contention_refuses(self):
        self.root.mkdir(mode=0o700)
        with stage._stage_lock(self.root):
            with self.assertRaisesRegex(stage.Refusal, "RUNTIME_STAGE_BUSY"):
                stage.stage("v2", root=self.root, _source_dir=self.source)

    def test_receipt_tamper_refuses_verification(self):
        stage.stage("v2", root=self.root, _source_dir=self.source)
        receipt_path = self.root / "v2" / "RUNTIME.json"
        original = json.loads(receipt_path.read_text())
        for key, bad in (
            ("bridge_sha256", "0" * 64),
            ("network_install_performed", True),
            ("production_acceptance", True),
        ):
            with self.subTest(key=key):
                tampered = dict(original)
                tampered[key] = bad
                receipt_path.write_text(json.dumps(tampered), encoding="utf-8")
                with self.assertRaisesRegex(stage.Refusal, "GENERATION_COLLISION"):
                    stage.verify("v2", root=self.root, _source_dir=self.source)
                receipt_path.write_text(json.dumps(original), encoding="utf-8")

    def test_parent_symlink_runtime_root_refuses_before_write(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        link = Path(self.tmp.name) / "runtime-link"
        link.symlink_to(outside, target_is_directory=True)
        escaped_root = link / "runtime"
        with self.assertRaisesRegex(stage.Refusal, "RUNTIME_ROOT_UNSAFE"):
            stage.stage("v2", root=escaped_root, _source_dir=self.source)
        self.assertFalse((outside / "runtime").exists())


    def test_precommit_bridge_probe_timeout_is_retryable_and_has_no_generation_effect(self):
        timeout = stage.subprocess.TimeoutExpired(["python", "bridge.py", "--help"], 15)
        with mock.patch.object(stage.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(stage.RetryableRefusal, "BRIDGE_PROBE_TIMEOUT"):
                stage.stage("v2", root=self.root, _source_dir=self.source)
        self.assertFalse((self.root / "v2").exists())

    def test_cli_reports_precommit_timeout_as_retryable_after_reconciliation(self):
        output = io.StringIO()
        argv = ["runtime_stage.py", "stage", "--generation", "v2"]
        with mock.patch.object(stage.sys, "argv", argv), \
             mock.patch.object(stage, "stage", side_effect=stage.RetryableRefusal("BRIDGE_PROBE_TIMEOUT")), \
             contextlib.redirect_stdout(output):
            self.assertEqual(stage.main(), 2)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["state"], "BRIDGE_PROBE_TIMEOUT")
        self.assertTrue(payload["retry_allowed"])
        self.assertEqual(payload["reconcile_action"], "verify")

    def test_post_rename_sync_failure_is_effect_unknown(self):
        real_fsync = stage.os.fsync

        def fail_directory_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("forced directory fsync failure")
            return real_fsync(fd)

        with mock.patch.object(stage.os, "fsync", side_effect=fail_directory_fsync):
            with self.assertRaisesRegex(stage.EffectUnknown, "RUNTIME_EFFECT_UNKNOWN"):
                stage.stage("v2", root=self.root, _source_dir=self.source)
        self.assertTrue((self.root / "v2").is_dir())
        self.assertEqual(
            stage.verify("v2", root=self.root, _source_dir=self.source)["state"],
            "RUNTIME_VERIFIED",
        )

    def test_receipt_and_source_are_private_regular_files(self):
        stage.stage("v2", root=self.root, _source_dir=self.source)
        target = self.root / "v2"
        for path in [target / "RUNTIME.json", *(target / "source").iterdir()]:
            info = path.lstat()
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(info.st_uid, os.getuid())
            self.assertEqual(stat.S_IMODE(info.st_mode) & 0o077, 0)


if __name__ == "__main__":
    unittest.main()