"""Hermetic mutation tests of the static capsule checker, not I3 signal tests."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("i3_capsule_verify", ROOT / "verify_evidence.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CapsuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="i3-capsule-test-")
        self.root = Path(self.temp.name) / "capsule"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns("__pycache__"))
    def tearDown(self) -> None:
        self.temp.cleanup()
    def mutate(self, name: str, field: str, value: object) -> None:
        p = self.root / name
        data = json.loads(p.read_text()); data[field] = value
        p.write_text(json.dumps(data, indent=2) + "\n")
        m = self.root / "PACKAGE_MANIFEST.json"
        manifest = json.loads(m.read_text())
        manifest["files"][name] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
        m.write_text(json.dumps(manifest))
    def test_original_capsule(self) -> None:
        result = module.verify(self.root)
        self.assertEqual(result["capsule_integrity"], "PASS")
        self.assertIs(result["i3_acceptance"], False)
    def test_changed_response_bytes(self) -> None:
        p = self.root / "evidence/aapl_unlinked_assets.response.json"
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaises(module.EvidenceError): module.verify(self.root)
    def test_self_promotion_even_with_rehashed_manifest(self) -> None:
        self.mutate("evidence/CAPTURE_BOUNDARY.json", "production_emitted", True)
        with self.assertRaisesRegex(module.EvidenceError, "unearned capability"): module.verify(self.root)
    def test_development_cannot_become_holdout(self) -> None:
        self.mutate("evidence/CAPTURE_BOUNDARY.json", "heldout", True)
        with self.assertRaisesRegex(module.EvidenceError, "development exposure"): module.verify(self.root)
    def test_failures_cannot_disappear(self) -> None:
        (self.root / "evidence/pytest-attempt-1.json").unlink()
        with self.assertRaises(module.EvidenceError): module.verify(self.root)
    def test_comparator_cannot_self_admit(self) -> None:
        self.mutate("COMPARATOR_DEFINITION_CANDIDATE.json", "admitted", True)
        with self.assertRaisesRegex(module.EvidenceError, "self-admitted"): module.verify(self.root)

if __name__ == "__main__": unittest.main()
