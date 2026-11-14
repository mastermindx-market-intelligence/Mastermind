"""Preserve per-cohort and per-entry-family results; never hide behind one average."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from evaluate import metrics,write_json
from modeling import block_interval,holm


def combine_curves(curves):
    if not curves:raise ValueError('No component accounts')
    index=curves[0].index
    if any(not c.index.equals(index) for c in curves):raise ValueError('Account clocks differ')
    eq=np.column_stack([c.equity.to_numpy() for c in curves])
    gross=np.column_stack([c.gross.to_numpy() for c in curves])
    aggregate=eq.mean(axis=1);exposure=(eq*gross).sum(axis=1)/eq.sum(axis=1)
    return pd.DataFrame({'equity':aggregate,'gross':exposure},index=index)


def mean_exposure_match(candidate,baseline):
    if not candidate.index.equals(baseline.index):raise ValueError('Exposure clock mismatch')
    target=float(candidate.gross.mean())
    if target>baseline.gross.mean()+1e-10:return None
    lo,hi=0.,1.
    for _ in range(60):
        a=(lo+hi)/2;equity=1-a+a*baseline.equity
        exposure=a*baseline.equity*baseline.gross/equity
        if exposure.mean()>target:hi=a
        else:lo=a
    a=(lo+hi)/2;equity=1-a+a*baseline.equity;exposure=a*baseline.equity*baseline.gross/equity
    m=metrics(equity,exposure,[]);return {'cash_mix_fraction':a,**m}


def account_summary(root,directory,dest):
    base=root/directory;records=pd.read_csv(base/'accounts.csv')
    grouping=['segment','group','family','policy','horizon','cost_bp']
    if 'kind' in records:grouping+=['kind','extra_delay']
    aggregates=[];curve_map={};exposure_checks=[]
    for key,part in records.groupby(grouping,dropna=False):
        curves=[pd.read_parquet(base/x) for x in part.curve]
        combined=combine_curves(curves)
        result=metrics(combined.equity,combined.gross,[{}]*int(part.closed_trades.sum()))
        row=dict(zip(grouping,key));row.update(result,names=len(part),median_name_cagr=float(part.cagr.median()),positive_name_fraction=float((part.cagr>0).mean()))
        aggregates.append(row)
        keystr='__'.join(str(x) for x in key);combined.to_parquet(dest/(keystr+'.parquet'));curve_map[keystr]=combined
    output=pd.DataFrame(aggregates);output.to_csv(dest/'cohort_accounts.csv',index=False)
    tests=[]
    # Fixed economic contrasts, all groups retained. Not same-exposure causal effects.
    if directory=='event_results':
        pairs=[('slow','raw'),('peer','raw'),('slow_peer','raw'),('slow_peer_relative','slow_peer'),('slow_behavior','slow_peer')]
        for (seg,group,fam,h),part in output.loc[output.cost_bp==5].groupby(['segment','group','family','horizon']):
            for high,low in pairs:
                match=lambda name:part.loc[part.policy==name]
                if len(match(high))!=1 or len(match(low))!=1:continue
                def curve(name):return curve_map['__'.join(str(v) for v in [seg,group,fam,name,h,5.0])]
                a,b=curve(high),curve(low)
                diff=a.equity.pct_change().iloc[1:]-b.equity.pct_change().iloc[1:]
                test=block_interval(diff.index,diff.to_numpy(),repetitions=999)
                tests.append({'segment':seg,'group':group,'family':fam,'horizon':h,'contrast':high+' - '+low,**test})
                check=mean_exposure_match(a,b)
                if check is not None:exposure_checks.append({'segment':seg,'group':group,'family':fam,'horizon':h,'candidate':high,'baseline':low,
                    'candidate_cagr':float(match(high).cagr.iloc[0]),'candidate_drawdown':float(match(high).maximum_drawdown.iloc[0]),
                    'hindsight_diagnostic_not_live_rule':True,**check})
        frame=pd.DataFrame(tests);frame['p_holm_family']=holm(frame);frame.to_csv(dest/'paired_cohort_returns.csv',index=False)
        pd.DataFrame(exposure_checks).to_csv(dest/'exposure_controls.csv',index=False)
    return len(aggregates),len(tests)


def event_summary(root,dest):
    events=pd.read_parquet(root/'event_results/events.parquet')
    q=events.loc[(events.outcome_status=='COMPLETE')&~events.exposed_design_case].copy()
    q['episode_key']=q.symbol+':'+q.segment+':'+q.family+':'+q.episode_number.fillna(0).astype(int).astype(str)
    zero=q.episode_number.fillna(0)==0;q.loc[zero,'episode_key']=q.loc[zero,'event_id']
    rows=[]
    for (seg,g,fam,h),part in q.groupby(['segment','group','family','horizon']):
        for key in [c for c in part if c.startswith('policy_')]:
            selected=part.loc[part[key].fillna(False)]
            if selected.empty:continue
            equal_date=selected.groupby('origin')[['net_return','peer_excess','low_held','close_mae']].mean()
            equal_cycle=selected.groupby('episode_key')[['net_return','peer_excess','low_held','close_mae']].mean()
            rows.append({'segment':seg,'group':g,'family':fam,'horizon':h,'policy':key[7:],
                'events':len(selected),'dates':selected.origin.nunique(),'episodes':selected.episode_key.nunique(),
                'event_net':selected.net_return.mean(),'event_peer_excess':selected.peer_excess.mean(),'event_low_held':selected.low_held.mean(),
                'date_equal_net':equal_date.net_return.mean(),'date_equal_peer_excess':equal_date.peer_excess.mean(),
                'cycle_equal_net':equal_cycle.net_return.mean(),'cycle_equal_peer_excess':equal_cycle.peer_excess.mean(),'mean_mae':selected.close_mae.mean()})
    pd.DataFrame(rows).to_csv(dest/'cohort_events.csv',index=False)
    # Selection conditional on same observed date: market/cross-cohort opportunity is not individual alpha.
    changes=[]
    for (seg,group,fam,h),part in q.groupby(['segment','group','family','horizon']):
        for key in ['policy_slow','policy_peer','policy_slow_peer','policy_slow_peer_relative']:
            local=[]
            for date,day in part.groupby('origin'):
                selected=day.loc[day[key].fillna(False)];rejected=day.loc[~day[key].fillna(False)]
                if len(selected) and len(rejected):local.append({'date':date,'difference':selected.net_return.mean()-rejected.net_return.mean()})
            if local:
                z=pd.DataFrame(local);changes.append({'segment':seg,'group':group,'family':fam,'horizon':h,'policy':key[7:],'mixed_dates':len(z),**block_interval(z.date,z.difference.to_numpy())})
    pd.DataFrame(changes).to_csv(dest/'within_cohort_date_selection.csv',index=False)
    return len(rows)


def main(root,which):
    root=Path(root);dest=root/(which+'_analysis');dest.mkdir(exist_ok=False)
    a,b=account_summary(root,which,dest)
    n=event_summary(root,dest) if which=='event_results' else 0
    write_json(dest/'receipt.json',{'status':'COMPLETE','cohort_accounts':a,'paired_return_contrasts':b,'event_summary_rows':n,
      'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'raw_vendor_history_exported':False})
    print('COHORT_ANALYSIS_COMPLETE',which,a,b,n,flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));ap.add_argument('--which',choices=['event_results','dynamics_results'],default='event_results');a=ap.parse_args();main(a.root,a.which)
