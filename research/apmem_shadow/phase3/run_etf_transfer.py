"""Canonical-entry transfer to eleven previously qualified ETFs, without refits."""
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
from .data import prepare_prices,future_mean
from .replay import replay
from .events import build_events
from .risk import matched_forecast_losses
from .portfolio import Market,Policy,simulate
from .run_risk import write_json

SYMBOLS=('QQQ','SPY','IWM','XLB','XLE','XLI','XLK','XLP','XLU','XLV','XLY')


def adapt_inputs(raw: pd.DataFrame,prepared: pd.DataFrame,saved: dict):
    required={'open','high','low','close','volume','distributions','stock_splits'}
    if not {'open','high','low','close','volume','dividends','capital_gains','stock_splits'}.issubset(raw):
        raise ValueError('missing source ETF price/action fields')
    if (raw.stock_splits!=0).any():raise ValueError('source split has not been qualified into constant share units')
    source=raw[['open','high','low','close','volume']].copy()
    source['dividend']=raw.dividends+raw.capital_gains;source['split']=1.
    p=prepare_prices(source)
    if not p.index[1:].equals(prepared.index):raise ValueError('saved forecasts and source dates differ')
    if not np.allclose(p.variance.iloc[1:],prepared.variance,rtol=1e-10,atol=1e-14):
        raise ValueError('independent target differs from saved phase2 input')
    if not np.allclose(p.return_log.iloc[1:],prepared.return_log,rtol=1e-10,atol=1e-14):
        raise ValueError('total-return action basis differs')
    f=pd.DataFrame(index=p.index)
    for model,key in [('mem','mem_delta1'),('ewma','ewma94')]:
        a=np.asarray(saved[key],float)
        if a.shape!=(len(prepared),3):raise ValueError('saved forecast shape mismatch')
        for j,h in enumerate((1,5,20)):f[f'{model}_h{h}']=np.r_[np.nan,a[:,j]]
    for h in (1,5,20):
        f[f'future_variance_h{h}']=future_mean(p.variance,h)
        f[f'future_return_square_h{h}']=future_mean(p.return_log.pow(2),h)
    return p,f


