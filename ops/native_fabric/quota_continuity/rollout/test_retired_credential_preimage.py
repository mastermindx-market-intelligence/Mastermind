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
        # Reproduce native_fabric's sibling Grok overlay source in scratch.
        # Otherwise the builder fails before this credential-safety fixture.
        self.root = Path(self.temp.name) / "quota_continuity"
        self.root.mkdir()
        grok = self.root.parent / "grok47" / "overlay"
        grok.mkdir(parents=True)
        for name, expected in builder.GROK47_MERGED_SOURCE_DIGESTS.items():
            raw = (ROOT.parent / "grok47" / "overlay" / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            (grok / name).write_bytes(raw)
        for directory in ("source", "candidate", "rollout"):
            (self.root / directory).mkdir()
        for name in builder.BASE_FILES | {"pool_launcher.sh"}:
            evidence_name = builder.PREIMAGE_ONLY.get(name, name)
            shutil.copyfile(ROOT / "source" / evidence_name,
                            self.root / "source" / evidence_name)
        for name in builder.BASE_FILES | builder.ADDITIONS | {"pool_launcher.sh"}:
            source = ROOT / "candidate" / name
            if source.is_file():
                shutil.copyfile(source, self.root / "candidate" / name)
        for name in ("build_review_stage.py", "native-preimages.json"):
            shutil.copyfile(HERE / name, self.root / "rollout" / name)

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
