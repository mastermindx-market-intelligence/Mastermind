#!/usr/bin/env python3
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent
R=json.loads((ROOT/'evidence/CORPUS_BETA_PIT_MEMBERSHIP_WITNESS.json').read_text())
class BetaPitWitnessTests(unittest.TestCase):
    def test_all_twelve_beta_candidates_are_present(self):
        self.assertEqual(len(R['rows']),12)
        self.assertEqual(len({x['ticker'] for x in R['rows']}),12)
    def test_every_witness_has_one_sp500_pit_membership(self):
        self.assertIs(R['all_beta_single_pit_membership'],True)
        for row in R['rows']:
            self.assertEqual(row['pit_membership_count'],1)
            self.assertEqual(row['pit_sources'],['sp500'])
    def test_event_keys_use_owner_cik_report_date_shape(self):
        for row in R['rows']:
            self.assertEqual(row['owner_event_key'],f"{row['cik']}|{row['report_date']}")
            self.assertTrue(row['accession'])
    def test_witness_does_not_assign_events_or_read_bodies(self):
        self.assertEqual(R['body_reads'],0)
        self.assertIs(R['event_identity_admitted'],False)
        self.assertIs(R['source_revision_assigned'],False)
        self.assertIs(R['trial_registered'],False)
        self.assertTrue(all(x['event_assigned'] is False and x['body_read'] is False for x in R['rows']))
    def test_current_proxy_does_not_back_project_historical_family(self):
        self.assertIs(R['historical_business_family_qualified'],False)
        self.assertIs(R['current_proxy_may_certify_historical_family'],False)
        self.assertIs(R['earnings_metadata_candidate']['admitted'],False)
if __name__=='__main__': unittest.main()