def one(phase2: str,output: str,symbol: str):
    if hasattr(os,'nice'):os.nice(10)
    root=Path(phase2);out=Path(output)
    original=json.loads((root/'moment_repair/run_receipt.json').read_text())
    directory=root/'results'/symbol
    if not directory.exists():directory=root/'sector_results'/symbol
    prepared_path=directory/'prepared_prices.parquet'
    digest=hashlib.sha256(prepared_path.read_bytes()).hexdigest()
    if digest!=original['inputs'][symbol]['prepared_prices_sha256']:raise ValueError('phase2 prepared input hash changed')
    raw_path=root/'qualified_data'/f'{symbol}_yahoo_raw.parquet'
    if not raw_path.exists():raw_path=root/'data'/f'{symbol}_yahoo_raw.parquet'
    saved_path=root/'moment_repair'/f'{symbol}_predictions.npz'
    p,f=adapt_inputs(pd.read_parquet(raw_path),pd.read_parquet(prepared_path),dict(np.load(saved_path,allow_pickle=False)))
    n=replay(symbol,p.signal_close,start='2015-01-01',end='2026-06-02')
    p.to_parquet(out/f'{symbol}_prices.parquet');f.to_parquet(out/f'{symbol}_forecasts.parquet');n.to_parquet(out/f'{symbol}_native.parquet')
    return {'instrument':symbol,'rows':len(p),'native_rows':len(n),'union_onsets':int(n.union_onset.sum()),
            'source_price_sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            'prepared_input_sha256':digest,'reused_forecast_sha256':hashlib.sha256(saved_path.read_bytes()).hexdigest(),
            'new_forecast_fits':0,'constant_share_unit_basis':True,'underlying_phase2_source':str(directory)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase2',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-commit',required=True);parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args(argv)
    if not 1<=args.workers<=4 or len(args.source_commit)!=40:parser.error('invalid bounded run')
    args.output.mkdir(parents=True,exist_ok=False)
    record={'started_at':datetime.now(timezone.utc).isoformat(),'source_commit':args.source_commit,
            'status':'RUNNING_ATTENDED','results':[],'failures':[],'new_forecast_fits':0,
            'exploratory_transfer':True,'same_account_window_as_stocks':True}
    write_json(args.output/'run_started.json',record)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(one,str(args.phase2),str(args.output),s):s for s in SYMBOLS}
        for task in as_completed(tasks):
            try:
                receipt=task.result();record['results'].append(receipt);print('ETF_NATIVE_DONE',receipt['instrument'],flush=True)
            except Exception as exc:
                failure={'instrument':tasks[task],'error':type(exc).__name__+': '+str(exc)}
                record['failures'].append(failure);print('ETF_TRANSFER_FAILED',json.dumps(failure),flush=True)
            write_json(args.output/'progress.json',record)
    if record['failures']:
        record['status']='COMPLETED_WITH_FAILURES';write_json(args.output/'run_receipt.json',record);return 1
    panels={s:pd.read_parquet(args.output/f'{s}_prices.parquet') for s in SYMBOLS};benchmark=panels['SPY']
    all_events=[];all_paths=[]
    for s in SYMBOLS:
        membership=pd.DataFrame({'ticker':[s],'start_date':[panels[s].index[0]],'end_date':[pd.NaT],
                                  'src':['fixed_ETF_research_panel_NOT_SP1500_membership']})
        events,paths,_=build_events(s,panels[s],pd.read_parquet(args.output/f'{s}_native.parquet'),
            pd.read_parquet(args.output/f'{s}_forecasts.parquet'),membership,benchmark)
        all_events.append(events);all_paths.append(paths)
    events=pd.concat(all_events,ignore_index=True);paths=pd.concat(all_paths,ignore_index=True)
    events.to_parquet(args.output/'events.parquet',index=False);paths.to_parquet(args.output/'paths.parquet',index=False)
    losses=matched_forecast_losses(events[events.family=='union'])
    losses.to_parquet(args.output/'forecast_losses.parquet',index=False)
    losses.groupby(['horizon','target','model']).agg(n=('event_id','size'),qlike=('qlike','mean'),mse=('mse','mean')).reset_index().to_csv(args.output/'forecast_summary.csv',index=False)
    market=Market(panels,benchmark.index);e=events[events.common_risk_available].copy();metrics=[]
    policies=[Policy('union',target_vol=.15),Policy('union_ewma',sizing='ewma',target_vol=.15),
        Policy('union_mem',sizing='mem',target_vol=.15),Policy('union_time21',exit_rule='time21',target_vol=.15),
        Policy('union_stop21',exit_rule='stop21',target_vol=.15),Policy('union_trail63',exit_rule='trail63',target_vol=.15),
        Policy('union_trail63_mem',exit_rule='trail63',sizing='mem',target_vol=.15)]
    policies += [Policy(name,family=name,target_vol=.15) for name in ('t1','t2','breakout20','reclaim50','trend63_126')]
    for policy in policies:
        result=simulate(market,e,policy);metrics.append(result['metrics'])
        pd.DataFrame({'date':result['dates'],'return':result['returns'],'equity':result['equity'][1:],
            'opening_exposure':result['opening_exposure'],'closing_exposure':result['exposure'],
            'turnover':result['turnover']}).to_parquet(args.output/(policy.name+'_daily.parquet'),index=False)
        result['trades'].to_parquet(args.output/(policy.name+'_trades.parquet'),index=False)
    pd.DataFrame(metrics).to_csv(args.output/'metrics.csv',index=False)
    record.update(status='COMPLETE',finished_at=datetime.now(timezone.utc).isoformat(),events=len(events),
                  union_events=int(events.family.eq('union').sum()),accounts=len(metrics))
    write_json(args.output/'run_receipt.json',record);print('ETF_TRANSFER_COMPLETE',len(events),len(metrics),flush=True)
    return 0


if __name__=='__main__':sys.exit(main())
