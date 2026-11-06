"""Hermetic selected-generation profile tests; no host worker/provider effects."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

PROFILE = Path(__file__).resolve().parent
PKG = PROFILE.parent
OWNER = PKG.parent / "experiential53"
sys.path.insert(0, str(PROFILE))
sys.path.insert(0, str(PKG))
import qualify_m2_current as q
import experiential_bridge as bridge


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class M2SourceOnlyQualification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.m = q.manifest_read(PROFILE / "profile_manifest.json")

    def selected_fixture(self, *, moved=False):
        store = self.root / "native-code-releases"
        ext = store / self.m["selected_generation"] / "ext"
        ext.mkdir(parents=True)
        raw = (PROFILE / "fixtures" / "selection_9691.json").read_bytes()
        (store / "CURRENT.json").write_bytes(
            raw if not moved else b'{"schema":"native-code-selection.v1","generation":"changed"}\n')
        for name in q.NAMES:
            (ext / name).write_text("wrong installed source\n")
        return ext

    def test_exact_manifest_seals_reviewed_source(self):
        self.assertEqual(self.m["status"], "source_candidate_not_installed")
        self.assertEqual(self.m["selected_sequence"], 30)
        self.assertEqual(
            sha(PROFILE / "fixtures" / "selection_9691.json"),
            self.m["current_selection_sha256"])
        self.assertEqual(sha(PKG / "experiential_bridge.py"), self.m["bridge_sha256"])
        self.assertEqual(set(self.m["preimages_sha256"]), set(q.NAMES))
        self.assertEqual(set(self.m["postimages_sha256"]), set(q.NAMES))
        for name, digest in self.m["patches_sha256"].items():
            self.assertEqual(sha(PROFILE / "patches" / name), digest)
        for name, digest in self.m["owner_modules_sha256"].items():
            self.assertEqual(sha(OWNER / name), digest)
        self.assertEqual(
            set(self.m["owner_modules_sha256"]),
            {"experiential_pin.py", "experiential_transport.py"})

    def test_tampered_manifest_refused(self):
        tmp = self.root / "manifest.json"
        altered = dict(self.m, selected_sequence="30")
        tmp.write_text(json.dumps(altered))
        with self.assertRaises(q.compose.CompositionRefused):
            q.manifest_read(tmp)

    def test_current_selection_move_refused_without_output(self):
        ext = self.selected_fixture(moved=True)
        output = self.root / "candidate"
        with self.assertRaises(q.compose.CompositionRefused) as cm:
            q.qualify(installed_ext=ext, owner_modules_root=OWNER, output=output)
        self.assertIn("PROFILE_PREIMAGE_MISMATCH", str(cm.exception))
        self.assertFalse(output.exists())

    def test_wrong_selected_generation_source_refused(self):
        ext = self.root / "native-code-releases" / "different" / "ext"
        ext.mkdir(parents=True)
        with self.assertRaises(q.compose.CompositionRefused) as cm:
            q.qualify(installed_ext=ext, owner_modules_root=OWNER,
                      output=self.root / "candidate")
        self.assertIn("PROFILE_GENERATION_IDENTITY_REFUSED", str(cm.exception))

    def test_changed_native_file_refused_without_output(self):
        ext = self.selected_fixture()
        before = {name: sha(ext / name) for name in q.NAMES}
        output = self.root / "candidate"
        with self.assertRaises(q.compose.CompositionRefused) as cm:
            q.qualify(installed_ext=ext, owner_modules_root=OWNER, output=output)
        self.assertIn("PROFILE_PREIMAGE_MISMATCH", str(cm.exception))
        self.assertFalse(output.exists())
        self.assertEqual(before, {name: sha(ext / name) for name in q.NAMES})

    def test_writing_into_original_generation_refused(self):
        ext = self.selected_fixture()
        with self.assertRaises(q.compose.CompositionRefused) as cm:
            q.qualify(installed_ext=ext, owner_modules_root=OWNER,
                      output=ext / "candidate")
        self.assertIn("PROFILE_OUTPUT_OVERLAP_REFUSED", str(cm.exception))
        self.assertFalse((ext / "candidate").exists())

    def test_tampered_patch_file_refused(self):
        patch_name = "fabric_task.py.patch"
        path = self.root / patch_name
        path.write_bytes((PROFILE / "patches" / patch_name).read_bytes() + b"#tampered\n")
        with self.assertRaises(q.compose.CompositionRefused):
            q.sealed_regular(path, expected_sha=self.m["patches_sha256"][patch_name])

    def test_flat_owner_modules_are_dark_by_default(self):
        ext = self.root / "ext"
        ext.mkdir()
        for name in self.m["owner_modules_sha256"]:
            shutil.copy2(OWNER / name, ext / name)
        adapter = bridge.resolve_host_adapter(ext)
        self.assertEqual(adapter.source, ext.resolve())
        self.assertFalse(adapter.pin.TRANSPORT_INSTALLED)
        self.assertFalse(adapter.transport.ROUTE_QUALIFIED)
        with self.assertRaises(bridge.ExperientialBridgeRefused) as cm:
            bridge.preview_command(
                run_id="exp-m2-offline-fixture", task_class="mechanical",
                pool="experiential", model="glm-5.3-uncensored",
                runtime_root=ext)
        self.assertEqual(cm.exception.reason, "EXPERIENTIAL_TRANSPORT_NOT_INSTALLED")
        self.assertFalse((ext / "state").exists())

    def test_flat_symlink_never_becomes_owner_module(self):
        ext = self.root / "ext"
        ext.mkdir()
        (ext / "experiential_pin.py").symlink_to(OWNER / "experiential_pin.py")
        shutil.copy2(OWNER / "experiential_transport.py",
                     ext / "experiential_transport.py")
        with self.assertRaises(bridge.ExperientialBridgeRefused) as cm:
            bridge.resolve_host_adapter(ext)
        self.assertEqual(cm.exception.reason, "EXPERIENTIAL_HOST_ADAPTER_MISSING")


if __name__ == "__main__":
    unittest.main()
