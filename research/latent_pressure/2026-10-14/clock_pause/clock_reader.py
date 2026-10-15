"""As-of historical execution visibility, never an accumulation forecast.
Example: python3 clock_reader.py --executions <qualified.csv.gz> --at 2026-10-05T14:00:00-04:00
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from clock_study import (EXPECTED_INPUT_SHA256, NAMES, SECOND, clock, count_window,
                         load, prefix_feature)


def asof_ns(value: str) -> tuple[pd.Timestamp, int]:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tz is None:
        raise ValueError('explicit finite timezone-aware as-of required')
    ns = int(timestamp.tz_convert('UTC').value)
    if not clock('10:00') <= ns <= clock('15:30'):
        raise ValueError('outside qualified historical date/window')
    return timestamp, ns


def observe_frame(frame: pd.DataFrame, cutoff_ns: int) -> list[dict[str, Any]]:
    if type(cutoff_ns) is not int or not clock('10:00') <= cutoff_ns <= clock('15:30'):
        raise ValueError('exact cutoff within qualified window required')
    records = []
    for ticker in NAMES:
        events = frame[(frame.ticker == ticker) & (frame.send_ns >= np.uint64(clock('09:45')))]
        times = events.send_ns.to_numpy(dtype=np.uint64)
        endpoint = int(np.searchsorted(times, np.uint64(cutoff_ns), side='right'))
        prefix = events.iloc[:endpoint]
        standard = prefix[prefix.sale_flags == 0]
        std_times = standard.send_ns.to_numpy(dtype=np.uint64)
        all_count = count_window(times[:endpoint], cutoff_ns - 60 * SECOND, cutoff_ns)
        standard_count = count_window(std_times, cutoff_ns - 60 * SECOND, cutoff_ns)
        other_count = all_count - standard_count
        if other_count < 0:
            raise ValueError('inconsistent standard/all record sets')
        if standard_count:
            activity = 'STANDARD_SUBSET_ACTIVE'
        elif other_count:
            activity = 'STANDARD_SUBSET_QUIET_OTHER_DISPLAYED_EXECUTIONS'
        else:
            activity = 'NO_DISPLAYED_EXECUTION_RECORDS_IN_LAST60S'
        feature, status = prefix_feature(standard, prefix, cutoff_ns, ticker)
        record = {
            'ticker': ticker, 'activity_state': activity, 'feature_status': status,
            'all_L_count_last60s': all_count, 'standard_flag0_count_last60s': standard_count,
            'other_flag_L_count_last60s': other_count,
            'last_observed_L_send_ns': str(int(prefix.send_ns.iloc[-1])) if len(prefix) else None,
            'last_observed_L_sequence': str(int(prefix.sequence.iloc[-1])) if len(prefix) else None,
            'last_standard_send_ns': str(int(standard.send_ns.iloc[-1])) if len(standard) else None,
            'standard_print_age_seconds': (cutoff_ns - int(standard.send_ns.iloc[-1])) / SECOND if len(standard) else None,
            'all_L_age_seconds': (cutoff_ns - int(prefix.send_ns.iloc[-1])) / SECOND if len(prefix) else None,
            'normalized_observed_standard_pause': feature['normalized_pause'] if feature else None,
            'pressure_direction': None, 'withdrawal_of_selling': None, 'quote_recovery': None,
            'institutional_inventory': None, 'forecast_probability': None,
            'warning': 'Absence in this subset is not absence of selling, all market trading, or resting liquidity.',
        }
        records.append(record)
    return records


def observe(path: Path, as_of: str) -> dict[str, Any]:
    stamp, ns = asof_ns(as_of)
    frame = load(path)
    records = observe_frame(frame, ns)
    return {
        'schema': 'historical_execution_visibility.v1_RESEARCH_ONLY',
        'as_of': stamp.isoformat(), 'decision_cutoff_ns': str(ns),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'input_sha256': EXPECTED_INPUT_SHA256,
        'source': 'Existing qualified IEX HIST DEEP+ displayed-execution extraction, 2026-10-05',
        'clock_basis': 'IEX source-send time; not original end-user receipt or execution latency proof',
        'coverage': 'All selected L records counted; only flag0 is the qualified price subset. Other message types and other venues excluded.',
        'records': records,
        'authority': {'rotation_call_write': False, 'live_alert': False, 'rank': False, 'size': False},
        'forecast_state': 'NO_VALIDATED_DIRECTIONAL_SIGNAL',
        'attribution': 'Data provided for free by IEX. Use of IEX Historical Data is subject to its terms.',
        'terms': 'https://www.iex.io/legal/hist-data-terms',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executions', type=Path, required=True)
    parser.add_argument('--at', required=True)
    args = parser.parse_args()
    print(json.dumps(observe(args.executions, args.at), indent=2, allow_nan=False))
