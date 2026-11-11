"""Exercise the proposal's Git object boundary using disposable local repositories."""
from pathlib import Path
import hashlib
import json
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import owner_source_support as support

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
        # Git versions differ when a requested promisor object is absent: some
        # report "missing", while others refuse with a nonzero exit status.
        # Inventory only local objects so the witness itself never requests it.
        def local_objects():
            return set(git(clone, "cat-file", "--batch-all-objects",
                           "--batch-check=%(objectname)").splitlines())

        before = local_objects()
        self.assertIn(self.commit.encode("ascii"), before)
        self.assertNotIn(oid, before)
        with self.assertRaises(RuntimeError):
            export_committed(clone, self.destination, self.commit, self.selected)
        after = local_objects()
        self.assertEqual(after, before)
        self.assertNotIn(oid, after)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_missing_blob_refusal_when_git_batch_check_exits_nonzero(self):
        original_run = subprocess.run
        refusals = []

        def refuse_missing_batch(arguments, **kwargs):
            if ("cat-file" in arguments and "--batch-all-objects" not in arguments
                    and any(arg.startswith("--batch-check") for arg in arguments)):
                self.assertEqual(kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
                self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
                self.assertTrue(kwargs["check"])
                refusals.append(arguments)
                raise subprocess.CalledProcessError(
                    128, arguments, stderr=b"fixture: missing promisor blob")
            return original_run(arguments, **kwargs)

        with patch.object(support.subprocess, "run", side_effect=refuse_missing_batch):
            self.test_missing_local_blob_refuses_without_lazy_fetch()
        self.assertEqual(len(refusals), 1)

    def test_unrelated_git_failure_still_refuses(self):
        with self.assertRaisesRegex(RuntimeError, "Source fixture git cat-file failed"):
            git(self.source, "cat-file", "--invalid-source-fixture-option")
        self.assertEqual(list(self.destination.iterdir()), [])


class CurrentSourceTests(unittest.TestCase):
    """The current owner is consumed as committed source, never patched in place."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hermes-current-source-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.adapter = self.root / "adapter"
        package = self.adapter / "integrations/hermes_application_fabric/qualification/application_owner_support"
        package.mkdir(parents=True)
        git(self.source, "init", "-q")
        git(self.source, "config", "user.name", "Hermes Source Fixture")
        git(self.source, "config", "user.email", "hermes-source-fixture@example.invalid")
        unchanged = ("config/capability_manifest.yml",
                     "config/provider_production_modes.v1.json",
                     "config/provider_workloads.v1.json",
                     "engine/fabric_inference_client.py",
                     "tests/test_fabric_service_identity.py")
        names = set(support.CHANGED) | set(support.TESTS) | set(unchanged)
        names.update(("lib/helper.py", "tests/__init__.py"))
        for name in names:
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((name + " committed fixture\n").encode())
        (self.source / "engine/provider_production_modes.py").write_bytes(
            b"qualified = True\napplication_allowed = True\n")
        # A replay through git apply would fail. The current mode must not invoke it.
        historical_patch = b"Historical proposal already incorporated.\n"
        (package / "a577-hermes-source-support.patch").write_bytes(historical_patch)
        contract = {"schema": "mastermind.hermes_owner_source_support.v1",
                    "owner_commit": support.OWNER_COMMIT,
                    "source_only": True, "operational_enrollment": False,
                    "patch_sha256": support.sha256(historical_patch),
                    "preimages": {name: None for name in support.CHANGED},
                    "postimages": {name: support.sha256((self.source / name).read_bytes())
                                   for name in support.CHANGED},
                    "unchanged_inputs": {}}
        for name in unchanged:
            raw = (self.source / name).read_bytes()
            contract["unchanged_inputs"][name] = hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\0" + raw,
                usedforsecurity=False).hexdigest()
        (package / "contract.json").write_text(json.dumps(contract))
        self.commit = self.commit_source()
        self.held = patch.object(support, "CURRENT_OWNER_COMMIT", self.commit)
        self.held.start()
        self.addCleanup(self.held.stop)
        self.destination = self.root / "exported"

    def commit_source(self):
        git(self.source, "add", ".")
        git(self.source, "commit", "--allow-empty", "-qm", "Disposable current source")
        return git(self.source, "rev-parse", "HEAD").decode().strip()

    def prepare(self):
        return support.prepare_current(self.source, self.adapter, self.destination)

    def test_current_exports_committed_support_without_replaying_the_proposal(self):
        (self.source / "engine/untracked.py").write_bytes(b"never export this\n")
        result = self.prepare()
        self.assertFalse(result["patch_applied"])
        self.assertFalse(result["runtime_enrollment"])
        self.assertEqual(result["owner_commit"], self.commit)
        self.assertTrue(result["original_source_unchanged"])
        self.assertFalse((self.destination / "engine/untracked.py").exists())
        self.assertEqual((self.destination / "engine/provider_production_modes.py").read_bytes(),
                         (self.source / "engine/provider_production_modes.py").read_bytes())
        self.assertEqual(git(self.source, "rev-parse", "HEAD").decode().strip(), self.commit)

    def test_current_refuses_another_clean_owner_commit(self):
        self.commit_source()
        with self.assertRaisesRegex(RuntimeError, "Current Macro source differs"):
            self.prepare()
        self.assertFalse(self.destination.exists())

    def test_current_refuses_dirty_tracked_source_before_export(self):
        (self.source / "engine/provider_production_modes.py").write_bytes(b"dirty source\n")
        with self.assertRaisesRegex(RuntimeError, "Source fixture git diff failed"):
            self.prepare()
        self.assertFalse(self.destination.exists())

    def test_current_refuses_committed_disabled_support_even_with_a_matching_root(self):
        target = self.source / "engine/provider_production_modes.py"
        target.write_bytes(target.read_bytes().replace(b"True", b"False"))
        changed = self.commit_source()
        with patch.object(support, "CURRENT_OWNER_COMMIT", changed):
            with self.assertRaisesRegex(RuntimeError, "Committed support postimage differs"):
                self.prepare()

    def test_current_refuses_changed_required_input_even_with_a_matching_root(self):
        (self.source / "engine/fabric_inference_client.py").write_bytes(b"changed client\n")
        changed = self.commit_source()
        with patch.object(support, "CURRENT_OWNER_COMMIT", changed):
            with self.assertRaisesRegex(RuntimeError, "Unchanged owner input differs"):
                self.prepare()


    def write_composed_contract(self, commit, *, postimages=None):
        package = self.adapter / "integrations/hermes_application_fabric/qualification/application_owner_support"
        historical = (package / "contract.json").read_bytes()
        contract = json.loads(historical)
        current = {"schema": "mastermind.hermes_owner_committed_support.v1",
            "owner_commit": commit, "previous_owner_commit": support.CURRENT_OWNER_COMMIT,
            "historical_contract_sha256": support.sha256(historical),
            "postimages": postimages or {name: support.sha256((self.source / name).read_bytes())
                                          for name in support.CHANGED},
            "unchanged_inputs": contract["unchanged_inputs"],
            "source_only": True, "operational_enrollment": False}
        (package / "attended-auto-current.json").write_text(json.dumps(current))
        return historical

    def test_composed_exports_its_actual_postimages_and_preserves_historical_contract(self):
        target = self.source / "engine/provider_production_modes.py"
        target.write_bytes(target.read_bytes() + b"attended_auto = True\n")
        composed = self.commit_source()
        historical = self.write_composed_contract(composed)
        with patch.object(support, "COMPOSED_OWNER_COMMIT", composed):
            result = support.prepare_current(self.source, self.adapter, self.destination, composed=True)
        self.assertEqual(result["owner_commit"], composed)
        self.assertEqual(result["source_context"], "committed_attended_auto")
        self.assertFalse(result["patch_applied"])
        self.assertFalse(result["runtime_enrollment"])
        self.assertEqual((self.destination / "engine/provider_production_modes.py").read_bytes(), target.read_bytes())
        path = self.adapter / "integrations/hermes_application_fabric/qualification/application_owner_support/contract.json"
        self.assertEqual(path.read_bytes(), historical)

    def test_composed_refuses_changed_factory_even_when_root_and_contract_owner_match(self):
        expected = {name: support.sha256((self.source / name).read_bytes()) for name in support.CHANGED}
        target = self.source / "engine/provider_production_modes.py"
        target.write_bytes(target.read_bytes() + b"unqualified_drift = True\n")
        composed = self.commit_source()
        self.write_composed_contract(composed, postimages=expected)
        with patch.object(support, "COMPOSED_OWNER_COMMIT", composed):
            with self.assertRaisesRegex(RuntimeError, "Committed support postimage differs"):
                support.prepare_current(self.source, self.adapter, self.destination, composed=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
