"""Paired calendar-block diagnostics, not independent-trade significance claims."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .arms import PRIMARY_TEST_FAMILY_SIZE,CLASSIFIER_CONTRASTS,PORTFOLIO_CONTRASTS


def block_indices(n: int, draws=2000, block=63, seed=20261114):
    if type(n) is not int or n<2 or type(draws) is not int or draws<100 or block<1:
        raise ValueError('invalid block resampling settings')
    b=min(block,n)
    starts=np.random.default_rng(seed).integers(0,n-b+1,size=(draws,int(np.ceil(n/b))))
    return (starts[:,:,None]+np.arange(b)[None,None,:]).reshape(draws,-1)[:,:n]


def interval(point,draws):
    a=np.asarray(draws,float);a=a[np.isfinite(a)]
    if not np.isfinite(point) or len(a)<100:
        return {'computed':False,'reason':'insufficient finite paired draws'}
    centered=a-point
    return {'computed':True,'difference':float(point),
            'pointwise_95_interval':np.quantile(a,[.025,.975]).tolist(),
            'centered_block_two_sided_p':float((1+np.sum(np.abs(centered)>=abs(point)))/(len(a)+1)),
            'draws':len(a),'inference':'approximate paired moving-calendar-block diagnostic',
            'simultaneous_confidence_interval':False}


def paired_events(a: pd.DataFrame,b: pd.DataFrame,value: str,calendar: pd.DatetimeIndex):
    if not a.event_id.is_unique or not b.event_id.is_unique:
        raise ValueError('duplicate event in paired comparison')
    x=a[['event_id','origin',value]].merge(b[['event_id','origin',value]],on='event_id',suffixes=('_a','_b'),validate='one_to_one')
    if not x.origin_a.eq(x.origin_b).all():raise ValueError('paired event dates differ')
    x=x[np.isfinite(x[value+'_a'])&np.isfinite(x[value+'_b'])].copy()
    if len(x)<30:return {'computed':False,'reason':'fewer than thirty paired events','n':len(x)}
    x['difference']=x[value+'_a']-x[value+'_b']
    group=x.groupby(pd.to_datetime(x.origin_a)).difference.agg(['sum','count']).reindex(calendar,fill_value=0)
    if group['count'].sum()!=len(x):raise ValueError('event outside comparison calendar')
    if len(group)<126:return {'computed':False,'reason':'fewer than two declared blocks','n':len(x)}
    indices=block_indices(len(group))
    sums=group['sum'].to_numpy(float)[indices].sum(axis=1)
    counts=group['count'].to_numpy(float)[indices].sum(axis=1)
    bootstrap=np.divide(sums,counts,out=np.full_like(sums,np.nan),where=counts>0)
    return {**interval(float(x.difference.mean()),bootstrap),'n':len(x),
            'distinct_event_dates':int((group['count']>0).sum()),'calendar_sessions':len(group),
            'same_date_cross_name_dependence_preserved':True,'block_sessions':63}


def es5(rows):
    a=np.asarray(rows,float)
    k=max(1,int(np.ceil(a.shape[-1]*.05)))
    return np.partition(a,k-1,axis=-1)[...,:k].mean(axis=-1)


def paired_returns(a: np.ndarray,b: np.ndarray):
    a,b=np.asarray(a,float),np.asarray(b,float)
    if a.shape!=b.shape or a.ndim!=1 or not np.isfinite(a).all() or not np.isfinite(b).all() or len(a)<126:
        raise ValueError('invalid paired account returns')
    indices=block_indices(len(a));aa=a[indices];bb=b[indices]
    return {'mean_daily_return':{**interval(float(np.mean(a-b)),np.mean(aa-bb,axis=1)),'calendar_sessions':len(a)},
            'worst5_daily_mean':{**interval(float(es5(a)-es5(b)),es5(aa)-es5(bb)),'calendar_sessions':len(a)}}


def holm(records: list[dict],family_size=PRIMARY_TEST_FAMILY_SIZE):
    if len(records)!=family_size:raise ValueError('the full registered family must remain present')
    p=np.array([r.get('centered_block_two_sided_p',1.) if r.get('computed') else 1. for r in records],float)
    if not np.isfinite(p).all() or ((p<0)|(p>1)).any():raise ValueError('invalid p-value')
    order=np.argsort(p,kind='stable');adjusted=np.empty(len(p));previous=0.
    for k,i in enumerate(order):
        previous=max(previous,min(1.,(family_size-k)*p[i]));adjusted[i]=previous
    return [{**r,'holm_family_size':family_size,'holm_adjusted_p':float(adjusted[i]),
             'holm_below_05':bool(r.get('computed') and adjusted[i]<.05)} for i,r in enumerate(records)]


def primary_family(forecast_losses,predictions,returns,calendar):
    records=[]
    for h in (1,5,20):
        for target in ('variance','return_square'):
            sub=forecast_losses[(forecast_losses.horizon==h)&(forecast_losses.target==target)]
            sub=sub[pd.to_datetime(sub.origin).isin(calendar)]
            result=paired_events(sub[sub.model=='mem'],sub[sub.model=='ewma'],'qlike',calendar)
            records.append({'family':'forecast','contrast':'mem-ewma','metric':'qlike',
                            'horizon':h,'target':target,**result})
    for a,b in CLASSIFIER_CONTRASTS:
        for metric in ('log_loss','brier'):
            if predictions.empty:
                result={'computed':False,'reason':'conditional models unavailable'}
            else:
                result=paired_events(predictions[predictions.model==a],predictions[predictions.model==b],metric,calendar)
            records.append({'family':'conditional_risk','contrast':a+'-'+b,'metric':metric,**result})
    for a,b in PORTFOLIO_CONTRASTS:
        if a in returns and b in returns:
            result=paired_returns(returns[a],returns[b])
        else:
            result={m:{'computed':False,'reason':'account comparison unavailable'} for m in ('mean_daily_return','worst5_daily_mean')}
        for metric,row in result.items():
            records.append({'family':'portfolio','contrast':a+'-'+b,'metric':metric,**row})
    return holm(records)
