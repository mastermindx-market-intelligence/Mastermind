"""Source-bound native confluence replay; no replacement oscillator or live policy.

The caller supplies the separately verified Macro source on PYTHONPATH. Only the
chart-history construction inside analyze is projected away. The native gate's
code, cascade, dates, filters and default parameters are unchanged. This module
must pass decision-parity tests before empirical use. No historical peer waiver
is invented. Full chart-payload parity is explicitly NOT claimed.
"""
from __future__ import annotations

import hashlib
import importlib
import types
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd

MACRO_PIN = "6bbc4b0fc694c847077661ff5bf4c19ea41e4e81"
FIELDS = (
    'eligible', 'tier', 'sub', 'reason', 'reasons', 'state', 'above200',
    'weekly_bull', 'early_now', 'asof', 'last', 'tier_cascade', 'weight',
    'tier_sub', 'bars_to_cross', 'fresh_bars', 'fresh_bars_knowable', 'ticks',
    'tier_event_date', 'tier_observed_date', 'tier_observation_provisional',
    'provisional', 'htf_s1', 'htf_s2', 'young_history', 'history_bars',
    'null_legs', 'veto_legs_null', 'stoch_ob', 'stoch_bear', 'macd_bear',
    'hist_d2', 'hist_d3', 'anchor_era', 'sq_anchor_era', 'near_miss_reason',
)


def verify_source(root: Path, manifest: Mapping) -> dict:
    """Verify exact source bytes before imports; reject ambiguous roots/manifests."""
    root = Path(root).resolve()
    if manifest.get('macro_pin') != MACRO_PIN:
        raise ValueError('wrong native source revision')
    required = {
        'engine/confluence_tiers.py', 'engine/signal_gate.py',
        'engine/signal_quality.py', 'engine/session_anchor.py',
        'engine/technicals.py', 'engine/hysteresis.py',
        'lib/nyse_calendar.py', 'lib/config.py',
    }
    files = manifest.get('files', {})
    if not required.issubset(files):
        raise ValueError('incomplete source manifest')
    if (root / '.env').exists():
        raise ValueError('research snapshot must not contain credentials')
    hashes = {}
    for rel in sorted(required):
        path = root / rel
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError('unexpected source resolution')
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != files[rel]['sha256']:
            raise ValueError('native source digest mismatch: ' + rel)
        hashes[rel] = digest
    return hashes


def last_marker_projection(ticker: str, daily_close: pd.Series,
                           daily_high=None, daily_low=None, *,
                           reclaim_veto: bool = True,
                           washout_waiver: bool = False) -> dict | None:
    """Compute the native last-marker decision without all historical chart lists."""
    if washout_waiver or daily_high is not None or daily_low is not None:
        raise ValueError('only close-driven no-peer-waiver research arm is supported')
    sq = importlib.import_module('engine.signal_quality')
    market = sq.session_anchor.market_for_ticker(ticker)
    sig = sq.signal_frame(daily_close, market=market)
    if sig.empty:
        return None
    sig = sig.dropna(subset=['macd', 'sig', 'k', 'd', 'rsi14'])
    if len(sig) < 5:
        return None
    idx, n = sig.index, len(sig)
    event = sig[['CB', 'revBuy', 'CS', 'revSell']].any(axis=1).to_numpy(bool)
    locations = np.flatnonzero(event)
    markers = []
    if len(locations):
        i = int(locations[-1])
        sessions = sq._bucket_last_session(daily_close, market=market)

        def session_string(label):
            value = sessions.get(label) if sessions is not None else None
            return None if value is None or pd.isna(value) else str(pd.Timestamp(value).date())

        marker = {'date': str(idx[i].date())}
        if bool(sig['CB'].iloc[i]) or bool(sig['revBuy'].iloc[i]):
            confirmed = session_string(idx[i + sq.CONFIRM_BARS]) if i + sq.CONFIRM_BARS < n else None
            high_points = sq._swing_highs(sig['high'])
            take, reason, reasons = sq._buy_filter_full(
                i, sig, sq._bear_div(i, sig['high'], sig['macd'], high_points), n,
                reclaim_veto=reclaim_veto, waiver=None)
            marker.update(type='rebuy' if bool(sig['revBuy'].iloc[i]) else 'buy',
                          quality='pending' if take is None else ('take' if take else 'block'),
                          reason=reason)
            if len(reasons) > 1:
                marker['reasons'] = reasons
            marker['signal_date'] = session_string(idx[i])
            marker['confirmed_date'] = confirmed
        else:
            marker['type'] = 'sell' if bool(sig['CS'].iloc[i]) else 'cut'
            marker['signal_date'] = session_string(idx[i])
        markers.append(marker)
    last = sig.iloc[-1]
    state = ('long-bias' if last['k'] >= last['d'] and last['macd'] >= last['sig']
             else 'short-bias' if last['k'] < last['d'] and last['macd'] < last['sig']
             else 'mixed')
    trail = float(last['ema_trail'])
    return {'ticker': ticker, 'asof': str(idx[-1].date()), 'tf': '3D',
            'anchor_era': sq.ANCHOR_ERA, 'state': state,
            'above200': bool(last['above200']), 'weekly_bull': bool(last['w_bull']),
            'trail_stop': round(trail, 4) if pd.notna(trail) else None,
            'trail_breach': bool(pd.notna(trail) and last['close'] < trail),
            'markers': markers, 'early_now': bool(last['early'])}


