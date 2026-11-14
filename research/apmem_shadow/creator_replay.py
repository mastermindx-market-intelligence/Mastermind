"""Audit published outputs against independent opens; this is NOT a generator."""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd
from .evaluation import validate_prices


def signed_replay(marks: np.ndarray, exposure: np.ndarray, dates: pd.DatetimeIndex,
                  *, cost: float = 0.0, short_borrow: float = 0.0) -> dict[str, Any]:
    p, w = np.asarray(marks, float), np.asarray(exposure, float)
    if (p.ndim != 1 or w.shape != (len(p)-1,) or len(p) < 3 or
            not np.isfinite(p).all() or np.any(p <= 0) or not np.isin(w, [-1.,0.,1.]).all()
            or not 0 <= cost < .5 or not 0 <= short_borrow < 1):
        raise ValueError('invalid signed replay inputs')
    turnover = np.abs(w-np.r_[0.,w[:-1]])
    step = (1-cost*turnover)*(1+w*(p[1:]/p[:-1]-1)-(w<0)*short_borrow/252)
    if np.any(step <= 0):
        raise ValueError('insolvent hypothetical exposure path')
    eq = np.r_[1.,np.cumprod(step)]
    eq[-1] *= 1-cost*abs(w[-1])
    years = (dates[-1]-dates[0]).days/365.25
    if years <= 0:
        raise ValueError('invalid time span')
    return {'total_return':float(eq[-1]-1), 'cagr':float(eq[-1]**(1/years)-1),
            'max_open_mark_drawdown':float((eq/np.maximum.accumulate(eq)-1).min()),
            'long_fraction':float(np.mean(w==1)), 'short_fraction':float(np.mean(w==-1)),
            'one_way_cost':cost, 'annual_short_borrow_assumption':short_borrow}


def replay_published(snapshot: dict[str, Any], prices: pd.DataFrame) -> dict[str, Any]:
    d = pd.DatetimeIndex(pd.to_datetime(snapshot['dates']))
    w = np.asarray(snapshot['regime'], float)
    published = np.asarray(snapshot['closes'], float)
    if (len(d)<4 or d.hasnans or not d.is_unique or not d.is_monotonic_increasing or
            w.shape!=(len(d),) or not np.isin(w,[-1.,1.]).all() or
            published.shape!=(len(d),) or not np.isfinite(published).all()):
        raise ValueError('malformed creator output snapshot')
    p = validate_prices(prices)
    missing = d.difference(p.index)
    if len(missing):
        raise ValueError('independent OHLC missing published session dates')
    p = p.loc[d]
    marks, dates = p.open.to_numpy()[1:], d[1:]
    out = []
    for delay in (1,2):
        target = w[:-2] if delay==1 else np.r_[0.,w[:-3]]
        for kind, exposure in (('published_long_short',target),
                               ('published_long_cash',np.maximum(target,0))):
            for cost, borrow in ((0.,0.),(.0005,.03)):
                out.append({'policy':kind,'delay_sessions':delay,
                    **signed_replay(marks,exposure,dates,cost=cost,short_borrow=borrow)})
    for cost in (0.,.0005):
        out.append({'policy':'buy_hold','delay_sessions':None,
            **signed_replay(marks,np.ones(len(marks)-1),dates,cost=cost)})
    flips = np.flatnonzero(np.diff(w)!=0)+1
    return {'schema':'mastermind.creator_output_open_replay.v1',
        'not_generator_reconstruction':True, 'historical_publication_time_verified':False,
        'start_open':str(dates[0].date()),'end_open':str(dates[-1].date()),
        'price_basis':'current_vintage_raw_OHLC_no_distributions',
        'published_close_max_abs_difference':float(np.max(np.abs(p.close.to_numpy()-published))),
        'published_close_median_abs_difference':float(np.median(np.abs(p.close.to_numpy()-published))),
        'regime_flips':[{'signal_session':str(d[i].date()),'new_regime':int(w[i]),
                         'next_open_session':str(d[i+1].date()) if i+1<len(d) else None} for i in flips],
        'results':out,
        'limitations':['Snapshot markers are not timestamped live signals.',
            'Constant +/-1 target exposure is reset each open; fixed-share shorts differ.',
            'Rebalance maintenance turnover, distributions, cash interest and tax omitted.',
            'Drawdown is open-mark only; intraday and closing troughs are not captured.']}
