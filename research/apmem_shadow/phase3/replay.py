"""Efficient observed-prefix replay without substituting historical tier_stream.

All excluded prefixes fail the native cascade's necessary not-topped condition.
The sieve uses the native primitives and is disabled when its hysteresis option
is active. Full native decisions are evaluated for every potentially eligible
prefix. The source of each exclusion is reported, never called a native payload.
"""
from __future__ import annotations

import importlib
import numpy as np
import pandas as pd
from .native import make_gate


def primary_possible(close: pd.Series) -> bool:
    ct = importlib.import_module('engine.confluence_tiers')
    if ct._veto_confirm() != 1 or len(close) < 270:
        return True
    three, _ = ct._tf_bars(close, 3, 'US')
    if three.empty:
        return True
    k, d = ct._stoch_rsi_kd(three)
    m, s = ct._rsi_macd(three)
    kn, dn, mn, sn = map(float, (k.iloc[-1], d.iloc[-1], m.iloc[-1], s.iloc[-1]))
    # Preserve the native NaN comparison semantics, rather than introducing a
    # stricter warmup rule. All T1/T2 paths require this condition when confirm=1.
    return not (kn >= ct.OB or dn >= ct.OB or kn < dn or mn < sn)


def observed_onsets(active, known, absence=3):
    active, known = np.asarray(active, bool), np.asarray(known, bool)
    if active.ndim != 1 or active.shape != known.shape or absence < 1:
        raise ValueError('invalid observed onset input')
    out = np.zeros(len(active), bool)
    gap = absence
    for i, (a, k) in enumerate(zip(active, known)):
        if not k:
            gap = 0
        elif a:
            out[i] = gap >= absence
            gap = 0
        else:
            gap += 1
    return out


def replay(ticker: str, close: pd.Series, *, start='2015-01-01',
           end='2026-06-02', sieve=True):
    if (not isinstance(close.index, pd.DatetimeIndex) or not close.index.is_unique
            or not close.index.is_monotonic_increasing or close.isna().any()
            or not np.isfinite(close.to_numpy(float)).all() or (close <= 0).any()):
        raise ValueError('invalid signal history')
    native = importlib.import_module('engine.signal_gate')
    gate = make_gate()
    rows = []
    begin = max(269, int(close.index.searchsorted(pd.Timestamp(start))) - 3)
    finish = int(close.index.searchsorted(pd.Timestamp(end), side='right'))
    for i in range(begin, finish):
        origin = close.index[i]
        prefix = close.iloc[:i+1]
        possible = primary_possible(prefix) if sieve else True
        if not possible:
            rows.append({'date': origin, 'ticker': ticker, 'evaluated': True,
                         'native_decision_computed': False, 't1': False, 't2': False,
                         'forming_t1': False, 'native_tier': None,
                         'reason': 'native_not_topped_necessary_condition'})
            continue
        value = gate(ticker, prefix, washout_waiver=False)
        known = value.get('reason') != native.ENGINE_ERROR and value.get('result') is not None
        tier = value.get('tier_cascade')
        t1 = bool(known and value.get('eligible') and tier == 'T1'
                  and value.get('tier') == native.TAKE
                  and not value.get('tier_observation_provisional'))
        t2 = bool(known and value.get('eligible') and tier == 'T2')
        last = value.get('last') or {}
        rows.append({'date': origin, 'ticker': ticker, 'evaluated': bool(known),
                     'native_decision_computed': True, 'native_tier': tier,
                     't1': t1, 't2': t2, 'forming_t1': tier == 'T1' and not t1,
                     'event_date': value.get('tier_event_date'),
                     'observed_date': value.get('tier_observed_date'),
                     'confirmation_date': last.get('confirmed_date'),
                     'tier_provisional': value.get('tier_observation_provisional'),
                     'reason': value.get('reason'), 'anchor_era': value.get('anchor_era'),
                     'sq_anchor_era': value.get('sq_anchor_era')})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.set_index('date')
    for name in ('t1', 't2'):
        frame[name+'_onset'] = observed_onsets(frame[name], frame.evaluated)
    frame['union_onset'] = observed_onsets(frame.t1 | frame.t2, frame.evaluated)
    return frame.loc[start:end]
