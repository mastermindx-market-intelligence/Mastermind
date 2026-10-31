"""Synthetic/structural tests. None of these are historical market backtests."""
import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Rules, _fill_trade, evaluate, leader_panel, validate_bars

DAY = date(2026, 10, 30)
PREV = date(2026, 10, 29)


def bar_rows(bars, day="2026-10-30", symbol="A", frame=30):
    start = pd.Timestamp(day + " 09:30", tz="America/New_York")
    return pd.DataFrame([{
        "timestamp_utc": (start + pd.Timedelta(minutes=(i + 1) * frame)).tz_convert("UTC"),
        "symbol": symbol, "open": o, "high": h, "low": l, "close": c,
        "volume": 100000,
        "session": "RTH", "final": True,
    } for i, (o, h, l, c) in enumerate(bars)])


def pattern():
    # 3 red candles, green pivot, trigger above pivot high, continuation to 2R.
    return [(100, 100.2, 98.8, 99), (99, 99.2, 97.8, 98),
            (98, 98.2, 96.8, 97), (97, 99, 96.5, 98),
            (98, 100.5, 97.8, 100), (100, 106, 99, 105)]


def leaders(d=PREV, who=("A",)):
    return {d: {"leaders": set(who), "coverage": 1, "expected": len(who), "qualified": len(who)},
            DAY: {"leaders": set(), "coverage": 1, "expected": len(who), "qualified": 0}}


def make_daily(n=75, missing=(), last_shift=0.0):
    days = list(pd.bdate_range("2026-06-15", periods=n).date)
    daily = []
    start = days[0]
    for j, dt in enumerate(days):
        for sym, slope, base in [("SPY", .001, 450), ("A", .005, 50),
                                  ("B", .0005, 50), ("C", .003, 60)]:
            if (dt, sym) in missing:
                continue
            adjustment = last_shift if j == n - 1 and sym == "A" else 0
            daily.append({"date": dt, "symbol": sym,
                          "close": base * (1 + slope) ** j + adjustment,
                          "volume": 1_000_000})
    membership = pd.DataFrame([{"symbol": s, "start_date": start, "end_date": ""}
                               for s in ("A", "B", "C")])
    return pd.DataFrame(daily), membership, days


