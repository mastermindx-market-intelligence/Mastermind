"""Frozen event construction: admission inputs and future outcomes stay explicit."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .data import member_at, momentum_states
from .native import onset_mask
from .labels import evaluate_path, RULES
from .risk import features, add_event_features

FAMILIES=('t1','t2','union','breakout20','reclaim50','trend63_126')


def build_events(ticker: str, prices: pd.DataFrame, native: pd.DataFrame,
                 forecasts: pd.DataFrame, membership: pd.DataFrame,
                 benchmark: pd.DataFrame, start='2015-01-01', end='2026-06-02'):
    if not prices.index.equals(forecasts.index) or native.index.has_duplicates:
        raise ValueError('misaligned instrument inputs')
    if not {'t1_onset','t2_onset','union_onset','evaluated'}.issubset(native):
        raise ValueError('native observed-prefix replay required')
    if not membership.ticker.str.upper().eq(ticker).all():
        raise ValueError('foreign membership row')
    allowed=member_at(prices.index,membership)&prices.tradable.to_numpy(bool)
    states=momentum_states(prices)
    masks={name:native[name+'_onset'].reindex(prices.index,fill_value=False).to_numpy(bool)
           for name in ('t1','t2','union')}
    masks.update({name:onset_mask(states[name].to_numpy(bool)) for name in states})
    f=features(prices,forecasts,benchmark)
    out=[];paths=[];cache={};counts={};exclusions={}
    for family in FAMILIES:
        all_positions=np.flatnonzero(masks[family])
        relevant=[int(i) for i in all_positions if pd.Timestamp(start)<=prices.index[i]<=pd.Timestamp(end)]
        counts[family]={'observed_onsets':len(relevant),'admitted':0}
        for i in relevant:
            if not allowed[i]:
                exclusions['membership_or_liquidity']=exclusions.get('membership_or_liquidity',0)+1
                continue
            origin=prices.index[i];key=(i,'barrier21',0,'stop_first')
            if key not in cache:cache[key]=evaluate_path(prices,i)
            primary=cache[key]
            if primary['status']!='COMPLETE':
                exclusions['censored']=exclusions.get('censored',0)+1;continue
            native_row=native.loc[origin] if origin in native.index else pd.Series(dtype=object)
            if family in ('t1','t2','union') and not native_row.get('evaluated',False):
                raise ValueError('unknown native observation produced an event')
            eid=f'phase3:{family}:{ticker}:{origin.date()}'
            record={**primary,'event_id':eid,'ticker':ticker,'family':family,
                    'native_tier':native_row.get('native_tier'),
                    'native_event_date':native_row.get('event_date'),
                    'native_observed_date':native_row.get('observed_date'),
                    'native_confirmation_date':native_row.get('confirmation_date'),
                    'native_no_peer_waiver':True if family in ('t1','t2','union') else None,
                    'membership_source':','.join(sorted(set(membership.src.astype(str)))),
                    'raw_origin_close':float(prices.close.iloc[i]),
                    'dollar_volume20':float(prices.dollar_volume20.iloc[i])}
            out.append(record);counts[family]['admitted']+=1
            for rule in RULES:
                k=(i,rule,0,'stop_first')
                if k not in cache:cache[k]=evaluate_path(prices,i,rule=rule)
                paths.append({**cache[k],'event_id':eid,'ticker':ticker,'family':family})
            if family=='union':
                for delay,order in ((1,'stop_first'),(0,'target_first')):
                    k=(i,'barrier21',delay,order)
                    if k not in cache:cache[k]=evaluate_path(prices,i,delay=delay,order=order)
                    paths.append({**cache[k],'event_id':eid,'ticker':ticker,'family':family})
    events=pd.DataFrame(out)
    if not events.empty:
        events=add_event_features(events,f)
        if not events.event_id.is_unique:raise AssertionError('duplicate event identity')
    return events,pd.DataFrame(paths),{'instrument':ticker,'counts':counts,'exclusions':exclusions,
                                     'outcomes_are_not_decision_features':True,
                                     'current_vintage_reconstruction':True}
