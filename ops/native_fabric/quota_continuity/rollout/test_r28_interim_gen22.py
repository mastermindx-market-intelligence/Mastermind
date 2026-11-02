"""Hermetic source/adversarial tests for the picker-only interim. No M2 effect."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import native_generation as g
import r28_interim_gen22 as interim

class R28InterimGen22Test(unittest.TestCase):
    def test_exact_ninety_five_member_seal(self):
        manifest=interim.contract()
        self.assertEqual(len(manifest),95)
        self.assertEqual(manifest["ext/pick.py"],interim.FUSED)
        self.assertEqual(manifest["pool"],"12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679")
        self.assertNotIn("ext/host_pull_daemon.sh",manifest)
        self.assertNotIn("ext/host_pull_launchd.plist.template",manifest)

    def test_provenance_links_genuine_protected_git_source(self):
        # The historical R28 source is the genuine protected object. The
        # current candidate already contains the separately qualified fuse.
        raw=subprocess.check_output(['git','-C',str(interim.REPO),'show',
            interim.PIN+':'+interim.SRC],timeout=15)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),interim.R28)
        for _,new in interim.HUNKS:
            self.assertEqual(raw.count(new),1)
        current=(interim.REPO/interim.SRC).read_bytes()
        self.assertEqual(hashlib.sha256(current).hexdigest(),interim.FUSED)
        self.assertNotEqual(raw,current)

    def test_exact_target_descriptor(self):
        proposed=interim.contract()
        base=dict(proposed)
        base["ext/pick.py"]=interim.BASE_PICK
        interim.compatible(base,proposed)
        self.assertEqual(
            g.digest(g.canonical(g.descriptor(proposed,str(interim.EXT)))),
            interim.TARGET)

    def test_one_member_only_rejects_other_source_change(self):
        files=interim.contract()
        base=dict(files)
        base["ext/pick.py"]=interim.BASE_PICK
        base["pool"]="0"*64
        with self.assertRaisesRegex(ValueError,"NON_PICKER_MEMBER_DRIFT"):
            interim.compatible(base,files)

    def test_member_set_rejects_hidden_extra(self):
        files=interim.contract()
        base=dict(files)
        base["ext/pick.py"]=interim.BASE_PICK
        base["ext/secret.py"]="0"*64
        with self.assertRaisesRegex(ValueError,"NON_PICKER_MEMBER_DRIFT"):
            interim.compatible(base,files)

    def synthetic(self):
        baseline=(b"def f(tc, doc):\n"
                  b"    classifications = (\n"+interim.HUNKS[0][0]+b"\n"
                  b"    )\n"
                  b"    def is_execute_class(*args):\n        return True\n"
                  b"    LABOR_CLASSES_R30 = set()\n"
                  + interim.HUNKS[1][0]
                  + b"tc)\n")
        protected=baseline.replace(interim.HUNKS[0][0],interim.HUNKS[0][1])
        protected=protected.replace(interim.HUNKS[1][0],interim.HUNKS[1][1])
        return baseline,protected

    def test_reconstructs_only_two_bounded_review_hunks(self):
        before, protected=self.synthetic()
        target=protected
        with (mock.patch.object(interim,"BASE_PICK",interim.digest(before)),
              mock.patch.object(interim,"R28",interim.digest(protected)),
              mock.patch.object(interim,"FUSED",interim.digest(target))):
            self.assertEqual(interim.fuse(before,protected),target)
            self.assertEqual(before.count(interim.HUNKS[1][0]),1)

    def test_refuses_wrong_selected_preimage(self):
        before,protected=self.synthetic()
        with self.assertRaisesRegex(ValueError,"BASE_OR_REVIEWED_PICKER_CHANGED"):
            interim.fuse(before,protected)

    def test_refuses_ambiguous_review_hunk(self):
        before,protected=self.synthetic()
        modified=before.replace(interim.HUNKS[0][0],interim.HUNKS[0][0]*2)
        with (mock.patch.object(interim,"BASE_PICK",interim.digest(modified)),
              mock.patch.object(interim,"R28",interim.digest(protected))):
            with self.assertRaisesRegex(ValueError,"PROTECTED_TWO_HUNK_SHAPE_CHANGED"):
                interim.fuse(modified,protected)

    def test_refuses_fake_reviewed_source(self):
        before,protected=self.synthetic()
        fake=protected.replace(interim.HUNKS[0][1],b"changed")
        with (mock.patch.object(interim,"BASE_PICK",interim.digest(before)),
              mock.patch.object(interim,"R28",interim.digest(fake))):
            with self.assertRaisesRegex(ValueError,"PROTECTED_TWO_HUNK_SHAPE_CHANGED"):
                interim.fuse(before,fake)

    def test_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            (base/"kit").mkdir()
            (base/"kit"/"native-code-releases").mkdir()
            output=base/"already"
            output.mkdir()
            with self.assertRaisesRegex(ValueError,"FRESH_EXTERNAL_STAGE_REQUIRED"):
                interim.staging_output(output,base/"kit"/"native-code-releases")

    def test_refuses_live_kit_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            kit=base/"kit"
            kit.mkdir()
            store=kit/"native-code-releases"
            store.mkdir()
            with self.assertRaisesRegex(ValueError,"FRESH_EXTERNAL_STAGE_REQUIRED"):
                interim.staging_output(kit/"new-source",store)

    def test_contract_fails_closed_on_unexpected_metadata(self):
        original=interim.PROVENANCE
        with tempfile.TemporaryDirectory() as tmp:
            fake=Path(tmp)/"provenance.json"
            p=json.loads(original.read_text())
            p["live_effects_authorized"]=True
            fake.write_text(json.dumps(p))
            with mock.patch.object(interim,"PROVENANCE",fake):
                with self.assertRaisesRegex(ValueError,"SOURCE_MANIFEST_OR_PROVENANCE_CHANGED"):
                    interim.contract()

if __name__=="__main__":
    unittest.main()
