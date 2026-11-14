"""One attended stock-research observation and offline maturity evaluation.

No network, account state, recurring collector or trading effects. The caller
supplies separately captured inputs and an immutable canonical-source snapshot.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from .data import parse_capture,prepare_prices
from .risk import forecasts
from .native import verify_source
from .consumer import attach,timestamp
from urllib.parse import parse_qs,urlsplit
from .run_risk import write_json


def prefix_digest(series: pd.Series) -> str:
    """Economic date/value identity, independent of pandas index/column metadata."""
    index=pd.DatetimeIndex(series.index)
    values=series.to_numpy(float)
    if (not index.is_unique or not index.is_monotonic_increasing or index.hasnans
            or not index.equals(index.normalize()) or not np.isfinite(values).all() or (values<=0).any()):
        raise ValueError('invalid economic prefix')
    rows=[[str(d.date()),float(v).hex()] for d,v in zip(index,values)]
    encoded=json.dumps({'schema':'date_floathex_close_v1','rows':rows},separators=(',',':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def maturity_scores(record: dict,prepared: pd.DataFrame,*,instrument: str,model: str):
    if record.get('instrument')!=instrument or record.get('status')!='RECORDED_RESEARCH':
        raise ValueError('wrong or unqualified frozen observation')
    if model not in record['forecasts']:raise ValueError('model not frozen in this record')
    if not prepared.index.is_unique or not prepared.index.is_monotonic_increasing:
        raise ValueError('invalid target observation index')
    origin=pd.Timestamp(record['origin_session']);out=[]
    for h in (1,5,20):
        dates=pd.DatetimeIndex(record['expected_future_sessions'][:h])
        if len(dates)!=h or (dates<=origin).any() or not dates.is_monotonic_increasing or not dates.is_unique:
            raise ValueError('invalid frozen future calendar')
        if dates[-1]>prepared.index[-1]:
            out.append({'horizon':h,'status':'NOT_MATURED'});continue
        if not dates.isin(prepared.index).all():
            out.append({'horizon':h,'status':'MISSING_REALIZED_SESSION'});continue
        values=prepared.loc[dates,['variance','return_log']].to_numpy(float)
        if not np.isfinite(values).all() or (values[:,0]<=0).any():
            out.append({'horizon':h,'status':'INVALID_TARGET_INPUT'});continue
        forecast=record['forecasts'][model]['mean_daily_variance'][str(h)]
        if type(forecast) not in (float,int) or not np.isfinite(forecast) or forecast<=0:
            raise ValueError('invalid frozen forecast')
        for target,y in [('variance',values[:,0].mean()),('return_square',np.mean(values[:,1]**2))]:
            ratio=max(y,1e-12)/forecast
            out.append({'horizon':h,'target':target,'status':'MATURED_OBSERVATION_ONLY',
                        'realized_mean':float(y),'forecast':forecast,
                        'qlike':float(ratio-np.log(ratio)-1),'mse':float((y-forecast)**2),
                        'not_strategy_validation':True})
    return out


def score_captured_outcomes(frozen_bytes: bytes,frozen_sha256: str,target_bytes: bytes,target_receipt: dict,*,model: str,now: str):
    """Bind immutable forecast bytes and later same-provider source before grading."""
    if hashlib.sha256(frozen_bytes).hexdigest()!=frozen_sha256:
        raise ValueError('frozen observation digest changed')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('ambiguous frozen record')
            result[key]=value
        return result
    record=json.loads(frozen_bytes,object_pairs_hook=unique)
    if timestamp(target_receipt.get('captured_at'))>timestamp(now):
        raise ValueError('target capture is in the future')
    query=parse_qs(urlsplit(target_receipt.get('request_path','')).query)
    ends=query.get('endDate',[])
    if len(ends)!=1:raise ValueError('target capture endpoint unknown')
    prices,quality=parse_capture(target_bytes,target_receipt,record['instrument'],cutoff=ends[0])
    if not quality['action_basis_qualified']:raise ValueError('target action basis unqualified')
    ordinary=[1.5]+list(range(1,21))+[1/i for i in range(1,21)]
    if any(not any(abs(x/v-1)<=1e-5 for v in ordinary) for x in prices.split):
        raise ValueError('target includes unqualified corporate action')
    prepared=prepare_prices(prices)
    if prepared.index[-1].date()>timestamp(target_receipt['captured_at']).date():
        raise ValueError('economic date exceeds source capture clock')
    digest=prefix_digest(prepared.signal_close.loc[:record['origin_session']])
    if digest!=record['lineage']['prefix_sha256']:
        return {'status':'SOURCE_REVISION_DETECTED','original_forecast_unchanged':True,
                'requires_explicit_revision_adjudication':True,'scores':[]}
    return {'status':'MATURED_HORIZONS_ONLY','frozen_sha256':frozen_sha256,
            'target_capture_sha256':hashlib.sha256(target_bytes).hexdigest(),
            'target_captured_at':target_receipt['captured_at'],
            'scores':maturity_scores(record,prepared,instrument=record['instrument'],model=model),
            'may_rank':False,'may_size':False,'may_trade':False}


def worker(captures: str,ticker: str,receipt: dict,output: str,source_commit: str,origin: str):
    if hasattr(os,'nice'):os.nice(10)
    from engine.signal_gate import gate,TAKE
    from portfolio.entry_engine import assess
    from lib.nyse_calendar import sessions_between
    target=Path(output)/f'{ticker}.json'
    raw=(Path(captures)/f'{ticker}.json').read_bytes()
    prices,quality=parse_capture(raw,receipt,ticker,cutoff=origin)
    if str(prices.index[-1].date())!=origin:raise ValueError('expected fresh origin is unavailable')
    if not quality['action_basis_qualified']:raise ValueError('action-basis change unqualified')
    ordinary=[1.5]+list(range(1,21))+[1/i for i in range(1,21)]
    unusual=[float(x) for x in prices.split if not any(abs(x/v-1)<=1e-5 for v in ordinary)]
    if unusual:raise ValueError('unqualified nonordinary action factor')
    calendar=pd.DatetimeIndex(sessions_between(prices.index[0].date(),prices.index[-1].date()))
    if not prices.index.equals(calendar):raise ValueError('missing or non-exchange session')
    p=prepare_prices(prices);f,fit_receipt=forecasts(p)
    if not np.isfinite(f[['mem_h1','mem_h5','mem_h20','ewma_h1','ewma_h5','ewma_h20']].iloc[-1]).all():
        raise ValueError('fresh risk forecast unavailable')
    history=[]
    for length in range(len(p)-3,len(p)+1):
        v=gate(ticker,p.signal_close.iloc[:length],washout_waiver=False)
        if v.get('reason')=='engine error' or v.get('result') is None:raise ValueError('native observation unavailable')
        t1=bool(v.get('eligible') and v.get('tier_cascade')=='T1' and v.get('tier')==TAKE and not v.get('tier_observation_provisional'))
        t2=bool(v.get('eligible') and v.get('tier_cascade')=='T2')
        history.append({'observed_session':str(p.index[length-1].date()),'t1':t1,'t2':t2,
                        'tier':v.get('tier_cascade'),'provisional':bool(v.get('tier_observation_provisional'))})
    new_onset=bool((history[-1]['t1'] or history[-1]['t2']) and not any(z['t1'] or z['t2'] for z in history[:-1]))
    report=assess(ticker,series=p.signal_close,signal_gate_row=v,as_of=origin,_use_defaults=False)
    last_fit=fit_receipt['fits'][-1]
    computed=datetime.now(timezone.utc).isoformat()
    lineage={'raw_capture_sha256':hashlib.sha256(raw).hexdigest(),
             'prefix_sha256':prefix_digest(p.signal_close),
             'native_source_commit':'6bbc4b0fc694c847077661ff5bf4c19ea41e4e81',
             'research_source_commit':source_commit}
    payload={'instrument':ticker,'origin_session':origin,'captured_at':receipt['captured_at'],
        'computed_at':computed,'historical_first_availability':None,'lineage':lineage,
        'forecast':{'model':'delta1_MEM','unit':'mean_daily_variance',
                    **{'h'+str(h):float(f['mem_h'+str(h)].iloc[-1]) for h in (1,5,20)},
                    'fit_cutoff':last_fit['train_end_session']},
        'native':{'eligible':history[-1]['t1'] or history[-1]['t2'],'tier':history[-1]['tier'],
                  'provisional':history[-1]['provisional']},'conditional':None}
    result=attach(report,payload,instrument=ticker,origin=origin,now=computed,expected_lineage=lineage)
    if {k:v for k,v in result.items() if k!='entry_risk_research'}!=report:
        raise AssertionError('incumbent entry verdict changed')
    future=[str(d) for d in sessions_between((pd.Timestamp(origin)+pd.Timedelta(days=1)).date(),
               (pd.Timestamp(origin)+pd.Timedelta(days=80)).date())][:20]
    frozen={'instrument':ticker,'status':'RECORDED_RESEARCH','origin_session':origin,
        'captured_at':receipt['captured_at'],'computed_at':computed,'lineage':lineage,
        'expected_future_sessions':future,'forecasts':{},'native_observations':history,
        'new_union_onset':new_onset,'price_native_only_entry_report':result,
        'missing_consumer_inputs':['stage','sector context','fundamental opportunity','holdings','production data health'],
        'conditional_model_status':'ABSTAIN_OLD_TRAINING_POPULATION_NOT_FRESH_QUALIFIED',
        'current_SP1500_membership_asserted':False,'ordinary_action_ratios_research_assumption':True,
        'source_capture_quality':quality,'selected_fits':len(fit_receipt['fits']),
        'successful_fits':sum(bool(x['success']) for x in fit_receipt['fits']),
        'may_rank':False,'may_size':False,'may_trade':False,'prospective_matured_outcomes':0}
    for model in ('mem','ewma'):
        daily={str(h):float(f[f'{model}_h{h}'].iloc[-1]) for h in (1,5,20)}
        frozen['forecasts'][model]={'mean_daily_variance':daily,
            'annualized_volatility_fraction':{h:float(np.sqrt(252*x)) for h,x in daily.items()}}
    frozen['maturity_at_issue']=maturity_scores(frozen,p,instrument=ticker,model='mem')
    if any(x['status']!='NOT_MATURED' for x in frozen['maturity_at_issue']):raise AssertionError('future target unexpectedly available')
    write_json(target,frozen)
    write_json(Path(output)/(ticker+'_fit_audit.json'),fit_receipt)
    return {'instrument':ticker,'status':'RECORDED_RESEARCH','new_union_onset':new_onset,
            'active_primary':history[-1]['t1'] or history[-1]['t2'],
            'incumbent_verdict':report.get('verdict'),'incumbent_buyable':report.get('buyable'),
            'forecast_values':6,'source_record_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}


def validate_capture_roster(selection: dict,captures: list,origin: str):
    if not isinstance(selection,dict) or selection.get('origin_session')!=origin:
        raise ValueError('capture roster origin mismatch')
    names=selection.get('instruments')
    if not isinstance(names,list) or not names or not all(isinstance(x,str) for x in names) or len(names)!=len(set(names)):
        raise ValueError('ambiguous fixed capture roster')
    if not isinstance(captures,list) or not all(isinstance(x,dict) for x in captures):
        raise ValueError('invalid capture receipts')
    observed=[x.get('instrument') for x in captures]
    if len(observed)!=len(set(observed)) or set(observed)!=set(names):
        raise ValueError('missing, duplicate or foreign instrument in capture receipts')
    if any(x.get('status') not in ('CAPTURED','CAPTURE_FAILED','NOT_ATTEMPTED_AFTER_PROVIDER_BOUNDARY') for x in captures):
        raise ValueError('unknown capture status')
    return names


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native-root',type=Path,required=True);parser.add_argument('--native-manifest',type=Path,required=True)
    parser.add_argument('--source-commit',required=True);parser.add_argument('--origin',default='2026-11-13')
    args=parser.parse_args(argv)
    if len(args.source_commit)!=40:parser.error('exact source revision required')
    verify_source(args.native_root,json.loads(args.native_manifest.read_text()))
    captures=json.loads((args.captures/'receipts.json').read_text())
    selection=json.loads((args.captures/'selection_receipt.json').read_text())
    names=validate_capture_roster(selection,captures,args.origin)
    args.output.mkdir(parents=True,exist_ok=False)
    record={'started_at':datetime.now(timezone.utc).isoformat(),'source_commit':args.source_commit,
            'origin_session':args.origin,'status':'RUNNING_ATTENDED','results':[],'failures':[],
            'future_outcomes_observed':0,'raw_provider_history_published':False,
            'fixed_instruments':names,'capture_roster_sha256':hashlib.sha256((args.captures/'selection_receipt.json').read_bytes()).hexdigest()}
    write_json(args.output/'run_started.json',record)
    with ProcessPoolExecutor(max_workers=4) as pool:
        pending={pool.submit(worker,str(args.captures),c['instrument'],c,str(args.output),args.source_commit,args.origin):c['instrument']
                 for c in captures if c['status']=='CAPTURED'}
        for task in as_completed(pending):
            try:
                row=task.result();record['results'].append(row);print('FORWARD_RESEARCH_OBSERVED',json.dumps(row),flush=True)
            except Exception as exc:
                row={'instrument':pending[task],'status':'ABSTAIN','error':type(exc).__name__+': '+str(exc)}
                record['failures'].append(row);print('FORWARD_RESEARCH_ABSTAIN',json.dumps(row),flush=True)
            write_json(args.output/'progress.json',record)
    record['failures'] += [c for c in captures if c['status']!='CAPTURED']
    record.update(status='COMPLETE' if not record['failures'] else 'COMPLETE_WITH_ABSTENTIONS',
                  finished_at=datetime.now(timezone.utc).isoformat(),forecast_values=6*len(record['results']))
    write_json(args.output/'run_receipt.json',record)
    print('FORWARD_OBSERVATION_COMPLETE',len(record['results']),len(record['failures']),record['forecast_values'],flush=True)
    return 0


if __name__=='__main__':sys.exit(main())
