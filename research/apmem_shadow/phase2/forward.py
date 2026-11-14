"""One offline, immutable forward research record from actually captured inputs.

No collection daemon, scheduler, position output, or market-action authority.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import re
import numpy as np
import pandas as pd
from .__main__ import save,digest
from .targets import prepare_prices,HORIZONS
from .forecasts import forecast_all
from .moments import replay_moments,fixed_power_forecasts
from .calibration import variance_upper


def validate_capture(prices,receipt,instrument,origin,now,actual_sha):
    if now.tzinfo is None:raise ValueError('timezone-aware computation clock required')
    date=pd.Timestamp(origin)
    if str(date.date())!=origin or date.tzinfo is not None:raise ValueError('invalid origin date')
    if prices.index[-1]!=date:raise ValueError('source does not end at the frozen origin')
    if receipt.get('instrument')!=instrument or receipt.get('sha256')!=actual_sha:
        raise ValueError('capture identity/digest mismatch')
    captured=datetime.fromisoformat(receipt['captured_at'].replace('Z','+00:00'))
    if captured.tzinfo is None or captured>now:raise ValueError('invalid capture clock')
    close=datetime(date.year,date.month,date.day,16,0,tzinfo=ZoneInfo('America/New_York'))
    if captured<close:raise ValueError('forming session cannot be a completed-origin observation')
    if now<close:raise ValueError('forecast origin session is not complete')
    if (now-captured).total_seconds()>3600:raise ValueError('source capture is no longer fresh for this first record')
    if receipt.get('historical_first_availability') is not None:
        raise ValueError('this route does not certify past vendor availability')
    return captured


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prices-root',type=Path,required=True)
    parser.add_argument('--capture-receipt',type=Path,required=True)
    parser.add_argument('--origin',required=True)
    parser.add_argument('--code-commit',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',args.code_commit):raise SystemExit('exact source commit required')
    if args.output.exists():raise SystemExit('existing forward observation must not be replaced')
    receipts=json.loads(args.capture_receipt.read_text())
    if set(receipts)!=set(('QQQ','SPY','IWM')):raise ValueError('exact frozen instrument roster required')
    args.output.mkdir(parents=True)
    started=datetime.now(timezone.utc).isoformat();outputs={}
    for sym in ('QQQ','SPY','IWM'):
        source=args.prices_root/(sym+'_yahoo_raw.parquet');raw=pd.read_parquet(source)
        now=datetime.now(timezone.utc);sha=digest(source)
        validate_capture(raw,receipts[sym],sym,args.origin,now,sha)
        p=prepare_prices(raw);pred,logs=forecast_all(p,instrument=sym)
        moment,lower,upper,diag=replay_moments(p.variance.to_numpy(),p.return_log.to_numpy(),logs['apmem'])
        linear,linear_logs,linear_diag=fixed_power_forecasts(p.variance.to_numpy(),p.return_log.to_numpy())
        roster={'ewma94':pred['ewma94'],'apmem_moment':moment,'har_extended':pred['har_extended'],
                'equal_moment':(moment+pred['ewma94']+pred['har_extended'])/3,'mem_delta1':linear}
        computed=datetime.now(timezone.utc).isoformat()
        record={'instrument':sym,'economic_origin':args.origin,'captured_at':receipts[sym]['captured_at'],
                'computed_at':computed,'source_sha256':sha,'prepared_sha256':None,
                'source_rows':len(raw),'source_vintage':'captured_current_snapshot',
                'historical_first_availability':None,'horizons_next_trading_observations':list(HORIZONS),
                'target':'mean_future_overnight_plus_parkinson_daily_variance',
                'secondary_target':'mean_future_squared_total_close_return',
                'annualization_sessions':252,'models':{},
                'parameter_fit_cutoffs':{'apmem':str(p.index[logs['apmem'][-1]['train_end']].date()),
                    'mem_delta1':str(p.index[linear_logs[-1]['train_end']].date()),
                    **{f'har_h{h}':str(p.index[[x for x in logs['har_extended'] if x['horizon']==h][-1]['latest_label_endpoint']].date()) for h in HORIZONS}},
                'filtered_state_origin':args.origin,
                'options_extension_status':'UNAVAILABLE_NO_FRESH_SAME_ORIGIN_OPTIONS_CAPTURE',
                'matured_forward_outcomes':0,'live_trading_or_ranking_authority':False,
                'method_notes':['Fractional APMEM means use a deterministic two-moment approximation.',
                                'Conditional-mean numerical bounds are not market prediction intervals.',
                                'Delta=1 model has exact finite-horizon empirical conditional means, not guaranteed market accuracy.']}
        for name,a in roster.items():
            f=a[-1]
            valid=bool(np.isfinite(f).all() and (f>0).all())
            record['models'][name]={'status':'RESEARCH_FORECAST' if valid else 'UNAVAILABLE',
                'daily_variance':f.tolist() if valid else None,
                'annualized_volatility_percent':(np.sqrt(252*f)*100).tolist() if valid else None,
                'empirical_upper90_variance':[variance_upper(p.variance.to_numpy(),a[:,j],h)[-1] for j,h in enumerate(HORIZONS)] if valid else None,
                'may_rank':False,'may_size':False,'may_trade':False}
        record['apmem_conditional_mean_numerical_bounds']={'lower':lower[-1].tolist(),'upper':upper[-1].tolist(),
                'relative_width':((upper[-1]-lower[-1])/moment[-1]).tolist(),
                'is_future_market_outcome_interval':False}
        record['apmem_last_transition_diagnostic']=diag['fit_diagnostics'][-1]
        record['mem_delta1_last_transition_diagnostic']=linear_diag['fit_diagnostics'][-1]
        p.to_parquet(args.output/(sym+'_prepared.parquet'))
        record['prepared_sha256']=digest(args.output/(sym+'_prepared.parquet'))
        save(args.output/(sym+'_fit_log.json'),{'original':logs,'fixed_power':linear_logs,'moments':diag})
        outputs[sym]=record
        print('FORWARD_RESEARCH_RECORD_COMPUTED',sym,args.origin,computed,flush=True)
    save(args.output/'forward_observation.json',{'schema':'mastermind.volatility_forward_research.v1',
        'started_at':started,'completed_at':datetime.now(timezone.utc).isoformat(),'source_commit':args.code_commit,
        'source_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},
        'capture_receipt_sha256':digest(args.capture_receipt),'instruments':outputs,
        'status':'COMPUTED_AWAITING_PUBLICATION_TIME_VERIFICATION','matured_forward_outcomes':0,
        'background_collector_or_grader_installed':False,'may_trade':False})


if __name__=='__main__':main()
