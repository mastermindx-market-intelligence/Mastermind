"""Offline BOATS 2H/3H/4H input-readiness count from already accepted L1 Bar rows.

Reuses ORIGINAL v13 session classification through v29 volume/clock validation.
No derived OHLC prices, indicators, cross-session patching, trend fitting,
collector, stored market rows, new calendar, quote assumption or trading logic.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from importlib import import_module
from typing import Sequence

from fullsession import Bar, ET, UTC

_v29 = import_module(
    "research.soxx-multitimeframe-cycle-2026-10-11."
    "prospective_validation_v26.boats_volume_support_v29"
)

WINDOWS_MINUTES = (120, 180, 240)
OVERNIGHT_MINUTES = 480


def audit_overnight_htf_inputs(bars: Sequence[Bar], *,
                               night_starts_et: Sequence[str]) -> dict:
    """Counts timestamp-complete blocks, not economically meaningful candles.

    The 8h overnight session is partitioned into FULL consecutive 2/3/4-hour
    windows anchored at 20:00 ET. The trailing 120m in a 3H partition is
    explicitly excluded, never promoted into a made-up 3H candle.

    The producer controls calendar holidays, licensing, source vintage and
    any RTH joins. This accepts only local source facts already qualified via
    the incumbent receipt-bound read_research_view/v13 consumer. It CANNOT
    prove execution, liquidity at order size, or PIT indicator eligibility.
    """
    verified = _v29.audit_volume_support(
        bars, night_starts_et=night_starts_et)
    by_time = {row.utc: row for row in bars}
    results = []
    for source_night in verified["nights"]:
        name = source_night["night_start_et"]
        start = datetime.combine(date.fromisoformat(name), time(20, 0), ET).astimezone(UTC)
        formats = {}
        for duration in WINDOWS_MINUTES:
            total = OVERNIGHT_MINUTES // duration
            trailing = OVERNIGHT_MINUTES % duration
            completed = zero = unknown = all_positive = missing_window = missing_inputs = overlap = 0
            for i in range(total):
                first = start + timedelta(minutes=i * duration)
                source = [by_time.get(first + timedelta(minutes=j))
                          for j in range(duration)]
                absent = sum(row is None for row in source)
                missing_inputs += absent
                if absent:
                    missing_window += 1
                    continue
                completed += 1
                has_zero = any(row.volume == 0 for row in source)
                has_unknown = any(row.volume is None for row in source)
                zero += int(has_zero)
                unknown += int(has_unknown)
                overlap += int(has_zero and has_unknown)
                if not has_zero and not has_unknown:
                    all_positive += 1
            if completed + missing_window != total:
                raise AssertionError("qualified full source input partition mismatch")
            if all_positive + zero + unknown - overlap != completed:
                raise AssertionError("volume support categories do not partition")
            formats[f"{duration}m"] = {
                "source_window_minutes": duration,
                "candidate_full_source_windows": total,
                "complete_original_1m_timestamp_windows": completed,
                "incomplete_original_1m_timestamp_windows": missing_window,
                "missing_source_minute_inputs_inside_evaluated_windows": missing_inputs,
                "complete_windows_with_zero_volume_minute": zero,
                "complete_windows_with_unknown_volume_minute": unknown,
                "complete_windows_with_both_zero_and_unknown_volume": overlap,
                "complete_windows_all_positive_reported_volume": all_positive,
                "excluded_trailing_minutes_not_called_complete": trailing,
                "actual_price_based_2H_3H_4H_indicator_calculated": False,
                "execution_marketability_proven": False,
            }
        results.append({
            "night_start_et": name,
            "source_minute_rows": source_night["observed_source_minute_slots"],
            "complete_eight_hour_source_clock": source_night["complete_clock_lattice"],
            "higher_timeframe_windows": formats,
        })
    return {
        "schema": "mastermind.soxx.boats_htf_input_support.v30",
        "status": "OVER_NIGHT_2H_3H_4H_SOURCE_WINDOW_COUNTS_ONLY",
        "method": "ORIGINAL_V13_BARS_AND_WEEKDAY_ONLY_V29_GATE",
        "nights": results,
        "source_rows": len(bars),
        "source_rights_admitted": False,
        "PIT_research_admitted": False,
        "venue_quotes_or_market_price_fills_proven": False,
        "independent_cycle_failure_strategy_accepted": False,
        "market_prices_or_rows_emitted": 0,
        "note": "Overnight-only partitions; original 3-RTH-hour exit and cross-session indicators require separate original RTH/calendar/marketability qualification.",
    }
