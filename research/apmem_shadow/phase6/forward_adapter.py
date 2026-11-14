"""New, separately qualified current-as-of EOD research adapter.

This is NOT an override of phase2's three-instrument/no-split admission. It
accepts only the already registered phase6 roster and bounded capture window.
Original raw observations and action factors remain in the immutable owner.
The current share-unit transform is valid only as of this capture; it is not
proof of historical first publication or a raw-share settlement backtest.
"""
from __future__ import annotations
import hashlib,json,math
from urllib.parse import parse_qs,urlsplit
import numpy as np
import pandas as pd
from features import validate_index

ORDINARY_FACTORS=np.asarray([.01,.02,.05,.1,.2,.25,1/3,.5,1.,2.,3.,4.,5.,10.,20.,50.,100.])
START='2023-06-01';ORIGIN='2026-11-13'


def adapt_capture(raw,receipt,instrument,roster,origin=ORIGIN):
    if instrument not in roster:raise ValueError('Instrument outside declared roster')
    if origin!=ORIGIN:raise ValueError('One-shot origin is frozen')
    if hashlib.sha256(raw).hexdigest()!=receipt.get('raw_sha256'):raise ValueError('Raw observation digest mismatch')
    if receipt.get('vendor')!='tiingo' or receipt.get('source')!='eod-bars' or receipt.get('symbol')!=instrument:
        raise ValueError('Wrong source identity')
    request=urlsplit(receipt.get('request_path',''));params=parse_qs(request.query)
    if request.scheme or request.netloc or request.path!=f'/tiingo/daily/{instrument}/prices' or params!={'endDate':[origin],'startDate':[START]}:
        raise ValueError('Request does not match declared window')
    capture=pd.Timestamp(receipt['observed_at_utc'])
    if capture.tzinfo is None or capture<pd.Timestamp(origin,tz='UTC')+pd.Timedelta(hours=21):
        raise ValueError('Observation captured before completed regular session')
    payload=json.loads(raw)
    if not isinstance(payload,list) or len(payload)<3:raise ValueError('Missing EOD observations')
    d=pd.DataFrame(payload);required=['open','high','low','close','adjClose','divCash','splitFactor','volume']
    if not set(required+['date']).issubset(d):raise ValueError('Missing OHLC/action/basis fields')
    dates=pd.to_datetime(d.date,utc=True,errors='raise')
    if not dates.eq(dates.dt.normalize()).all():raise ValueError('EOD economic dates are not midnight labels')
    index=pd.DatetimeIndex(dates).tz_localize(None).as_unit('ns');validate_index(index)
    if index[0]<pd.Timestamp(START) or str(index[-1].date())!=origin:raise ValueError('Wrong or stale observation window')
    for key in required:
        if not d[key].map(lambda v:type(v) in (float,int)).all():raise ValueError('Unqualified numeric value: '+key)
    a=d[required].to_numpy(float)
    if not np.isfinite(a).all() or (a[:,:5]<=0).any() or (d.divCash<0).any() or (d.volume<0).any():raise ValueError('Invalid numerical observation')
    if (d.high<d[['open','low','close']].max(axis=1)).any() or (d.low>d[['open','high','close']].min(axis=1)).any() or (d.high<=d.low).any():
        raise ValueError('Malformed OHLC range')
    factors=d.splitFactor.to_numpy(float)
    if not np.isclose(factors[:,None],ORDINARY_FACTORS[None,:],atol=1e-8,rtol=1e-8).any(axis=1).all():
        raise ValueError('Unsupported corporate-action factor; no detailed endpoint fallback')
    # A split on t changes t's raw units already. Only later splits adjust t.
    following=np.r_[np.cumprod(factors[:0:-1])[::-1],1.]
    if not np.isfinite(following).all() or (following<=0).any():raise ValueError('Invalid cumulative share factor')
    out=pd.DataFrame(index=index)
    for key in ['open','high','low','close']:out[key]=d[key].to_numpy(float)/following
    out['dividends']=d.divCash.to_numpy(float)/following
    out['volume']=d.volume.to_numpy(float)*following
    out['source_split_factor']=factors;out['applied_future_share_factor']=following
    out['stock_splits']=0. # ZERO UNAPPLIED actions, after explicit qualified transform
    out['total_return_close']=d.adjClose.to_numpy(float)
    record={'instrument':instrument,'origin':origin,'source_receipt_id':receipt['receipt_id'],
       'raw_sha256':receipt['raw_sha256'],'source_observed_at':receipt['observed_at_utc'],
       'share_basis':'current_capture_constant_share_units','dividend_basis':'vendor_divCash_in_same_current_units',
       'historical_first_availability':None,'ordinary_action_count':int(np.sum(factors!=1)),
       'source_action_factors_retained':True,'adjusted_close_used_for_technical_predictors':False,
       'price_or_distribution_imputed':False,'rows':len(out)}
    return out,record


def compare_overlap(prices,incumbent,tolerance=.002):
    joint=pd.concat([prices.close.rename('new'),incumbent.rename('old')],axis=1,join='inner').dropna()
    if len(joint)<100:raise ValueError('Insufficient same-basis cross-provider overlap')
    errors=(joint.new/joint.old-1).abs()
    result={'overlap_rows':len(joint),'max_relative_discrepancy':float(errors.max()),
            'median_relative_discrepancy':float(errors.median()),'allowed_max':tolerance,
            'qualified':bool(errors.max()<=tolerance),'start':str(joint.index[0].date()),'end':str(joint.index[-1].date())}
    if not result['qualified']:raise ValueError('Material unexplained cross-provider overlap disagreement')
    return result
