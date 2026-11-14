"""Exact probability-loss decomposition and count-matched exploratory controls."""
from __future__ import annotations
import numpy as np
import pandas as pd


def likelihood_decomposition(predictions: pd.DataFrame):
    required={'event_id','model','class_id','p_stop','p_target','p_timeout','log_loss'}
    if not required.issubset(predictions) or predictions.duplicated(['event_id','model']).any():
        raise ValueError('invalid prediction identities')
    p=predictions[['p_stop','p_target','p_timeout']].to_numpy(float)
    y=predictions.class_id.to_numpy(int)
    if (not np.isfinite(p).all() or (p<=0).any() or (p>=1).any()
            or not np.allclose(p.sum(axis=1),1,atol=1e-10) or not np.isin(y,[0,1,2]).all()):
        raise ValueError('invalid outcome probabilities')
    active=y!=2;a=p[:,0]+p[:,1];q=p[:,1]/a;direction=(y==1)
    activity_loss=-np.where(active,np.log(a),np.log1p(-a))
    directional_loss=-np.where(direction,np.log(q),np.log1p(-q))
    weighted=np.where(active,directional_loss,0.)
    total=activity_loss+weighted
    if not np.allclose(total,predictions.log_loss.to_numpy(float),rtol=1e-10,atol=1e-12):
        raise ValueError('stored log loss does not reconcile with exact decomposition')
    out=predictions[['event_id','model']].copy()
    out['active_observed']=active;out['activity_probability']=a;out['conditional_target_probability']=q
    out['activity_log_loss']=activity_loss;out['direction_log_loss_on_active']=np.where(active,directional_loss,np.nan)
    out['direction_contribution_all_events']=weighted
    out['activity_brier']=(a-active)**2
    out['direction_brier_on_active']=np.where(active,(q-direction)**2,np.nan)
    out['total_log_loss_reconciled']=total
    summary=out.groupby('model').agg(n=('event_id','size'),active_n=('active_observed','sum'),
        activity_log_loss=('activity_log_loss','mean'),conditional_direction_log_loss=('direction_log_loss_on_active','mean'),
        direction_contribution_all_events=('direction_contribution_all_events','mean'),
        activity_brier=('activity_brier','mean'),conditional_direction_brier=('direction_brier_on_active','mean'),
        total_log_loss=('total_log_loss_reconciled','mean')).reset_index()
    return out,summary


def exact_date_retention(parent: pd.DataFrame,kept_ids: set[str],seed: int):
    if not {'event_id','origin'}.issubset(parent) or not parent.event_id.is_unique:
        raise ValueError('invalid parent opportunity set')
    if not kept_ids.issubset(set(parent.event_id)):raise ValueError('retained event not in parent set')
    rng=np.random.default_rng(seed);selected=[];exchangeable_events=exchangeable_dates=0
    for _,group in parent.sort_values(['origin','event_id']).groupby('origin',sort=True):
        n=len(group);k=int(group.event_id.isin(kept_ids).sum())
        if 0<k<n:
            exchangeable_events+=n;exchangeable_dates+=1
        if k: selected.extend(rng.choice(group.event_id.to_numpy(),size=k,replace=False).tolist())
    result=parent[parent.event_id.isin(selected)].copy()
    original=parent[parent.event_id.isin(kept_ids)].groupby('origin').size()
    actual=result.groupby('origin').size()
    if not original.equals(actual):raise AssertionError('exact-date retention counts changed')
    return result,{'seed':seed,'parent_events':len(parent),'retained_events':len(result),
                   'exchangeable_events':exchangeable_events,'exchangeable_dates':exchangeable_dates,
                   'exchangeable_fraction':exchangeable_events/max(1,len(parent)),
                   'exact_date_counts_preserved':True}
