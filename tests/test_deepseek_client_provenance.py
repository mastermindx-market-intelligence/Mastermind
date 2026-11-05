"""Offline provenance checks for the selectively reused DeepSeek client code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


DONOR = Path(__file__).resolve().parents[1] / "app/mastermind_os/src/vendor/deepseek"


class DeepSeekClientProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((DONOR / "manifest.json").read_text(encoding="utf-8"))

    def test_exact_revision_and_allowlist(self) -> None:
        self.assertEqual(self.manifest["repository"], "deepseek-ai/deepseek-harness")
        self.assertEqual(self.manifest["revision"], "687f282e8625c6b8d11ff58211a90524be2e4317")
        self.assertEqual(
            [entry["local_path"] for entry in self.manifest["files"]],
            ["keyboard-composition.ts", "incremental-markdown.ts", "use-scroll-follow.ts"],
        )

    def test_exact_donor_bytes(self) -> None:
        for entry in self.manifest["files"]:
            with self.subTest(source=entry["upstream_path"]):
                self.assertEqual(entry["modifications"], "NONE")
                self.assertEqual(hashlib.sha256((DONOR / entry["local_path"]).read_bytes()).hexdigest(), entry["sha256"])

    def test_complete_upstream_mit_notice(self) -> None:
        license_entry = self.manifest["license"]
        content = (DONOR / license_entry["local_path"]).read_bytes()
        self.assertEqual(hashlib.sha256(content).hexdigest(), license_entry["sha256"])
        self.assertIn(b"Permission is hereby granted", content)
        self.assertIn(b"THE SOFTWARE IS PROVIDED", content)


    def test_distribution_preserves_licenses(self) -> None:
        app = DONOR.parents[2]
        distribution = self.manifest["distribution"]
        self.assertEqual(
            (app / distribution["license_path"]).read_bytes(),
            (DONOR / "LICENSE").read_bytes(),
        )
        notices = (app / distribution["dependency_notices_path"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(notices).hexdigest(),
            distribution["dependency_notices_sha256"],
        )
        self.assertEqual(distribution["new_runtime_dependency_count"], 58)
        self.assertIn(b"mdast-util-from-markdown@2.0.3", notices)
        self.assertIn(b"micromark-extension-gfm@3.0.0", notices)


if __name__ == "__main__":
    unittest.main()
