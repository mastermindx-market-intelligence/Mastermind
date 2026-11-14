"""One attended, pre-2020 risk-axis diagnostic using existing read-only stores."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from .core import ContractError, calendar_index
from .risk_axis import CUTOFF, MODELS, HORIZONS, holm, paired_block_summary, walk_forward

INSTRUMENTS = ('QQQ','SPY','IWM','XLB','XLE','XLI','XLK','XLP','XLU','XLV','XLY')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str)+'\n')


def _load(path: Path, columns: list[str], index_column: str) -> pd.DataFrame:
    # Filter in the parquet reader, before any target or statistical operation.
    import pyarrow.parquet as pq
    metadata=pq.ParquetFile(path).schema_arrow.metadata or {}
    stored=json.loads(metadata.get(b'pandas',b'{}')).get('index_columns',[])
    if (len(stored)!=1 or not isinstance(stored[0],str)
            or stored[0].casefold()!=index_column.casefold()):
        raise ContractError('declared economic date index absent or ambiguous')
    frame = pd.read_parquet(path, columns=columns, filters=[(stored[0],'<=',CUTOFF)])
    calendar_index(frame.index)
    if frame.index[-1] > CUTOFF:
        raise ContractError('reader crossed the sealed evaluation boundary')
    return frame


def main(argv=None) -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--etf-root',type=Path,required=True)
    ap.add_argument('--macro-data-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--source-commit',required=True)
    ap.add_argument('--reuse-from',type=Path)
    args=ap.parse_args(argv)
    if len(args.source_commit)!=40 or any(x not in '0123456789abcdef' for x in args.source_commit):
        ap.error('immutable source commit required')
    args.output.mkdir(parents=True,exist_ok=False)
    receipt={'started_at':datetime.now(timezone.utc).isoformat(),'status':'RUNNING_ATTENDED',
             'source_commit':args.source_commit,'cutoff':str(CUTOFF.date()),'prospective':False,
             'availability_basis':'one_session_assumption_not_original_publication_proof',
             'inputs':{},'failures':[],'may_rank':False,'may_size':False,'may_trade':False}
    save(args.output/'run_started.json',receipt)
    def load_bound(key,path,columns,index_column):
        frame=_load(path,columns,index_column)
        receipt['inputs'][key]={'path':str(path),'container_sha256':sha(path),
            'filtered_sha256':hashlib.sha256(frame.to_csv(float_format='%.17g').encode()).hexdigest(),
            'first_session':str(frame.index[0].date()),'last_session':str(frame.index[-1].date()),
            'rows':len(frame),'columns':columns}
        return frame
    try:
        vix=load_bound('VIX',args.macro_data_root/'yahoo/_VIX.parquet',['close'],'Date').close
        vvix=load_bound('VVIX',args.macro_data_root/'cboe/vvix.parquet',['vvix'],'date').vvix
    except Exception as exc:
        receipt.update(status='INPUT_UNAVAILABLE',failures=[{'input':'indices','error':type(exc).__name__+': '+str(exc)}])
        save(args.output/'run_receipt.json',receipt)
        return 2
    all_rows=[];fit_logs=[]
    reuse_receipt=None;reuse_data=None;reuse_fits=[]
    if args.reuse_from is not None:
        reuse_receipt=json.loads((args.reuse_from/'run_receipt.json').read_text())
        for name in ('core.py','risk_axis.py'):
            if reuse_receipt.get('source_files',{}).get(name)!=sha(Path(__file__).parent/name):
                raise ContractError('reuse model source changed')
        if reuse_receipt.get('model_roster')!=list(MODELS) or reuse_receipt.get('cutoff')!=str(CUTOFF.date()):
            raise ContractError('reuse experiment contract changed')
        for key in ('VIX','VVIX'):
            if reuse_receipt['inputs'][key]['filtered_sha256']!=receipt['inputs'][key]['filtered_sha256']:
                raise ContractError('reuse index input changed')
        reuse_data=pd.read_parquet(args.reuse_from/'private_predictions.parquet')
        if (pd.to_datetime(reuse_data.label_end)>CUTOFF).any():
            raise ContractError('reused outcomes cross the fixed boundary')
        reuse_fits=json.loads((args.reuse_from/'fit_log.json').read_text())
        receipt['reused_from']=str(args.reuse_from)
        receipt['reused_instruments']=[]
    prior=args.etf_root/'run_receipt.json'
    if not prior.is_file():
        raise ContractError('retained ETF lineage receipt absent')
    transfer=json.loads(prior.read_text())
    parents={r['instrument']:r for r in transfer.get('results',[])}
    for ticker in INSTRUMENTS:
        try:
            if ticker not in parents or not parents[ticker].get('prepared_input_sha256'):
                raise ContractError('original prepared-target lineage absent')
            frame=load_bound(ticker,args.etf_root/f'{ticker}_prices.parquet',['variance','return_log'],'date')
            receipt['inputs'][ticker]['original_prepared_sha256']=parents[ticker]['prepared_input_sha256']
            if reuse_receipt and ticker in reuse_receipt.get('instruments_completed',[]):
                if reuse_receipt['inputs'][ticker]['filtered_sha256']!=receipt['inputs'][ticker]['filtered_sha256']:
                    raise ContractError('reused ETF target input changed')
                rows=reuse_data.loc[reuse_data.instrument==ticker].copy()
                fits=[x for x in reuse_fits if x['instrument']==ticker]
                receipt['reused_instruments'].append(ticker)
            else:
                rows,fits=walk_forward(frame,vix,vvix)
            if rows.empty:raise ContractError('no qualified common predictions')
            rows['instrument']=ticker
            all_rows.append(rows)
            fit_logs.extend({'instrument':ticker,**x} for x in fits)
            print('RISK_AXIS_COMPLETE',ticker,'paired_origins',rows[['origin','horizon']].drop_duplicates().shape[0],flush=True)
        except Exception as exc:
            receipt['failures'].append({'instrument':ticker,'error':type(exc).__name__+': '+str(exc)})
        save(args.output/'progress.json',receipt)
    if not all_rows:
        receipt['status']='NO_QUALIFIED_RESULTS';save(args.output/'run_receipt.json',receipt);return 2
    data=pd.concat(all_rows,ignore_index=True)
    # Detailed predictions stay in the private numerical root, not public evidence.
    data.to_parquet(args.output/'private_predictions.parquet',index=False)
    scores=data.groupby(['instrument','horizon','target','model']).qlike.agg(['count','mean']).reset_index()
    scores.to_csv(args.output/'forecast_scores.csv',index=False)
    all_tests=[]
    for h in HORIZONS:
        for target in ('variance','return_square'):
            block=data[(data.horizon==h)&(data.target==target)]
            pivot=block.pivot(index=['origin','instrument'],columns='model',values='qlike').dropna()
            for candidate,base in zip(MODELS[1:],MODELS[:-1]):
                delta=(pivot[candidate]-pivot[base]).groupby('origin').mean().sort_index()
                rec={'candidate':candidate,'baseline':base,'horizon':h,'target':target,
                     'n_instruments':int(pivot.index.get_level_values('instrument').nunique()),
                     'n_asset_origins':len(pivot),'mean_candidate_loss':float(pivot[candidate].mean()),
                     'mean_baseline_loss':float(pivot[base].mean()),'computed':False}
                try:rec.update(**paired_block_summary(delta.to_numpy()),computed=True)
                except ContractError as exc:rec['unavailable_reason']=str(exc)
                all_tests.append(rec)
    adjusted=holm([x.get('centered_bootstrap_p',1.) for x in all_tests])
    for rec,pvalue in zip(all_tests,adjusted):rec['holm12_p']=pvalue
    save(args.output/'paired_tests.json',all_tests)
    save(args.output/'fit_log.json',fit_logs)
    receipt.update(status='COMPLETE' if not receipt['failures'] else 'COMPLETE_WITH_GAPS',
                   finished_at=datetime.now(timezone.utc).isoformat(),
                   instruments_completed=sorted(data.instrument.unique().tolist()),
                   prediction_rows=len(data),fit_attempts=len(fit_logs),
                   successful_fits=sum(x['status']=='FITTED' for x in fit_logs),
                   declared_contrasts=len(all_tests),
                   model_roster=list(MODELS),source_files={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')})
    save(args.output/'run_receipt.json',receipt)
    print('RISK_AXIS_FINISHED',receipt['status'],receipt['declared_contrasts'],flush=True)
    return 0


if __name__=='__main__':sys.exit(main())
