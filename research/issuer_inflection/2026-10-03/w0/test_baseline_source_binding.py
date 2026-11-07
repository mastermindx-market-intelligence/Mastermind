"""Consumer reference-binding regressions; synthetic mutations, never source edits."""
from __future__ import annotations
import json
from pathlib import Path
import unittest
from baseline_replay import ReplayRefusal, canonical, digest, owner_snapshot

ROOT = Path(__file__).resolve().parent / "evidence/baseline-replay"

class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        name = "after_a2_admission"
        self.raw = (ROOT / (name + ".response.json")).read_bytes()
        self.request = json.loads((ROOT / "method-before-execution.json").read_text())["requests"][name]
        self.data = json.loads(self.raw)
        self.cell = next(n for n in self.data["receipt"]["nodes"] if n["metric_id"] == "revenue" and n["state"] == "value")
        self.prov = self.cell["provenance"]
        self.fact = self.prov["selected_raw_fact"]
    def reject(self):
        raw = canonical(self.data)
        with self.assertRaises(ReplayRefusal):
            owner_snapshot(raw, digest(raw), self.request)
    def test_wrong_duration_start_cannot_back_same_period(self):
        self.fact["context"]["start"] = "2023-09-29"; self.reject()
    def test_wrong_duration_end_cannot_back_same_period(self):
        self.fact["context"]["end"] = "2024-09-27"; self.reject()
    def test_instant_cannot_back_duration(self):
        self.fact["context"]["instant"] = "2025-09-27"; self.reject()
    def test_context_issuer_must_match_source_issuer(self):
        self.fact["context"]["entity_identifier"] = "0000789019"; self.reject()
    def test_selected_unit_must_match_owner_unit(self):
        self.fact["unit"]["measures"] = ["iso4217:JPY"]; self.reject()
    def test_ratio_unit_cannot_back_absolute_usd(self):
        self.fact["unit"]["denominator_measures"] = ["xbrli:shares"]; self.reject()
    def test_provenance_unit_must_match_cell_unit(self):
        self.prov["unit"] = "JPY"; self.reject()
    def test_selected_concept_must_match_provenance(self):
        self.fact["concept_qname"] = "us-gaap:Assets"; self.reject()
    def test_selected_clock_must_match_provenance(self):
        self.prov["accepted_at"] = "2025-10-30T10:01:26Z"; self.reject()
    def test_source_readiness_must_not_exceed_cutoff(self):
        self.prov["source_ready_at"] = "2026-09-01T00:00:00Z"; self.reject()
    def test_source_readiness_must_not_precede_fact(self):
        self.prov["source_ready_at"] = "2025-01-01T00:00:00Z"; self.reject()
    def test_system_readiness_cannot_precede_admission(self):
        self.prov["system_ready_at"] = "2026-08-01T00:00:00Z"; self.reject()
    def test_system_readiness_cannot_ignore_later_governance(self):
        self.prov["governance_available_at"] = "2026-09-01T00:00:00Z"; self.reject()
    def test_bad_unit_shape_has_typed_refusal(self):
        self.fact["unit"] = []; self.reject()
    def test_every_original_owner_response_remains_accepted(self):
        meta = json.loads((ROOT / "method-before-execution.json").read_text())
        for name, request in meta["requests"].items():
            with self.subTest(name=name):
                raw = (ROOT / (name + ".response.json")).read_bytes()
                self.assertEqual(len(owner_snapshot(raw, digest(raw), request)["requested"]), 4)

if __name__ == "__main__": unittest.main()