def make_gate() -> Callable:
    """Clone only the globals binding, never mutate a shared native module."""
    module = importlib.import_module('engine.signal_gate')
    original = module.gate
    namespace = dict(original.__globals__)
    namespace['analyze'] = last_marker_projection
    projected = types.FunctionType(original.__code__, namespace, original.__name__,
                                   original.__defaults__, original.__closure__)
    projected.__kwdefaults__ = dict(original.__kwdefaults__ or {})
    return projected


def decision_view(result: Mapping) -> dict:
    """All declared gate decisions and relevant telemetry, not omitted chart history."""
    return {name: result.get(name) for name in FIELDS}


def equal_values(left, right) -> bool:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(equal_values(left[k], right[k]) for k in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(equal_values(x, y) for x, y in zip(left, right))
    if isinstance(left, (float, np.floating)) and isinstance(right, (float, np.floating)):
        return bool((np.isnan(left) and np.isnan(right)) or left == right)
    return bool(left == right)


def onset_mask(active: np.ndarray, absence: int = 3) -> np.ndarray:
    """New event only after the registered number of consecutive absent observations."""
    a = np.asarray(active)
    if a.ndim != 1 or a.dtype != bool or type(absence) is not int or absence < 1:
        raise ValueError('invalid onset arguments')
    out = np.zeros(len(a), bool)
    gap = absence
    for i, value in enumerate(a):
        if value:
            out[i] = gap >= absence
            gap = 0
        else:
            gap += 1
    return out


def replay(ticker: str, close: pd.Series, *, start: str = '2015-01-01',
           end: str = '2026-06-02', accelerated: bool = True) -> pd.DataFrame:
    """Native observed-prefix decisions; not full-series raw-tier backcasts."""
    if (not isinstance(close.index, pd.DatetimeIndex) or close.index.has_duplicates
            or not close.index.is_monotonic_increasing or close.isna().any()
            or not np.isfinite(close.to_numpy(float)).all() or (close <= 0).any()):
        raise ValueError('invalid signal close history')
    native = importlib.import_module('engine.signal_gate')
    gate = make_gate() if accelerated else native.gate
    rows = []
    for i, origin in enumerate(close.index):
        if i < 269 or origin < pd.Timestamp(start) or origin > pd.Timestamp(end):
            continue
        result = gate(ticker, close.iloc[:i+1], washout_waiver=False)
        if result.get('reason') == native.ENGINE_ERROR or result.get('result') is None:
            evaluated = False
        else:
            evaluated = True
        tier = result.get('tier_cascade')
        t1 = (evaluated and result.get('eligible') is True and tier == 'T1'
              and result.get('tier') == native.TAKE
              and result.get('tier_observation_provisional') is not True)
        t2 = evaluated and result.get('eligible') is True and tier == 'T2'
        rows.append({'date': origin, 'ticker': ticker, 'evaluated': evaluated,
                     'native_tier': tier, 't1': bool(t1), 't2': bool(t2),
                     'forming_t1': tier == 'T1' and not t1,
                     'event_date': result.get('tier_event_date'),
                     'observed_date': result.get('tier_observed_date'),
                     'tier_provisional': result.get('tier_observation_provisional'),
                     'reason': result.get('reason'), 'anchor_era': result.get('anchor_era'),
                     'sq_anchor_era': result.get('sq_anchor_era')})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.set_index('date')
    for name in ('t1', 't2'):
        frame[name+'_onset'] = onset_mask(frame[name].to_numpy(bool))
    frame['union_onset'] = onset_mask((frame.t1 | frame.t2).to_numpy(bool))
    return frame
