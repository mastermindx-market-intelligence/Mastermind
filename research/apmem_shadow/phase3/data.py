"""Pure price/action adapters for the frozen entry-risk experiments.

Raw source records and their receipt stay separate. No provider calls, credentials,
price interpolation, adjusted-price predictors or historical-publication claims.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pandas as pd

FLOOR = 1e-12
SYMBOL = re.compile(r'^[A-Z][A-Z0-9.-]{0,15}$')


def parse_capture(raw: bytes, receipt: Mapping, ticker: str,
                  cutoff: str = '2026-11-12') -> tuple[pd.DataFrame, dict]:
    if not SYMBOL.fullmatch(ticker) or receipt.get('instrument') != ticker:
        raise ValueError('instrument identity mismatch')
    digest = hashlib.sha256(raw).hexdigest()
    if digest != receipt.get('raw_sha256') or receipt.get('historical_first_availability') is not None:
        raise ValueError('source digest or historical-clock claim invalid')
    request = urlsplit(receipt.get('request_path', ''))
    query = parse_qs(request.query)
    if (request.scheme or request.netloc or request.path != f'/tiingo/daily/{ticker}/prices'
            or set(query) != {'startDate', 'endDate'} or query['startDate'] != ['2010-01-01']
            or len(query['endDate']) != 1 or pd.Timestamp(query['endDate'][0]) < pd.Timestamp(cutoff)):
        raise ValueError('source request does not cover declared experiment')
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) != receipt.get('rows') or not rows:
        raise ValueError('invalid source row count')
    frame = pd.DataFrame(rows)
    cols = ['open', 'high', 'low', 'close', 'volume', 'divCash', 'splitFactor']
    if not set(cols + ['date']).issubset(frame):
        raise ValueError('missing raw price or corporate-action field')
    dates = pd.to_datetime(frame.date, utc=True, errors='raise')
    if not dates.eq(dates.dt.normalize()).all():
        raise ValueError('non-EOD economic date')
    index = pd.DatetimeIndex(dates).tz_localize(None)
    if not index.is_unique or not index.is_monotonic_increasing or index.hasnans:
        raise ValueError('duplicate, missing or unordered source dates')
    if index[0] < pd.Timestamp('2010-01-01') or index[-1] > pd.Timestamp(query['endDate'][0]):
        raise ValueError('source dates outside request')
    for col in cols:
        if not frame[col].map(lambda x: type(x) in (float, int)).all():
            raise ValueError('nonnumeric or boolean source value: ' + col)
    a = frame[cols].to_numpy(float)
    if not np.isfinite(a).all() or (a[:, :4] <= 0).any() or (a[:, 4:6] < 0).any() or (a[:, 6] <= 0).any():
        raise ValueError('nonfinite, negative or zero raw inputs')
    if (a[:, 1] < np.maximum(a[:, 0], a[:, 3]) - 1e-7).any() or (a[:, 2] > np.minimum(a[:, 0], a[:, 3]) + 1e-7).any():
        raise ValueError('inconsistent OHLC')
    out = pd.DataFrame(a, columns=cols, index=index).rename(columns={'divCash': 'dividend', 'splitFactor': 'split'})
    out = out.loc[:cutoff].copy()
    if len(out) < 3:
        raise ValueError('insufficient observations')
    audit = {'instrument': ticker, 'raw_sha256': digest, 'captured_at': receipt.get('captured_at'),
             'source_request_path': receipt['request_path'], 'input_rows': len(frame),
             'retained_rows': len(out), 'data_end': str(out.index[-1].date()),
             'split_events': int((out.split != 1).sum()), 'dividend_events': int((out.dividend != 0).sum()),
             'historical_first_availability': None, 'price_imputation': False,
             'adjusted_fields_used_as_predictors': False, 'unsupported_action_dates': []}
    # Adjustment factors are a diagnostic only: a large discontinuity unexplained
    # by the vendor's cash/split records may be a spin-off or missing entitlement.
    # Such a panel is quarantined, not converted into a fictitious investment loss.
    if 'adjClose' in frame:
        adjusted = pd.Series(pd.to_numeric(frame.adjClose, errors='coerce').to_numpy(float), index=index).loc[out.index]
        factor = adjusted / out.close
        prev = out.close.shift(1)
        expected = out.split / (1 - out.dividend * out.split / prev)
        discrepancy = np.log((factor / factor.shift(1)) / expected)
        bad = discrepancy.abs() > .005
        audit['adjustment_factor_log_error_max'] = float(discrepancy.abs().max()) if discrepancy.notna().any() else None
        audit['unsupported_action_dates'] = [str(d.date()) for d in out.index[bad.fillna(False)]]
    audit['action_basis_qualified'] = not audit['unsupported_action_dates']
    return out, audit


def prepare_prices(raw: pd.DataFrame) -> pd.DataFrame:
    """Causal total-return signal index and common variance target from raw actions."""
    names = ['open', 'high', 'low', 'close', 'volume', 'dividend', 'split']
    if (not set(names).issubset(raw) or not isinstance(raw.index, pd.DatetimeIndex)
            or not raw.index.is_unique or not raw.index.is_monotonic_increasing):
        raise ValueError('invalid raw panel schema/index')
    p = raw[names].astype(float).copy()
    a = p.to_numpy()
    if (not np.isfinite(a).all() or (a[:, :4] <= 0).any() or (a[:, 4:6] < 0).any()
            or (a[:, 6] <= 0).any()):
        raise ValueError('invalid price/action numbers')
    if (p.high < p[['open','low','close']].max(axis=1)).any() or (p.low > p[['open','high','close']].min(axis=1)).any():
        raise ValueError('inconsistent OHLC')
    previous = p.close.shift(1)
    gross = p.split * (p.close + p.dividend) / previous
    gross.iloc[0] = 1.0
    if (gross <= 0).any() or not np.isfinite(gross).all():
        raise ValueError('invalid investment gross return')
    p['total_return'] = gross - 1
    p['return_log'] = np.log(gross)
    p['signal_close'] = p.close.iloc[0] * gross.cumprod()
    overnight = np.log(p.split * (p.open + p.dividend) / previous)
    overnight.iloc[0] = 0.0
    p['overnight_variance'] = overnight.pow(2)
    p['range_variance'] = np.log(p.high / p.low).pow(2) / (4*np.log(2))
    p['variance'] = (p.overnight_variance + p.range_variance).clip(lower=FLOOR)
    p['variance21'] = p.variance.rolling(21, min_periods=21).mean()
    p['overnight_share21'] = p.overnight_variance.rolling(21).mean() / p.variance21
    c = p.signal_close
    p['momentum63'] = c.pct_change(63, fill_method=None)
    p['momentum126'] = c.pct_change(126, fill_method=None)
    p['momentum126_skip21'] = c.shift(21) / c.shift(126) - 1
    p['distance_high63'] = c / c.rolling(63).max() - 1
    p['dollar_volume20'] = (p.close * p.volume).rolling(20, min_periods=20).mean()
    p['tradable'] = (p.close >= 5) & (p.dollar_volume20 >= 5e6)
    return p


def member_at(index: pd.DatetimeIndex, rows: pd.DataFrame,
              snapshot_end: str = '2026-06-02') -> np.ndarray:
    """Effective-add inclusive, effective-delete exclusive; no post-snapshot extension."""
    if not {'start_date', 'end_date'}.issubset(rows):
        raise ValueError('missing membership intervals')
    valid = np.zeros(len(index), bool)
    for row in rows.itertuples():
        start = pd.Timestamp(row.start_date)
        if pd.isna(start):
            raise ValueError('missing effective membership start')
        end = pd.Timestamp(row.end_date)
        if not pd.isna(end) and end < start:
            raise ValueError('inverted membership interval')
        valid |= (index >= start) & ((index < end) if not pd.isna(end) else True)
    return valid & (index <= pd.Timestamp(snapshot_end))


def momentum_states(p: pd.DataFrame) -> pd.DataFrame:
    c = p.signal_close
    average = c.rolling(50, min_periods=50).mean()
    return pd.DataFrame({
        'breakout20': c > c.shift(1).rolling(20, min_periods=20).max(),
        'reclaim50': (c > average) & (c.shift(1) <= average.shift(1)) & (p.momentum126 > 0),
        'trend63_126': (p.momentum63 > 0) & (p.momentum126 > 0),
    }, index=p.index).fillna(False)


def future_mean(values, horizon: int) -> np.ndarray:
    if type(horizon) is not int or horizon < 1:
        raise ValueError('invalid target horizon')
    s = pd.Series(np.asarray(values, float))
    return s.shift(-1).rolling(horizon).mean().shift(-(horizon-1)).to_numpy()
