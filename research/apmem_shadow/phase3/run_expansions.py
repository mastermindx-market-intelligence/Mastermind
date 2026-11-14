"""Frozen persistent controls plus disclosed outcome-guided factorial diagnostics.

Existing primary accounts are reused by exact file identity. No model refits or
new thresholds. The entire factorial remains exploratory after primary results.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import asdict,replace
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from . import continuous
from .portfolio import Policy,simulate,summarize
from .data import member_at
from .arms import core_policies,data_for_policy
from .run_portfolios import initialize,one,save_account,_STATE
from .run_risk import write_json


def era_metrics(daily):
    rows=[]
    for label,lo,hi in [('2020_2023','2020-01-02','2023-12-31'),('2024_2026','2024-01-01','2026-06-02')]:
        sub=daily[(daily.date>=lo)&(daily.date<=hi)]
        if len(sub)<2:continue
        eq=np.r_[1.,np.cumprod(1+sub['return'].to_numpy(float))]
        metric=summarize(eq,pd.DatetimeIndex(sub.date),sub.closing_exposure.to_numpy(float),sub.turnover.to_numpy(float))
        metric.update(era=label,mean_decision_open_gross=float(sub.opening_exposure.mean()))
        rows.append(metric)
    return rows


def exposure_match(market,events,base_policy,target):
    low,high=0.,1.;best=None
    for _ in range(13):
        multiplier=(low+high)/2
        policy=replace(base_policy,sizing='static',static_multiplier=multiplier)
        result=simulate(market,events,policy)
        observed=result['metrics']['mean_decision_open_gross'];error=abs(observed-target)
        if best is None or error<best[0]:best=(error,multiplier,result,policy)
        if observed<target:low=multiplier
        else:high=multiplier
    return best


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-commit',required=True);parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args(argv)
    if not 1<=args.workers<=4 or len(args.source_commit)!=40:parser.error('invalid bounded run')
    r=args.root;out=args.output;out.mkdir(parents=True,exist_ok=False)
    original=json.loads((r/'portfolio_results/run_receipt.json').read_text())
    if original['status']!='COMPLETE':raise ValueError('original accounts incomplete')
    record={'started_at':datetime.now(timezone.utc).isoformat(),'source_commit':args.source_commit,
            'status':'RUNNING_ATTENDED','original_source_commit':original['source_commit'],
            'factorial_exploratory_after_results':True,'new_model_fits':0,'new_thresholds':0,
            'reused':[],'new_accounts':[],'failures':[]}
    write_json(out/'run_started.json',record)
    # Exact original policies identify eligible reused cells, not matching prose names.
    available={}
    for policy in core_policies():
        if policy.selection=='identifier' and policy.name not in ('union_price_ev','union_risk_ev','union_interaction_ev'):
            key=(policy.family,policy.exit_rule,policy.sizing)
            path=r/'portfolio_results'/('primary__'+policy.name+'_receipt.json')
            if path.exists():available[key]=(policy,path)
    jobs=[];matrix=[];eras=[]
    for family in ('t1','t2','union','breakout20','reclaim50','trend63_126'):
        for exit_rule in ('time21','stop21','barrier21','trail63'):
            for sizing in ('none','ewma','mem'):
                key=(family,exit_rule,sizing);name='factorial_'+family+'_'+exit_rule+'_'+sizing
                policy=Policy(name,family=family,exit_rule=exit_rule,sizing=sizing)
                if key in available:
                    old,path=available[key];saved=json.loads(path.read_text())
                    expected=asdict(old);stored=saved['policy']
                    if stored!=expected:raise ValueError('reused policy differs from registered source')
                    dpath=r/'portfolio_results'/('primary__'+old.name+'_daily.parquet')
                    metric={**saved['metrics'],'factorial_name':name,'reused_original':True,
                            'reused_daily_sha256':hashlib.sha256(dpath.read_bytes()).hexdigest()}
                    matrix.append(metric);record['reused'].append(name)
                    eras.extend({**x,'factorial_name':name} for x in era_metrics(pd.read_parquet(dpath)))
                else:jobs.append((asdict(policy),'factorial',None))
    with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(str(r),str(out))) as pool:
        tasks={pool.submit(one,*job):job for job in jobs}
        for task in as_completed(tasks):
            job=tasks[task]
            try:
                metric=task.result();metric.update(factorial_name=metric['policy'],reused_original=False)
                matrix.append(metric);record['new_accounts'].append(metric['policy'])
                dpath=out/(metric['run_key']+'_daily.parquet')
                eras.extend({**x,'factorial_name':metric['policy']} for x in era_metrics(pd.read_parquet(dpath)))
                print('FACTORIAL_ACCOUNT_DONE',metric['policy'],flush=True)
            except Exception as exc:
                failure={'policy':job[0]['name'],'error':type(exc).__name__+': '+str(exc)}
                record['failures'].append(failure);print('FACTORIAL_FAILED',json.dumps(failure),flush=True)
            write_json(out/'progress.json',record)
    if record['failures']:write_json(out/'run_receipt.json',record);return 1
    if len(matrix)!=72:raise AssertionError('complete factorial not retained')
    pd.DataFrame(matrix).to_csv(out/'factorial_metrics.csv',index=False)
    pd.DataFrame(eras).to_csv(out/'factorial_eras.csv',index=False)
    initialize(str(r),str(out));market=_STATE['market'];events=_STATE['events'];pred=_STATE['predictions']
    e=data_for_policy(events,pred,Policy('union'))
    attribution={}
    for name,exit_rule in [('union','barrier21'),('union_trail63','trail63')]:
        result=simulate(market,e,Policy(name,exit_rule=exit_rule))
        old=pd.read_parquet(r/'portfolio_results'/('primary__'+name+'_daily.parquet'))
        if not np.array_equal(result['equity'][1:],old.equity.to_numpy(float)):
            raise AssertionError('attribution instrumentation changed an account action')
        pnl=float(result['trades'].pnl_equity_units.sum())
        if not np.isclose(pnl,result['equity'][-1]-1,atol=1e-12):raise AssertionError('per-lot P&L does not reconcile')
        result['trades'].to_parquet(out/(name+'_attributed_trades.parquet'),index=False)
        names=result['trades'].groupby('ticker').pnl_equity_units.sum().sort_values(ascending=False)
        attribution[name]={'exact_original_equity_equal':True,'sum_closed_lot_pnl':pnl,
                           'net_account_gain':float(result['equity'][-1]-1),
                           'by_name_pnl':names.to_dict(),
                           'largest_three_positive_pnl_share_of_net_gain':float(names.head(3).sum()/pnl) if pnl>0 else None,
                           'median_trade_return':float(result['trades'].net_return_on_committed_cash.median())}
    write_json(out/'attribution.json',attribution)
    fragility=[]
    leaders=list(attribution['union_trail63']['by_name_pnl'])
    for count in (1,3):
        removed=leaders[:count];policy=Policy('trail63_without_top'+str(count),exit_rule='trail63')
        result=simulate(market,e[~e.ticker.isin(removed)].copy(),policy)
        fragility.append({**save_account(result,'fragility__'+policy.name,'fragility',policy),
                          'removed_names':removed,'outcome_selected_exclusion_not_investable':True})
    base=next(x for x in matrix if x['factorial_name']=='factorial_union_barrier21_none')
    err,mult,result,policy=exposure_match(market,e,Policy('trail63_barrier_exposure_match',exit_rule='trail63'),base['mean_decision_open_gross'])
    fragility.append({**save_account(result,'fragility__'+policy.name,'fragility',policy),
                      'hindsight_static_multiplier':mult,'match_error':err,'deployable':False})
    write_json(out/'trailing_fragility.json',fragility)
    paths=pd.read_parquet(r/'event_results/paths.parquet')
    sub=paths[(paths.family=='union')&(paths.status=='COMPLETE')&(paths.extra_session_delay==0)&(paths.barrier_order=='stop_first')]
    by_rule=sub.groupby('rule').agg(events=('event_id','size'),mean_net=('net_return','mean'),median_net=('net_return','median'),
        mean_holding_sessions=('days_held','mean'),mean_path_mae=('full_horizon_mae','mean'),mean_path_mfe=('full_horizon_mfe','mean'))
    by_rule.to_csv(out/'same_entry_path_payoffs.csv')
    # Build the previously frozen persistent-opportunity controls, using the same input identities.
    members=pd.read_parquet(r/'private/membership.parquet');benchmark=_STATE['benchmark'];features={}
    for ticker in market.names:
        p=pd.read_parquet(r/'private/qualified'/f'{ticker}.parquet')
        f=pd.read_parquet(r/'risk_results'/f'{ticker}.parquet')
        eligible=member_at(p.index,members[members.ticker.str.upper().eq(ticker)])&p.tradable.to_numpy(bool)
        eligible&=(p.momentum63>0).to_numpy()&(p.momentum126>0).to_numpy()
        features[ticker]=pd.DataFrame({'eligible':eligible,
            'relative_momentum':p.momentum126_skip21-benchmark.momentum126_skip21.reindex(p.index),
            'mem_h5':f.mem_h5,'ewma_h5':f.ewma_h5},index=p.index)
    persistent=[];core=None
    for cost in (.0005,.002):
        for policy in continuous.controls():
            policy=replace(policy,cost=cost);result=continuous.simulate(market,features,policy)
            key=('cost5' if cost==.0005 else 'cost20')+'__'+policy.name
            persistent.append(result['metrics'])
            daily=pd.DataFrame({'date':result['dates'],'return':result['returns'],'equity':result['equity'][1:],
                'opening_exposure':result['opening_exposure'],'closing_exposure':result['exposure'],'turnover':result['turnover']})
            daily.to_parquet(out/(key+'_daily.parquet'),index=False)
            np.savez_compressed(out/(key+'_weights.npz'),weights=result['holdings_weights'],symbols=np.asarray(result['instruments'],dtype='U32'))
            if cost==.0005 and policy.name=='trend_relative_mem_daily':core=result
            print('PERSISTENT_CONTROL_DONE',key,flush=True)
    pd.DataFrame(persistent).to_csv(out/'persistent_metrics.csv',index=False)
    tactical=pd.read_parquet(r/'portfolio_results/primary__union_mem_daily.parquet')
    if not pd.DatetimeIndex(tactical.date).equals(core['dates']):raise ValueError('sleeve calendars differ')
    mixture=[]
    for name,second,second_exposure in [('half_core_half_tactical',np.r_[1.,tactical.equity.to_numpy()],tactical.closing_exposure.to_numpy()),
                                      ('half_core_half_cash',np.ones(len(core['equity'])),np.zeros(len(core['dates'])))]:
        eq=.5*core['equity']+.5*second
        exp=(.5*core['equity'][1:]*core['exposure']+.5*second[1:]*second_exposure)/eq[1:]
        metric=summarize(eq,core['dates'],exp,np.zeros(len(exp)))
        metric.update(policy=name,turnover_per_year=None,turnover_reason='not reconstructed from per-sleeve dollar ledgers',
                      fixed_initial_capital_weights=[.5,.5],rebalancing_between_sleeves=False,
                      all_within_sleeve_costs_included=True,possible_twenty_name_union=True,
                      authority='research_only')
        mixture.append(metric)
        pd.DataFrame({'date':core['dates'],'equity':eq[1:],'return':np.diff(eq)/eq[:-1],'closing_exposure':exp}).to_csv(out/(name+'_daily.csv'),index=False)
    write_json(out/'fixed_sleeve_comparisons.json',mixture)
    record.update(status='COMPLETE',finished_at=datetime.now(timezone.utc).isoformat(),factorial_cells=len(matrix),
                  persistent_controls=len(persistent),reused_original_count=len(record['reused']),
                  new_factorial_count=len(record['new_accounts']),attribution_equity_parity=True)
    write_json(out/'run_receipt.json',record)
    print('EXPANSIONS_COMPLETE',json.dumps({k:record[k] for k in ('factorial_cells','persistent_controls','reused_original_count','new_factorial_count')}),flush=True)
    return 0


if __name__=='__main__':sys.exit(main())
