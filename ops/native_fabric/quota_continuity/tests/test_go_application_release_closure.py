"""The external component is a closed source artifact, never an installation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("go_application_review_stage", ROOT / "rollout/build_review_stage.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class ExternalComponentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source-root"
        self.output = Path(self.temp.name) / "stage"
        for rel in ("source/go_shim.py", "candidate/go_shim.py", *("candidate/" + name for name in BUILDER.GO_APPLICATION_DEPENDENCIES)):
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)

    def stage(self, output=None, stable_ext="/fixture/original/ext"):
        return BUILDER.stage_external_go_component(self.root, output or self.output, stable_ext)

    def test_exact_preimage_candidate_and_three_a_dependencies_are_bound(self):
        record = self.stage()
        bundle = self.output / "external-go-component"
        self.assertEqual(record, json.loads((bundle / "component.json").read_text()))
        self.assertEqual(record["destination_relative_to_stable_ext"], "go_shim/go_shim.py")
        self.assertEqual(record["installed_preimage_sha256"], "4a41548a757f763ed5210df96aff6c7148d25d9e192cd3d849e108e1e917d100")
        self.assertEqual(record["candidate_sha256"], hashlib.sha256((bundle / "go_shim.py").read_bytes()).hexdigest())
        self.assertEqual(set(record["dependencies"]), {"lease_broker.py", "go_lease_capability.py", "go_lease_gateway.py"})
        self.assertEqual(record["installation_state"], "HELD_REQUIRES_PROTECTED_RELEASE_AND_EXISTING_OWNER_INSTALLATION")
        self.assertFalse((self.output / "native-code-stage").exists())
        self.assertFalse((self.output / "native-manifest.json").exists())
        second = Path(self.temp.name) / "second"
        self.assertEqual(record, self.stage(second))
        self.assertEqual((bundle / "component.json").read_bytes(), (second / "external-go-component/component.json").read_bytes())

    def test_preimage_drift_refuses_before_any_artifact(self):
        path = self.root / "source/go_shim.py"
        path.write_bytes(path.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(ValueError, "preimage mismatch"):
            self.stage()
        self.assertFalse(self.output.exists())

    def test_candidate_dependency_and_output_aliases_are_refused(self):
        for rel in ("candidate/go_shim.py", "candidate/lease_broker.py"):
            path = self.root / rel
            raw = path.read_bytes()
            target = self.root / "target.py"
            target.write_bytes(raw)
            path.unlink()
            path.symlink_to(target)
            with self.assertRaises(ValueError):
                self.stage()
            self.assertFalse(self.output.exists())
            path.unlink()
            path.write_bytes(raw)
        target = Path(self.temp.name) / "unrelated"
        target.mkdir()
        self.output.mkdir()
        (self.output / "external-go-component").symlink_to(target)
        with self.assertRaises(ValueError):
            self.stage()
        self.assertEqual(list(target.iterdir()), [])

    def test_relative_or_traversing_installed_owner_names_are_not_bundled(self):
        for path in ("relative/ext", "/fixture/../elsewhere/ext"):
            with self.assertRaises(ValueError):
                self.stage(stable_ext=path)
        self.assertFalse(self.output.exists())

    def test_component_dependencies_match_exact_captured_native_stage(self):
        manifest = {}
        for name in BUILDER.GO_APPLICATION_DEPENDENCIES:
            source = self.root / "candidate" / name
            path = self.output / "native-code-stage/ext" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, path)
            manifest["ext/" + name] = hashlib.sha256(path.read_bytes()).hexdigest()
        record = BUILDER.stage_external_go_component(self.root, self.output, "/fixture/original/ext", staged_manifest=manifest)
        self.assertEqual(record["native_stage_dependencies"], {name: manifest["ext/" + name] for name in BUILDER.GO_APPLICATION_DEPENDENCIES})
        shutil.rmtree(self.output / "external-go-component")
        source = self.root / "candidate/lease_broker.py"
        source.write_bytes(source.read_bytes() + b"\n# changed after staging\n")
        with self.assertRaisesRegex(ValueError, "captured native stage"):
            BUILDER.stage_external_go_component(self.root, self.output, "/fixture/original/ext", staged_manifest=manifest)
        self.assertFalse((self.output / "external-go-component").exists())


if __name__ == "__main__":
    unittest.main()
