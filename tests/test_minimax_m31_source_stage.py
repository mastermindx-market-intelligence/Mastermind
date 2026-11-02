"""Regression for the source-only MiniMax M3.1 immutable-native stage consumer.

Never publishes/selects an installed generation, reads provider credentials,
starts a worker, or contacts an account. Uses the incumbent release builder.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROLLOUT = ROOT / "ops/native_fabric/quota_continuity/rollout"
PATCHES = ROOT / "ops/native_fabric/patches"
PREDECESSOR = "28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce"
CANDIDATE = "c66e4744ca788c081cdffc0ed52e559b6261b9914e806abbae28986edb6db7d4"


class MiniMaxM31SourceStage(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="minimax-m31-stage-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.baseline = self.root / "baseline"
        self.baseline.mkdir()
        p = subprocess.run(
            [sys.executable, str(ROLLOUT / "build_review_stage.py"),
             "--output", str(self.baseline)],
            cwd=ROOT, capture_output=True, text=True, timeout=25,
        )
        self.assertEqual(p.returncode, 0, p.stderr)

    def invoke(self, output):
        return subprocess.run(
            [sys.executable, str(PATCHES / "stage_minimax_m31_flash.py"),
             "--base-stage", str(self.baseline), "--output", str(output)],
            cwd=ROOT, capture_output=True, text=True, timeout=25,
        )

    def test_real_incumbent_source_stages_identical_reviewed_generation(self):
        output = self.root / "new"
        result = self.invoke(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        reported = json.loads(result.stdout)
        self.assertEqual(reported["candidate"], CANDIDATE)
        self.assertEqual(reported["predecessor"], PREDECESSOR)
        self.assertEqual(reported["members"], 102)
        self.assertEqual(reported["status"], "SOURCE_ONLY_NOT_PUBLISHED")
        manifest = json.loads((output / "native-manifest.json").read_text())
        receipt = json.loads((output / "SOURCE_STAGE_RECEIPT.json").read_text())
        baseline = json.loads((self.baseline / "native-manifest.json").read_text())
        changed = {k for k in manifest if manifest[k] != baseline[k]}
        self.assertEqual(changed, {
            "ext/pick.py", "ext/sub.sh", "ext/mm_codex_exec.sh",
            "ext/host_pick.py", "ext/placement_view.py"})
        self.assertEqual(receipt["candidate"], CANDIDATE)
        self.assertEqual(receipt["changed_members"], sorted(changed))
        self.assertEqual(json.loads((self.baseline / "native-manifest.json").read_text()),
                         baseline, "historical manifest changed")

    def test_altered_historical_source_fails_before_any_output_write(self):
        path = self.baseline / "native-code-stage/ext/sub.sh"
        path.write_bytes(path.read_bytes() + b"\n# forged historical source\n")
        out = self.root / "held"
        result = self.invoke(out)
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertIn("baseline file mismatch", result.stderr)
        self.assertFalse(out.exists(), "refusal must not leave published-looking stage")

    def test_source_stage_cannot_target_native_release_store(self):
        store = self.root / "native-code-releases"
        store.mkdir()
        output = store / "forbidden"
        result = self.invoke(output)
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertIn("source stage cannot target native release store", result.stderr)
        self.assertFalse(output.exists())

    def test_symlinked_output_parent_cannot_point_into_historical_source(self):
        alias = self.root / "input-alias"
        alias.symlink_to(self.baseline, target_is_directory=True)
        result = self.invoke(alias / "forbidden")
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertIn("source/output overlap", result.stderr)
        self.assertFalse((self.baseline / "forbidden").exists())

    def test_existing_output_is_never_overwritten(self):
        out = self.root / "already"
        out.mkdir()
        marker = out / "keep"
        marker.write_text("original")
        result = self.invoke(out)
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertIn("output already exists", result.stderr)
        self.assertEqual(marker.read_text(), "original")


if __name__ == "__main__":
    unittest.main()
