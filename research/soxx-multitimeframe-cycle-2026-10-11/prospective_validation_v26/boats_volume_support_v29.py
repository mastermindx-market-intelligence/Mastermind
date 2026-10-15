"""BOATS historical minute-bar volume support, never historical execution proof.

Pure research-only consumer of already receipt-qualified original Bar objects.
The incumbent fullsession_v12 supplies the actual ET session calendar and the
unmodified completeness-gated 1m->30m resampler. No API, filesystem, credentials,
alternative calendar, return forecast, model fitting, fill assumptions or trading.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Sequence

from fullsession import Bar, classify_session, trade_date
from tiingo_l1_v13 import audit_overnight_nights, resample_complete_30m


def audit_volume_support(bars: Sequence[Bar], *, night_starts_et: Sequence[str]) -> dict:
    """Separately describe minute-slot presence and reported trade-volume support.

    Zero-volume OHLC with nonzero range is *ambiguous source price semantics*.
    It is not permission to assume quote-derived price or a trade that did not
    occur. Even strictly positive reported venue volume cannot prove the high,
    low, midpoint, or any contemplated sale was marketably executable.

    Inputs must come from the ORIGINAL receipt-bound v13 consumer. This pure
    function does not authenticate caller claims or accept provider source rights.
    """
    if not isinstance(bars, (list, tuple)) or not isinstance(night_starts_et, (list, tuple)):
        raise ValueError("explicit Bar sequence and original ET night selection required")
    if any(not isinstance(b, Bar) for b in bars):
        raise ValueError("only original normalized Bar objects accepted")
    if any(b.minutes != 1 or b.source != "tiingo-boats" or b.basis != "raw"
           or classify_session(b.utc) != "overnight" for b in bars):
        raise ValueError("qualified raw 1-minute BOATS overnight bars required")
    if len({b.symbol for b in bars}) > 1:
        raise ValueError("mixed original symbol populations")
    if any(b.utc.second or b.utc.microsecond for b in bars):
        raise ValueError("one-minute timestamps must align to exact minute starts")

    times = [b.utc for b in bars]
    if times != sorted(times):
        raise ValueError("unsorted original minute bars")
    if len(times) != len(set(times)):
        raise ValueError("duplicate source minute instant")

    coverage = audit_overnight_nights(bars, night_starts_et=night_starts_et)
    completed, rollup = resample_complete_30m(bars)
    by_night = defaultdict(Counter)
    selected = {r["night_start_et"] for r in coverage}
    for b in bars:
        night = (trade_date(b.utc) - timedelta(days=1)).isoformat()
        if night not in selected:
            raise ValueError("unrequested night in source input")
        stats = by_night[night]
        stats["observed_source_minutes"] += 1
        if b.volume is None:
            stats["unknown_volume_minutes"] += 1
        elif b.volume == 0:
            stats["zero_volume_minutes"] += 1
            if b.high > b.low:
                stats["zero_volume_nonflat_ohlc_minutes"] += 1
            if b.open != b.close:
                stats["zero_volume_open_close_movement_minutes"] += 1
        else:
            stats["positive_reported_volume_minutes"] += 1

    by_utc = {b.utc: b for b in bars}
    for bucket in completed:
        night = (trade_date(bucket.utc) - timedelta(days=1)).isoformat()
        stats = by_night[night]
        stats["complete_30m_timestamp_buckets"] += 1
        original = [by_utc.get(bucket.utc + timedelta(minutes=i)) for i in range(30)]
        if any(b is None for b in original):
            raise AssertionError("canonical complete bucket omitted original minute")
        zero = sum(b.volume == 0 for b in original)
        unknown = sum(b.volume is None for b in original)
        if zero:
            stats["complete_30m_buckets_with_zero_volume_minute"] += 1
        if unknown:
            stats["complete_30m_buckets_with_unknown_volume_minute"] += 1
        if zero and unknown:
            stats["complete_30m_buckets_with_zero_and_unknown"] += 1
        if not zero and not unknown:
            stats["complete_30m_buckets_all_positive_reported_volume"] += 1
        stats["largest_zero_volume_minutes_in_a_30m_bucket"] = max(
            stats["largest_zero_volume_minutes_in_a_30m_bucket"], zero
        )

    per_night = []
    for item in coverage:
        night = item["night_start_et"]
        stats = by_night[night]
        expected = item["observed_minutes"]
        if expected != stats["observed_source_minutes"]:
            raise AssertionError("original session denominator does not match volume evidence")
        if (stats["positive_reported_volume_minutes"] + stats["zero_volume_minutes"]
                + stats["unknown_volume_minutes"]) != expected:
            raise AssertionError("volume categories fail to partition the source")
        n = stats["complete_30m_timestamp_buckets"]
        partition = (stats["complete_30m_buckets_all_positive_reported_volume"]
                     + stats["complete_30m_buckets_with_zero_volume_minute"]
                     + stats["complete_30m_buckets_with_unknown_volume_minute"]
                     - stats["complete_30m_buckets_with_zero_and_unknown"])
        if partition != n:
            raise AssertionError("30m support counts do not reconcile")
        per_night.append({
            "night_start_et": night,
            "expected_source_minute_slots": item["expected_minutes"],
            "observed_source_minute_slots": expected,
            "missing_source_minute_slots": item["missing_minutes"],
            "complete_clock_lattice": item["complete_overnight"],
            "positive_reported_volume_minutes": stats["positive_reported_volume_minutes"],
            "zero_volume_minutes": stats["zero_volume_minutes"],
            "unknown_volume_minutes": stats["unknown_volume_minutes"],
            "zero_volume_nonflat_ohlc_minutes": stats["zero_volume_nonflat_ohlc_minutes"],
            "zero_volume_open_close_movement_minutes": stats[
                "zero_volume_open_close_movement_minutes"],
            "strict_complete_30m_timestamp_buckets": n,
            "complete_30m_buckets_with_zero_volume_minute": stats[
                "complete_30m_buckets_with_zero_volume_minute"],
            "complete_30m_buckets_with_unknown_volume_minute": stats[
                "complete_30m_buckets_with_unknown_volume_minute"],
            "complete_30m_buckets_all_positive_reported_volume": stats[
                "complete_30m_buckets_all_positive_reported_volume"],
            "complete_30m_buckets_with_zero_and_unknown": stats[
                "complete_30m_buckets_with_zero_and_unknown"],
            "max_zero_volume_minutes_inside_30m": stats[
                "largest_zero_volume_minutes_in_a_30m_bucket"],
            "volume_proves_execution_marketability": False,
            "zero_volume_price_basis_qualified_as_trades": False,
        })
    return {
        "schema": "mastermind.soxx.boats_volume_support.v29",
        "status": "SOURCE_CADENCE_AND_VOLUME_DESCRIPTIVE_ONLY",
        "original_v13_source_rows": len(bars),
        "original_v13_30m_buckets": rollup["complete_30m"],
        "nights": per_night,
        "zero_volume_nonflat_bar_price_semantics": "UNQUALIFIED",
        "marketable_bid_ask_fill_proven": False,
        "point_in_time_research_accepted": False,
        "source_rights_redistribution_admitted": False,
        "independent_trading_performance_accepted": False,
        "market_data_price_rows_emitted": 0,
        "note": "A full minute clock and trade volume count never establish executable transaction prices.",
    }
