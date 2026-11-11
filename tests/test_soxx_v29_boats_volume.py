"""Synthetic falsifiers for BOATS source-clock versus trade-volume support.

No vendor prices, credentials, network, original 91-episode backtest or
source-dependent private files are needed in hosted CI.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path
import sys
import unittest

FULL = (Path(__file__).resolve().parents[1] /
        "research" / "soxx-multitimeframe-cycle-2026-10-11" / "fullsession_v12")
sys.path.insert(0, str(FULL))

from fullsession import Bar  # noqa: E402

m = importlib.import_module(
    "research.soxx-multitimeframe-cycle-2026-10-11.prospective_validation_v26."
    "boats_volume_support_v29"
)

UTC = timezone.utc
START = datetime(2026, 10, 13, 0, 0, tzinfo=UTC)


def originals(n=480):
    return [Bar("SOXX", START + timedelta(minutes=i), 1,
                100., 100., 100., 100., 1, "tiingo-boats", "raw")
            for i in range(n)]


def zero_nonflat(row):
    return replace(row, open=100., high=101., low=99., close=100.5, volume=0)


class TestV29TradeSupport(unittest.TestCase):
    def run_night(self, bars=None):
        return m.audit_volume_support(
            originals() if bars is None else bars,
            night_starts_et=["2026-10-12"]
        )

    def test_full_timestamp_night_does_not_assert_fill_or_backtest(self):
        x = self.run_night()
        self.assertEqual(x["status"], "SOURCE_CADENCE_AND_VOLUME_DESCRIPTIVE_ONLY")
        self.assertEqual(x["original_v13_source_rows"], 480)
        self.assertEqual(x["original_v13_30m_buckets"], 16)
        self.assertTrue(x["nights"][0]["complete_clock_lattice"])
        self.assertEqual(x["nights"][0]["positive_reported_volume_minutes"], 480)
        self.assertEqual(x["nights"][0]["complete_30m_buckets_all_positive_reported_volume"], 16)
        self.assertFalse(x["marketable_bid_ask_fill_proven"])
        self.assertFalse(x["independent_trading_performance_accepted"])
        self.assertFalse(x["point_in_time_research_accepted"])
        self.assertEqual(x["market_data_price_rows_emitted"], 0)

    def test_single_zero_volume_moving_price_is_not_trade_supported(self):
        bars=originals()
        bars[15]=zero_nonflat(bars[15])
        x=self.run_night(bars)["nights"][0]
        self.assertEqual(x["zero_volume_minutes"],1)
        self.assertEqual(x["zero_volume_nonflat_ohlc_minutes"],1)
        self.assertEqual(x["zero_volume_open_close_movement_minutes"],1)
        self.assertEqual(x["complete_30m_buckets_with_zero_volume_minute"],1)
        self.assertEqual(x["complete_30m_buckets_all_positive_reported_volume"],15)
        self.assertFalse(x["volume_proves_execution_marketability"])

    def test_zero_volume_flat_is_not_spurious_price_movement(self):
        bars=originals()
        bars[19]=replace(bars[19],volume=0)
        x=self.run_night(bars)["nights"][0]
        self.assertEqual(x["zero_volume_minutes"],1)
        self.assertEqual(x["zero_volume_nonflat_ohlc_minutes"],0)

    def test_unknown_volume_is_not_silently_zero(self):
        bars=originals()
        bars[29]=replace(bars[29],volume=None)
        x=self.run_night(bars)["nights"][0]
        self.assertEqual(x["unknown_volume_minutes"],1)
        self.assertEqual(x["zero_volume_minutes"],0)
        self.assertEqual(x["complete_30m_buckets_with_unknown_volume_minute"],1)
        self.assertEqual(x["complete_30m_buckets_all_positive_reported_volume"],15)

    def test_overlap_of_zero_and_unknown_is_not_miscounted(self):
        bars=originals()
        bars[0]=replace(bars[0],volume=None)
        bars[1]=zero_nonflat(bars[1])
        x=self.run_night(bars)["nights"][0]
        self.assertEqual(x["complete_30m_buckets_with_unknown_volume_minute"],1)
        self.assertEqual(x["complete_30m_buckets_with_zero_volume_minute"],1)
        self.assertEqual(x["complete_30m_buckets_all_positive_reported_volume"],15)
        self.assertEqual(x["complete_30m_buckets_with_zero_and_unknown"],1)

    def test_all_480_zero_volume_can_still_have_a_complete_clock(self):
        bars=originals()
        bars=[replace(b,volume=0) for b in bars]
        x=self.run_night(bars)
        night=x["nights"][0]
        self.assertTrue(night["complete_clock_lattice"])
        self.assertEqual(night["zero_volume_minutes"],480)
        self.assertEqual(night["positive_reported_volume_minutes"],0)
        self.assertEqual(night["strict_complete_30m_timestamp_buckets"],16)
        self.assertEqual(night["complete_30m_buckets_with_zero_volume_minute"],16)
        self.assertEqual(night["complete_30m_buckets_all_positive_reported_volume"],0)
        self.assertFalse(x["marketable_bid_ask_fill_proven"])

    def test_one_missing_minute_destroys_30m_completeness(self):
        bars=originals()
        del bars[15]
        x=self.run_night(bars)
        self.assertEqual(x["original_v13_source_rows"],479)
        self.assertFalse(x["nights"][0]["complete_clock_lattice"])
        self.assertEqual(x["nights"][0]["missing_source_minute_slots"],1)
        self.assertEqual(x["nights"][0]["strict_complete_30m_timestamp_buckets"],15)

    def test_reversed_order_not_silently_sorted(self):
        bars=originals()
        bars[5],bars[6]=bars[6],bars[5]
        with self.assertRaisesRegex(ValueError,"unsorted"):
            self.run_night(bars)

    def test_duplicate_minute_not_second_economic_observation(self):
        bars=originals()
        bars.insert(8,bars[8])
        with self.assertRaisesRegex(ValueError,"duplicate source minute"):
            self.run_night(bars)

    def test_mixed_symbol_rejected(self):
        bars=originals()
        bars[0]=replace(bars[0],symbol="AMD")
        with self.assertRaisesRegex(ValueError,"mixed original symbol"):
            self.run_night(bars)

    def test_non_venue_bars_rejected(self):
        bars=originals()
        bars[0]=replace(bars[0],source="other-venue")
        with self.assertRaisesRegex(ValueError,"qualified raw"):
            self.run_night(bars)

    def test_adjusted_prices_not_raw_evidence(self):
        bars=originals()
        bars[0]=replace(bars[0],basis="split")
        with self.assertRaisesRegex(ValueError,"qualified raw"):
            self.run_night(bars)

    def test_off_minute_clock_rejected(self):
        bars=originals()
        bars[0]=replace(bars[0],utc=START+timedelta(seconds=3))
        with self.assertRaisesRegex(ValueError,"exact minute"):
            self.run_night(bars)

    def test_requested_night_is_not_any_arbitrary_source_night(self):
        with self.assertRaisesRegex(ValueError,"unrequested night"):
            m.audit_volume_support(originals(),night_starts_et=["2026-10-11"])

    def test_duplicate_source_night_request_refused_by_owner_calendar(self):
        with self.assertRaisesRegex(ValueError,"duplicate overnight date"):
            m.audit_volume_support(originals(),night_starts_et=["2026-10-12","2026-10-12"])

    def test_friday_night_closed_session_not_called_missing_data(self):
        with self.assertRaisesRegex(ValueError, "nontrading overnight start"):
            m.audit_volume_support([], night_starts_et=["2026-10-09"])

    def test_saturday_night_closed_session_not_called_missing_data(self):
        with self.assertRaisesRegex(ValueError, "nontrading overnight start"):
            m.audit_volume_support([], night_starts_et=["2026-10-10"])

    def test_sunday_night_is_eligible_but_still_unknown_without_source(self):
        out=m.audit_volume_support([], night_starts_et=["2026-10-11"])
        self.assertEqual(out["nights"][0]["observed_source_minute_slots"],0)
        self.assertEqual(out["nights"][0]["missing_source_minute_slots"],480)
        self.assertFalse(out["nights"][0]["complete_clock_lattice"])

    def test_empty_source_is_missing_not_zero_return(self):
        result=self.run_night([])
        self.assertEqual(result["nights"][0]["observed_source_minute_slots"],0)
        self.assertFalse(result["nights"][0]["complete_clock_lattice"])
        self.assertEqual(result["nights"][0]["missing_source_minute_slots"],480)
        self.assertEqual(result["nights"][0]["strict_complete_30m_timestamp_buckets"],0)
        self.assertFalse(result["independent_trading_performance_accepted"])


if __name__=="__main__":
    unittest.main()
