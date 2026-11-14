"""Run disclosed post-primary diagnostics from preserved phase-two results only."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from .__main__ import save,digest
from .targets import HORIZONS,future_mean
from .forecasts import qlike
from .evaluation import MAIN_MODELS,block_mean_interval,holm
from .followup import (options_ablation,scale_calibrate,execution_calibration_study,
                      exact_static_and_decomposition,disagreement_diagnostic)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.study_root;output=args.output
    if output.exists():raise SystemExit('output exists; do not replay an original run')
    paths={}
    for directory in ('results','sector_results'):
        for path in (root/directory).glob('*/summary.json'):
            sym=path.parent.name
            if sym in paths:raise ValueError('duplicate instrument result')
            paths[sym]=path.parent
    if len(paths)!=11:raise ValueError('the declared complete family requires eleven admitted assets')
    output.mkdir(parents=True)
    started=datetime.now(timezone.utc).isoformat()
    paired,scaled,exposure,execution,disagreement,option_scores,option_pairs=[],[],[],[],[],[],[]
    source_inputs={}
    for sym,path in sorted(paths.items()):
        p=pd.read_parquet(path/'prepared_prices.parquet');pred=dict(np.load(path/'predictions.npz'))
        returns=dict(np.load(path/'utility_paths.npz'))
        source_inputs[sym]={name:digest(path/name) for name in ('prepared_prices.parquet','predictions.npz','utility_paths.npz','summary.json')}
        for j,h in enumerate(HORIZONS):
            calibrated={m:scale_calibrate(p.variance.to_numpy(),pred[m][:,j],h) for m in MAIN_MODELS}
            for target in ('variance','return_square'):
                y=future_mean(p[target],h);common=np.isfinite(y)&(p.index>='2015-01-01')
                for m in MAIN_MODELS:common &= np.isfinite(pred[m][:,j])&(pred[m][:,j]>0)
                ids=np.where(common)[0]
                for baseline in ('incumbent','ewma94','apmem','har_extended'):
                    diff=qlike(y[ids],pred['equal_blend'][ids,j])-qlike(y[ids],pred[baseline][ids,j])
                    paired.append({'instrument':sym,'target':target,'horizon':h,'candidate':'equal_blend',
                                   'baseline':baseline,**block_mean_interval(diff,resamples=20000),
                                   'common_row_gaps':int(np.sum(np.diff(ids)>1))})
                for a in calibrated.values():common &= np.isfinite(a)&(a>0)
                ids=np.where(common)[0]
                for m in MAIN_MODELS:
                    scaled.append({'instrument':sym,'target':target,'horizon':h,'model':m,'n':len(ids),
                                   'original_qlike':float(qlike(y[ids],pred[m][ids,j]).mean()),
                                   'scale_calibrated_qlike':float(qlike(y[ids],calibrated[m][ids]).mean()),
                                   'exploratory_post_primary':True})
        exposure.extend({'instrument':sym,**x} for x in exact_static_and_decomposition(p,pred,returns))
        execution.extend({'instrument':sym,**x} for x in execution_calibration_study(p,pred))
        disagreement.extend({'instrument':sym,**x} for x in disagreement_diagnostic(p,pred))
        if sym in ('QQQ','SPY','IWM'):
            options_path=root/'data'/(sym+'_gex.parquet')
            options=pd.read_parquet(options_path);options=options.loc[options.index<='2026-11-12']
            new,logs,rows,pairs=options_ablation(p,options,sym,pred)
            save(output/(sym+'_options_fits.json'),logs)
            np.savez_compressed(output/(sym+'_options_predictions.npz'),**new)
            option_scores.extend(rows);option_pairs.extend(pairs)
            source_inputs[sym]['options_sha256']=digest(options_path)
        print('FOLLOWUP_COMPLETE',sym,flush=True)
    for rec,adj in zip(paired,holm(np.array([x['centered_bootstrap_two_sided_p'] for x in paired]))):
        rec['holm_adjusted_p_full_264_family']=float(adj)
    save(output/'paired_tests_20000.json',paired)
    save(output/'exact_static_and_attribution.json',exposure)
    save(output/'options_pairs.json',option_pairs)
    for name,rows in [('scale_control',scaled),('execution_calibration',execution),
                      ('disagreement',disagreement),('options_ablation',option_scores)]:
        pd.DataFrame(rows).to_csv(output/(name+'.csv'),index=False)
    save(output/'run_receipt.json',{'schema':'mastermind.volatility_followup.v1','started_at':started,
        'ended_at':datetime.now(timezone.utc).isoformat(),'source_inputs':source_inputs,
        'source_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},
        'paired_tests':len(paired),'options_comparisons':len(option_scores),
        'exploratory_after_primary':True,'prospective':False,'may_trade':False})


if __name__=='__main__':main()
