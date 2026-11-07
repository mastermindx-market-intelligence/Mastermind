"""Exercise the proposal's Git object boundary using disposable local repositories."""
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from owner_source_support import export_committed, git


class CommittedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hermes-source-materialization-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        git(self.source, "init", "-q")
        git(self.source, "config", "user.name", "Hermes Source Fixture")
        git(self.source, "config", "user.email", "hermes-source-fixture@example.invalid")
        git(self.source, "config", "uploadpack.allowFilter", "true")
        self.files = {"engine/module.py": b"committed module\n",
                      "lib/helper.py": b"committed helper\n",
                      "config/example.json": b"{}\n",
                      "tests/selected.py": b"committed test\n",
                      "tests/unselected.py": b"outside the selected closure\n"}
        for name, raw in self.files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (self.source / "lib/helper.py").chmod(0o755)
        self.commit = self.commit_source()
        self.destination = self.root / "exported"
        self.destination.mkdir()
        self.selected = ("engine", "lib", "config", "tests/selected.py")

    def commit_source(self):
        git(self.source, "add", ".")
        git(self.source, "commit", "-qm", "Disposable source fixture")
        return git(self.source, "rev-parse", "HEAD").decode().strip()

    def test_exports_committed_bytes_and_modes_without_worktree_or_untracked_data(self):
        (self.source / "engine/module.py").write_bytes(b"dirty worktree\n")
        (self.source / "engine/untracked.py").write_bytes(b"untracked\n")
        result = export_committed(self.source, self.destination, self.commit, self.selected)
        observed = {str(path.relative_to(self.destination)): path.read_bytes()
                    for path in self.destination.rglob("*") if path.is_file()}
        self.assertEqual(observed, {name: raw for name, raw in self.files.items()
                                    if name != "tests/unselected.py"})
        self.assertEqual(stat.S_IMODE((self.destination / "lib/helper.py").stat().st_mode), 0o755)
        self.assertFalse(result["lazy_fetch_permitted"])
        self.assertFalse(result["worktree_content_used"])
        self.assertEqual((self.source / "engine/module.py").read_bytes(), b"dirty worktree\n")
        self.assertEqual(git(self.source, "rev-parse", "HEAD").decode().strip(), self.commit)

    def test_refuses_a_committed_link_before_exporting_any_member(self):
        (self.source / "engine/link.py").symlink_to("module.py")
        commit = self.commit_source()
        with self.assertRaisesRegex(RuntimeError, "unsafe committed member"):
            export_committed(self.source, self.destination, commit, self.selected)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_missing_local_blob_refuses_without_lazy_fetch(self):
        clone = self.root / "partial"
        subprocess.run(["git", "-c", "gc.auto=0", "clone", "--no-checkout",
                        "--filter=blob:none", self.source.as_uri(), str(clone)],
                       check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
        oid = git(self.source, "rev-parse", self.commit + ":engine/module.py").strip()
        before = git(clone, "cat-file", "--batch-check", input_data=oid + b"\n")
        self.assertEqual(before, oid + b" missing\n")
        with self.assertRaisesRegex(RuntimeError, "not locally available"):
            export_committed(clone, self.destination, self.commit, self.selected)
        after = git(clone, "cat-file", "--batch-check", input_data=oid + b"\n")
        self.assertEqual(after, before)
        self.assertEqual(list(self.destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
