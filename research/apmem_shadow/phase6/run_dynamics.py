from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import features as f
from dynamics import relative_dynamics,cross_cycle,support_exit
from evaluate import account,metrics,outcome,write_json


def main(root):
    root=Path(root);dest=root/'dynamics_results';dest.mkdir(exist_ok=False)
    m=json.loads((root/'INPUT_MANIFEST.json').read_text());groups={s:(g,peers) for g,peers in m['groups'].items() for s in peers}
    for s in ['RSP','DIA','QQQ']:groups[s]=('index_diagnostic',['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY'])
    metrics_rows=[];events=[];case=[]
    for segment in ['pre','post']:
        p,t,_,_=f.load_segment(root,segment)
        for symbol,(group,peers) in groups.items():
            file=(root/('enriched' if group!='index_diagnostic' else 'features')/segment/f'{symbol}.parquet')
            x=pd.read_parquet(file);rel=relative_dynamics(t[symbol],x.peer_return_1);x=x.join(rel)
            index=(x.index>='2001-01-01')&(x.index<='2019-12-31') if segment=='pre' else (x.index>='2025-06-01')&(x.index<='2026-11-06')
            for family in ['dot','rsi_macd_3d_cross']:
                raw=x[family].fillna(False).astype(bool);valid=x.eligible.fillna(False).astype(bool)
                base=raw & x.slow_improving.fillna(False).astype(bool)&x.peer_repair.fillna(False).astype(bool)
                cycle=cross_cycle(p[symbol],raw,x.w2_hist,x.episode_number)
                variants={'raw':raw,'slow_peer':base,'relative21':base&(x.relative_resilience21>0),
                    'relative5':base&x.relative_short_positive,'relative_acceleration':base&x.relative_accelerating,
                    'relative5_acceleration':base&x.relative_short_positive&x.relative_accelerating,
                    'cross_cycle_only':raw&cycle.cross_cycle_divergence,
                    'cross_cycle_repair':base&cycle.cross_cycle_divergence}
                if symbol=='MCD' and segment=='post':
                    for at in x.index[(raw&valid)&(x.index>='2026-01-01')]:
                        row={'date':str(at.date()),'family':family,'price':p[symbol].loc[at],
                           **{k:x.loc[at,k] for k in ['w2_hist','w2_hist_delta','month_hist','month_hist_delta','relative_resilience21','relative_log5','relative_acceleration','peer_return_21','peer_repair']},
                           **cycle.loc[at].to_dict()}
                        for key,signal in variants.items():row['selected_'+key]=bool(signal.loc[at])
                        # Partial paths are descriptive only, never mature 21/63 labels.
                        pos=x.index.get_loc(at);start=pos+1
                        if start<len(x):
                            path=p[symbol].iloc[start:].dropna();row['partial_sessions']=len(path)-1
                            if len(path):row.update(partial_entry=str(path.index[0].date()),partial_net_return=t[symbol].loc[path.index[-1]]/t[symbol].loc[path.index[0]]*.9995/1.0005-1,partial_close_mae=path.min()/path.iloc[0]-1)
                        case.append(row)
                    continue
                for h in [21,63]:
                    for key,sig in variants.items():
                        for cost in [.0005,.002]:
                            a=account(t[symbol].loc[index],sig.loc[index],valid.loc[index],h,cost)
                            if a is None:continue
                            name=f'{segment}__{symbol}__{family}__{key}__{h}__{int(cost*10000)}'
                            a['curve'].to_parquet(dest/(name+'.parquet'))
                            metrics_rows.append({'segment':segment,'symbol':symbol,'group':group,'family':family,'policy':key,'horizon':h,'cost_bp':cost*10000,'kind':'relative_dynamics','curve':name+'.parquet',**a['metrics']})
                    for i in np.flatnonzero((raw&valid).to_numpy()&index):
                        o=outcome(p,t,p.index,symbol,peers,i,h)
                        o.update(symbol=symbol,group=group,segment=segment,family=family,episode_number=x.episode_number.iloc[i])
                        for key,sig in variants.items():o['policy_'+key]=bool(sig.iloc[i])
                        events.append(o)
            # Whole-cycle sell comparisons, independent of the percentage-stop experiments.
            if symbol=='MCD' and segment=='post':continue
            raw=x.rsi_macd_3d_cross.fillna(False).astype(bool);valid=x.eligible.fillna(False).astype(bool)
            for entry,signal in [('cross',raw),('cross_slow_peer',raw&x.slow_improving.fillna(False)&x.peer_repair.fillna(False))]:
                for policy,h in [('fixed63',63),('fast_cross',126),('nested_support',126)]:
                    ex=None if policy=='fixed63' else support_exit(x,policy)
                    for cost in [.0005,.002]:
                        for delay in [0,1]:
                            a=account(t[symbol].loc[index],signal.loc[index],valid.loc[index],h,cost,extra_delay=delay,exit_support=None if ex is None else ex.loc[index])
                            if a is None:continue
                            name=f'{segment}__{symbol}__{entry}__{policy}__{h}__{int(cost*10000)}__{delay}'
                            a['curve'].to_parquet(dest/(name+'.parquet'))
                            metrics_rows.append({'segment':segment,'symbol':symbol,'group':group,'family':'rsi_macd_3d_cross','policy':entry+'__'+policy,'horizon':h,'cost_bp':cost*10000,'extra_delay':delay,'kind':'cycle_exit','curve':name+'.parquet',**a['metrics']})
            print('DYNAMICS_TESTED',segment,symbol,flush=True)
    pd.DataFrame(metrics_rows).to_csv(dest/'accounts.csv',index=False);pd.DataFrame(events).to_parquet(dest/'events.parquet',index=False)
    pd.DataFrame(case).to_csv(dest/'MCD_EXPOSED_DYNAMICS.csv',index=False)
    write_json(dest/'receipt.json',{'status':'COMPLETE','accounts':len(metrics_rows),'event_horizon_rows':len(events),'exposed_case_rows':len(case),
       'case_guided_exploratory':True,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'no_capital_authority':True})
    print('DYNAMICS_EXPERIMENT_COMPLETE',len(metrics_rows),len(events),len(case),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));main(ap.parse_args().root)
