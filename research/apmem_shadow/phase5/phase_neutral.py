"""Calendar-phase-neutral momentum challengers; never relabels native G0.

Three native phase observations are correlated representations of the same prices,
not independent votes or probabilities. Every confirmation enters at its own known
session and fills no earlier than the following close.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import experiment as ex
from robustness import recovered_dot,extended_context


def combine(phases):
    if len(phases)!=3:raise ValueError('Exactly three fixed native phases required')
    first=phases[0]
    if any(not f.index.equals(first.index) or not f.columns.equals(first.columns) for f in phases):
        raise ValueError('Different native observation calendars')
    if any(f.isna().to_numpy().any() or not all(str(x)=='bool' for x in f.dtypes) for f in phases):
        raise ValueError('Native event states must be observed booleans')
    seen=[f.rolling(6,min_periods=1).max().eq(1) for f in phases]
    count=sum(x.astype(int) for x in seen)
    any_now=phases[0]|phases[1]|phases[2]
    return {'any_phase':ex.onset(any_now),
            'two_phase':ex.onset(count.ge(2)),
            'all_phase':ex.onset(count.eq(3))}


def mean_accounts(curves):
    if len(curves)!=3 or any(not x.index.equals(curves[0].index) for x in curves):
        raise ValueError('Phase-account calendars differ')
    e=np.column_stack([x.equity.to_numpy() for x in curves])
    g=np.column_stack([x.gross.to_numpy() for x in curves])
    equity=e.mean(axis=1);gross=(e*g).mean(axis=1)/equity
    return ex.metrics(equity,gross,[]),pd.DataFrame({'equity':equity,'gross':gross},index=curves[0].index)


def main(root):
    out=root/'phase_neutral_results'
    if out.exists():raise ValueError('Original phase-neutral output exists')
    out.mkdir();(out/'private').mkdir()
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text());accounts=[];counts=[];parity=[]
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,manifest);ctx=ex.context(p,t,v);xt=extended_context(p,t,ctx)
        phases=[recovered_dot(root,p.index,segment,i) for i in (0,1,2)]
        combined=combine(phases);rep=pd.DataFrame(np.repeat(ctx['repair'].to_numpy()[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
        pressure=pd.DataFrame(np.repeat(xt['lower_pressure'].to_numpy()[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
        contexts={'unfiltered':pd.DataFrame(True,index=p.index,columns=ex.SECTORS),
                  'repair':rep,'repair_pressure':rep&pressure}
        eras={'2007_2019' if segment=='pre' else 'post_reset':ex.eval_mask(p.index,segment)}
        if segment=='pre':eras['2001_2006']=np.asarray((p.index>='2001-01-01')&(p.index<='2006-12-31'))
        for era,valid in eras.items():
            for detector,s in combined.items():
                for condition,g in contexts.items():
                    selected=s&g;eligible=np.asarray(valid)[:,None]
                    counts.append({'era':era,'detector':detector,'context':condition,
                       'raw_events':int((s.to_numpy()&eligible).sum()),'selected_events':int((selected.to_numpy()&eligible).sum()),
                       'selected_dates':int(((selected.to_numpy()&eligible).any(axis=1)).sum())})
                    for h in (21,63):
                        for cost in (.0005,.002):
                            result=ex.account(t,selected,valid,h,cost)
                            policy=detector+'_'+condition
                            result['curve'].to_csv(out/'private'/f'{era}_h{h}_c{int(cost*10000)}_{policy}.csv')
                            accounts.append({'era':era,'horizon':h,'cost_bp':cost*10000,'policy':policy,**result['metrics']})
            for condition,g in contexts.items():
                for h in (21,63):
                    for cost in (.0005,.002):
                        curves=[];total_trades=0
                        for phase in (0,1,2):
                            # Context selects pre-existing native onsets, never invents a later onset.
                            s=ex.onset(phases[phase])&g
                            result=ex.account(t,s,valid,h,cost);curves.append(result['curve']);total_trades+=result['metrics']['closed_trades']
                            if era!='2001_2006' and condition=='unfiltered' and (phase==0 or cost==.0005):
                                original=pd.read_csv(root/'primary_results/private'/f'{segment}_p{phase}_h{h}_c{int(cost*10000)}_dot.csv',index_col=0,parse_dates=True)
                                err=float(np.max(np.abs(original.equity.to_numpy()-result['curve'].equity.to_numpy())))
                                if err>1e-12:raise AssertionError('Original phase account changed')
                                parity.append({'era':era,'phase':phase,'horizon':h,'cost_bp':cost*10000,'max_difference':err})
                        m,curve=mean_accounts(curves);m['closed_trades']=total_trades
                        policy='equal_phase_portfolios_'+condition
                        accounts.append({'era':era,'horizon':h,'cost_bp':cost*10000,'policy':policy,**m})
                        curve.to_csv(out/'private'/f'{era}_h{h}_c{int(cost*10000)}_{policy}.csv')
            print('PHASE_NEUTRAL_ERA',era,flush=True)
    pd.DataFrame(accounts).to_csv(out/'portfolio_metrics.csv',index=False)
    pd.DataFrame(counts).to_csv(out/'event_counts.csv',index=False)
    ex.write_json(out/'original_parity.json',parity)
    ex.write_json(out/'RUN_RECEIPT.json',{'status':'COMPLETE','accounts':len(accounts),'event_count_rows':len(counts),
      'source_sha256':hashlib.sha256((root/'phase_neutral.py').read_bytes()).hexdigest(),
      'outcome_guided_source_robustness_experiment':True,'independent_phase_votes':False,
      'native_producer_unchanged':True,'may_rank':False,'may_size':False,'may_trade':False})
    print('PHASE_NEUTRAL_COMPLETE',len(accounts),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();main(a.root)
