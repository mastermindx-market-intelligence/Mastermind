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
        self.actual_manifest=json.loads((ROLLOUT/'native-manifest.json').read_bytes())
        self.manifest=builder.before_sparse_index_advice(self.actual_manifest)

    def test_exact_one_member_forward_normalization_retains_emitted_source(self):
        original=dict(self.manifest)
        self.assertEqual(len(original),107)
        self.assertEqual(original['ext/lease_broker.py'],builder.QUALIFICATION_QUIESCENCE_BROKER_SHA256)
        parent=builder.before_qualification_quiescence(original)
        self.assertEqual({k for k in parent if parent[k]!=original[k]},{'ext/lease_broker.py'})
        self.assertEqual(parent['ext/lease_broker.py'],builder.QUALIFICATION_QUIESCENCE_BROKER_PREIMAGE)
        raw=(json.dumps(builder.before_host_pull_integrity(parent),sort_keys=True,indent=2)+'\n').encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),"eb74b020c76c70081562d7be69bf8e154d5d7ad50b03381de0bd15ba24b634b7")
        builder.before_admission_integrity(builder.before_host_pull_integrity(original))
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
        builder.before_admission_integrity(builder.before_host_pull_integrity(parent))


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


    def test_both_exact_source_deltas_retain_their_separate_historical_parents(self):
        # Frozen old-observer identities and their exact current-observer
        # compositions are distinct, independently enumerated proof rows.
        histories = [('42ebe6f4db11669447f499099299bcf02c881a1e7d334b73e72f1675429f9f18', ('8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6', 'a42259df6aa9dc910abd3e6eacb75f30b9089663d569c88f946f965bc8ceedd3', '7b58e10efbf879ac6e2e3e4c6b89ddc2a79cba4f0b1b47f0131bbafc34bc1ce9', '45a90565e189bca551cb79f579296689aa00674778d3917a6af75a720ff71c18')), ('c969cfc5dc5fc179b9a6eed28605017c22a30a4ef17550ec5e84b524f48c5d5a', ('eb74b020c76c70081562d7be69bf8e154d5d7ad50b03381de0bd15ba24b634b7', 'd8e17896581fcf5568157cae6dfb71b502cd5029364586f123240b5f05b8b7f1', 'f80fed5257def029c349edd5d11373cdd1107b1cdbe9266dbe7cca3af4e9a22f', '2c395c2a259e1027b5fe9243667ee0cd2dfc66c1cdc055dc19897950e91371a3'))]
        for observer, expected in histories:
            current = dict(self.manifest)
            current["ext/current_source_observation.py"] = observer
            base = dict(current)
            base.update(builder.HOST_PULL_INTEGRITY_PREIMAGES)
            base['ext/lease_broker.py'] = builder.QUALIFICATION_QUIESCENCE_BROKER_PREIMAGE
            host_only = dict(base, **builder.HOST_PULL_INTEGRITY_DIGESTS)
            broker_only = dict(base)
            broker_only['ext/lease_broker.py'] = builder.QUALIFICATION_QUIESCENCE_BROKER_SHA256
            for source, expected_sha in zip((base, host_only, broker_only, current), expected):
                with self.subTest(observer=observer, cohort=expected_sha):
                    original = dict(source)
                    self.assertEqual(hashlib.sha256((json.dumps(source,sort_keys=True,indent=2)+'\n').encode()).hexdigest(),expected_sha)
                    q = builder.before_qualification_quiescence(source)
                    h = builder.before_host_pull_integrity(source)
                    self.assertLessEqual({k for k in q if q[k] != source[k]}, {'ext/lease_broker.py'})
                    self.assertLessEqual({k for k in h if h[k] != source[k]}, set(builder.HOST_PULL_INTEGRITY_PREIMAGES))
                    self.assertEqual(builder.before_host_pull_integrity(q), base)
                    self.assertEqual(builder.before_qualification_quiescence(h), base)
                    captured = {name: source['ext/'+name] for name in builder.GO_APPLICATION_DEPENDENCIES}
                    builder.validate_go_base_manifest(source, captured)
                    self.assertEqual(source, original)

    def test_source_successors_refuse_every_unbound_observer_without_mutation(self):
        for observer in ("0" * 64, "", None):
            source = dict(self.manifest)
            if observer is None:
                source.pop("ext/current_source_observation.py")
            else:
                source["ext/current_source_observation.py"] = observer
            original = dict(source)
            captured = {name: source["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
            with self.subTest(observer=observer):
                with self.assertRaises(ValueError):
                    builder.before_qualification_quiescence(source)
                with self.assertRaises(ValueError):
                    builder.before_host_pull_integrity(source)
                with self.assertRaises(ValueError):
                    builder.validate_go_base_manifest(source, captured)
                self.assertEqual(source, original)

    def test_combined_parent_cannot_hide_partial_host_pull_or_foreign_broker(self):
        for member, predecessor in builder.HOST_PULL_INTEGRITY_PREIMAGES.items():
            for value in (predecessor, '0'*64):
                broken = dict(self.manifest); broken[member] = value
                captured = {name: broken['ext/'+name] for name in builder.GO_APPLICATION_DEPENDENCIES}
                with self.subTest(member=member,value=value):
                    with self.assertRaises(ValueError): builder.before_qualification_quiescence(broken)
                    with self.assertRaises(ValueError): builder.before_host_pull_integrity(broken)
                    with self.assertRaises(ValueError): builder.validate_go_base_manifest(broken,captured)
        broken = dict(self.manifest); broken['ext/lease_broker.py'] = '0'*64
        with self.assertRaises(ValueError): builder.before_host_pull_integrity(broken)
        with self.assertRaises(ValueError): builder.before_admission_integrity(broken)


if __name__=='__main__':unittest.main()
