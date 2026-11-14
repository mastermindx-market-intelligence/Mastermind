"""Evaluate the frozen stock-risk models on already captured private inputs.

No provider access or background service. One attended invocation has an exact
output directory and refuses to overwrite an existing run.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
from .risk import forecasts


def jsonable(value):
    if isinstance(value,dict):return {str(k):jsonable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [jsonable(v) for v in value]
    if isinstance(value,np.ndarray):return jsonable(value.tolist())
    if isinstance(value,(np.integer,)):return int(value)
    if isinstance(value,(np.bool_,)):return bool(value)
    if isinstance(value,(float,np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def write_json(path,value):
    Path(path).write_text(json.dumps(jsonable(value),indent=2,allow_nan=False)+'\n')


def evaluate_one(source: str, output: str, ticker: str):
    if hasattr(os,'nice'):os.nice(10)
    started=time.perf_counter()
    path=Path(source)/f'{ticker}.parquet'
    p=pd.read_parquet(path)
    predictions,receipt=forecasts(p)
    destination=Path(output)/f'{ticker}.parquet'
    if destination.exists():raise ValueError('risk result already exists')
    predictions.to_parquet(destination)
    write_json(Path(output)/f'{ticker}_fits.json',receipt)
    return {'instrument':ticker,'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'output_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
            'rows':len(p),'data_end':str(p.index[-1].date()),
            'fits':len(receipt['fits']),'successful_fits':sum(bool(f['success']) for f in receipt['fits']),
            'h5_forecasts':int(predictions.mem_h5.notna().sum()),
            'seconds':round(time.perf_counter()-started,3)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--qualification',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args(argv)
    if not 1<=args.workers<=4 or len(args.source_commit)!=40:
        parser.error('bounded worker count and exact source commit required')
    audits=json.loads(args.qualification.read_text())
    symbols=[a['instrument'] for a in audits if a.get('primary') and a.get('qualified_v2')]
    if len(symbols)!=len(set(symbols)) or not symbols:
        parser.error('invalid qualified instrument list')
    args.output.mkdir(parents=True,exist_ok=False)
    receipt={'started_at':datetime.now(timezone.utc).isoformat(),'source_commit':args.source_commit,
             'qualification_sha256':hashlib.sha256(args.qualification.read_bytes()).hexdigest(),
             'workers':args.workers,'symbols':symbols,'status':'RUNNING_ATTENDED',
             'results':[],'failures':[],'numpy':np.__version__,'pandas':pd.__version__}
    write_json(args.output/'run_started.json',receipt)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(evaluate_one,str(args.input),str(args.output),s):s for s in symbols}
        for task in as_completed(tasks):
            try:
                result=task.result();receipt['results'].append(result)
                print('RISK_MODEL_DONE',json.dumps(result),flush=True)
            except Exception as exc:
                failure={'instrument':tasks[task],'error':type(exc).__name__+': '+str(exc)}
                receipt['failures'].append(failure);print('RISK_MODEL_FAILED',json.dumps(failure),flush=True)
            write_json(args.output/'progress.json',receipt)
    receipt.update(finished_at=datetime.now(timezone.utc).isoformat(),
                   status='COMPLETE' if not receipt['failures'] else 'COMPLETED_WITH_FAILURES')
    write_json(args.output/'run_receipt.json',receipt)
    print('RISK_PANEL_FINISHED',len(receipt['results']),'failures',len(receipt['failures']),flush=True)
    return int(bool(receipt['failures']))


if __name__=='__main__':sys.exit(main())
