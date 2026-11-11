"""The obsolete secret-stdout helper remains evidence, never deployable fallback."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("credential_preimage_builder", HERE / "build_review_stage.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class RetiredCredentialPreimageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        repository = Path(self.temp.name)
        self.root = repository / "ops/native_fabric/quota_continuity"
        self.root.mkdir(parents=True)
        grok = self.root.parent / "grok47" / "overlay"
        grok.mkdir(parents=True)
        for name, expected in builder.GROK47_MERGED_SOURCE_DIGESTS.items():
            raw = (ROOT.parent / "grok47" / "overlay" / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            (grok / name).write_bytes(raw)
        # The real builder qualifies its locked pure-YAML artifact from the
        # repository root; preserve that production-relative layout in scratch.
        lock = json.loads((ROOT / "candidate/paid_pyyaml_provenance.json").read_text())["lock_path"]
        target = repository / lock
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT.parents[2] / lock, target)
        for directory in ("source", "candidate", "rollout"):
            (self.root / directory).mkdir()
        for name in builder.BASE_FILES | {"pool_launcher.sh", "go_shim.py"}:
            evidence_name = builder.PREIMAGE_ONLY.get(name, name)
            shutil.copyfile(ROOT / "source" / evidence_name,
                            self.root / "source" / evidence_name)
        for name in builder.BASE_FILES | builder.ADDITIONS | {"pool_launcher.sh", "go_shim.py"}:
            source = ROOT / "candidate" / name
            if source.is_file():
                shutil.copyfile(source, self.root / "candidate" / name)
        for name in ("build_review_stage.py", "native-preimages.json"):
            shutil.copyfile(HERE / name, self.root / "rollout" / name)
        retained = Path("rollout/preimages/glm_application_core_5c3d")
        (self.root / retained).mkdir(parents=True)
        for name, expected in {
            "go_lease_capability.py": "d8562f38a397900bd851ddbe8bb27f511fcefc2bcd2af6ae1eea5d55d15c5940",
            "go_lease_gateway.py": "adad5ea3bcfd091730b92707d1ad231f5566cb200b5ffedfe41ef086aab86949",
            "lease_broker.py": "0bbf1ca05b655c30e895cebf63c914cbf97f9d17fc8b3e55c852fd4652ed8807",
        }.items():
            raw = (ROOT / retained / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            (self.root / retained / name).write_bytes(raw)

    def build(self):
        return subprocess.run([sys.executable, str(self.root / "rollout/build_review_stage.py")],
                              text=True, capture_output=True)

    def test_publishes_secure_overlay_and_preserves_exact_nonimportable_evidence(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = (self.root / "source/bailian_keys.py.preimage").read_bytes()
        inventory = json.loads((self.root / "rollout/native-preimages.json").read_text())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), inventory["files"]["bailian_keys.py"])
        self.assertFalse((self.root / "source/bailian_keys.py").exists())
        published = (self.root / "rollout/native-code-stage/ext/bailian_keys.py").read_bytes()
        self.assertEqual(published, (self.root / "candidate/bailian_keys.py").read_bytes())
        self.assertNotEqual(published, raw)

    def test_missing_secure_overlay_cannot_deploy_retired_helper(self):
        (self.root / "candidate/bailian_keys.py").unlink()
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing explicit regular code dependency: bailian_keys.py", result.stderr)
        self.assertFalse((self.root / "rollout/native-code-stage/ext/bailian_keys.py").exists())

    def test_changed_preimage_refuses_publication_despite_valid_overlay(self):
        with (self.root / "source/bailian_keys.py.preimage").open("ab") as handle:
            handle.write(b"\n# changed evidence\n")
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("installed preimage mismatch: bailian_keys.py", result.stderr)
        self.assertFalse((self.root / "rollout/native-code-stage/ext/bailian_keys.py").exists())


if __name__ == "__main__":
    unittest.main()
