import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

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
        (self.source / "bridge.py").write_text(
            "import argparse\nargparse.ArgumentParser().parse_args()\n", encoding="utf-8"
        )

    def tearDown(self):
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