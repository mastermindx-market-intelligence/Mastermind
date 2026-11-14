"""Retain all registered comparisons, dependence controls and adverse results."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from experiment import write_json, SECTORS

CONTRASTS=[('sequence_repair','same_day_sequence'),('sequence_repair','repair_no_dot'),
 ('sequence_repair','dot'),('phase_router','dot'),('phase_router','continuation'),
 ('dot_stress','dot'),('dot_repair','dot'),('dot_stress_repair','dot'),
 ('dot_vix_not_rising','dot_common'),('dot_vvix_not_rising','dot_common'),
 ('dot_both_not_rising','dot_vix_not_rising'),('dot_vol_easing','dot_common')]


def block_mean_interval(x, seed=20261114, length=63, draws=2000):
    x=np.asarray(x,float)
    if x.ndim!=1 or not len(x) or not np.isfinite(x).all():raise ValueError('Invalid paired observations')
    n=len(x);blocks=int(np.ceil(n/length));rng=np.random.default_rng(seed)
    starts=rng.integers(0,n,size=(draws,blocks));lengths=np.full(blocks,length);lengths[-1]=n-(blocks-1)*length
    # Circular calendar blocks preserve common-day cross-sector co-movement upstream.
    z=np.r_[x,np.tile(x,int(np.ceil(length/n))+1)]
    cum=np.r_[0.,np.cumsum(z)]
    samples=(cum[starts+lengths]-cum[starts]).sum(axis=1)/n
    mean=float(x.mean());centered=samples-mean
    p=float((1+np.count_nonzero(np.abs(centered)>=abs(mean)))/(draws+1))
    return mean,[float(q) for q in np.quantile(samples,[.025,.975])],p


def holm(values):
    p=np.asarray(values,float);order=np.argsort(p);out=np.empty(len(p));running=0.
    for rank,i in enumerate(order):
        running=max(running,min(1.,(len(p)-rank)*p[i]));out[i]=running
    return out


def main(root):
    out=root/'primary_results'
    receipt=json.loads((out/'RUN_RECEIPT.json').read_text())
    if receipt['status']!='COMPLETE':raise ValueError('Original experiment incomplete')
    rows=[]
    for segment in ('pre','post'):
        for h in (21,63):
            for a,b in CONTRASTS:
                x=pd.read_csv(out/'private'/f'{segment}_p0_h{h}_c5_{a}.csv',index_col=0).equity.pct_change().iloc[1:]
                y=pd.read_csv(out/'private'/f'{segment}_p0_h{h}_c5_{b}.csv',index_col=0).equity.pct_change().iloc[1:]
                if not x.index.equals(y.index):raise ValueError('Mismatched execution calendar')
                mean,ci,p=block_mean_interval((x-y).to_numpy())
                rows.append({'segment':segment,'horizon':h,'contrast':a+' - '+b,'sessions':len(x),
                 'difference_mean_daily':mean,'annualized_mean_difference':mean*252,
                 'pointwise_95_lower':ci[0]*252,'pointwise_95_upper':ci[1]*252,'p_raw':p})
    adj=holm([x['p_raw'] for x in rows])
    for r,p in zip(rows,adj):r['p_holm_all48']=float(p)
    pd.DataFrame(rows).to_csv(out/'paired_return_tests.csv',index=False)
    events=pd.concat([pd.read_parquet(p) for p in (out/'private').glob('events_*.parquet')],ignore_index=True)
    eras=[]
    for label,start,end in [('2007_2012','2007-01-01','2012-12-31'),('2013_2019','2013-01-01','2019-12-31'),('post_reset','2023-06-01','2026-11-09')]:
        x=events[(events.phase==0)&events.origin.ge(start)&events.end.le(end)]
        g=x.groupby(['policy','horizon']).agg(events=('ticker','size'),dates=('origin','nunique'),mean_net=('net_return','mean'),
             mean_sector_excess=('sector_excess','mean'),mean_mae=('mae_close','mean'),low_hold_rate=('prior_low_holds','mean')).reset_index()
        g['era']=label;eras.append(g)
    pd.concat(eras).to_csv(out/'era_event_summary.csv',index=False)
    # Compare selected and unselected native dots on the same date only where both exist.
    selection=[]
    for segment in ('pre','post'):
        for h in (21,63):
            base=events[(events.phase==0)&(events.segment==segment)&(events.horizon==h)&events.policy.eq('dot')].copy()
            for policy in ['dot_stress','dot_repair','dot_stress_repair','dot_vix_not_rising','dot_vvix_not_rising','dot_both_not_rising','dot_vol_easing']:
                selected=events[(events.phase==0)&(events.segment==segment)&(events.horizon==h)&events.policy.eq(policy)]
                keys=set(zip(selected.origin,selected.ticker));base['selected']=[(d,t) in keys for d,t in zip(base.origin,base.ticker)]
                d=base.groupby(['origin','selected']).net_return.mean().unstack('selected')
                mixed=d.dropna() if False in d and True in d else pd.DataFrame()
                gated=base[base.selected];other=base[~base.selected]
                selection.append({'segment':segment,'horizon':h,'policy':policy,'selected':len(gated),'other':len(other),
                 'pooled_net_gap':float(gated.net_return.mean()-other.net_return.mean()) if len(gated) and len(other) else None,
                 'mixed_dates':len(mixed),'within_date_net_gap':float((mixed[True]-mixed[False]).mean()) if len(mixed) else None,
                 'selected_sector_excess':float(gated.sector_excess.mean()) if len(gated) else None,
                 'global_timing_filter_not_stock_selection':len(mixed)==0})
    write_json(out/'date_vs_selection.json',selection)
    native_counts=[]
    for p in (out/'private').glob('native_*.csv'):
        x=pd.read_csv(p);native_counts.append({'file':p.name,'events':len(x),'unique_dates':x.known_session.nunique()})
    write_json(out/'ANALYSIS_RECEIPT.json',{'paired_return_tests':len(rows),'block_sessions':63,'bootstrap_draws':2000,
      'holm_family_size':len(rows),'statistical_scope':'exploratory paired account returns; not independent validation',
      'native_counts':native_counts,'no_forecast_direction_probability_claim':True})
    print('PAIRED_TESTS_COMPLETE',len(rows),'holm_below_05',int(np.sum(adj<.05)),flush=True)
    m=pd.read_csv(out/'portfolio_metrics.csv')
    cols=['policy','cagr','sharpe','maximum_drawdown','mean_exposure','closed_trades']
    for seg in ('pre','post'):
        for h in (21,63):
            print('PRIMARY_BOOK',seg,h,m[(m.segment==seg)&(m.phase==0)&(m.horizon==h)&(m.cost_bp==5)][cols].round(6).to_dict('records'),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root)
