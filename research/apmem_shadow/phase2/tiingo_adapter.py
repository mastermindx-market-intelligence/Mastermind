"""Pure adapter for actual receipts from the existing approved Tiingo EOD owner.

No provider access, credentials, collection service, or market-action authority.
Raw OHLC and divCash are retained; adjusted fields are not used as predictors.
"""
from __future__ import annotations
import hashlib
import json
from urllib.parse import urlsplit, parse_qs
import numpy as np
import pandas as pd
from .targets import validate_prices


def adapt_eod_capture(raw: bytes, receipt: dict, instrument: str, origin: str):
    if instrument not in ('QQQ', 'SPY', 'IWM'):
        raise ValueError('instrument outside frozen forward roster')
    if hashlib.sha256(raw).hexdigest() != receipt.get('raw_sha256'):
        raise ValueError('raw capture digest mismatch')
    if receipt.get('instrument') != instrument or receipt.get('historical_first_availability') is not None:
        raise ValueError('invalid source identity or historical timing claim')
    url = urlsplit(receipt.get('request_path', ''))
    params = parse_qs(url.query)
    if (url.scheme or url.netloc or url.path != f'/tiingo/daily/{instrument}/prices'
            or params.get('endDate') != [origin] or params.get('startDate') != ['2010-01-01']
            or set(params) != {'startDate', 'endDate'}):
        raise ValueError('capture request does not match frozen source window')
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) < 3 or receipt.get('rows') != len(rows):
        raise ValueError('invalid source row count')
    frame = pd.DataFrame(rows)
    columns = ['open', 'high', 'low', 'close', 'divCash', 'splitFactor', 'volume']
    if not set(columns + ['date']).issubset(frame):
        raise ValueError('missing vendor OHLC/action fields')
    dates = pd.to_datetime(frame.date, utc=True, errors='raise')
    if not dates.eq(dates.dt.normalize()).all():
        raise ValueError('EOD date is not a UTC economic-date label')
    index = pd.DatetimeIndex(dates).tz_localize(None)
    if (index.hasnans or not index.is_unique or not index.is_monotonic_increasing
            or str(index[-1].date()) != origin or str(index[0].date()) < '2010-01-01'):
        raise ValueError('source dates are duplicated, unordered or wrong-origin')
    for column in columns:
        if not frame[column].map(lambda x: type(x) in (float, int)).all():
            raise ValueError('source numeric field has nonnumeric/boolean values')
    a = frame[columns].to_numpy(float)
    if not np.isfinite(a).all() or (a[:, :4] <= 0).any() or (a[:, 4] < 0).any():
        raise ValueError('nonfinite or invalid source price/distribution')
    if not np.equal(a[:, 5], 1).all():
        raise ValueError('unqualified split event in forward source')
    if (a[:, 6] < 0).any() or not np.equal(a[:, 6], np.floor(a[:, 6])).all():
        raise ValueError('invalid volume')
    result = frame[['open', 'high', 'low', 'close', 'volume']].copy()
    result.index = index
    result['dividends'] = frame.divCash.to_numpy(float)
    # splitFactor=1 is the vendor's no-split encoding; zero is our no-event encoding.
    result['stock_splits'] = 0.0
    validate_prices(result)
    return result, {
        'adapter': 'tiingo_eod_raw_cash_distribution.v1', 'instrument': instrument,
        'origin': origin, 'source_raw_sha256': receipt['raw_sha256'],
        'source_request_path': receipt['request_path'], 'captured_at': receipt['captured_at'],
        'price_basis': 'vendor_raw_ohlc_no_adj_fields',
        'cash_distribution_basis': 'vendor_divCash_no_separate_supplemental_distribution',
        'split_mapping': 'all_vendor_splitFactor_1_to_no_unapplied_event',
        'historical_first_availability': None, 'price_or_distribution_imputation': False,
        'raw_rows_retained_separately': True,
    }
