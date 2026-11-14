"""Fixed sector leadership controls and nonoptimized recovery-sleeve mixtures."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import experiment as ex


def settle(values, cash, weights, cost):
    values=np.asarray(values,float);weights=np.asarray(weights,float)
    if values.shape!=weights.shape or not np.isfinite(cash) or (values<0).any() or cash<0 or (weights<0).any() or weights.sum()>1+1e-12:
        raise ValueError('Unlevered funding contract violated')
    if not np.isfinite(values).all() or not np.isfinite(weights).all() or not 0<=cost<.1:
        raise ValueError('Invalid execution inputs')
    wealth=float(values.sum()+cash);lo=wealth*(1-2*cost);hi=wealth
    for _ in range(60):
        after=(lo+hi)/2
        residual=after+cost*np.abs(weights*after-values).sum()-wealth
        if residual>0:hi=after
        else:lo=after
    after=(lo+hi)/2;target=weights*after;newcash=after-target.sum()
    fee=float(cost*np.abs(target-values).sum())
    if abs(wealth-after-fee)>1e-10 or newcash<-1e-12:raise AssertionError('Cost funding failed')
    return target,max(0.,float(newcash)),fee


def target_weights(price,total,kind):
    ex.check_index(price.index)
    p,t=price[ex.SECTORS],total[ex.SECTORS]
    momentum=t.shift(21)/t.shift(126)-1
    good=p.gt(p.rolling(126).mean())&momentum.gt(0)
    sigma=np.sqrt(t.pct_change(fill_method=None).pow(2).ewm(alpha=.06,adjust=False,min_periods=126).mean()*252)
    w=pd.DataFrame(0.,index=p.index,columns=p.columns)
    for i in range(126,len(p)):
        if not np.isfinite(momentum.iloc[i]).all():continue
        selected=list(momentum.iloc[i].sort_values(ascending=False,kind='stable').index[:3])
        if kind=='equal_trend':
            w.iloc[i]=good.iloc[i].astype(float)/9
        else:
            for k in selected:
                if kind!='top3' and not good[k].iloc[i]:continue
                scale=1.
                if kind=='top3_trend_risk':
                    if not np.isfinite(sigma[k].iloc[i]) or sigma[k].iloc[i]<=0:continue
                    scale=min(1.,.15/sigma[k].iloc[i])
                w.loc[p.index[i],k]=scale/3
    return w


def core_account(total,weights,valid,cost):
    if not total.index.equals(weights.index):raise ValueError('Target clock mismatch')
    ix=np.flatnonzero(valid);start,end=int(ix[0]),int(ix[-1])
    t=total[ex.SECTORS].to_numpy(float);w=weights[ex.SECTORS].to_numpy(float)
    periods=total.index.to_period('M')
    observed=np.r_[periods[:-1]!=periods[1:],False];observed[start]=True
    units=np.zeros(9);cash=1.;equity=[];gross=[];rebalance=[]
    for i in range(start,end+1):
        val=units*t[i];before=float(cash+val.sum())
        origin=i-1
        act=(origin>=start and observed[origin]) or i==end
        if act:
            desired=np.zeros(9) if i==end else w[origin]
            newval,cash,fee=settle(val,cash,desired,cost)
            turnover=float(np.abs(newval-val).sum()/before)
            units=newval/t[i];val=newval
            rebalance.append({'observed':str(total.index[origin].date()),'executed':str(total.index[i].date()),
                 'fee':fee,'turnover_fraction':turnover,'post_gross':float(desired.sum()),'terminal':i==end})
        wealth=float(cash+val.sum())
        equity.append(wealth);gross.append(float(val.sum()/wealth))
    curve=pd.DataFrame({'equity':equity,'gross':gross},index=total.index[start:end+1])
    m=ex.metrics(curve.equity.to_numpy(),curve.gross.to_numpy(),[]);m.pop('closed_trades')
    m['rebalances']=len(rebalance);m['annual_turnover']=sum(x['turnover_fraction'] for x in rebalance)*252/(len(curve)-1)
    return m,curve,rebalance


def mixture(a,b=None):
    if b is not None and not a.index.equals(b.index):raise ValueError('Mixture calendar mismatch')
    aeq=a.equity.to_numpy();beq=np.ones(len(a)) if b is None else b.equity.to_numpy()
    bg=np.zeros(len(a)) if b is None else b.gross.to_numpy()
    eq=.5*aeq+.5*beq;gross=(.5*aeq*a.gross.to_numpy()+.5*beq*bg)/eq
    return ex.metrics(eq,gross,[]),pd.DataFrame({'equity':eq,'gross':gross},index=a.index)


def main(root):
    out=root/'core_results'
    if out.exists():raise ValueError('Original core run already exists')
    out.mkdir();(out/'private').mkdir()
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text());results=[];mixtures=[]
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,manifest);valid=ex.eval_mask(p.index,segment)
        for kind in ('top3','top3_trend','top3_trend_risk','equal_trend'):
            weights=target_weights(p,t,kind)
            for cost in (.0005,.002):
                m,curve,trades=core_account(t,weights,valid,cost)
                name=f'{segment}_c{int(cost*10000)}_{kind}'
                curve.to_csv(out/'private'/(name+'.csv'));pd.DataFrame(trades).to_csv(out/'private'/(name+'_rebalances.csv'),index=False)
                results.append({'segment':segment,'policy':kind,'cost_bp':cost*10000,**m})
                for h in (21,63):
                    for tactical in ('cash','dot','dot_repair'):
                        b=None if tactical=='cash' else pd.read_csv(root/'primary_results/private'/f'{segment}_p0_h{h}_c{int(cost*10000)}_{tactical}.csv',index_col=0,parse_dates=True)
                        mm,cc=mixture(curve,b)
                        mixtures.append({'segment':segment,'core':kind,'tactical':tactical,'horizon':h,'cost_bp':cost*10000,**mm})
                        cc.to_csv(out/'private'/f'{name}_{tactical}_h{h}.csv')
            print('CORE_CONTROL_COMPLETE',segment,kind,flush=True)
    pd.DataFrame(results).to_csv(out/'core_metrics.csv',index=False)
    pd.DataFrame(mixtures).to_csv(out/'mixture_metrics.csv',index=False)
    ex.write_json(out/'RUN_RECEIPT.json',{'status':'COMPLETE','core_accounts':len(results),'fixed_mixtures':len(mixtures),
       'initial_mixture_weight':.5,'outcome_guided_exploratory_extension':True,'may_trade':False,
       'source_sha256':hashlib.sha256((root/'core_complement.py').read_bytes()).hexdigest()})
    print('CORE_COMPLEMENT_COMPLETE',len(results),len(mixtures),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();main(a.root)
