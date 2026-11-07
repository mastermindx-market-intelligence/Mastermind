"""Exact source-only Broker successor; never a native install/selection proof."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
ROLLOUT=ROOT/'ops/native_fabric/quota_continuity/rollout'
spec=importlib.util.spec_from_file_location('inert_quiescence_cohort_builder',ROLLOUT/'build_review_stage.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class Cohort(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads((ROLLOUT/'native-manifest.json').read_bytes())

    def test_exact_one_member_forward_normalization_retains_emitted_source(self):
        original=dict(self.manifest)
        self.assertEqual(len(original),107)
        self.assertEqual(original['ext/lease_broker.py'],builder.QUALIFICATION_QUIESCENCE_BROKER_SHA256)
        parent=builder.before_qualification_quiescence(original)
        self.assertEqual({k for k in parent if parent[k]!=original[k]},{'ext/lease_broker.py'})
        self.assertEqual(parent['ext/lease_broker.py'],builder.QUALIFICATION_QUIESCENCE_BROKER_PREIMAGE)
        raw=(json.dumps(parent,sort_keys=True,indent=2)+'\n').encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),builder.QUALIFICATION_QUIESCENCE_PARENT_SHA256)
        builder.before_admission_integrity(original)
        self.assertEqual(original,self.manifest)

    def test_foreign_or_mixed_member_is_rejected(self):
        for member in ['ext/remote_sub.sh','ext/fabric_task.py','ext/lane_runtime.py']:
            source=dict(self.manifest);source[member]='0'*64
            with self.subTest(member=member),self.assertRaises(ValueError):
                builder.before_qualification_quiescence(source)

    def test_broker_byte_drift_cannot_reuse_review(self):
        path=ROOT/'ops/native_fabric/quota_continuity/candidate/lease_broker.py'
        raw=path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),builder.QUALIFICATION_QUIESCENCE_BROKER_SHA256)
        changed=dict(self.manifest);changed['ext/lease_broker.py']=hashlib.sha256(raw+b'\n# unrelated byte drift\n').hexdigest()
        with self.assertRaises(ValueError):builder.before_admission_integrity(changed)

    def test_missing_or_extra_namespace_is_rejected(self):
        missing=dict(self.manifest);missing.pop('ext/remote_sub.sh')
        extra=dict(self.manifest);extra['ext/foreign.py']='0'*64
        for source in [missing,extra]:
            with self.assertRaises(ValueError):builder.before_qualification_quiescence(source)

    def test_captured_parent_remains_valid_without_relabel(self):
        parent=dict(self.manifest);parent['ext/lease_broker.py']=builder.QUALIFICATION_QUIESCENCE_BROKER_PREIMAGE
        self.assertEqual(builder.before_qualification_quiescence(parent),parent)
        builder.before_admission_integrity(parent)


    def test_go_current_capture_and_exact_parent_are_independent_obligations(self):
        original = dict(self.manifest)
        captured = {name: original["ext/" + name]
                    for name in builder.GO_APPLICATION_DEPENDENCIES}
        builder.validate_go_base_manifest(original, captured)
        self.assertEqual(original, self.manifest)
        parent = builder.before_qualification_quiescence(original)
        parent_capture = {name: parent["ext/" + name]
                          for name in builder.GO_APPLICATION_DEPENDENCIES}
        builder.validate_go_base_manifest(parent, parent_capture)
        # Historical validation never substitutes bytes for the current capture.
        for source, wrong_capture in [(original, parent_capture), (parent, captured)]:
            with self.subTest(source=source["ext/lease_broker.py"]), self.assertRaises(ValueError):
                builder.validate_go_base_manifest(source, wrong_capture)

    def test_go_capture_drift_and_namespace_substitution_are_refused(self):
        original = dict(self.manifest)
        captured = {name: original["ext/" + name]
                    for name in builder.GO_APPLICATION_DEPENDENCIES}
        for member in captured:
            changed = dict(captured)
            changed[member] = "0" * 64
            with self.subTest(captured=member), self.assertRaises(ValueError):
                builder.validate_go_base_manifest(original, changed)
        missing_capture = dict(captured)
        missing_capture.pop("lease_broker.py")
        for wrong_capture in [missing_capture, {**captured, "foreign.py": "0" * 64}]:
            with self.assertRaises(ValueError):
                builder.validate_go_base_manifest(original, wrong_capture)
        missing = dict(original)
        missing.pop("ext/remote_sub.sh")
        for source in [missing, {**original, "ext/foreign.py": "0" * 64}]:
            with self.assertRaises(ValueError):
                builder.validate_go_base_manifest(source, captured)
        self.assertEqual(original, self.manifest)


if __name__=='__main__':unittest.main()
