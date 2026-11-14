"""Same-panel native T1/T2 comparison using recovered phase3 source unchanged."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import experiment as ex
from robustness import extended_context


def prepare_native(root):
    sys.path.insert(0,str(root/'source'));sys.path.insert(0,str(root/'source/macro_native'))
    from native_adapter.native import verify_source
    verify_source(root/'source/macro_native',json.loads((root/'MACRO_NATIVE_MANIFEST.json').read_text()))
    if os.environ.get('VETO_HYSTERESIS_CONFIRM','1')!='1':raise ValueError('Unexpected native hysteresis policy')


def parity(root):
    prepare_native(root)
    from engine.signal_gate import gate
    from native_adapter.native import make_gate,decision_view,equal_values
    from native_adapter.replay import primary_possible
    projected=make_gate();m=json.loads((root/'INPUT_MANIFEST.json').read_text());records=[];positive={'T1':0,'T2':0}
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,m)
        for ticker in ex.SECTORS:
            for n in (600,850,1200,1800,2400,3200,4100,5000):
                if n>len(p):continue
                prefix=p[ticker].iloc[:n];a=gate(ticker,prefix,washout_waiver=False);b=projected(ticker,prefix,washout_waiver=False)
                ok=equal_values(decision_view(a),decision_view(b))
                if not ok:raise AssertionError('Native projection parity failed')
                if a.get('eligible') and a.get('tier_cascade') in positive:positive[a['tier_cascade']]+=1
                if a.get('eligible') and a.get('tier_cascade') in positive and not primary_possible(prefix):raise AssertionError('Sieve false negative')
                records.append({'segment':segment,'ticker':ticker,'prefix_rows':n,'tier':a.get('tier_cascade'),
                                'eligible':bool(a.get('eligible')),'decision_equal':ok})
    ex.write_json(root/'native_comparison_parity.json',{'cases':len(records),'positive_cases':positive,'records':records,
        'native_pin':'6bbc4b0fc694c847077661ff5bf4c19ea41e4e81','full_chart_payload_parity_claimed':False})
    print('NATIVE_COMPARISON_PARITY',len(records),positive,flush=True)


def worker(rootstr,segment,ticker):
    root=Path(rootstr);prepare_native(root)
    from native_adapter.replay import replay
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text());p,t,v=ex.load_segment(root,segment,manifest)
    valid=ex.eval_mask(p.index,segment);dates=p.index[valid]
    r=replay(ticker,p[ticker],start=str(dates[0].date()),end=str(dates[-1].date()))
    path=root/'native_comparison_results/private'/f'{segment}_{ticker}_observations.parquet';r.to_parquet(path)
    return {'segment':segment,'ticker':ticker,'rows':len(r),'unknown':int((~r.evaluated).sum()),
            't1_events':int(r.t1_onset.sum()),'t2_events':int(r.t2_onset.sum()),
            'union_events':int(r.union_onset.sum()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main(root):
    out=root/'native_comparison_results'
    if out.exists():raise ValueError('Original native comparison output exists')
    parity(root);out.mkdir();(out/'private').mkdir();receipts=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        work={pool.submit(worker,str(root),seg,t):seg+':'+t for seg in ('pre','post') for t in ex.SECTORS}
        for task in as_completed(work):
            r=task.result();receipts.append(r);ex.write_json(out/'progress.json',receipts)
            print('NATIVE_COMPARISON_REPLAY',r['segment'],r['ticker'],r['t1_events'],r['t2_events'],flush=True)
    results=[];events=[];manifest=json.loads((root/'INPUT_MANIFEST.json').read_text())
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,manifest);ctx=ex.context(p,t,v);xt=extended_context(p,t,ctx);valid=ex.eval_mask(p.index,segment)
        repair=pd.DataFrame(np.repeat(ctx['repair'].to_numpy()[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
        low=pd.DataFrame(np.repeat(xt['lower_pressure'].to_numpy()[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
        for family in ('t1','t2','union'):
            raw=pd.DataFrame(False,index=p.index,columns=ex.SECTORS)
            for ticker in ex.SECTORS:
                f=pd.read_parquet(out/'private'/f'{segment}_{ticker}_observations.parquet')
                raw.loc[f.index,ticker]=f[family+'_onset'].to_numpy(bool)
            arms={family:raw,family+'_repair':raw&repair,family+'_declining_pressure':raw&repair&low}
            # A context filter selects native onset events; it cannot manufacture a later onset.
            for policy,sig in arms.items():
                ev=ex.event_outcomes(p,t,{'dot':sig},valid,ctx,0,segment);ev['policy']=policy;events.append(ev)
                for h in (21,63):
                    for cost in (.0005,.002):
                        a=ex.account(t,sig,valid,h,cost)
                        results.append({'segment':segment,'horizon':h,'cost_bp':cost*10000,'policy':policy,**a['metrics']})
                        a['curve'].to_csv(out/'private'/f'{segment}_h{h}_c{int(cost*10000)}_{policy}.csv')
    pd.DataFrame(results).to_csv(out/'portfolio_metrics.csv',index=False)
    e=pd.concat(events,ignore_index=True)
    e.groupby(['segment','horizon','policy']).agg(events=('ticker','size'),dates=('origin','nunique'),mean_net=('net_return','mean'),
      sector_relative=('sector_excess','mean'),low_hold_rate=('prior_low_holds','mean'),mean_mae=('mae_close','mean')).to_csv(out/'event_metrics.csv')
    ex.write_json(out/'RUN_RECEIPT.json',{'status':'COMPLETE','accounts':len(results),'replay_receipts':receipts,
      'source_sha256':hashlib.sha256((root/'native_comparison.py').read_bytes()).hexdigest(),
      'source_reused_not_reimplemented':'Mastermind219b6d355108912f410d09adf35eced45c376797 phase3 native/replay',
      'no_historical_peer_waiver':True,'may_trade':False})
    print('NATIVE_COMPARISON_COMPLETE',len(results),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();main(a.root)
