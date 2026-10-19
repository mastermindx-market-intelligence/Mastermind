#!/usr/bin/env python3
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent
RECORD=json.loads((ROOT/'evidence/FIF_LINEAGE_POST_MERGE_PROBE.json').read_text())
class ProbeTests(unittest.TestCase):
    def test_merged_owner_value_is_recorded_without_production_promotion(self):
        g=RECORD['genuine_owner_response']; self.assertEqual(g['cell']['state'],'value'); self.assertEqual(g['cell']['value'],'359241000000'); self.assertIs(g['delivery']['attested'],False); self.assertIs(g['delivery']['production_issuer_service'],False)
    def test_historical_refusal_is_preserved(self): self.assertIs(RECORD['disposition']['historical_pre_lineage_refusal_preserved'],True)
    def test_forged_disclosure_field_was_accepted_and_reemitted(self):
        f=RECORD['forged_field_probe']; self.assertIs(f['accepted'],True); self.assertEqual(f['emitted_parent_document_id'],f['forged_parent_document_id'])
    def test_lineage_is_not_admitted_to_i3(self):
        d=RECORD['disposition']; self.assertIs(d['lineage_disclosure_trusted_for_i3_source_reference'],False); self.assertIs(d['cross_filing_i3_comparison_admitted'],False)
    def test_probe_is_exact_main_and_owner_comment_is_bound(self):
        self.assertEqual(RECORD['macro_main_pin'],'05216ea0ec0367a1e4061c05c73d0b0a363d4e00'); self.assertEqual(RECORD['disposition']['owner_comment'],'macro#7518 issuecomment-5983145862')
if __name__=='__main__': unittest.main()
