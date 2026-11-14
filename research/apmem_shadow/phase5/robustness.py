"""Exposure, leave-one-out and state-support follow-up. Explicitly exploratory.

The original experiments are immutable. No threshold, bar phase or model is
selected by maximizing these follow-up results. All new arms are retained.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import experiment as ex
from analyze import block_mean_interval


def static_match(curve, target):
    eq=curve.equity.to_numpy();g=curve.gross.to_numpy()
    lo,hi=0.,1.
    for _ in range(55):
        a=(lo+hi)/2;mix=(1-a)+a*eq;expo=a*eq*g/mix
        if expo.mean()<target:lo=a
        else:hi=a
    a=(lo+hi)/2;mix=(1-a)+a*eq;expo=a*eq*g/mix
    return a,ex.metrics(mix,expo,[]),mix,expo


def recovered_dot(root,index,segment,phase):
    d=pd.DataFrame(False,index=index,columns=ex.SECTORS)
    p=root/'primary_results/private'/f'native_{segment}_{phase}.csv'
    for r in pd.read_csv(p).itertuples():
        t=pd.Timestamp(r.known_session)
        if t not in index:raise ValueError('Native observation outside frozen segment')
        d.loc[t,r.ticker]=True
    return d


def extended_context(price,total,ctx):
    other_rep=pd.DataFrame(False,index=price.index,columns=ex.SECTORS)
    other_stress=other_rep.copy()
    p=price[ex.SECTORS];t=total[ex.SECTORS]
    for k in ex.SECTORS:
        others=[x for x in ex.SECTORS if x!=k]
        ma=p[others].rolling(20).mean()
        above=p[others].gt(ma).astype(float).where(ma.notna()).sum(axis=1,min_count=8)
        basket=(1+t[others].pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()
        other_rep[k]=(basket/basket.shift(5)-1).gt(0)&above.gt(above.shift(5))
        dd=p[others]/p[others].rolling(63).max()-1
        count=dd.le(-.05).astype(float).where(dd.notna()).mean(axis=1)
        other_stress[k]=count.rolling(21,min_periods=21).max().ge(5/9)
    low=p.le(p.shift(1).rolling(20).min()).astype(float)
    lowfreq=low.mean(axis=1).rolling(5).mean()
    lower_pressure=lowfreq.lt(lowfreq.shift(5))
    support=p.ge(p.rolling(126).mean())
    past_lead=(t/t.shift(63)-1).shift(21)
    rotation=pd.DataFrame(False,index=p.index,columns=ex.SECTORS)
    own5=ctx['own5']
    for i in range(84,len(p)):
        if not np.isfinite(past_lead.iloc[i]).all():continue
        leaders=list(past_lead.iloc[i].nlargest(2).index)
        leader_return=float(own5.loc[p.index[i],leaders].mean())
        if leader_return<0:
            for k in ex.SECTORS:
                if k not in leaders and own5[k].iloc[i]>0:rotation.iloc[i,rotation.columns.get_loc(k)]=True
    deterioration=ctx['market5'].lt(0)&ctx['above20'].lt(ctx['above20'].shift(5))
    ongoing=deterioration&deterioration.shift(1,fill_value=False)
    return {'loo_repair':other_rep,'loo_stress':other_stress,'lower_pressure':lower_pressure,
            'slow_support':support,'rotation':rotation,'ongoing_exit':ongoing}


def evaluate(root):
    out=root/'followup_results'
    if out.exists():raise ValueError('Original follow-up output exists; do not duplicate')
    out.mkdir();(out/'private').mkdir()
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text())
    rows=[];matches=[];yearly=[];placebos=[];retention=[];parity=[]
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,manifest);ctx=ex.context(p,t,v);extra=extended_context(p,t,ctx);valid=ex.eval_mask(p.index,segment)
        for phase in (0,1,2):
            d=recovered_dot(root,p.index,segment,phase);old=ex.policies(d,ctx)
            repair=pd.DataFrame(np.repeat(ctx['repair'].to_numpy()[:,None],9,axis=1),index=d.index,columns=d.columns)
            low=pd.DataFrame(np.repeat(extra['lower_pressure'].to_numpy()[:,None],9,axis=1),index=d.index,columns=d.columns)
            arms={'loo_dot_repair':ex.onset(d&extra['loo_repair']),
                  'loo_dot_stress_repair':ex.onset(d&extra['loo_repair']&extra['loo_stress']),
                  'slow_supported_repair':ex.onset(d&repair&extra['slow_support']),
                  'declining_low_pressure':ex.onset(d&repair&low),
                  'prior_leader_rotation':ex.onset(d&repair&extra['rotation']),
                  'ongoing_repair':old['dot_repair']}
            for h in (21,63):
                baseline_path=root/'primary_results/private'/f'{segment}_p{phase}_h{h}_c5_dot.csv'
                raw=pd.read_csv(baseline_path,index_col=0,parse_dates=True)
                rep=pd.read_csv(root/'primary_results/private'/f'{segment}_p{phase}_h{h}_c5_dot_repair.csv',index_col=0,parse_dates=True)
                a,m,_,_=static_match(raw,float(rep.gross.mean()))
                matches.append({'segment':segment,'phase':phase,'horizon':h,'control':'raw_dot_hindsight_exposure_match','capital_fraction':a,**m,'not_deployable_selection':True})
                # Reconcile the extended implementation's default with the original account.
                redo=ex.account(t,old['dot'],valid,h,.0005)
                err=float(np.max(np.abs(redo['curve'].equity.to_numpy()-raw.equity.to_numpy())))
                if err>2e-14:raise AssertionError('Original account changed')
                parity.append({'segment':segment,'phase':phase,'horizon':h,'maximum_equity_difference':err})
                for policy,sig in arms.items():
                    costs=(.0005,.002) if phase==0 else (.0005,)
                    for cost in costs:
                        r=ex.account(t,sig,valid,h,cost,exit_condition=extra['ongoing_exit'] if policy=='ongoing_repair' else None)
                        r['curve'].to_csv(out/'private'/f'{segment}_p{phase}_h{h}_c{int(cost*10000)}_{policy}.csv')
                        pd.DataFrame(r['trades']).to_csv(out/'private'/f'{segment}_p{phase}_h{h}_c{int(cost*10000)}_{policy}_trades.csv',index=False)
                        rows.append({'segment':segment,'phase':phase,'horizon':h,'cost_bp':cost*10000,'policy':policy,**r['metrics']})
                if phase==0:
                    for policy in ('dot','dot_repair','dot_stress_repair','sequence_repair','continuation','phase_router'):
                        r=ex.account(t,old[policy],valid,h,.0005,extra_delay=1)
                        rows.append({'segment':segment,'phase':phase,'horizon':h,'cost_bp':5,'policy':'delay1_'+policy,**r['metrics']})
                    if segment=='pre':
                        train=raw.index<'2013-01-01'
                        alpha,_,_,_=static_match(raw.loc[train],float(rep.loc[train,'gross'].mean()))
                        ev=valid&(p.index>='2013-01-01')
                        for policy in ('dot','dot_repair'):
                            result=ex.account(t,old[policy],ev,h,.0005);cr=result['curve']
                            if policy=='dot':
                                mixed=(1-alpha)+alpha*cr.equity.to_numpy()
                                exposure=alpha*cr.equity.to_numpy()*cr.gross.to_numpy()/mixed
                                mm=ex.metrics(mixed,exposure,result['trades'])
                            else:mm=result['metrics']
                            matches.append({'segment':'2013_2019','phase':0,'horizon':h,'control':policy+'_training_fraction_control',
                                            'capital_fraction':alpha if policy=='dot' else 1.,**mm,'not_deployable_selection':False,
                                            'historical_research_not_untouched_holdout':True})
                    # Date-cluster controls are disclosed descriptive placebos, not 64 new models.
                    eligible=valid.copy();eligible[-h-1:]=False
                    candidate=old['dot'].any(axis=1)&eligible
                    selected=old['dot_repair'].any(axis=1)&eligible
                    rng=np.random.default_rng(20261114+h+(0 if segment=='pre' else 1000))
                    for draw in range(64):
                        keep=np.zeros(len(p),bool)
                        for year in sorted(set(p.index[eligible].year)):
                            ix=np.flatnonzero(candidate.to_numpy()&(p.index.year==year))
                            count=int(np.sum(selected.to_numpy()&(p.index.year==year)))
                            if count:keep[rng.choice(ix,size=count,replace=False)]=True
                        sig=old['dot']&pd.DataFrame(np.repeat(keep[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
                        result=ex.account(t,sig,valid,h,.0005)
                        placebos.append({'segment':segment,'horizon':h,'draw':draw,'retained_dates':int(keep.sum()),**result['metrics']})
                    actual=ex.metrics(rep.equity.to_numpy(),rep.gross.to_numpy(),[])
                    vals=[x for x in placebos if x['segment']==segment and x['horizon']==h]
                    retention.append({'segment':segment,'horizon':h,'actual_cagr':actual['cagr'],'actual_sharpe':actual['sharpe'],
                       'placebo_cagr_median':float(np.median([x['cagr'] for x in vals])),
                       'placebo_cagr_05_95':[float(x) for x in np.quantile([x['cagr'] for x in vals],[.05,.95])],
                       'fraction_at_least_actual':float(np.mean([x['cagr']>=actual['cagr'] for x in vals])),
                       'not_a_confirmatory_p_value':True})
            print('FOLLOWUP_PHASE_FINISHED',segment,phase,flush=True)
    pd.DataFrame(rows).to_csv(out/'policy_metrics.csv',index=False)
    pd.DataFrame(matches).to_csv(out/'exposure_controls.csv',index=False)
    pd.DataFrame(placebos).to_csv(out/'date_cluster_placebos.csv',index=False)
    ex.write_json(out/'placebo_summary.json',retention)
    ex.write_json(out/'original_equity_parity.json',parity)
    ex.write_json(out/'RUN_RECEIPT.json',{'status':'COMPLETE','new_accounts':len(rows),'exposure_controls':len(matches),'date_cluster_controls':len(placebos),
      'all_original_accounts_unchanged':True,'outcome_guided_followup':True,'may_trade':False,
      'source_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['experiment.py','robustness.py']}})
    print('FOLLOWUP_COMPLETE',len(rows),len(matches),len(placebos),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();evaluate(a.root)
