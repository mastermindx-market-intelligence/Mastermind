"""Stdlib-only boundary checks for the diagnostic harness's static byte lookup."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mastermind_loopback_harness import trusted_static_assets


class StaticAssetBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="auction-static-boundary-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "static"
        self.root.mkdir()
        (self.root / "nested").mkdir()
        (self.root / "nested/style.css").write_bytes(b"body{color:blue}")
        (self.root / "font.WOFF2").write_bytes(b"font-bytes")
        (self.root / "private.json").write_bytes(b"not-an-approved-static-type")
        (self.root / "page.html").write_bytes(b"not-served-by-the-static-catch-all")

    def test_only_approved_files_are_snapshotted_with_correct_types(self):
        assets = trusted_static_assets(self.root)
        self.assertEqual(set(assets), {"nested/style.css", "font.WOFF2"})
        self.assertEqual(assets["nested/style.css"], (b"body{color:blue}", "text/css"))
        self.assertEqual(assets["font.WOFF2"], (b"font-bytes", "font/woff2"))
        with self.assertRaises(TypeError):
            assets["injected.css"] = (b"new", "text/css")

    def test_resolved_file_and_directory_symlinks_cannot_escape_root(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "secret.css").write_bytes(b"outside-root")
        (self.root / "escape.css").symlink_to(outside / "secret.css")
        (self.root / "escape-dir").symlink_to(outside, target_is_directory=True)
        (self.root / "inside-alias.css").symlink_to(self.root / "nested/style.css")
        (self.root / "disguised.css").symlink_to(self.root / "private.json")
        (self.root / "broken.css").symlink_to(outside / "missing.css")
        assets = trusted_static_assets(self.root)
        self.assertEqual(set(assets), {"nested/style.css", "font.WOFF2", "inside-alias.css"})
        self.assertEqual(assets["inside-alias.css"], (b"body{color:blue}", "text/css"))
        self.assertNotIn(b"outside-root", [payload[0] for payload in assets.values()])

    def test_request_keys_are_literal_memory_lookups_after_source_changes(self):
        assets = trusted_static_assets(self.root)
        (self.root / "nested/style.css").write_bytes(b"changed-after-snapshot")
        (self.root / "later.css").write_bytes(b"not-in-startup-snapshot")
        invalid = ["../outside/secret.css", "../static/nested/style.css", "/nested/style.css",
                   "nested/../font.WOFF2", "%2e%2e/outside/secret.css", "nested%2fstyle.css",
                   "nested\\style.css", "nested/style.css\x00", "nested/style.css?x=1",
                   "private.json", "page.html", "nested", "later.css"]
        with mock.patch.object(Path, "resolve", side_effect=AssertionError("No request-time resolve")), \
             mock.patch.object(Path, "is_file", side_effect=AssertionError("No request-time stat")), \
             mock.patch.object(Path, "read_bytes", side_effect=AssertionError("No request-time file read")):
            self.assertEqual(assets.get("nested/style.css"), (b"body{color:blue}", "text/css"))
            for key in invalid:
                with self.subTest(key=key):
                    self.assertIsNone(assets.get(key))


if __name__ == "__main__":
    unittest.main()
