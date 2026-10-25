"""Fail-closed Grok 4.7 incumbent policy compatibility before any CAS."""
from __future__ import annotations
import importlib.util
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent

def module():
    spec=importlib.util.spec_from_file_location("grok47_policy_qualification", HERE/"qualify_installed_generation.py")
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

class GrokPolicyPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="grok47-policy-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.store=self.root/"native-code-releases"
        self.store.mkdir()
        self.file=self.root/"orch/fabric/pools.yaml"
        self.file.parent.mkdir(parents=True)
        self.file.write_text("pools:\n  grok:\n    task_classes: [review]\n")
        self.owner=module()

    def invoke(self,doc):
        fake=SimpleNamespace(safe_load=lambda _:doc)
        with patch.dict(sys.modules, {"yaml":fake}):
            return self.owner.verify_incumbent_grok_policy(self.store)

    def test_unset_model_uses_47(self):
        result=self.invoke({"pools":{"grok":{"task_classes":["review"]}}})
        self.assertEqual(result["effective_default"],"grok-4.7")
        self.assertIsNone(result["configured_default"])
        self.assertRegex(result["sha256"],r"^[0-9a-f]{64}$")

    def test_incumbent_exact_47_is_eligible(self):
        result=self.invoke({"pools":{"grok":{"default_model":"grok-4.7"}}})
        self.assertEqual(result["configured_default"],"grok-4.7")

    def test_old_or_unsupported_default_refuses(self):
        for setting in ("grok-4.6","grok-4.8",47,["grok-4.7"]):
            with self.subTest(setting=setting):
                with self.assertRaisesRegex(ValueError,"grok47_policy_default_conflict"):
                    self.invoke({"pools":{"grok":{"default_model":setting}}})

    def test_missing_policy_structure_refuses(self):
        for setting in ({}, {"pools":{}}, {"pools":{"grok":[]}}, [], None):
            with self.subTest(setting=setting):
                with self.assertRaisesRegex(ValueError,"grok47_incumbent_"):
                    self.invoke(setting)

    def test_preserves_accepted_disjoint_release_files(self):
        reviewed={rel:"a"*64 for rel in self.owner.OVERLAYS}
        reviewed["ext/slot.py"]="b"*64
        reviewed["ext/lane_runtime.py"]="c"*64
        newer=dict(reviewed)
        newer["ext/slot.py"]="d"*64
        newer["ext/lane_runtime.py"]="e"*64
        changed=self.owner.verified_rebase_changes(
            {"files":reviewed},{"files":newer})
        self.assertEqual(changed,["ext/lane_runtime.py","ext/slot.py"])

    def test_refuses_overlapping_or_changed_release_closure(self):
        reviewed={rel:"a"*64 for rel in self.owner.OVERLAYS}
        reviewed["ext/slot.py"]="b"*64
        overlap=dict(reviewed)
        overlap["ext/pick.py"]="c"*64
        with self.assertRaisesRegex(ValueError,"native_rebase_reviewed_overlay_preimage_changed"):
            self.owner.verified_rebase_changes(
                {"files":reviewed},{"files":overlap})
        missing=dict(reviewed)
        del missing["ext/slot.py"]
        with self.assertRaisesRegex(ValueError,"native_rebase_release_closure_changed"):
            self.owner.verified_rebase_changes(
                {"files":reviewed},{"files":missing})

    def test_symlink_policy_refuses(self):
        self.file.unlink()
        external=self.root/"untrusted-policy"
        external.write_text("pools: {grok: {}}")
        self.file.symlink_to(external)
        with self.assertRaisesRegex(ValueError,"grok47_incumbent_policy_unavailable"):
            self.invoke({"pools":{"grok":{}}})

if __name__=="__main__":
    unittest.main()
