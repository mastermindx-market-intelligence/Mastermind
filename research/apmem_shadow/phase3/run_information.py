"""No-refit information attribution and exact-date retention placebos."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from .information import likelihood_decomposition,exact_date_retention
from .arms import data_for_policy
from .portfolio import Policy,simulate
from .run_portfolios import initialize,_STATE
from .run_risk import write_json


def placebo(kind,seed):
    policy=Policy('union' if kind=='rs' else 'union_model_common')
    parent=data_for_policy(_STATE['events'],_STATE['predictions'],policy)
    parent=parent[parent.family.eq('union')].copy()
    if kind=='rs':kept=set(parent.loc[parent.relative_momentum>0,'event_id'])
    else:
        available=data_for_policy(_STATE['events'],_STATE['predictions'],Policy('union_risk_ev',selection='ev_positive'))
        kept=set(available.loc[available.expected_net_payoff>0,'event_id'])
    selected,receipt=exact_date_retention(parent,kept,seed)
    result=simulate(_STATE['market'],selected,Policy('placebo_'+kind))
    return {**result['metrics'],**receipt,'selection_kind':kind,'descriptive_placebo_not_confirmatory':True}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-commit',required=True);args=p.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=False)
    record={'started_at':datetime.now(timezone.utc).isoformat(),'source_commit':args.source_commit,
            'status':'RUNNING_ATTENDED','new_model_fits':0,'exploratory_after_outcomes':True,'placebos':[],'failures':[]}
    predictions=pd.read_parquet(args.root/'event_results/risk_predictions.parquet')
    d,s=likelihood_decomposition(predictions);d.to_parquet(args.output/'decomposed_predictions.parquet',index=False)
    s.to_csv(args.output/'likelihood_decomposition.csv',index=False)
    with ProcessPoolExecutor(max_workers=4,initializer=initialize,initargs=(str(args.root),str(args.output))) as pool:
        pending={pool.submit(placebo,kind,2026111400+i):(kind,i) for kind in ('rs','risk_ev') for i in range(64)}
        for task in as_completed(pending):
            try:record['placebos'].append(task.result())
            except Exception as exc:record['failures'].append({'job':pending[task],'error':type(exc).__name__+': '+str(exc)})
        write_json(args.output/'progress.json',record)
    results=pd.DataFrame(record['placebos']);results.to_csv(args.output/'exact_date_placebos.csv',index=False)
    original=pd.read_csv(args.root/'portfolio_results/metrics.csv')
    summaries=[]
    for kind,name in [('rs','union_rs'),('risk_ev','union_risk_ev')]:
        baseline=original[(original.scenario=='primary')&(original.policy==name)].iloc[0]
        sub=results[results.selection_kind==kind]
        summaries.append({'selection_kind':kind,'tested_policy':name,'controls':len(sub),
            'tested_cagr':float(baseline.cagr),'control_cagr_median':float(sub.cagr.median()),
            'control_cagr_05_95':sub.cagr.quantile([.05,.95]).tolist(),
            'fraction_controls_cagr_at_least_tested':float((sub.cagr>=baseline.cagr).mean()),
            'tested_sharpe':float(baseline.sharpe),'control_sharpe_median':float(sub.sharpe.median()),
            'exchangeable_events':int(sub.exchangeable_events.iloc[0]),
            'exchangeable_dates':int(sub.exchangeable_dates.iloc[0]),
            'exchangeable_fraction':float(sub.exchangeable_fraction.iloc[0]),
            'not_a_confirmatory_p_value':True})
    write_json(args.output/'retention_summary.json',summaries)
    record.update(status='COMPLETE' if not record['failures'] else 'COMPLETED_WITH_FAILURES',
                  finished_at=datetime.now(timezone.utc).isoformat(),placebo_accounts=len(results))
    write_json(args.output/'run_receipt.json',record)
    print('INFORMATION_DECOMPOSITION',s.to_json(orient='records'),flush=True)
    print('EXACT_DATE_RETENTION',json.dumps(summaries),flush=True)
    return int(bool(record['failures']))


if __name__=='__main__':sys.exit(main())
