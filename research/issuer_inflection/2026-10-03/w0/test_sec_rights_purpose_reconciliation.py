#!/usr/bin/env python3
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent
R=json.loads((ROOT/'evidence/SEC_RIGHTS_PURPOSE_RECONCILIATION.json').read_text())
class RightsTests(unittest.TestCase):
    def test_source_law_records_all_five_sec_dimensions(self):
        sec=R['source_rights_register']['sec_edgar']
        self.assertEqual(set(sec),{'acquisition','processing','storage','model_use','user_redistribution','remaining_source_caveat'})
        for key in ('acquisition','processing','storage','model_use','user_redistribution'):
            self.assertTrue(sec[key].startswith('DETERMINED_FROM_PUBLISHED_TERMS_USER_FACING'))
    def test_shared_runtime_registry_still_lacks_sec_family(self):
        self.assertIs(R['runtime_rights_registry']['sec_edgar_row_present'],False)
    def test_runtime_purposes_do_not_self_promote_from_source_law(self):
        self.assertEqual(R['i3_purposes']['public_display'],'NOT_ADMITTED_RUNTIME')
        for key in ('internal_use','historical_research','model_context'):
            self.assertEqual(R['i3_purposes'][key],'SOURCE_LAW_SUPPORTED_NOT_RUNTIME_BOUND')
    def test_no_product_or_model_runtime_admission_is_claimed(self):
        p=R['promotion']
        self.assertEqual(p['rights_state'],'not_admitted')
        self.assertIs(p['product_publication_admitted'],False)
        self.assertIs(p['model_context_admitted'],False)
        self.assertIs(p['historical_research_runtime_admitted'],False)
        self.assertIs(p['copied_runtime_profile'],False)
    def test_third_party_filing_caveat_is_preserved(self):
        self.assertEqual(R['source_rights_register']['sec_edgar']['remaining_source_caveat'],'filing_specific_third_party_restriction')
if __name__=='__main__': unittest.main()
