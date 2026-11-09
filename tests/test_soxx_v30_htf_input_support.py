"""Synthetic, offline 2H/3H/4H source-window readiness tests.

No historical backtest replays, prices, vendor requests or actual order/quote
fills. Uses the incumbent fullsession.Bar and V29 original session validator.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from importlib import import_module
from pathlib import Path
import sys
import unittest

FULL = (Path(__file__).resolve().parents[1] /
        "research" / "soxx-multitimeframe-cycle-2026-10-11" / "fullsession_v12")
sys.path.insert(0, str(FULL))
from fullsession import Bar, ET, UTC

m = import_module(
    "research.soxx-multitimeframe-cycle-2026-10-11."
    "prospective_validation_v26.higher_timeframe_support_v30"
)


def bars_for(night="2026-10-12", n=480):
    start = datetime.combine(date.fromisoformat(night), time(20, 0), ET).astimezone(UTC)
    return [Bar("SOXX", start + timedelta(minutes=i), 1,
                100., 100., 100., 100., 1, "tiingo-boats", "raw")
            for i in range(n)]


def row(source, night="2026-10-12"):
    out=m.audit_overnight_htf_inputs(source,night_starts_et=[night])
    return out["nights"][0]["higher_timeframe_windows"]


class TestV30Readiness(unittest.TestCase):
    def test_full_overnight_source_2h_3h_4h_candidate_counts(self):
        bars=bars_for()
        grid=row(bars)
        for period,total in (("120m",4),("180m",2),("240m",2)):
            self.assertEqual(grid[period]["candidate_full_source_windows"],total)
            self.assertEqual(grid[period]["complete_original_1m_timestamp_windows"],total)
            self.assertEqual(grid[period]["complete_windows_all_positive_reported_volume"],total)
            self.assertEqual(grid[period]["incomplete_original_1m_timestamp_windows"],0)
            self.assertFalse(grid[period]["actual_price_based_2H_3H_4H_indicator_calculated"])
            self.assertFalse(grid[period]["execution_marketability_proven"])

    def test_3h_trailing_two_hours_not_promoted(self):
        grid=row(bars_for())
        self.assertEqual(grid["180m"]["candidate_full_source_windows"],2)
        self.assertEqual(grid["180m"]["excluded_trailing_minutes_not_called_complete"],120)
        self.assertEqual(grid["120m"]["excluded_trailing_minutes_not_called_complete"],0)
        self.assertEqual(grid["240m"]["excluded_trailing_minutes_not_called_complete"],0)

    def test_one_opening_minute_missing_blocks_each_first_higher_timeframe(self):
        bars=bars_for()[1:]
        grid=row(bars)
        self.assertEqual(grid["120m"]["complete_original_1m_timestamp_windows"],3)
        self.assertEqual(grid["180m"]["complete_original_1m_timestamp_windows"],1)
        self.assertEqual(grid["240m"]["complete_original_1m_timestamp_windows"],1)
        for tf in ("120m","180m","240m"):
            self.assertEqual(grid[tf]["missing_source_minute_inputs_inside_evaluated_windows"],1)

    def test_missing_minute_in_3h_trailing_part_not_a_missing_3h(self):
        bars=bars_for()[:-1]
        grid=row(bars)
        self.assertEqual(grid["120m"]["complete_original_1m_timestamp_windows"],3)
        self.assertEqual(grid["180m"]["complete_original_1m_timestamp_windows"],2)
        self.assertEqual(grid["240m"]["complete_original_1m_timestamp_windows"],1)
        self.assertEqual(grid["180m"]["missing_source_minute_inputs_inside_evaluated_windows"],0)

    def test_single_zero_volume_source_minute_taints_each_containing_block(self):
        bars=bars_for()
        bars[20]=replace(bars[20],volume=0)
        grid=row(bars)
        for tf,total in (("120m",4),("180m",2),("240m",2)):
            self.assertEqual(grid[tf]["complete_original_1m_timestamp_windows"],total)
            self.assertEqual(grid[tf]["complete_windows_with_zero_volume_minute"],1)
            self.assertEqual(grid[tf]["complete_windows_all_positive_reported_volume"],total-1)

    def test_unknown_volume_never_becomes_positive_trade(self):
        bars=bars_for()
        bars[5]=replace(bars[5],volume=None)
        grid=row(bars)
        self.assertEqual(grid["180m"]["complete_windows_with_unknown_volume_minute"],1)
        self.assertEqual(grid["180m"]["complete_windows_with_zero_volume_minute"],0)
        self.assertEqual(grid["180m"]["complete_windows_all_positive_reported_volume"],1)

    def test_zero_and_unknown_in_same_block_reconcile(self):
        bars=bars_for()
        bars[0]=replace(bars[0],volume=None)
        bars[1]=replace(bars[1],volume=0)
        grid=row(bars)
        self.assertEqual(grid["120m"]["complete_windows_with_both_zero_and_unknown_volume"],1)
        self.assertEqual(grid["120m"]["complete_windows_with_zero_volume_minute"],1)
        self.assertEqual(grid["120m"]["complete_windows_with_unknown_volume_minute"],1)
        self.assertEqual(grid["120m"]["complete_windows_all_positive_reported_volume"],3)

    def test_all_zero_volume_blocks_remain_timestamp_complete_not_executable(self):
        bars=[replace(b,volume=0) for b in bars_for()]
        out=m.audit_overnight_htf_inputs(bars,night_starts_et=["2026-10-12"])
        for tf,total in (("120m",4),("180m",2),("240m",2)):
            x=out["nights"][0]["higher_timeframe_windows"][tf]
            self.assertEqual(x["complete_original_1m_timestamp_windows"],total)
            self.assertEqual(x["complete_windows_all_positive_reported_volume"],0)
            self.assertEqual(x["complete_windows_with_zero_volume_minute"],total)
        self.assertFalse(out["venue_quotes_or_market_price_fills_proven"])
        self.assertFalse(out["independent_cycle_failure_strategy_accepted"])
        self.assertEqual(out["market_prices_or_rows_emitted"],0)

    def test_empty_eligible_sunday_does_not_imply_zero_return(self):
        grid=row([],"2026-10-11")
        self.assertEqual(grid["120m"]["complete_original_1m_timestamp_windows"],0)
        self.assertEqual(grid["120m"]["incomplete_original_1m_timestamp_windows"],4)
        self.assertEqual(grid["180m"]["incomplete_original_1m_timestamp_windows"],2)

    def test_closed_friday_and_saturday_are_refused_not_fake_gaps(self):
        for night in ("2026-10-09","2026-10-10"):
            with self.assertRaisesRegex(ValueError,"nontrading overnight start"):
                row([],night)

    def test_dst_after_fall_back_uses_original_session_clock(self):
        # Nov 1, 2026 is DST fall-back Sunday. Session starts at 20:00 in
        # EST; the local 01:00 fold occurred BEFORE the BOATS session.
        grid=row(bars_for("2026-11-01"),"2026-11-01")
        self.assertEqual(grid["120m"]["complete_original_1m_timestamp_windows"],4)
        self.assertEqual(grid["240m"]["complete_original_1m_timestamp_windows"],2)

    def test_two_valid_nights_are_not_one_independent_trial(self):
        a=bars_for("2026-10-11")
        b=bars_for("2026-10-12")
        out=m.audit_overnight_htf_inputs(a+b,night_starts_et=["2026-10-11","2026-10-12"])
        self.assertEqual(len(out["nights"]),2)
        self.assertEqual(out["source_rows"],960)
        self.assertFalse(out["PIT_research_admitted"])

    def test_duplicate_source_clock_rejected_by_underlying_original_v29(self):
        bars=bars_for()
        bars.insert(3,bars[3])
        with self.assertRaisesRegex(ValueError,"duplicate source minute"):
            row(bars)

    def test_adjusted_or_mixed_source_rejected_by_original_v29(self):
        bars=bars_for()
        bars[0]=replace(bars[0],basis="split")
        with self.assertRaisesRegex(ValueError,"qualified raw"):
            row(bars)


if __name__=="__main__":
    unittest.main()