class Bars(unittest.TestCase):
    def test_valid_pivot(self):
        b = validate_bars(bar_rows(pattern()), Rules())
        self.assertEqual(len(b), 6)
        self.assertEqual(b.iloc[0].session_date, DAY)

    def test_reject_ohlc_and_nonfinite(self):
        b = bar_rows(pattern())
        b.loc[0, "high"] = 1
        with self.assertRaises(ValueError):
            validate_bars(b, Rules())
        b = bar_rows(pattern())
        b.loc[0, "volume"] = float("nan")
        with self.assertRaises(ValueError):
            validate_bars(b, Rules())

    def test_duplicate_and_missing_intraday(self):
        b = bar_rows(pattern())
        with self.assertRaises(ValueError):
            validate_bars(pd.concat([b, b.iloc[[0]]]), Rules())
        with self.assertRaises(ValueError):
            validate_bars(b.drop(2), Rules())

    def test_24h_bars_rejected_without_qualified_path(self):
        b = bar_rows(pattern())
        b["session"] = "24H"
        with self.assertRaises(ValueError):
            validate_bars(b, Rules())

    def test_incomplete_and_45m_partial(self):
        b = bar_rows(pattern())
        b.loc[0, "final"] = False
        with self.assertRaises(ValueError):
            validate_bars(b, Rules())
        b = bar_rows(pattern()[:3], frame=45)
        self.assertEqual(len(validate_bars(b, Rules(timeframe_minutes=45))), 3)
        b.loc[2, "timestamp_utc"] += pd.Timedelta(minutes=15)
        with self.assertRaises(ValueError):
            validate_bars(b, Rules(timeframe_minutes=45))

    def test_csv_string_false_is_false(self):
        b = bar_rows(pattern())
        b["final"] = ["true"] * 5 + ["false"]
        with self.assertRaises(ValueError):
            validate_bars(b, Rules())

    def test_prior_session_leader_works_before_current_close(self):
        # Today's closing snapshot cannot be required for an intraday signal.
        r = evaluate(bar_rows(pattern()), {PREV: {"leaders": {"A"}}}, Rules())
        self.assertEqual(len(r["events"]["pivot"]), 1)

    def test_owner_prior_calendar_refuses_stale_last_known_snapshot(self):
        old = date(2026, 10, 28)
        r = evaluate(bar_rows(pattern()), {old: {"leaders": {"A"}}}, Rules(),
                     prior_session_by_day={DAY: PREV})
        self.assertEqual(len(r["events"]["pivot"]), 0)

    def test_strict_historical_evaluation_requires_prior_session_owner(self):
        with self.assertRaisesRegex(ValueError, "prior session map"):
            evaluate(bar_rows(pattern()), {PREV: {"leaders": {"A"}}}, Rules(),
                     session_schedule={DAY: (
                         pd.Timestamp('2026-10-30T13:30:00Z'),
                         pd.Timestamp('2026-10-30T20:00:00Z'))},
                     require_complete_sessions=True)

    def test_new_york_dst(self):
        b = pd.concat([bar_rows(pattern()[:2], day="2026-10-30"),
                       bar_rows(pattern()[:2], day="2026-11-02")], ignore_index=True)
        b = validate_bars(b, Rules())
        self.assertEqual(b.iloc[0].local_end.utcoffset().total_seconds(), -4*3600)
        self.assertEqual(b.iloc[2].local_end.utcoffset().total_seconds(), -5*3600)


class Leaders(unittest.TestCase):
    def test_prior_day_rs_leader_and_not_survivors_only(self):
        d, m, days = make_daily()
        p = leader_panel(d, m, Rules(min_universe=3, min_adv_dollars=1, rs_top_fraction=.34))
        self.assertIn("A", p[days[-1]]["leaders"])
        self.assertNotIn("B", p[days[-1]]["leaders"])
        self.assertEqual(p[days[-1]]["expected"], 3)

    def test_missing_member_disqualifies_even_if_survivor_wins(self):
        d, m, days = make_daily()
        # A missing daily row reduces PIT coverage below 95%; no new leaders.
        d = d[~((d.date == days[-1]) & (d.symbol == "C"))]
        p = leader_panel(d, m, Rules(min_universe=2, min_adv_dollars=1))
        self.assertEqual(p[days[-1]]["leaders"], set())
        self.assertLess(p[days[-1]]["coverage"], 0.95)

    def test_delisted_membership_asof(self):
        d, m, days = make_daily()
        m.loc[m.symbol == "C", "end_date"] = str(days[-2])
        p = leader_panel(d, m, Rules(min_universe=2, min_adv_dollars=1, rs_top_fraction=.5))
        self.assertEqual(p[days[-1]]["expected"], 2)

    def test_future_price_does_not_change_yesterday(self):
        d, m, days = make_daily()
        cfg = Rules(min_universe=2, min_adv_dollars=1, rs_top_fraction=.5)
        p0 = leader_panel(d, m, cfg)
        d2 = d.copy()
        d2.loc[(d2.date == days[-1]) & (d2.symbol == "A"), "close"] *= .25
        p1 = leader_panel(d2, m, cfg)
        self.assertEqual(p0[days[-2]]["leaders"], p1[days[-2]]["leaders"])

    def test_not_enough_trading_sessions_no_leaders(self):
        d, m, days = make_daily(50)
        p = leader_panel(d, m, Rules(min_universe=2, min_adv_dollars=1))
        self.assertEqual(p[days[-1]]["leaders"], set())

    def test_missing_benchmark_rejected(self):
        d, m, _ = make_daily()
        with self.assertRaises(ValueError):
            leader_panel(d[d.symbol != "SPY"], m, Rules(min_universe=1))


