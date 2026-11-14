"""Finite portfolio experiments and retained controls; no best-arm selection."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import asdict,replace
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from .portfolio import Market,Policy,simulate
from .arms import core_policies,SCENARIOS,data_for_policy,scenario_policy
from .run_risk import write_json
from .statistics import primary_family

_STATE={}


def initialize(root,output):
    if hasattr(os,'nice'):os.nice(10)
    r=Path(root);out=Path(output)
    audits=json.loads((r/'data_qualification_v2.json').read_text())
    names=[a['instrument'] for a in audits if a['primary'] and a['qualified_v2']]
    panels={t:pd.read_parquet(r/'private/qualified'/f'{t}.parquet') for t in names}
    benchmark=pd.read_parquet(r/'event_results/benchmark.parquet')
    _STATE.update(root=r,output=out,market=Market(panels,benchmark.index),benchmark=benchmark,
                  events=pd.read_parquet(r/'event_results/events.parquet'),
                  predictions=pd.read_parquet(r/'event_results/risk_predictions.parquet'),
                  no_split={a['instrument'] for a in audits if a['primary'] and a['qualified_v2'] and a['no_split_instrument']})


def diagnostic_alpha(returns,benchmark):
    r=np.asarray(returns,float);b=np.asarray(benchmark,float)
    x=np.column_stack([np.ones(len(r)),b]);bread=np.linalg.pinv(x.T@x)
    coefficient=bread@x.T@r;u=r-x@coefficient;z=x*u[:,None];meat=z.T@z
    for lag in range(1,min(63,len(r)-1)+1):
        gamma=z[lag:].T@z[:-lag];meat+=(1-lag/64)*(gamma+gamma.T)
    covariance=bread@meat@bread
    se=float(np.sqrt(max(0,covariance[0,0])))
    return {'descriptive_spy_beta':float(coefficient[1]),
            'descriptive_annualized_spy_intercept':float(coefficient[0]*252),
            'descriptive_hac63_intercept_t':float(coefficient[0]/se) if se>1e-15 else None,
            'not_multifactor_alpha_or_primary_test':True}


def save_account(result,key,scenario,policy):
    out=_STATE['output'];result['metrics'].update(run_key=key,scenario=scenario)
    b=_STATE['benchmark'].total_return.reindex(result['dates']).to_numpy(float)
    result['metrics'].update(diagnostic_alpha(result['returns'],b))
    daily=pd.DataFrame({'date':result['dates'],'return':result['returns'],
                        'equity':result['equity'][1:],'opening_exposure':result['opening_exposure'],
                        'closing_exposure':result['exposure'],'turnover':result['turnover']})
    daily.to_parquet(out/f'{key}_daily.parquet',index=False)
    result['trades'].to_parquet(out/f'{key}_trades.parquet',index=False)
    write_json(out/f'{key}_receipt.json',{'policy':asdict(policy),'metrics':result['metrics'],
                                         'rejections':result['rejections']})
    return result['metrics']


def one(policy_dict,scenario,subset=None):
    policy=Policy(**policy_dict);e=data_for_policy(_STATE['events'],_STATE['predictions'],policy)
    if subset=='no_split':e=e[e.ticker.isin(_STATE['no_split'])].copy()
    result=simulate(_STATE['market'],e,policy)
    key=scenario+'__'+policy.name
    if subset:key+='__'+subset
    return save_account(result,key,scenario,policy)


def match_static(market,events,target,start,end,name):
    best=None;lo,hi=0.,1.
    for step in range(13):
        multiplier=(lo+hi)/2
        policy=Policy(name,sizing='static',static_multiplier=multiplier)
        result=simulate(market,events,policy,start=start,end=end)
        observed=result['metrics']['mean_decision_open_gross']
        difference=abs(observed-target)
        if best is None or difference<best[0]:best=(difference,multiplier,result,policy)
        if observed<target:lo=multiplier
        else:hi=multiplier
    return best


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-commit',required=True);p.add_argument('--workers',type=int,default=4)
    args=p.parse_args(argv)
    if not 1<=args.workers<=4 or len(args.source_commit)!=40:p.error('invalid bounded run')
    event_receipt=json.loads((args.root/'event_results/run_receipt.json').read_text())
    if event_receipt['status']!='COMPLETE':raise ValueError('event run incomplete')
    args.output.mkdir(parents=True,exist_ok=False)
    registry=[]
    for scenario in SCENARIOS:
        registry.extend((asdict(scenario_policy(policy,scenario)),scenario,None) for policy in core_policies())
    registry += [(asdict(Policy('union_model_common')),'primary',None),
                 (asdict(Policy('union_mem_model_common',sizing='mem')),'primary',None)]
    for name,sizing in (('union','none'),('union_ewma','ewma'),('union_mem','mem')):
        registry += [(asdict(Policy(name,sizing=sizing,barrier_order='target_first')),'target_first',None),
                     (asdict(Policy(name,sizing=sizing,distribution_cash='ex_date_spendable')),'ex_date_cash',None),
                     (asdict(Policy(name,sizing=sizing)),'no_split','no_split')]
    record={'started_at':datetime.now(timezone.utc).isoformat(),'source_commit':args.source_commit,
            'registered_accounts':len(registry),'event_run_sha256':hashlib.sha256((args.root/'event_results/run_receipt.json').read_bytes()).hexdigest(),
            'status':'RUNNING_ATTENDED','metrics':[],'failures':[]}
    write_json(args.output/'registry.json',registry);write_json(args.output/'run_started.json',record)
    with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(str(args.root),str(args.output))) as pool:
        tasks={pool.submit(one,*item):item for item in registry}
        for task in as_completed(tasks):
            try:
                row=task.result();record['metrics'].append(row)
                print('PORTFOLIO_DONE',row['run_key'],'cagr',round(row['cagr'],5),'drawdown',round(row['maximum_close_drawdown'],5),flush=True)
            except Exception as exc:
                item=tasks[task];failure={'policy':item[0]['name'],'scenario':item[1],'error':type(exc).__name__+': '+str(exc)}
                record['failures'].append(failure);print('PORTFOLIO_FAILED',json.dumps(failure),flush=True)
            write_json(args.output/'progress.json',record)
    if record['failures']:
        record.update(status='COMPLETED_WITH_FAILURES',finished_at=datetime.now(timezone.utc).isoformat())
        write_json(args.output/'run_receipt.json',record);return 1
    initialize(str(args.root),str(args.output))
    e=data_for_policy(_STATE['events'],_STATE['predictions'],Policy('union'))
    match_records=[]
    for model in ('ewma','mem'):
        trained=simulate(_STATE['market'],e,Policy('training',sizing=model),start='2015-01-02',end='2019-12-31')
        target=trained['metrics']['mean_decision_open_gross']
        difference,multiplier,_,_=match_static(_STATE['market'],e,target,'2015-01-02','2019-12-31','training_static')
        policy=Policy('union_'+model+'_training_static',sizing='static',static_multiplier=multiplier)
        result=simulate(_STATE['market'],e,policy)
        record['metrics'].append(save_account(result,'primary__'+policy.name,'primary',policy))
        match_records.append({'overlay':model,'control':'training_static','training_end':'2019-12-31',
                              'multiplier':multiplier,'training_open_exposure_target':target,'match_error':difference,
                              'out_of_sample_weights':True})
        main=next(row for row in record['metrics'] if row['run_key']=='primary__union_'+model)
        target=main['mean_decision_open_gross']
        difference,multiplier,result,policy=match_static(_STATE['market'],e,target,'2020-01-02','2026-06-02','union_'+model+'_hindsight_static')
        record['metrics'].append(save_account(result,'primary__'+policy.name,'primary',policy))
        match_records.append({'overlay':model,'control':'hindsight_static','multiplier':multiplier,
                              'open_exposure_target':target,'match_error':difference,'deployable':False})
    write_json(args.output/'exposure_controls.json',match_records)
    pd.DataFrame(record['metrics']).to_csv(args.output/'metrics.csv',index=False)
    calendar=_STATE['benchmark'].loc['2020-01-02':'2026-06-02'].index
    daily={}
    for row in record['metrics']:
        if row['scenario']=='primary':
            d=pd.read_parquet(args.output/(row['run_key']+'_daily.parquet'))
            if not pd.DatetimeIndex(d.date).equals(calendar):raise ValueError('account calendars differ')
            daily[row['policy']]=d['return'].to_numpy(float)
    family=primary_family(pd.read_parquet(args.root/'event_results/forecast_losses.parquet'),
                          _STATE['predictions'],daily,calendar)
    write_json(args.output/'primary_34_tests.json',family)
    record.update(status='COMPLETE',finished_at=datetime.now(timezone.utc).isoformat(),
                  total_accounts=len(record['metrics']),primary_contrasts=len(family),
                  multiple_test_significant=sum(r['holm_below_05'] for r in family))
    write_json(args.output/'run_receipt.json',record)
    print('PORTFOLIO_RESEARCH_COMPLETE',record['total_accounts'],'accounts',len(family),'contrasts',flush=True)
    return 0


if __name__=='__main__':sys.exit(main())
