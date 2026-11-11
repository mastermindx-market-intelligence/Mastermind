"""Pure invented-data falsifiers for BOATS original-vintage comparison.

No Tiingo data, credentials, vendor requests, OHLC rows or strategy backtest.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime,timedelta,timezone
from importlib import import_module
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"/"soxx-multitimeframe-cycle-2026-10-11"/"fullsession_v12"))
from fullsession import Bar  # noqa E402

m=import_module("research.soxx-multitimeframe-cycle-2026-10-11.prospective_validation_v26.boats_source_overlap_v31")
UTC=timezone.utc
T0=datetime(2026,9,28,0,tzinfo=UTC)
A="a"*64
B="b"*64


def series(start=0,stop=6):
    return [Bar("SOXX",T0+timedelta(minutes=i),1,
                100.,100.,100.,100.,1,"tiingo-boats","raw")
            for i in range(start,stop)]


def audit(old=None,new=None,**kwargs):
    return m.audit_receipt_overlap(
      series(0,6) if old is None else old,
      series(3,9) if new is None else new,
      original_raw_sha256=kwargs.get("oldsha",A),
      candidate_raw_sha256=kwargs.get("newsha",B))


class TestV31Overlap(unittest.TestCase):
    def test_exact_overlap_does_not_invent_market_acceptance(self):
        x=audit()
        self.assertEqual(x["status"],"SOURCE_TIME_OVERLAP_EXACT_NO_PRICE_CONFLICT")
        self.assertEqual(x["overlapping_original_UTC_minute_instants"],3)
        self.assertEqual(x["overlapping_identical_OHLCV_rows"],3)
        self.assertEqual(x["overlapping_conflicting_OHLCV_rows"],0)
        self.assertEqual(x["candidate_new_UTC_minute_instants"],3)
        self.assertEqual(x["original_only_UTC_minute_instants"],3)
        self.assertEqual(x["distinct_UTC_minute_instants"],9)
        self.assertFalse(x["joined_price_series_constructed"])
        self.assertFalse(x["overlap_consistency_implies_point_in_time_qualified"])
        self.assertFalse(x["overlap_consistency_implies_quote_executable"])
        self.assertFalse(x["independent_strategy_validation_accepted"])
        self.assertEqual(x["source_price_rows_exported"],0)

    def test_ohlc_change_quarantines_without_outputting_price(self):
        new=series(3,9)
        new[0]=replace(new[0],high=101.,low=99.,close=100.5)
        x=audit(new=new)
        self.assertEqual(x["status"],"QUARANTINE_CONFLICTING_HISTORICAL_VINTAGES")
        self.assertEqual(x["overlapping_conflicting_OHLCV_rows"],1)
        self.assertEqual(x["overlapping_identical_OHLCV_rows"],2)
        self.assertEqual(x["overlap_conflicting_field_counts"],{"high":1,"low":1,"close":1})
        self.assertNotIn("prices",x)

    def test_volume_change_is_a_vintage_disagreement(self):
        new=series(3,9)
        new[1]=replace(new[1],volume=0)
        x=audit(new=new)
        self.assertEqual(x["overlapping_conflicting_OHLCV_rows"],1)
        self.assertEqual(x["overlap_conflicting_field_counts"],{"volume":1})

    def test_unknown_volume_to_zero_is_not_equal(self):
        old=series()
        new=series(3,9)
        old[4]=replace(old[4],volume=None)
        new[1]=replace(new[1],volume=0)
        x=audit(old=old,new=new)
        self.assertEqual(x["overlap_conflicting_field_counts"],{"volume":1})

    def test_disjoint_is_not_market_proof(self):
        x=audit(old=series(0,3),new=series(3,9))
        self.assertEqual(x["status"],"DISJOINT_ORIGINAL_SOURCE_TIMESTAMPS_NO_VINTAGE_COMPARISON")
        self.assertEqual(x["overlapping_original_UTC_minute_instants"],0)
        self.assertEqual(x["candidate_new_UTC_minute_instants"],6)
        self.assertFalse(x["overlap_consistency_implies_quote_executable"])

    def test_entirely_matching_different_receipts_not_two_trials(self):
        x=audit(old=series(0,6),new=series(0,6))
        self.assertEqual(x["overlapping_identical_OHLCV_rows"],6)
        self.assertEqual(x["candidate_new_UTC_minute_instants"],0)
        self.assertEqual(x["distinct_UTC_minute_instants"],6)

    def test_empty_candidate_cannot_add_history(self):
        x=audit(new=[])
        self.assertEqual(x["candidate_source_minute_rows"],0)
        self.assertEqual(x["candidate_new_UTC_minute_instants"],0)

    def test_empty_baseline_keeps_source_truth_unverified(self):
        x=audit(old=[])
        self.assertEqual(x["candidate_new_UTC_minute_instants"],6)
        self.assertFalse(x["overlap_consistency_implies_point_in_time_qualified"])

    def test_same_digest_is_not_distinct_vintage(self):
        with self.assertRaisesRegex(ValueError,"same source digest"):
            audit(newsha=A)

    def test_malformed_digest_rejected(self):
        with self.assertRaisesRegex(ValueError,"canonical lowercase"):
            audit(oldsha="BAD")
        with self.assertRaisesRegex(ValueError,"canonical lowercase"):
            audit(newsha="F"*64)

    def test_duplicate_original_clock_is_rejected(self):
        old=series()
        old.insert(1,old[0])
        with self.assertRaisesRegex(ValueError,"unsorted or duplicate"):
            audit(old=old)

    def test_unsorted_candidate_clock_is_rejected(self):
        new=series(3,9)
        new[0],new[1]=new[1],new[0]
        with self.assertRaisesRegex(ValueError,"unsorted or duplicate"):
            audit(new=new)

    def test_mixed_original_symbol_refused(self):
        old=series()
        old[0]=replace(old[0],symbol="AMD")
        with self.assertRaisesRegex(ValueError,"SOXX one-minute"):
            audit(old=old)

    def test_wrong_source_and_adjusted_basis_refused(self):
        old=series()
        old[0]=replace(old[0],source="other-venue")
        with self.assertRaisesRegex(ValueError,"not raw canonical"):
            audit(old=old)
        old=series()
        old[1]=replace(old[1],basis="split")
        with self.assertRaisesRegex(ValueError,"not raw canonical"):
            audit(old=old)

    def test_wrong_interval_refused(self):
        old=series()
        old[0]=replace(old[0],minutes=5)
        with self.assertRaisesRegex(ValueError,"SOXX one-minute"):
            audit(old=old)

    def test_off_minute_start_refused(self):
        old=series()
        old[0]=replace(old[0],utc=old[0].utc+timedelta(seconds=10))
        with self.assertRaisesRegex(ValueError,"not aligned"):
            audit(old=old)

if __name__=="__main__":
    unittest.main()
