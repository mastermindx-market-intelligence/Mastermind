"""Common-origin exit comparison and separately measured entry/exit latency.

The earlier max-63/max-126 account rows retain their original end-of-sample
admission conventions. This additional comparison uses one conservative origin
cutoff for every policy, so the last permissible entry is not policy-dependent.
Position occupancy still legitimately changes subsequent account entries; a
standalone common-event comparison below separates that effect from exit payoff.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import features as f
from dynamics import support_exit
from evaluate import account,write_json


def common_eligibility(valid,maximum_horizon=126,maximum_delay=1):
    if maximum_horizon<1 or maximum_delay<0:raise ValueError('Invalid fixed common boundary')
    positions=np.arange(len(valid))
    return valid.astype(bool)&(positions+1+maximum_delay+maximum_horizon<len(valid))


def standalone_path(total,origin,horizon,cost=.0005,delay=0,exit_observation=None):
    """Same issued opportunity, executable next-close entry and next-close exit."""
    if horizon<1 or delay<0 or not 0<=cost<.1:raise ValueError('Invalid exit comparison')
    entry=origin+1+delay;end=entry+horizon
    if end>=len(total):return {'status':'RIGHT_CENSORED_AT_CAPTURE'}
    if not np.isfinite(total.iloc[entry]) or total.iloc[entry]<=0:return {'status':'MISSING_ENTRY'}
    chosen=end;reason='maximum_horizon'
    if exit_observation is not None:
        if not exit_observation.index.equals(total.index):raise ValueError('Exit clock mismatch')
        for at in range(entry+1,end+1):
            observed=at-1-delay
            if observed>=entry and bool(exit_observation.iloc[observed]) and np.isfinite(total.iloc[at]):
                chosen=at;reason='observed_support_exit';break
    if not np.isfinite(total.iloc[chosen]):return {'status':'MISSING_EXIT'}
    path=total.iloc[entry:chosen+1]
    if path.isna().any():return {'status':'MISSING_PATH'}
    return {'status':'COMPLETE','entry':total.index[entry],'exit':total.index[chosen],'held_sessions':chosen-entry,
      'net_return':total.iloc[chosen]/total.iloc[entry]*(1-cost)/(1+cost)-1,
      'total_return_mae':path.min()/path.iloc[0]-1,'exit_reason':reason}


def main(root):
    root=Path(root);dest=root/'matched_exit_results';dest.mkdir(exist_ok=False)
    m=json.loads((root/'INPUT_MANIFEST.json').read_text())
    groups={s:g for g,names in m['groups'].items() for s in names}
    groups.update({s:'index_diagnostic' for s in ['RSP','DIA','QQQ']})
    accounts=[];events=[];admissions=[]
    for segment in ['pre','post']:
        _,total,_,_=f.load_segment(root,segment)
        for symbol,group in groups.items():
            if symbol=='MCD' and segment=='post':continue
            path=root/('features' if group=='index_diagnostic' else 'enriched')/segment/f'{symbol}.parquet'
            x=pd.read_parquet(path)
            selected=(x.index>='2001-01-01')&(x.index<='2019-12-31') if segment=='pre' else (x.index>='2025-06-01')&(x.index<='2026-11-06')
            x=x.loc[selected];t=total[symbol].loc[x.index];valid=common_eligibility(x.eligible.fillna(False))
            raw=x.rsi_macd_3d_cross.fillna(False).astype(bool)
            for entry_rule,signal in [('cross',raw),('cross_slow_peer',raw&x.slow_improving.fillna(False)&x.peer_repair.fillna(False))]:
                origins=np.flatnonzero((signal&valid).to_numpy())
                admissions.append({'segment':segment,'symbol':symbol,'entry_rule':entry_rule,'common_origin_count':len(origins),
                    'last_permitted_origin':str(x.index[np.flatnonzero(valid)[-1]].date()) if valid.any() else None})
                for exit_rule,horizon in [('fixed63',63),('fixed126',126),('fast_cross',126),('nested_support',126)]:
                    ex=None if exit_rule.startswith('fixed') else support_exit(x,exit_rule)
                    for delay in [0,1]:
                        for cost in [.0005,.002]:
                            delayed=None if ex is None else ex.shift(delay,fill_value=False)
                            a=account(t,signal,valid,horizon,cost,extra_delay=delay,exit_support=delayed)
                            if a is None:continue
                            name=f'{segment}__{symbol}__{entry_rule}__{exit_rule}__{int(cost*10000)}__{delay}'
                            a['curve'].to_parquet(dest/(name+'.parquet'))
                            accounts.append({'segment':segment,'symbol':symbol,'group':group,'family':'rsi_macd_3d_cross',
                              'policy':entry_rule+'__'+exit_rule,'horizon':horizon,'cost_bp':cost*10000,'entry_and_exit_delay':delay,
                              'common_origin_count':len(origins),'curve':name+'.parquet',**a['metrics']})
                            if cost==.0005:
                                for origin in origins:
                                    path=standalone_path(t,int(origin),horizon,cost,delay,ex)
                                    events.append({'segment':segment,'symbol':symbol,'group':group,'entry_rule':entry_rule,
                                      'exit_rule':exit_rule,'delay':delay,'origin':x.index[origin],**path})
            print('MATCHED_EXIT_TESTED',segment,symbol,flush=True)
    pd.DataFrame(accounts).to_csv(dest/'accounts.csv',index=False);pd.DataFrame(events).to_parquet(dest/'events.parquet',index=False)
    pd.DataFrame(admissions).to_csv(dest/'admission_counts.csv',index=False)
    q=pd.DataFrame(events);q=q.loc[q.status=='COMPLETE']
    q.groupby(['segment','group','entry_rule','exit_rule','delay']).agg(events=('symbol','size'),dates=('origin','nunique'),
       mean_net=('net_return','mean'),median_net=('net_return','median'),mean_held=('held_sessions','mean'),mean_mae=('total_return_mae','mean')).reset_index().to_csv(dest/'event_summary.csv',index=False)
    write_json(dest/'receipt.json',{'status':'COMPLETE','accounts':len(accounts),'common_opportunity_path_rows':len(events),
      'common_maximum_entry_lookahead':128,'all_delays_apply_entry_and_dynamic_exit':True,'no_stop_optimization':True,
      'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'interpretation':'method correction; original distinct-admission rows retained'})
    print('MATCHED_EXIT_COMPLETE',len(accounts),len(events),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));main(ap.parse_args().root)
