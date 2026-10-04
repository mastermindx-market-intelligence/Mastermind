#!/usr/bin/env python3
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent
R=json.loads((ROOT/'evidence/CORPUS_EVENT_IDENTITY_GATE.json').read_text())
class EventIdentityGateTests(unittest.TestCase):
    def test_canonical_key_requires_accession_and_zero_date_tolerance(self):
        k=R['canonical_filing_identity']
        self.assertEqual(k['fields'],['cik','accession'])
        self.assertEqual(k['date_tolerance_days'],0)
        self.assertIs(k['date_join_permitted'],False)
    def test_committed_store_is_legacy_and_cannot_key_events(self):
        s=R['committed_store']
        self.assertEqual(s['columns'],['ticker','cik','filing_date','acceptance_datetime','items'])
        self.assertIs(s['accession_column_present'],False)
        self.assertNotIn('accession',s['columns'])
    def test_beta_pool_is_not_fully_covered(self):
        b=R['frozen_pool_coverage']['beta_validation_candidate']
        self.assertEqual((b['present_tickers'],b['candidate_count']),(11,12))
        self.assertEqual(b['missing'],['CFG'])
    def test_historical_holdout_metadata_is_not_holdout_assignment(self):
        h=R['frozen_pool_coverage']['prospective_temporal_holdout_candidate']
        self.assertEqual((h['present_tickers'],h['candidate_count']),(12,12))
        self.assertIs(h['historical_rows_eligible_as_holdout_events'],False)
    def test_reserve_gap_is_retained(self):
        r=R['frozen_pool_coverage']['broad_reserve_candidate']
        self.assertEqual(r['missing'],['EL'])
    def test_no_body_or_event_assignment_is_claimed(self):
        self.assertEqual(R['body_reads'],0)
        self.assertEqual(R['event_assignments'],0)
        self.assertEqual(R['source_revision_assignments'],0)
        self.assertIs(R['event_identity_admitted'],False)
        self.assertIs(R['trial_registered'],False)
if __name__=='__main__': unittest.main()
