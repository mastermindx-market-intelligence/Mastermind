"""Inert source staging, with no privileged install or provider effects."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import unittest
from unittest.mock import patch
import zipfile

from ops.executive_os import capacity_host_artifacts as owner


class HermesAttendedProjectionTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init", "-q")
        for name in ("config/owner.json", "engine/__init__.py", "lib/__init__.py"):
            path = self.source / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("{}\n" if name.endswith(".json") else 'raise RuntimeError("source must not execute")\n')
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.archive = self.root / "source.zip"
        self.commitment = owner.build_hermes_attended_source_projection(
            self.source, self.archive, commit=self.commit)
        self.stage = self.root / "stage"
        (self.stage / owner.HERMES_ATTENDED_COMMITMENT).parent.mkdir(parents=True)
        self.commitment_path = self.stage / owner.HERMES_ATTENDED_COMMITMENT
        self.write_commitment()
        self.published = Path("/Library/Application Support/MastermindExecutive/releases") / ("a" * 40)

    def git(self, *args):
        result = subprocess.run(["/usr/bin/git", "-C", str(self.source), *args],
                                capture_output=True, text=True, check=True)
        return result.stdout

    def write_commitment(self):
        self.commitment_path.write_bytes(owner.canonical_json(self.commitment) + b"\n")

    def stage_sources(self):
        return owner.materialize_hermes_attended_source_projection(
            self.archive, release_root=self.stage, published_release_root=self.published,
            adapter_package_sha256="b" * 64)

    def test_exact_git_sources_stage_without_git_or_python_execution(self):
        (self.source / "engine/__init__.py").write_text("uncommitted = True\n")
        with patch.object(owner, "_git", side_effect=AssertionError("privileged Git executed")):
            result = self.stage_sources()
        self.assertEqual(result["commit"], self.commit)
        installed = self.stage / owner.HERMES_ATTENDED_SOURCE_SUFFIX
        self.assertEqual((installed / "engine/__init__.py").read_text(),
                         'raise RuntimeError("source must not execute")\n')
        raw = (self.stage / owner.HERMES_ATTENDED_INVENTORY_SUFFIX).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), result["dependency_inventory"]["sha256"])
        inventory = json.loads(raw)
        self.assertEqual([row["path"] for row in inventory["roots"]], result["import_roots"])
        self.assertTrue(all(path.startswith(str(self.published)) for path in result["import_roots"]))
        self.assertEqual(stat.S_IMODE((installed / "engine/__init__.py").stat().st_mode), 0o644)

    def test_changed_archive_refuses_before_creating_dependency_tree(self):
        self.archive.write_bytes(self.archive.read_bytes() + b"changed")
        with self.assertRaisesRegex(owner.CapacityHostArtifactError, "ARCHIVE_MISMATCH"):
            self.stage_sources()
        self.assertFalse((self.stage / "native-dependencies").exists())

    def test_same_destination_is_never_overwritten_or_repaired(self):
        self.stage_sources()
        path = self.stage / owner.HERMES_ATTENDED_SOURCE_SUFFIX / "engine/__init__.py"
        path.write_text("already_published_candidate = True\n")
        with self.assertRaisesRegex(owner.CapacityHostArtifactError, "STAGE_OCCUPIED"):
            self.stage_sources()
        self.assertEqual(path.read_text(), "already_published_candidate = True\n")

    def test_exact_build_is_deterministic_and_ignores_uncommitted_bytes(self):
        (self.source / "lib/__init__.py").write_text("uncommitted = True\n")
        output = self.root / "second.zip"
        rebuilt = owner.build_hermes_attended_source_projection(self.source, output, commit=self.commit)
        self.assertEqual(rebuilt, self.commitment)
        self.assertEqual(output.read_bytes(), self.archive.read_bytes())

    def test_duplicate_extra_traversal_or_link_members_cannot_be_staged(self):
        original = self.archive.read_bytes()
        for mutation in ("duplicate", "extra", "traversal", "symlink"):
            with self.subTest(mutation=mutation):
                data = io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(data, "w") as dest:
                    for index, entry in enumerate(source.infolist()):
                        payload = source.read(entry)
                        if mutation == "traversal" and index == 1:
                            entry.filename = "payload/../outside.py"
                        if mutation == "symlink" and index == 1:
                            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                        dest.writestr(entry, payload)
                    if mutation in {"duplicate", "extra"}:
                        name = "manifest.json" if mutation == "duplicate" else "payload/engine/extra.py"
                        dest.writestr(owner._attended_zip_member(name, 0o644), b"extra")
                raw = data.getvalue()
                self.archive.write_bytes(raw)
                # Even an independently approved outer hash cannot make the
                # format accept an undeclared member or unsafe file type.
                self.commitment.update(archive_sha256=hashlib.sha256(raw).hexdigest(), archive_size=len(raw))
                self.write_commitment()
                with self.assertRaises(owner.CapacityHostArtifactError):
                    self.stage_sources()
                self.assertFalse((self.stage / "native-dependencies").exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "platform has no FIFO")
    def test_fifo_input_refuses_without_waiting_for_a_writer(self):
        fifo = self.root / "fifo.zip"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(owner.CapacityHostArtifactError, "SOURCE_METADATA_INVALID"):
            owner.check_hermes_attended_source_projection(fifo, self.commitment_path)


if __name__ == "__main__":
    unittest.main()