class PivotExecution(unittest.TestCase):
    def test_pivot_two_r_and_no_same_bar_entry(self):
        r = evaluate(bar_rows(pattern()), leaders(), Rules(min_universe=1))
        xs = r["events"]["pivot"]
        self.assertEqual(len(xs), 1)
        self.assertEqual(xs[0]["entry_method"], "stop_above_pivot_high")
        self.assertTrue(xs[0]["entry_bar_end_utc"].endswith("16:00:00+00:00"))
        self.assertEqual(xs[0]["exit_reason"], "TARGET")
        self.assertGreater(xs[0]["net_r"], 1.9)
        self.assertFalse(r["performance_is_empirically_validated"])

    def test_no_leader_at_prior_session_rejects(self):
        r = evaluate(bar_rows(pattern()), leaders(who=("B",)), Rules())
        self.assertEqual(len(r["events"]["pivot"]), 0)
        self.assertEqual(r["diagnostics"]["pivot"]["skipped_no_leader"], 1)

    def test_current_day_does_not_make_yesterday_leader(self):
        r = evaluate(bar_rows(pattern()), {DAY: {"leaders": {"A"}}}, Rules())
        self.assertEqual(len(r["events"]["pivot"]), 0)

    def test_two_bar_trigger_expiry_and_invalidation(self):
        q = pattern()[:4] + [(98, 98.5, 97.5, 98.1),
                              (98.1, 98.7, 96.0, 98.5), (98.5, 102, 98, 101)]
        r = evaluate(bar_rows(q), leaders(), Rules())
        self.assertEqual(len(r["events"]["pivot"]), 0)

    def test_stop_first_when_same_bar_hits_both(self):
        q = pattern()[:4] + [(98, 106, 95, 104)]
        r = evaluate(bar_rows(q), leaders(), Rules())
        self.assertEqual(r["events"]["pivot"][0]["exit_reason"], "STOP")
        self.assertLess(r["events"]["pivot"][0]["net_r"], -1.0)

    def test_gap_through_stop_worse_than_stop(self):
        q = pattern()[:5] + [(94, 95, 90, 93)]
        r = evaluate(bar_rows(q), leaders(), Rules())
        t = r["events"]["pivot"][0]
        self.assertEqual(t["exit_reason"], "STOP_GAP")
        self.assertLess(t["exit_px_after_cost"], t["raw_stop"])

    def test_entry_price_respects_gap_above_trigger(self):
        q = pattern()[:4] + [(102, 104, 100.5, 103), (103, 109, 102, 108)]
        t = evaluate(bar_rows(q), leaders(), Rules())["events"]["pivot"][0]
        self.assertGreater(t["entry_px_after_cost"], 102)

    def test_unresolved_horizon_is_censored_not_win(self):
        q = pattern()[:5]
        r = evaluate(bar_rows(q), leaders(), Rules(hold_sessions=5))
        self.assertIsNone(r["events"]["pivot"][0]["net_return"])
        self.assertIsNone(r["metrics"]["pivot"]["win_rate"])
        self.assertEqual(r["metrics"]["pivot"]["censored"], 1)

    def test_no_shaping_from_future_after_signal(self):
        q = pattern()
        one = evaluate(bar_rows(q), leaders(), Rules())["events"]["pivot"][0]
        two = evaluate(bar_rows(q + [(105, 109, 104, 108)]), leaders(), Rules())["events"]["pivot"][0]
        self.assertEqual(one["entry_px_after_cost"], two["entry_px_after_cost"])
        self.assertEqual(one["raw_stop"], two["raw_stop"])


