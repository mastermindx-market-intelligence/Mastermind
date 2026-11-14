"""No-retuning diagnostics of all fixed phase-neutral arms and their delay cost."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import experiment as ex
from analyze import block_mean_interval,holm
from robustness import recovered_dot,extended_context,static_match
from phase_neutral import combine


def main(root):
    out=root/'phase_neutral_audit_results'
    if out.exists():raise ValueError('Original phase-neutral audit exists')
    out.mkdir();tests=[];matches=[];timing=[];raw=[]
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text())
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,manifest);ctx=ex.context(p,t,v);xt=extended_context(p,t,ctx)
        phases=[recovered_dot(root,p.index,segment,i) for i in (0,1,2)];signals=combine(phases)
        rep=pd.DataFrame(np.repeat(ctx['repair'].to_numpy()[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
        pressure=pd.DataFrame(np.repeat(xt['lower_pressure'].to_numpy()[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
        contexts={'unfiltered':pd.DataFrame(True,index=p.index,columns=ex.SECTORS),'repair':rep,'repair_pressure':rep&pressure}
        eras={'2007_2019' if segment=='pre' else 'post_reset':ex.eval_mask(p.index,segment)}
        if segment=='pre':eras['2001_2006']=np.asarray((p.index>='2001-01-01')&(p.index<='2006-12-31'))
        for era,valid in eras.items():
            for detector in ('any_phase','two_phase','all_phase'):
                for condition,g in contexts.items():
                    selected=signals[detector]&g
                    for ticker in ex.SECTORS:
                        for i in np.flatnonzero(selected[ticker].to_numpy()&valid):
                            if i+1>=len(p):continue
                            observed=[]
                            for phase in phases:
                                positions=np.flatnonzero(phase[ticker].iloc[max(0,i-5):i+1].to_numpy())
                                if len(positions):observed.append(max(0,i-5)+int(positions[-1]))
                            first=i if detector=='any_phase' else min(observed)
                            raw.append({'era':era,'detector':detector,'context':condition,'ticker':ticker,
                              'confirmation_session':str(p.index[i].date()),'earliest_recent_phase':str(p.index[first].date()),
                              'confirmation_delay_sessions':i-first,
                              'entry_price_change':float(p[ticker].iloc[i+1]/p[ticker].iloc[first+1]-1),
                              'matched_confirmed_population_only':True})
                    for h in (21,63):
                        prefix=root/'phase_neutral_results/private'/f'{era}_h{h}_c5_'
                        candidate=pd.read_csv(str(prefix)+detector+'_'+condition+'.csv',index_col=0,parse_dates=True)
                        benchmark=pd.read_csv(str(prefix)+'equal_phase_portfolios_'+condition+'.csv',index_col=0,parse_dates=True)
                        if not candidate.index.equals(benchmark.index):raise ValueError('Mismatched phase comparison')
                        delta=candidate.equity.pct_change().iloc[1:]-benchmark.equity.pct_change().iloc[1:]
                        mean,ci,pv=block_mean_interval(delta.to_numpy())
                        tests.append({'era':era,'horizon':h,'detector':detector,'context':condition,'mean_daily_difference':mean,
                          'annualized_mean_difference':mean*252,'pointwise_lower':ci[0]*252,'pointwise_upper':ci[1]*252,'p_raw':pv})
                        fraction,m,_,_=static_match(benchmark,float(candidate.gross.mean()))
                        matches.append({'era':era,'horizon':h,'detector':detector,'context':condition,
                          'candidate_mean_exposure':float(candidate.gross.mean()),'benchmark_mean_exposure':float(benchmark.gross.mean()),
                          'matching_feasible_without_leverage':float(candidate.gross.mean())<=float(benchmark.gross.mean()),
                          'hindsight_fraction':fraction,'matched_cagr':m['cagr'],'matched_sharpe':m['sharpe'],
                          'matched_maximum_drawdown':m['maximum_drawdown'],'diagnostic_not_live_rule':True})
    hp=holm([x['p_raw'] for x in tests])
    for x,pv in zip(tests,hp):x['p_holm_all54']=float(pv)
    pd.DataFrame(tests).to_csv(out/'paired_mean_return_tests.csv',index=False)
    pd.DataFrame(matches).to_csv(out/'exposure_controls.csv',index=False)
    z=pd.DataFrame(raw)
    z.groupby(['era','detector','context']).agg(confirmations=('ticker','size'),dates=('confirmation_session','nunique'),
       median_delay=('confirmation_delay_sessions','median'),mean_delay=('confirmation_delay_sessions','mean'),
       median_entry_price_change=('entry_price_change','median'),mean_entry_price_change=('entry_price_change','mean')).to_csv(out/'confirmation_cost.csv')
    ex.write_json(out/'RUN_RECEIPT.json',{'status':'COMPLETE','paired_tests':len(tests),'holm_rejections':int(np.sum(hp<.05)),
      'conditional_confirmation_measure_not_all_dot_coverage':True,'outcome_guided_diagnostic':True,'may_trade':False,
      'source_sha256':hashlib.sha256((root/'phase_neutral_audit.py').read_bytes()).hexdigest()})
    print('PHASE_NEUTRAL_AUDIT_COMPLETE',len(tests),'corrected_rejections',int(np.sum(hp<.05)),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();main(a.root)
