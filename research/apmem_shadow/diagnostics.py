"""Post-evaluation uncertainty and bounded derived-result export, not retuning.

Run from a source checkout: python -m research.apmem_shadow.diagnostics ROOT OUTPUT
ROOT contains the three existing results_{QQQ,SPY,IWM} directories. OUTPUT must
not exist. No network, new forecasts, parameter selection, or trading effects.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .model import qlike
from .evaluation import known_correction_forecast, write_json


def block_mean_interval(values, block: int, *, repetitions: int = 2000,
                        seed: int = 20261113) -> dict:
    """Circular moving-block percentile interval for a paired mean difference.

    Descriptive, pointwise, conditional on this historical sample. This assumes
    resampled blocks are informative for sampling uncertainty; it does not fix
    selection, regime nonstationarity, data revision or prospective validity.
    """
    x = np.asarray(values, float)
    if x.ndim != 1 or not np.isfinite(x).all() or len(x) < 2:
        raise ValueError('need a finite one-dimensional paired loss difference')
    if not isinstance(block, int) or not 1 <= block <= len(x) or repetitions < 100:
        raise ValueError('invalid bootstrap block or repetition count')
    rng = np.random.default_rng(seed)
    nblocks = (len(x)+block-1)//block
    offsets = np.arange(block)
    means = np.empty(repetitions)
    for b in range(repetitions):
        starts = rng.integers(0,len(x),nblocks)
        indices = ((starts[:,None]+offsets) % len(x)).ravel()[:len(x)]
        means[b] = x[indices].mean()
    lower, upper = np.quantile(means,[.025,.975])
    return {'n':len(x),'block_sessions':block,'resamples':repetitions,'seed':seed,
            'mean_apmem_minus_control_loss':float(x.mean()),
            'pointwise_95pct_interval':[float(lower),float(upper)],
            'multiple_comparison_adjusted':False,'prospective_validation':False}


def export(root: Path, output: Path) -> None:
    if output.exists():
        raise ValueError('refusing to overwrite an evidence export')
    output.mkdir(parents=True)
    small = {'evidence_mode':'retrospective_not_prospective','runs':[],
             'uncertainty_note':'Post-evaluation descriptive intervals; no threshold changes; not multiplicity corrected.'}
    strategies = []
    for symbol in ('QQQ','SPY','IWM'):
        folder = root/f'results_{symbol}'
        manifest = json.loads((folder/'source_manifest.json').read_text())
        for tag in ('0_05','0_94'):
            path = folder/f'evaluation_{tag}.json'
            result = json.loads(path.read_text())
            data_path = folder/f'predictions_{tag}.csv'
            expected = manifest['output_sha256'][data_path.name]
            if hashlib.sha256(data_path.read_bytes()).hexdigest() != expected:
                raise ValueError('prediction digest mismatch: '+symbol+' '+tag)
            data = pd.read_csv(data_path)
            lam = result['preprocessing']['retention']
            control = known_correction_forecast(data.high,data.low,data.return_log,lam)
            forecast = data.forecast_next_daily_variance.to_numpy()[:-1]
            target = data.variance_proxy.to_numpy()[1:]
            valid = np.isfinite(forecast) & (forecast>0)
            loss = qlike(target[valid],forecast[valid])-qlike(target[valid],control[:-1][valid])
            record = {'instrument':symbol,'retention':lam,
                      'evaluation_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'source_manifest_sha256':hashlib.sha256((folder/'source_manifest.json').read_bytes()).hexdigest(),
                      'input_sha256':result['input_sha256'],'environment':manifest['environment'],
                      'first_session':result['first_session'],'last_session':result['last_session'],
                      'comparison_start':result['comparison_start'],
                      'paired_eligible_decisions':result['paired_eligible_decisions'],
                      'forecast_metrics':result['forecast_metrics'],
                      'fit_count':len(result['fits']),
                      'fit_successes':sum(f['success'] for f in result['fits']),
                      'fits_with_boundary_parameter':sum(bool(f['boundary_parameters']) for f in result['fits']),
                      'event_summaries':{k:{a:b for a,b in v.items() if a!='event_indices'} for k,v in result['event_summaries'].items()},
                      'loss_intervals':[block_mean_interval(loss,b) for b in (20,63)],
                      'consumer':json.loads((folder/'shadow_context.json').read_text())}
            small['runs'].append(record)
            for strategy in result['strategies']:
                row = {'instrument':symbol,'retention':lam}
                row.update({k:v for k,v in strategy.items() if k not in ('trades','year_returns')})
                row['episodes']=len(strategy['trades'])
                row['censored_episodes']=sum(t['censored'] for t in strategy['trades'])
                strategies.append(row)
    write_json(output/'summary.json',small)
    pd.DataFrame(strategies).to_csv(output/'all_strategies.csv',index=False,float_format='%.12g')
    for name in ('creator_next_open.json','creator_receipt.json','data_receipt.json','source_receipt.json'):
        body=(root/name).read_bytes()
        (output/name).write_bytes(body)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    write_json(output/'SHA256.json',hashes)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();export(a.root,a.output)
    print(json.dumps({'status':'DERIVED_EXPORT_SAVED','output':str(a.output)}))


if __name__=='__main__':main()