class Oscillator(unittest.TestCase):
    def setUp(self):
        self.b = bar_rows(pattern())
        self.b["osc_fast"] = [-2, -3, -5, -3, -1, 1]
        self.b["osc_slow"] = [-2, -2.5, -4, -4, -2, 0]
        self.b["osc_oversold"] = [False, False, True, True, False, False]

    def test_cross_occurs_at_close_and_entry_next_bar(self):
        r = evaluate(self.b, leaders(), Rules())
        self.assertEqual(len(r["events"]["macd_rsi_proxy"]), 1)
        self.assertEqual(len(r["events"]["hybrid"]), 1)
        self.assertIn("16:00", r["events"]["macd_rsi_proxy"][0]["entry_bar_end_utc"])

    def test_supplied_boolean_strings_parsed_strictly(self):
        self.b["osc_oversold"] = ["false", "false", "true", "true", "false", "false"]
        r = evaluate(self.b, leaders(), Rules())
        self.assertEqual(len(r["events"]["macd_rsi_proxy"]), 1)
        self.assertEqual(r["osc_source"], "supplied_precomputed_columns")

    def test_hybrid_filters_pivot_without_prior_osc_cross(self):
        self.b["osc_fast"] = [-3] * len(self.b)
        self.b["osc_slow"] = [-4] * len(self.b)
        r = evaluate(self.b, leaders(), Rules())
        self.assertEqual(len(r["events"]["pivot"]), 1)
        self.assertEqual(len(r["events"]["hybrid"]), 0)
        self.assertEqual(len(r["events"]["macd_rsi_proxy"]), 0)

    def test_osc_cross_future_bar_cannot_qualify_past_pivot(self):
        self.b["osc_fast"] = [-5, -5, -5, -5, -3, -2]
        self.b["osc_slow"] = [-4] * len(self.b)
        self.b["osc_oversold"] = True
        r = evaluate(self.b, leaders(), Rules())
        self.assertEqual(len(r["events"]["hybrid"]), 0)

    def test_macd_proxy_not_named_exact_user_indicator(self):
        r = evaluate(bar_rows(pattern()), leaders(), Rules())
        self.assertIn("macd_rsi_proxy", r["metrics"])
        self.assertNotIn("TradingView_MACD_RSI_exact", r["metrics"])


