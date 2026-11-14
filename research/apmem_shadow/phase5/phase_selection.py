"""Phase-dependent relative selection at common market event dates.

An explicitly exploratory test of recovering laggards versus persistent leaders.
All-sector benchmarks share the same event dates and execution accounting.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import experiment as ex
from robustness import recovered_dot,extended_context
from core_complement import settle


def schedules(price,total,ctx,xt,dots):
    support=(price[ex.SECTORS]>price[ex.SECTORS].rolling(126).mean()).sum(axis=1)
    recovery=ctx['stress']&ctx['repair']&xt['lower_pressure']&dots.any(axis=1)
    continuation=(~ctx['stress'])&ctx['market5'].gt(0)&support.ge(5)&ctx['continuation'].any(axis=1)
    return {'recovery':ex.onset(recovery),'continuation':ex.onset(continuation)}


def selection_weights(total):
    x=total[ex.SECTORS];score=x.shift(5)/x.shift(63)-1
    risk=np.sqrt(x.pct_change(fill_method=None).pow(2).ewm(alpha=.06,adjust=False,min_periods=126).mean()*252)
    result={}
    for selection in ('all','leaders','laggards'):
        w=pd.DataFrame(0.,index=x.index,columns=x.columns)
        for i in range(126,len(x)):
            if not np.isfinite(score.iloc[i]).all():continue
            selected=list(x.columns) if selection=='all' else list(score.iloc[i].sort_values(ascending=selection=='laggards',kind='stable').index[:3])
            w.loc[x.index[i],selected]=1/len(selected)
        result[selection+'_equal']=w
        result[selection+'_risk']=w*np.minimum(1.,.15/risk)
        result[selection+'_risk']=result[selection+'_risk'].fillna(0.)
    return result


def market_account(total,schedule,weights,valid,horizon,cost):
    if not total.index.equals(schedule.index) or not total.index.equals(weights.index):raise ValueError('Unbound schedule')
    t=total[ex.SECTORS].to_numpy(float);w=weights[ex.SECTORS].to_numpy(float);s=schedule.to_numpy(bool)
    ids=np.flatnonzero(valid);start,end=int(ids[0]),int(ids[-1]);units=np.zeros(9);cash=1.;exit_at=-1;entry=-1
    curve=[];gross=[];trades=[];turnover=0.;capital_at_entry=None;received_at_exit=None
    for i in range(start,end+1):
        val=units*t[i]
        if entry>=0 and (i==exit_at or i==end):
            before=float(val.sum()+cash);values,cash,fee=settle(val,cash,np.zeros(9),cost)
            turnover+=float(val.sum());units=np.zeros(9)
            trades.append({'entry':str(total.index[entry].date()),'exit':str(total.index[i].date()),
              'net_account_trade_return':float(cash/capital_at_entry-1)})
            entry=-1;exit_at=-1
        origin=i-1
        if entry<0 and origin>=start and valid[origin] and s[origin] and i+horizon<=end:
            desired=w[origin]
            if not np.isfinite(desired).all() or desired.sum()>1+1e-12:raise ValueError('Invalid decision weights')
            if desired.sum()>0:
                capital_at_entry=cash
                val,cash,fee=settle(np.zeros(9),cash,desired,cost);units=val/t[i];turnover+=float(val.sum())
                entry=i;exit_at=i+horizon
        val=units*t[i];wealth=float(val.sum()+cash)
        if wealth<=0 or cash<-1e-12:raise AssertionError('Funding error')
        curve.append(wealth);gross.append(float(val.sum()/wealth))
    cc=pd.DataFrame({'equity':curve,'gross':gross},index=total.index[start:end+1]);m=ex.metrics(np.array(curve),gross,trades)
    m['turnover_equity_units']=turnover
    return m,cc,trades


def main(root):
    out=root/'phase_selection_results'
    if out.exists():raise ValueError('Original phase-selection output exists')
    out.mkdir();(out/'private').mkdir();results=[];events=[]
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text())
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,manifest);ctx=ex.context(p,t,v);xt=extended_context(p,t,ctx);valid=ex.eval_mask(p.index,segment)
        d=recovered_dot(root,p.index,segment,0);sch=schedules(p,t,ctx,xt,d);weights=selection_weights(t)
        for phase,s in sch.items():
            for i in np.flatnonzero(s.to_numpy()&valid):
                entry=i+1
                for h in (21,63):
                    end=entry+h
                    if end>=len(p):continue
                    returns=t[ex.SECTORS].iloc[end]/t[ex.SECTORS].iloc[entry]-1
                    for selection,w in weights.items():
                        ww=w.iloc[i];r=float(ww@returns)
                        path=(t[ex.SECTORS].iloc[entry:end+1]/t[ex.SECTORS].iloc[entry]).mul(ww).sum(axis=1)+(1-ww.sum())
                        events.append({'segment':segment,'phase':phase,'origin':str(p.index[i].date()),'horizon':h,'selection':selection,
                           'gross_return':r,'mean_exposure_at_entry':float(ww.sum()),'closing_mae':float(path.min()-1),
                           'excess_equal_sector':r-float(returns.mean())})
        for h in (21,63):
            for cost in (.0005,.002):
                for phase,s in sch.items():
                    for selection,w in weights.items():
                        m,c,rr=market_account(t,s,w,valid,h,cost)
                        name=f'{segment}_{phase}_{selection}_h{h}_c{int(cost*10000)}'
                        c.to_csv(out/'private'/(name+'.csv'));pd.DataFrame(rr).to_csv(out/'private'/(name+'_trades.csv'),index=False)
                        results.append({'segment':segment,'phase':phase,'selection':selection,'horizon':h,'cost_bp':cost*10000,**m})
                for selection in ('always_all','always_leaders','phase_dependent'):
                    both=sch['recovery']|sch['continuation'];ww=weights['all_equal'].copy() if selection=='always_all' else weights['leaders_equal'].copy()
                    if selection=='phase_dependent':ww.loc[sch['recovery']]=weights['laggards_equal'].loc[sch['recovery']]
                    m,c,rr=market_account(t,both,ww,valid,h,cost)
                    name=f'{segment}_router_{selection}_h{h}_c{int(cost*10000)}';c.to_csv(out/'private'/(name+'.csv'))
                    results.append({'segment':segment,'phase':'router','selection':selection,'horizon':h,'cost_bp':cost*10000,**m})
        print('PHASE_SELECTION_SEGMENT',segment,'recovery_origins',int((sch['recovery']&valid).sum()),'continuation_origins',int((sch['continuation']&valid).sum()),flush=True)
    pd.DataFrame(results).to_csv(out/'portfolio_metrics.csv',index=False)
    e=pd.DataFrame(events);e.to_parquet(out/'private/events.parquet')
    e.groupby(['segment','phase','selection','horizon']).agg(events=('origin','size'),mean_return=('gross_return','mean'),
      median_return=('gross_return','median'),mean_excess=('excess_equal_sector','mean'),mean_mae=('closing_mae','mean'),
      mean_entry_exposure=('mean_exposure_at_entry','mean')).to_csv(out/'event_scores.csv')
    ex.write_json(out/'RUN_RECEIPT.json',{'status':'COMPLETE','accounts':len(results),'event_comparison_rows':len(e),
      'outcome_guided_exploratory':True,'may_trade':False,'source_sha256':hashlib.sha256((root/'phase_selection.py').read_bytes()).hexdigest()})
    print('PHASE_SELECTION_COMPLETE',len(results),len(e),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();main(a.root)
