"""Temporary Git fixtures for read-only Paper design link impact scanning."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import paper_link_reference_audit as scan

INVENTORY = json.loads((ROOT / "docs/paper_migrations/MASTERMIND_PAGES_INVENTORY_2026-10-22.json").read_text(encoding="utf-8"))


class LinkAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "fixture"
        self.root.mkdir()
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, data):
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(data, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", name], check=True)

    def test_known_page_exact_url_and_raw_id_are_observed(self):
        self.put("README.md", "https://app.paper.design/file/01M2WGNCX9475G79JRKJTCM08P/p-N-1\n")
        self.put("src/route.ts", 'const fid = "01M2WGNCX9475G79JRKJTCM08P";\n')
        result = scan.run(INVENTORY, [f"fixture={self.root}"])
        self.assertEqual(result["total_references"], 2)
        self.assertEqual(result["repositories"][0]["files_scanned"], 2)
        refs = result["repositories"][0]["references"]
        self.assertEqual(refs[0]["page_ids_near_reference"], ["p-N-1"])
        self.assertEqual(refs[1]["classification"], "FILE_ID_ONLY_REVIEW_REQUIRED")
        self.assertEqual(result["classification"], "READ_ONLY_LINK_INVENTORY_NOT_REWRITE_AUTHORITY")

    def test_unsupported_page_and_p19_are_held(self):
        self.put("old.md", "file/01M2WGNCX9475G79JRKJTCM08P/p-R-0\n"
                 "file/01M2WGNCX9475G79JRKJTCM08P/p-19-0\n")
        x = scan.run(INVENTORY, [f"f={self.root}"])
        classes = x["repositories"][0]["counts_by_classification"]
        self.assertEqual(classes["UNKNOWN_OR_HISTORICAL_PAGE_REVIEW_REQUIRED"], 1)
        self.assertEqual(classes["UNRESOLVED_PAGE_HISTORY_REVIEW_REQUIRED"], 1)

    def test_untracked_binary_and_symlink_never_scanned(self):
        self.put("tracked.md", "01M2WGNCX9475G79JRKJTCM08P")
        self.put("ignored.bin", "01M2WGNCX9475G79JRKJTCM08P")
        (self.root / "untracked.md").write_text("01M2WGNCX9475G79JRKJTCM08P")
        self.root.joinpath("linked.md").symlink_to(self.root / "tracked.md")
        subprocess.run(["git", "-C", str(self.root), "add", "linked.md"], check=True)
        res = scan.run(INVENTORY, [f"f={self.root}"])
        self.assertEqual(res["total_references"], 1)
        self.assertEqual(res["files_skipped_total"], 1)
        self.assertEqual(res["repositories"][0]["skipped_files"][0]["reason"], "SYMLINK")

    def test_no_generic_folder_scan_and_wrong_file_refused(self):
        with self.assertRaises(scan.AuditError):
            scan.run(INVENTORY, [f"wrong={Path(self.tmp.name)}"])
        changed = dict(INVENTORY, source_file_id="incorrect")
        with self.assertRaises(scan.AuditError):
            scan.run(changed, [f"f={self.root}"])
        with self.assertRaises(scan.AuditError):
            scan.run(INVENTORY, [f"f={self.root}", f"f={self.root}"])

    def test_cli_cannot_write_report_into_scanned_repo(self):
        self.put("README.md", "01M2WGNCX9475G79JRKJTCM08P")
        cli = ROOT / "scripts/paper_link_reference_audit.py"
        inv = ROOT / "docs/paper_migrations/MASTERMIND_PAGES_INVENTORY_2026-10-22.json"
        forbidden = self.root / "report.json"
        result = subprocess.run([sys.executable, str(cli), "--inventory", str(inv),
                                 "--root", f"fixture={self.root}", "--out", str(forbidden)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(forbidden.exists())
        self.assertIn("PAPER_LINK_AUDIT_REFUSED", result.stderr)

    def test_does_not_modify_tracked_files(self):
        target = 'file/01M2WGNCX9475G79JRKJTCM08P/p-21-0\n'
        self.put("info.md", target)
        scan.run(INVENTORY, [f"f={self.root}"])
        self.assertEqual((self.root / "info.md").read_text(), target)
        status = subprocess.run(["git", "-C", str(self.root), "diff", "--", "info.md"],
                                capture_output=True, text=True, check=True)
        self.assertFalse(status.stdout)


if __name__ == "__main__":
    unittest.main()
