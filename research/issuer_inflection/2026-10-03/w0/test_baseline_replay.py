"""Adversarial reconstruction tests using the captured unchanged FIF responses.

These are development integration tests, not financial-owner, production or I3
architecture acceptance. Synthetic mutations never overwrite original responses.
"""
from __future__ import annotations
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest

from baseline_replay import ReplayRefusal, canonical, compare_snapshots, digest, owner_snapshot

HERE = Path(__file__).resolve().parent
EVIDENCE = Path(os.environ.get("I3_BASELINE_EVIDENCE_DIR", str(HERE / "evidence/baseline-replay"))).resolve()
UNLINKED = "unlinked source vintages require an explicit typed revision lineage"

class BaselineReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metadata = json.loads((EVIDENCE / "method-before-execution.json").read_text())
        cls.requests = cls.metadata["requests"]
        cls.raw = {n:(EVIDENCE / (n + ".response.json")).read_bytes() for n in cls.requests}
        cls.hashes = {r["name"]:r["response_sha256"] for r in json.loads((EVIDENCE / "owner-queries.json").read_text())}
    def result(self, before="after_a1_before_a2_admission", after="after_a2_admission") -> dict:
        return compare_snapshots(self.raw[before], self.raw[after], before_sha256=self.hashes[before], after_sha256=self.hashes[after], before_request=self.requests[before], after_request=self.requests[after])
    def root(self, data, metric="revenue", kind="duration"):
        return next(n for n in data["receipt"]["nodes"] if n["cell_id"] in data["receipt"]["root_cell_ids"] and n["metric_id"] == metric and n["period"]["kind"] == kind)
    def mutate(self, fn, name="after_a2_admission"):
        data=json.loads(self.raw[name]); fn(data); raw=canonical(data)
        return raw, self.requests[name]
    def refused(self, fn, name="after_a2_admission"):
        raw,request=self.mutate(fn,name)
        with self.assertRaises(ReplayRefusal): owner_snapshot(raw,digest(raw),request)
    def test_all_four_variables_are_preserved_on_both_sides(self):
        p=self.result()["payload"]
        self.assertEqual(p["requested_variable_count"],4)
        self.assertEqual(len(p["variables"]),4)
        self.assertEqual(sum(p["counts"].values()),4)
        self.assertTrue(all("baseline" in r and "target" in r for r in p["variables"]))
    def test_first_admission_is_not_economic_change(self):
        p=self.result("before_a1_admission","after_a1_before_a2_admission")["payload"]
        self.assertEqual(p["counts"],{"became_available_not_economic_change":2,"unchanged_refusal":2})
        became=[r for r in p["variables"] if r["reconstruction_state"] == "became_available_not_economic_change"]
        self.assertTrue(all(r["baseline"]["value"] is None and r["baseline"]["selected_occurrence_ref"] is None for r in became))
        self.assertTrue(all(r["economic_interpretation"] is None for r in became))
    def test_later_admission_preserves_unlinked_refusal(self):
        p=self.result()["payload"]
        asset=next(r for r in p["variables"] if r["variable"]["metric_id"] == "total_assets" and r["variable"]["period"]["kind"] == "instant")
        self.assertEqual(asset["baseline"]["state"],"value")
        self.assertEqual(asset["target"]["state"],"not_evaluable")
        self.assertIsNone(asset["target"]["value"])
        self.assertIsNone(asset["target"]["selected_occurrence_ref"])
        self.assertEqual(asset["target"]["reason"],UNLINKED)
        self.assertEqual(asset["reconstruction_state"],"became_not_evaluable")
    def test_revenue_is_carried_unchanged_not_dropped(self):
        rows=self.result()["payload"]["variables"]
        revenue=next(r for r in rows if r["variable"]["metric_id"] == "revenue" and r["variable"]["period"]["kind"] == "duration")
        self.assertEqual(revenue["reconstruction_state"],"unchanged_value")
        self.assertEqual(revenue["baseline"]["value"],"416161000000")
        self.assertEqual(revenue["target"]["value"],"416161000000")
        self.assertEqual(revenue["baseline"]["selected_occurrence_ref"],revenue["target"]["selected_occurrence_ref"])
        self.assertEqual(revenue["target"]["period"]["calendar_kind"],"unknown")
    def test_identical_cutoff_has_no_new_change(self):
        self.assertEqual(self.result("after_a2_admission","after_a2_admission")["payload"]["counts"],{"unchanged_refusal":3,"unchanged_value":1})
    def test_refusal_to_missing_is_not_unchanged_value(self):
        name="after_a2_admission"
        data=json.loads(self.raw[name])
        cell=self.root(data,"total_assets","instant")
        cell["state"]="missing"; cell["status"]="missing"
        cell["reason"]="TEST_ONLY owner source no longer available"
        cell["provenance"]["reason"]=cell["reason"]
        data["coverage"]["not_evaluable_cells"]-=1
        data["coverage"]["missing_cells"]+=1
        after=canonical(data)
        result=compare_snapshots(self.raw[name],after,before_sha256=self.hashes[name],after_sha256=digest(after),before_request=self.requests[name],after_request=self.requests[name])
        row=next(r for r in result["payload"]["variables"] if r["variable"]["metric_id"] == "total_assets" and r["variable"]["period"]["kind"] == "instant")
        self.assertEqual(row["reconstruction_state"],"became_missing")
        self.assertIsNone(row["baseline"]["value"])
        self.assertIsNone(row["target"]["value"])
        self.assertIsNone(row["economic_interpretation"])
    def test_source_time_refusal_separate_from_system_admission(self):
        p=self.result("before_a2_source","after_a2_admission")["payload"]
        self.assertEqual(p["baseline_cutoffs"]["recorded_at"],p["target_cutoffs"]["recorded_at"])
        self.assertNotEqual(p["baseline_cutoffs"]["source_snapshot_at"],p["target_cutoffs"]["source_snapshot_at"])
        self.assertEqual(p["counts"],{"became_not_evaluable":1,"unchanged_refusal":2,"unchanged_value":1})
    def test_missing_slots_survive_identical_early_cutoff(self):
        p=self.result("before_a1_admission","before_a1_admission")["payload"]
        self.assertEqual(p["counts"],{"missing_at_both_cutoffs":2,"unchanged_refusal":2})
        self.assertEqual(p["requested_variable_count"],4)
    def test_deterministic_semantic_digest(self):
        a=self.result();b=self.result()
        self.assertEqual(canonical(a),canonical(b))
        self.assertEqual(a["artifact_sha256"],digest(canonical(a["payload"])))
    def test_no_product_trial_schema_or_emission_promotion(self):
        p=self.result()["payload"]
        for field in ("comparison_admitted","registered_transition_schema","trial_registered","product_publication_admitted"):
            self.assertIs(p[field],False)
        self.assertIsNone(p["emitted_at"])
        self.assertNotIn("transition_id",p)
        self.assertNotIn("issuer_score",p)
    def test_output_mutation_cannot_change_later_calls(self):
        result=self.result(); expected=deepcopy(result)
        try:
            result["payload"]["issuer_ref"]["entity_id"]="CORRUPTED_BY_CALLER"
            result["payload"]["authority"]["display_only"]=False
            self.assertEqual(self.result(),expected)
        finally:
            from baseline_replay import ENTITY,AUTHORITY
            ENTITY["entity_id"]="ISS:US-XNAS-AAPL"; AUTHORITY["display_only"]=True
    def test_input_request_mutation_cannot_rewrite_returned_evidence(self):
        result=self.result(); prior=deepcopy(result)
        original=self.requests["after_a1_before_a2_admission"]["policy"]["recorded_at"]
        try:
            self.requests["after_a1_before_a2_admission"]["policy"]["recorded_at"]="2020-01-01T00:00:00Z"
            self.assertEqual(result,prior)
        finally:self.requests["after_a1_before_a2_admission"]["policy"]["recorded_at"]=original
    def test_malformed_owner_state_yields_typed_refusal(self):
        self.refused(lambda o:self.root(o).__setitem__("state",[]))
    def test_malformed_accession_yields_typed_refusal(self):
        self.refused(lambda o:self.root(o)["provenance"]["selected_raw_fact"]["source"].__setitem__("accession",[]))
    def test_selected_document_id_is_required(self):
        def remove(o):
            node=self.root(o);node["provenance"]["selected_raw_fact"]["source"].pop("document_id")
            node["provenance"].pop("document_id")
        self.refused(remove)
    def test_input_bytes_and_requests_are_unchanged(self):
        old=deepcopy(self.requests);raw=dict(self.raw);self.result()
        self.assertEqual(old,self.requests);self.assertEqual(raw,self.raw)
    def test_missing_root_or_variable_rejected(self):
        self.refused(lambda o:o["receipt"]["root_cell_ids"].pop())
    def test_duplicate_root_rejected(self):
        self.refused(lambda o:o["receipt"]["root_cell_ids"].__setitem__(1,o["receipt"]["root_cell_ids"][0]))
    def test_duplicate_node_rejected(self):
        self.refused(lambda o:o["receipt"]["nodes"].append(deepcopy(o["receipt"]["nodes"][0])))
    def test_coverage_lie_rejected(self):
        self.refused(lambda o:o["coverage"].__setitem__("value_cells",4))
    def test_coverage_float_is_not_integer_proof(self):
        self.refused(lambda o:o["coverage"].__setitem__("value_cells",1.0))
    def test_boolean_integer_authority_confusion_rejected(self):
        self.refused(lambda o:o["authority"].__setitem__("display_only",1))
    def test_golden_cannot_be_promoted(self):
        self.refused(lambda o:o["delivery"].__setitem__("production_issuer_service",True))
    def test_integer_false_delivery_is_invalid(self):
        self.refused(lambda o:o["delivery"].__setitem__("attested",0))
    def test_wrong_issuer_rejected(self):
        self.refused(lambda o:o["entity"].__setitem__("entity_id","ISS:US-XNAS-MSFT"))
    def test_bad_digest_rejected(self):
        n="after_a2_admission"
        with self.assertRaises(ReplayRefusal): owner_snapshot(self.raw[n],"0"*64,self.requests[n])
    def test_duplicate_json_keys_rejected_even_with_matching_hash(self):
        n="after_a2_admission";raw=b'{"schema":"fake",'+self.raw[n].lstrip()[1:]
        with self.assertRaises(ReplayRefusal):owner_snapshot(raw,digest(raw),self.requests[n])
    def test_response_byte_limit(self):
        raw=b" "*1_048_577
        with self.assertRaises(ReplayRefusal):owner_snapshot(raw,digest(raw),self.requests["after_a2_admission"])
    def test_aggregate_policy_mismatch(self):
        self.refused(lambda o:o["receipt"]["policy"].__setitem__("recorded_at","2020-01-01T00:00:00Z"))
    def test_cell_cutoff_mismatch(self):
        self.refused(lambda o:self.root(o)["provenance"].__setitem__("recorded_cutoff_at","2020-01-01T00:00:00Z"))
    def test_timezone_required(self):
        self.refused(lambda o:self.root(o)["provenance"].__setitem__("source_snapshot_at","2026-08-01T00:00:00"))
    def test_reversed_comparison_cutoff(self):
        with self.assertRaises(ReplayRefusal): self.result("after_a2_admission","after_a1_before_a2_admission")
    def test_selected_source_must_not_come_from_future(self):
        self.refused(lambda o:self.root(o)["provenance"]["selected_raw_fact"]["clocks"].__setitem__("accepted_at","2026-09-01T00:00:00Z"))
    def test_selected_fact_must_be_system_admitted(self):
        self.refused(lambda o:self.root(o)["provenance"]["selected_raw_fact"]["clocks"].__setitem__("recorded_at","2026-09-01T00:00:00Z"))
    def test_mapping_method_readiness_is_not_source_time(self):
        self.refused(lambda o:self.root(o)["provenance"].__setitem__("system_ready_at","2026-09-01T00:00:00Z"))
    def test_undefined_dimension_scope_rejected(self):
        self.refused(lambda o:self.root(o)["provenance"]["selected_raw_fact"].__setitem__("dimensions_known",False))
    def test_wrong_source_accession_rejected(self):
        self.refused(lambda o:self.root(o)["provenance"]["selected_raw_fact"]["source"].__setitem__("accession","0000320193-99-999999"))
    def test_value_must_match_owner_selected_fact(self):
        self.refused(lambda o:self.root(o).__setitem__("value","1"))
    def test_refusal_may_not_leak_value(self):
        self.refused(lambda o:self.root(o,"total_assets","instant").__setitem__("value","999"))
    def test_source_receipt_hash_shape(self):
        self.refused(lambda o:self.root(o)["provenance"]["selected_raw_fact"]["source"].__setitem__("body_sha256","not-a-hash"))
    def test_source_receipt_must_agree_with_owner_provenance(self):
        self.refused(lambda o:self.root(o)["provenance"]["selected_raw_fact"]["source"].__setitem__("body_sha256","f"*64))
    def test_selected_occurrence_must_belong_to_receipt(self):
        self.refused(lambda o:self.root(o)["provenance"]["selected_raw_fact"].__setitem__("occurrence_id","rawfact_not_in_receipt"))

if __name__ == "__main__":unittest.main()
