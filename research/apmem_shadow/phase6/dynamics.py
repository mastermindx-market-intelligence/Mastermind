"""Case-guided recovery dynamics; no hindsight troughs or first/second labels."""
from __future__ import annotations
import numpy as np
import pandas as pd
from features import validate_index


def relative_dynamics(total,peer_daily):
    if not total.index.equals(peer_daily.index):raise ValueError('Relative context clock mismatch')
    validate_index(total.index)
    own=np.log(total/total.shift(1));peer=np.log1p(peer_daily)
    relative=own-peer
    five=relative.rolling(5,min_periods=5).sum()
    prior=relative.shift(5).rolling(16,min_periods=16).sum()
    return pd.DataFrame({'relative_log5':five,'relative_acceleration':five/5-prior/16,
                         'relative_short_positive':five>0,'relative_accelerating':(five/5-prior/16)>0},index=total.index)


def cross_cycle(price,signal,slow_hist,episode_number):
    """Compare only with the latest actually failed prior same-family attempt.

    All past attempt records keep their original reference and oscillator value.
    A current observation cannot rewrite past events or know a future failure.
    """
    for x in (signal,slow_hist,episode_number):
        if not x.index.equals(price.index):raise ValueError('Cross-cycle calendar mismatch')
    validate_index(price.index)
    low=price.rolling(21,min_periods=21).min();attempts=[];rows=[];previous_episode=None
    for i,at in enumerate(price.index):
        current_episode=episode_number.iloc[i]
        p=price.iloc[i];hist=slow_hist.iloc[i]
        if pd.isna(current_episode) or current_episode==0 or current_episode!=previous_episode:attempts=[]
        previous_episode=current_episode
        if pd.notna(p):
            for a in attempts:
                if not a['failed'] and p<a['low']:a['failed']=True;a['failed_at']=at
        failed=[a for a in attempts if a['failed']]
        prior=failed[-1] if failed else None
        valid=prior is not None and pd.notna(p) and pd.notna(hist) and np.isfinite(prior['hist'])
        row={'prior_failed_at':None,'prior_attempt_at':None,'prior_attempt_price':np.nan,'prior_attempt_slow_hist':np.nan,
             'cross_cycle_price_change':np.nan,'cross_cycle_slow_improvement':np.nan,'cross_cycle_divergence':False,
             'cross_cycle_known':bool(valid)}
        if prior is not None:
            row.update(prior_failed_at=prior['failed_at'],prior_attempt_at=prior['at'],
                       prior_attempt_price=prior['price'],prior_attempt_slow_hist=prior['hist'])
        if valid:
            row.update(cross_cycle_price_change=p/prior['price']-1,cross_cycle_slow_improvement=hist-prior['hist'],
                       cross_cycle_divergence=bool(p<prior['price'] and hist>prior['hist']))
        rows.append(row)
        if bool(signal.iloc[i]) and pd.notna(p) and pd.notna(low.iloc[i]) and pd.notna(current_episode) and current_episode!=0:
            attempts.append({'at':at,'price':float(p),'hist':float(hist) if pd.notna(hist) else np.nan,
                             'low':float(low.iloc[i]),'failed':False,'failed_at':None})
    return pd.DataFrame(rows,index=price.index)


def support_exit(features,policy):
    """Price stops and overbought levels are not substituted for deterioration."""
    fast=features.fast_hist
    if policy=='fast_cross':
        # fire only when the known completed histogram changes sign
        return ((fast<0)&(fast.shift(1)>=0)&fast.notna()).fillna(False)
    if policy=='nested_support':
        slow=features.w2_hist_delta<0
        peer=(features.peer_return_5<0)&(features.peer_breadth_change<0)&features.peer_valid.fillna(False)
        return ((fast<0)&(slow|peer)&fast.notna()).fillna(False)
    if policy=='none':return pd.Series(False,index=features.index)
    raise ValueError('Unknown exit policy')
