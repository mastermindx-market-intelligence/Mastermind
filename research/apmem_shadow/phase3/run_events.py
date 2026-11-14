"""Build the registered event panel and chronological conditional-risk estimates.

Consumes exact, completed native/risk runs and private price inputs. No network,
source mutation or live trading action. Existing output directories are refused.
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
from .events import build_events
from .learning import walk_forward,calibration_table
from .risk import matched_forecast_losses
from .run_risk import write_json


def build_one(root: str, output: str, ticker: str):
    if hasattr(os,'nice'):os.nice(10)
    r=Path(root);out=Path(output)
    p=pd.read_parquet(r/'private/qualified'/f'{ticker}.parquet')
    n=pd.read_parquet(r/'native_results'/f'{ticker}.parquet')
    f=pd.read_parquet(r/'risk_results'/f'{ticker}.parquet')
    m=pd.read_parquet(r/'private/membership.parquet')
    m=m[m.ticker.str.upper().eq(ticker)]
    b=pd.read_parquet(out/'benchmark.parquet')
    events,paths,receipt=build_events(ticker,p,n,f,m,b)
    events.to_parquet(out/f'{ticker}_events.parquet',index=False)
    paths.to_parquet(out/f'{ticker}_paths.parquet',index=False)
    receipt['event_rows']=len(events);receipt['path_rows']=len(paths)
    receipt['input_sha256']={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in {
        'prices':r/'private/qualified'/f'{ticker}.parquet',
        'native':r/'native_results'/f'{ticker}.parquet',
        'risk':r/'risk_results'/f'{ticker}.parquet'}.items()}
    return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--benchmark-raw',type=Path,required=True)
    parser.add_argument('--benchmark-receipts',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args(argv)
    if not 1<=args.workers<=4 or len(args.source_commit)!=40:parser.error('invalid bounded source/run settings')
    r=args.root;native_receipt=json.loads((r/'native_run_receipt.json').read_text())
    risk_receipt=json.loads((r/'risk_results/run_receipt.json').read_text())
    if native_receipt['status']!='COMPLETE' or risk_receipt['status']!='COMPLETE':
        raise ValueError('upstream runs have unresolved failures')
    audits=json.loads((r/'data_qualification_v2.json').read_text())
    symbols=[a['instrument'] for a in audits if a['primary'] and a['qualified_v2']]
    args.output.mkdir(parents=True,exist_ok=False)
    raw=args.benchmark_raw.read_bytes();receipts=json.loads(args.benchmark_receipts.read_text())
    receipt=receipts['SPY'] if isinstance(receipts,dict) else next(x for x in receipts if x['instrument']=='SPY')
    prices,quality=parse_capture(raw,receipt,'SPY')
    if not quality['action_basis_qualified']:raise ValueError('benchmark action basis unavailable')
    benchmark=prepare_prices(prices);benchmark.to_parquet(args.output/'benchmark.parquet')
    record={'started_at':datetime.now(timezone.utc).isoformat(),'source_commit':args.source_commit,
            'symbols':symbols,'benchmark_receipt':quality,'results':[],'failures':[],
            'status':'RUNNING_ATTENDED','native_run_sha256':hashlib.sha256((r/'native_run_receipt.json').read_bytes()).hexdigest(),
            'risk_run_sha256':hashlib.sha256((r/'risk_results/run_receipt.json').read_bytes()).hexdigest()}
    write_json(args.output/'run_started.json',record)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(build_one,str(r),str(args.output),t):t for t in symbols}
        for task in as_completed(tasks):
            try:
                item=task.result();record['results'].append(item)
                print('EVENTS_DONE',item['instrument'],item['event_rows'],item['path_rows'],flush=True)
            except Exception as exc:
                failure={'instrument':tasks[task],'error':type(exc).__name__+': '+str(exc)}
                record['failures'].append(failure);print('EVENTS_FAILED',json.dumps(failure),flush=True)
            write_json(args.output/'progress.json',record)
    if record['failures']:
        record.update(status='COMPLETED_WITH_FAILURES',finished_at=datetime.now(timezone.utc).isoformat())
        write_json(args.output/'run_receipt.json',record);return 1
    events=pd.concat([pd.read_parquet(args.output/f'{t}_events.parquet') for t in symbols],ignore_index=True)
    paths=pd.concat([pd.read_parquet(args.output/f'{t}_paths.parquet') for t in symbols],ignore_index=True)
    if not events.event_id.is_unique:raise ValueError('duplicate cross-panel event')
    events.to_parquet(args.output/'events.parquet',index=False)
    paths.to_parquet(args.output/'paths.parquet',index=False)
    union=events[events.family.eq('union')].copy()
    calendar=benchmark.index[benchmark.index<=pd.Timestamp('2026-06-02')]
    predicted,fit_receipts,_=walk_forward(union,calendar)
    predicted.to_parquet(args.output/'risk_predictions.parquet',index=False)
    write_json(args.output/'classifier_fits.json',fit_receipts)
    if len(predicted):calibration_table(predicted).to_csv(args.output/'risk_calibration.csv',index=False)
    losses=matched_forecast_losses(union)
    losses.to_parquet(args.output/'forecast_losses.parquet',index=False)
    counts=events.groupby('family').agg(events=('event_id','size'),names=('ticker','nunique'),
        stop_fraction=('class_id',lambda x:float((x==0).mean())),
        target_fraction=('class_id',lambda x:float((x==1).mean())),
        timeout_fraction=('class_id',lambda x:float((x==2).mean())),
        mean_net_return=('net_return','mean'),median_net_return=('net_return','median'),
        common_risk_rows=('common_risk_available','sum')).reset_index()
    counts.to_csv(args.output/'event_summary.csv',index=False)
    if len(predicted):
        predicted.groupby('model').agg(n=('event_id','size'),log_loss=('log_loss','mean'),brier=('brier','mean'),
            clipping_fraction=('feature_clipped','mean')).reset_index().to_csv(args.output/'classifier_summary.csv',index=False)
    record.update(status='COMPLETE',finished_at=datetime.now(timezone.utc).isoformat(),
                  events=len(events),union_events=len(union),paths=len(paths),
                  conditional_prediction_rows=len(predicted),classifier_fit_attempts=len(fit_receipts),
                  selected_forecast_loss_rows=len(losses))
    write_json(args.output/'run_receipt.json',record)
    print('EVENT_RISK_RESEARCH_COMPLETE',json.dumps({k:record[k] for k in ('events','union_events','paths','conditional_prediction_rows','classifier_fit_attempts')}),flush=True)
    print('EVENT_SUMMARY',counts.to_json(orient='records'),flush=True)
    return 0


if __name__=='__main__':sys.exit(main())
