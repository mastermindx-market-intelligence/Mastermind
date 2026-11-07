"""Hermetic selected-generation profile tests; no provider or native runtime effects."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
PKG=HERE.parent
OWNER=PKG.parent/"experiential53"
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(PKG))
import qualify_m2_sequence33 as run
import compose_overlay as co

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class Sequence33Qualification(unittest.TestCase):
    def setUp(self):
        self.m=run.q.manifest_read(HERE/"profile_manifest.json",
                                   expected_profile_id=run.PROFILE_ID)
    def test_sealed_selected_generation_and_inputs(self):
        self.assertEqual(self.m["selected_sequence"],33)
        self.assertEqual(self.m["selected_generation"],
                         "177118be6675cf5a292524610afaaf4d5afc33dc6a150c22291240e3b6245fcd")
        self.assertEqual(self.m["status"],"source_candidate_not_installed")
        self.assertEqual(sha(HERE/"fixtures"/"selection_1771.json"),
                         self.m["current_selection_sha256"])
        self.assertEqual(set(self.m["preimages_sha256"]),set(run.q.NAMES))
        for name in run.q.NAMES:
            patch=HERE/"patches"/(name+".patch")
            self.assertEqual(self.m["patches_sha256"][name+".patch"],sha(patch))
            target,hunks=co._parse_patch(patch.read_text(),name)
            self.assertEqual(target,name)
            self.assertTrue(hunks)
        self.assertEqual(sha(PKG/"experiential_bridge.py"),self.m["bridge_sha256"])
        for name,digest in self.m["owner_modules_sha256"].items():
            self.assertEqual(sha(OWNER/name),digest)
    def test_wrong_profile_identity_refused(self):
        with self.assertRaises(co.CompositionRefused):
            run.q.manifest_read(HERE/"profile_manifest.json")
    def test_changed_selection_refused_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"native-code-releases"
            ext=root/self.m["selected_generation"]/"ext"
            ext.mkdir(parents=True)
            (root/"CURRENT.json").write_text('{"schema":"native-code-selection.v1","generation":"changed"}\n')
            output=Path(tmp)/"candidate"
            with self.assertRaises(co.CompositionRefused):
                run.q.qualify(installed_ext=ext,output=output,
                   owner_modules_root=OWNER,profile_dir=HERE,
                   expected_profile_id=run.PROFILE_ID,verify_only=True)
            self.assertFalse(output.exists())
    def test_wrong_installed_generation_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            ext=Path(tmp)/"native-code-releases"/"wrong"/"ext"
            ext.mkdir(parents=True)
            with self.assertRaises(co.CompositionRefused):
                run.q.qualify(installed_ext=ext,output=Path(tmp)/"candidate",
                    owner_modules_root=OWNER,profile_dir=HERE,
                    expected_profile_id=run.PROFILE_ID,verify_only=True)

if __name__=="__main__":
    unittest.main()