class OwnerCalendarCoverage(unittest.TestCase):
    """Owner calendar is supplied; this test never claims an admitted market source."""

    @staticmethod
    def schedule(day="2026-10-30", closing="16:00"):
        open_et = pd.Timestamp(day + " 09:30", tz="America/New_York")
        close_et = pd.Timestamp(day + " " + closing, tz="America/New_York")
        return {date.fromisoformat(day): (open_et.tz_convert("UTC"), close_et.tz_convert("UTC"))}

    def test_historical_complete_requires_owner_schedule(self):
        with self.assertRaisesRegex(ValueError, "owner calendar"):
            validate_bars(bar_rows(pattern()), Rules(), require_complete_sessions=True)

    def test_first_opening_slot_missing_refuses_strict(self):
        b = bar_rows(pattern()).iloc[1:]
        with self.assertRaisesRegex(ValueError, "missing opening"):
            validate_bars(b, Rules(), session_schedule=self.schedule(), require_complete_sessions=True)
        kept = validate_bars(b, Rules(), session_schedule=self.schedule())
        self.assertEqual(set(kept.session_coverage_state), {"PARTIAL_OBSERVATION"})

    def test_final_truncated_session_refuses_strict(self):
        b = bar_rows(pattern()[:2])
        with self.assertRaisesRegex(ValueError, "trailing"):
            validate_bars(b, Rules(), session_schedule=self.schedule(), require_complete_sessions=True)

    def test_nyse_early_close_rejects_13_30_bar(self):
        day = "2026-11-27"
        b = bar_rows([(100, 101, 99, 100)] * 8, day=day)
        with self.assertRaisesRegex(ValueError, "early close"):
            validate_bars(b, Rules(), session_schedule=self.schedule(day, "13:00"))

    def test_halfday_full_bar_count_has_explicit_stub(self):
        day = "2026-11-27"
        b = bar_rows([(100, 101, 99, 100)], day=day, frame=180)
        out = validate_bars(b, Rules(timeframe_minutes=180),
                            session_schedule=self.schedule(day, "13:00"),
                            require_complete_sessions=True)
        self.assertEqual(out.iloc[0].session_coverage_state, "FULL_SUPPORTED_BARS")
        self.assertEqual(int(out.iloc[0].terminal_stub_minutes), 30)

    def test_normal_2h_and_3h_full_bars_preserve_30m_stubs(self):
        for frame, count in [(120, 3), (180, 2)]:
            with self.subTest(frame=frame):
                b = bar_rows([(100, 101, 99, 100)] * count, frame=frame)
                out = validate_bars(b, Rules(timeframe_minutes=frame),
                                    session_schedule=self.schedule(), require_complete_sessions=True)
                self.assertEqual(set(out.session_coverage_state), {"FULL_SUPPORTED_BARS"})
                self.assertEqual(set(out.terminal_stub_minutes), {30})

    def test_30m_normal_session_requires_all_13_full_slots(self):
        b = bar_rows([(100, 101, 99, 100)] * 13)
        out = validate_bars(b, Rules(), session_schedule=self.schedule(),
                            require_complete_sessions=True)
        self.assertEqual(set(out.session_coverage_state), {"FULL_SUPPORTED_BARS"})
        self.assertEqual(set(out.terminal_stub_minutes), {0})

    def test_missing_whole_session_between_observations(self):
        px = [(100, 101, 99, 100)] * 13
        b = pd.concat([bar_rows(px, day="2026-10-30"),
                       bar_rows(px, day="2026-11-03")], ignore_index=True)
        schedule = self.schedule("2026-10-30")
        schedule.update(self.schedule("2026-11-02"))
        schedule.update(self.schedule("2026-11-03"))
        with self.assertRaisesRegex(ValueError, "entire expected"):
            validate_bars(b, Rules(), session_schedule=schedule, require_complete_sessions=True)

    def test_dst_transition_uses_exchange_zone_not_utc_hour(self):
        before, after = self.schedule("2026-10-30"), self.schedule("2026-11-02")
        self.assertEqual(next(iter(before.values()))[0].hour, 13)
        self.assertEqual(next(iter(after.values()))[0].hour, 14)
        b = pd.concat([bar_rows([(100, 101, 99, 100)] * 13, day="2026-10-30"),
                       bar_rows([(100, 101, 99, 100)] * 13, day="2026-11-02")])
        s = {**before, **after}
        self.assertEqual(len(validate_bars(b, Rules(), session_schedule=s,
                                           require_complete_sessions=True)), 26)

    def test_naive_owner_calendar_is_refused(self):
        schedule = {DAY: ("2026-10-30T09:30:00", "2026-10-30T16:00:00")}
        with self.assertRaisesRegex(ValueError, "aware UTC"):
            validate_bars(bar_rows(pattern()), Rules(), session_schedule=schedule)

    def test_unqualified_bars_report_no_owner_schedule(self):
        b = validate_bars(bar_rows(pattern()), Rules())
        self.assertEqual(set(b.session_coverage_state), {"NO_OWNER_SCHEDULE"})

    def test_calendar_day_not_in_schedule_refused(self):
        with self.assertRaisesRegex(ValueError, "absent from supplied"):
            validate_bars(bar_rows(pattern()), Rules(), session_schedule=self.schedule("2026-11-02"))

    def test_evaluate_explicit_source_status_not_a_market_verdict(self):
        row = evaluate(bar_rows(pattern()), leaders(), Rules())
        self.assertEqual(row["session_calendar_status"], "NOT_OWNER_ATTESTED")
        self.assertFalse(row["historical_coverage_strict"])
        self.assertFalse(row["performance_is_empirically_validated"])


if __name__ == "__main__":
    unittest.main()
