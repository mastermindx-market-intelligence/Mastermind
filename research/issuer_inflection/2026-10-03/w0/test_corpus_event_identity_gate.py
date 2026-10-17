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
    def test_owner_store_is_accession_complete_and_accepted(self):
        s=R['accepted_owner_store']
        self.assertIs(R['canonical_filing_metadata_admitted'],True)
        self.assertIs(R['event_identity_source_admitted'],True)
        self.assertEqual(s['columns'],['ticker','cik','accession','form','filing_date','acceptance_datetime','report_date','items'])
        self.assertIs(s['accession_column_present'],True)
        self.assertEqual(s['empty_accessions'],0)
        self.assertEqual(s['duplicate_cik_accession_pairs'],0)
        self.assertEqual(s['hosted_ci_conclusion'],'success')
        self.assertEqual(s['fences_conclusion'],'success')
    def test_all_frozen_names_have_owner_metadata(self):
        for role,count in [('beta_validation_candidate',12),('prospective_temporal_holdout_candidate',12),('broad_reserve_candidate',6)]:
            with self.subTest(role=role):
                row=R['frozen_pool_coverage'][role]
                self.assertEqual(row['candidate_count'],count)
                self.assertEqual(row['present_tickers'],count)
                self.assertEqual(row['missing'],[])
    def test_historical_rows_are_not_prospective_holdout_events(self):
        h=R['frozen_pool_coverage']['prospective_temporal_holdout_candidate']
        self.assertIs(h['historical_rows_eligible_as_holdout_events'],False)
        self.assertLess(h['max_filing_date'],'2026-10-04')
    def test_legacy_store_is_preserved_as_historical_gate_evidence(self):
        s=R['legacy_store_at_premerge_pin']
        self.assertIs(s['accession_column_present'],False)
        self.assertNotIn('accession',s['columns'])
    def test_no_body_or_trial_event_assignment_is_claimed(self):
        self.assertEqual(R['body_reads'],0)
        self.assertEqual(R['event_assignments'],0)
        self.assertEqual(R['source_revision_assignments'],0)
        self.assertIs(R['event_identity_admitted'],False)
        self.assertIs(R['trial_registered'],False)
if __name__=='__main__': unittest.main()
