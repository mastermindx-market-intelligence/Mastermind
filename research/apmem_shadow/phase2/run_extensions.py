"""Reproduce frozen utility, earlier-crisis, and numerical falsification checks."""
from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
from .__main__ import save,digest
from .targets import prepare_prices
from .forecasts import forecast_all
from .evaluation import ERAS
from .extensions import (common_execution_end,window_utility,window_forecast_scores,
                         window_tail_scores,numerical_precision)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.study_root;out=args.output
    if out.exists():raise SystemExit('output exists; inspect the original run')
    out.mkdir(parents=True);started=datetime.now(timezone.utc).isoformat()
    utility,forecast,tails,numerical=[],[],[],[];inputs={}
    names=('ewma94','apmem','equal_blend','har_iv','apmem_iv_half')
    for sym in ('QQQ','SPY','IWM'):
        directory=root/'results'/sym
        p=pd.read_parquet(directory/'prepared_prices.parquet')
        original=dict(np.load(directory/'predictions.npz'))
        candidate_path=root/'followup'/(sym+'_options_predictions.npz')
        pred=dict(np.load(candidate_path));pred['ewma94']=original['ewma94']
        end,common=common_execution_end(p,pred,names)
        utility.extend({'instrument':sym,**x} for x in window_utility(p,pred,'2021-01-01',names))
        forecast.extend({'instrument':sym,**x} for x in window_forecast_scores(p,pred,'2015-01-01','2026-11-12',ERAS))
        tails.extend({'instrument':sym,**x} for x in window_tail_scores(p,pred,'2021-01-01',str(p.index[end-2].date()),names))
        inputs[sym]={'prepared_prices_sha256':digest(directory/'prepared_prices.parquet'),
                     'candidate_predictions_sha256':digest(candidate_path),
                     'last_common_execution_open':str(p.index[end].date())}
        print('CANDIDATE_EXTENSION_COMPLETE',sym,str(p.index[end].date()),flush=True)
    for name,rows in (('candidate_utility',utility),('candidate_forecasts',forecast),('candidate_tails',tails)):
        pd.DataFrame(rows).to_csv(out/(name+'.csv'),index=False)
    for parent in ('results','sector_results'):
        for path in sorted((root/parent).glob('*/summary.json')):
            p=pd.read_parquet(path.parent/'prepared_prices.parquet')
            predictions=np.load(path.parent/'predictions.npz')['apmem']
            records=json.loads((path.parent/'fit_log.json').read_text())['apmem']
            numerical.extend({'instrument':path.parent.name,**x} for x in numerical_precision(p,records,predictions))
    pd.DataFrame(numerical).to_csv(out/'numerical_precision.csv',index=False)
    print('NUMERICAL_RECONSTRUCTION_VERIFIED',len(numerical),'origin-horizon checks',flush=True)
    source=root/'early_stress_data/SPY_yahoo_raw.parquet'
    raw=pd.read_parquet(source);p=prepare_prices(raw)
    pred,logs=forecast_all(p,instrument='SPY')
    eras={'all':('1998-01-01','2009-12-31'),'1998_2002':('1998-01-01','2002-12-31'),
          '2003_2006':('2003-01-01','2006-12-31'),'2007_2009':('2007-01-01','2009-12-31')}
    fs=window_forecast_scores(p,pred,'1998-01-01','2009-12-31',eras)
    names=('incumbent','ewma94','apmem','har_extended','equal_blend','adaptive_blend')
    us=window_utility(p,pred,'1998-01-01',names,end='2009-12-31')
    ts=window_tail_scores(p,pred,'1998-01-01',str(p.index[-3].date()),names)
    save(out/'early_SPY_fit_log.json',logs)
    for name,rows in (('early_SPY_forecasts',fs),('early_SPY_utility',us),('early_SPY_tails',ts)):
        pd.DataFrame(rows).to_csv(out/(name+'.csv'),index=False)
    np.savez_compressed(out/'early_SPY_predictions.npz',**pred)
    p.to_parquet(out/'early_SPY_prepared_prices.parquet')
    print('EARLIER_REGIME_STRESS_COMPLETE','SPY',len(raw),len(us),'utility scenarios',flush=True)
    save(out/'run_receipt.json',{'schema':'mastermind.volatility_extensions.v1','started_at':started,
        'ended_at':datetime.now(timezone.utc).isoformat(),'candidate_inputs':inputs,
        'early_stress_source_sha256':digest(source),'source_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},
        'candidate_utility_scenarios':len(utility),'early_stress_utility_scenarios':len(us),
        'numerical_origin_horizon_checks':len(numerical),
        'earlier_regime_fit_summary':{k:{'fits':len(v),'successful':sum(x['success'] for x in v)}
            for k,v in logs.items() if k in ('apmem','har','har_extended')},
        'exploratory_after_primary':True,'prospective':False,'may_trade':False})


if __name__=='__main__':main()
