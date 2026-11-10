"""Exact-base native source distribution; no live T3 or existing worktree writes."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_t3_agent_bus import materialize_source, qualify_package


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class NativePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package = self.root / "package"
        self.package.mkdir()
        self.archive = self.root / "base.tar"
        self.output = self.root / "overlay"
        self.license = b"MIT License\nCopyright (c) Test fixture\n"
        self.old = b"old\n"
        self.new = b"new\n"
        self.patch = b"diff --git a/src/value.txt b/src/value.txt\n--- a/src/value.txt\n+++ b/src/value.txt\n@@ -1 +1 @@\n-old\n+new\n"
        self.write_archive()
        self.manifest = {
            "schema": "mastermind.t3-agent-bus-native-overlay.v1", "upstream_repository": "pingdotgg/t3code",
            "upstream_revision": "a" * 40, "base_archive_sha256": digest(self.archive.read_bytes()),
            "base_archive_paths": ["LICENSE", "src/value.txt"], "patch_sha256": digest(self.patch),
            "license_sha256": digest(self.license), "files": [{"path": "src/value.txt",
            "before_sha256": digest(self.old), "after_sha256": digest(self.new)}],
        }
        self.write_package()

    def write_archive(self, extras=()):
        with tarfile.open(self.archive, "w") as archive:
            for name, raw in [("LICENSE", self.license), ("src/value.txt", self.old)]:
                info = tarfile.TarInfo(name); info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
            for info, raw in extras:
                archive.addfile(info, None if raw is None else io.BytesIO(raw))

    def write_package(self):
        (self.package / "manifest.json").write_text(json.dumps(self.manifest))
        (self.package / "native.patch").write_bytes(self.patch)
        (self.package / "UPSTREAM_LICENSE").write_bytes(self.license)

    def build(self):
        return materialize_source(package=self.package, archive=self.archive, output=self.output)

    def test_actual_git_apply_produces_exact_source_overlay_and_not_a_runtime(self):
        result = self.build()
        self.assertFalse(result["installed"])
        self.assertEqual(result["runtime_effects"], "none")
        self.assertEqual(result["output_kind"], "affected-source-files-only")
        self.assertEqual((self.output / "src/value.txt").read_bytes(), self.new)
        self.assertEqual((self.output / "LICENSE").read_bytes(), self.license)
        self.assertEqual(json.loads((self.output / "source-build.json").read_text()), result)
        self.assertFalse((self.output / ".git").exists())
        self.assertEqual(self.archive.read_bytes()[:1], b"L")

    def test_package_and_two_independent_builds_are_deterministic(self):
        first = self.build()
        second_path = self.root / "overlay-two"
        second = materialize_source(package=self.package, archive=self.archive, output=second_path)
        self.assertEqual(first, second)
        self.assertEqual((self.output / "source-build.json").read_bytes(), (second_path / "source-build.json").read_bytes())

    def test_existing_directory_or_file_is_never_replaced(self):
        for is_dir in (True, False):
            self.output = self.root / ("existing-dir" if is_dir else "existing-file")
            if is_dir:
                self.output.mkdir(); (self.output / "sentinel").write_bytes(b"retain")
            else:
                self.output.write_bytes(b"retain")
            with self.assertRaises(FileExistsError):
                self.build()
            self.assertEqual((self.output / "sentinel" if is_dir else self.output).read_bytes(), b"retain")

    def test_symlink_destination_cannot_redirect_source_writes(self):
        target = self.root / "unrelated"; target.mkdir()
        self.output.symlink_to(target, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(list(target.iterdir()), [])

    def test_aliased_parent_is_refused(self):
        target = self.root / "real"; target.mkdir()
        alias = self.root / "alias"; alias.symlink_to(target, target_is_directory=True)
        self.output = alias / "output"
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((target / "output").exists())

    def test_tampered_archive_is_rejected_before_any_output(self):
        self.archive.write_bytes(self.archive.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "exact reviewed"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_tampered_patch_or_license_is_rejected_before_any_output(self):
        for name in ("native.patch", "UPSTREAM_LICENSE"):
            with self.subTest(name=name):
                self.write_package()
                p = self.package / name; p.write_bytes(p.read_bytes() + b"tampered")
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse(self.output.exists())

    def test_preimage_mismatch_cannot_reach_apply(self):
        self.manifest["files"][0]["before_sha256"] = "0" * 64; self.write_package()
        with patch("scripts.build_t3_agent_bus.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "preimage"):
                self.build()
        run.assert_not_called(); self.assertFalse(self.output.exists())

    def test_postimage_mismatch_never_creates_a_success_receipt(self):
        self.manifest["files"][0]["after_sha256"] = "0" * 64; self.write_package()
        with self.assertRaisesRegex(ValueError, "postimage"):
            self.build()
        self.assertFalse((self.output / "source-build.json").exists())
        self.assertTrue(self.output.exists())  # Original partial output retained, not silently retried.

    def test_patch_escape_or_duplicate_target_is_refused(self):
        for path in ("../escape", "/absolute", ".git/config", "src/../escape", "node_modules/pkg"):
            with self.subTest(path=path):
                original = self.patch
                self.patch = original.replace(b"src/value.txt", path.encode())
                self.manifest["patch_sha256"] = digest(self.patch); self.write_package()
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse(self.output.exists())
                self.patch = original
        self.patch += self.patch; self.manifest["patch_sha256"] = digest(self.patch); self.write_package()
        with self.assertRaises(ValueError):
            self.build()

    def test_duplicate_manifest_keys_cannot_shadow_reviewed_values(self):
        p = self.package / "manifest.json"
        p.write_text('{"schema":"first","schema":"second"}')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_symlink_input_is_refused_even_with_matching_content(self):
        actual = self.root / "real-patch"; actual.write_bytes(self.patch)
        target = self.package / "native.patch"; target.unlink(); target.symlink_to(actual)
        with self.assertRaises(OSError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_archive_links_unknown_members_and_traversal_are_rejected(self):
        for name, kind in [("src/link", tarfile.SYMTYPE), ("../outside", tarfile.REGTYPE),
                           ("unlisted", tarfile.REGTYPE), ("src/value.txt", tarfile.REGTYPE)]:
            with self.subTest(name=name, kind=kind):
                info = tarfile.TarInfo(name); info.type = kind; info.linkname = "/tmp/outside" if kind == tarfile.SYMTYPE else ""
                self.write_archive([(info, None if kind == tarfile.SYMTYPE else b"")])
                self.manifest["base_archive_sha256"] = digest(self.archive.read_bytes()); self.write_package()
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse(self.output.exists())

    def test_missing_archive_file_is_rejected(self):
        with tarfile.open(self.archive, "w") as archive:
            info = tarfile.TarInfo("LICENSE"); info.size = len(self.license); archive.addfile(info, io.BytesIO(self.license))
        self.manifest["base_archive_sha256"] = digest(self.archive.read_bytes()); self.write_package()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_committed_package_has_qualified_hashes_and_no_runtime_files(self):
        package = Path(__file__).resolve().parents[1] / "integrations/t3_agent_bus"
        manifest, patch_bytes = qualify_package(package)
        self.assertEqual(len(manifest["files"]), 13)
        self.assertEqual(manifest["upstream_revision"], "0770446869d247a8b28c27d7ed93f47f8ff0c1e4")
        self.assertEqual(digest(patch_bytes), manifest["patch_sha256"])
        self.assertTrue(all(row["path"].startswith(("apps/server/src/", "packages/contracts/src/")) for row in manifest["files"]))


if __name__ == "__main__":
    unittest.main()
