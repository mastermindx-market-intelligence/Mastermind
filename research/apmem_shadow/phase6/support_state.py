"""Research state estimator: improving participation is not persistent health.

No runtime lifecycle, signal registry, operational queue or trading gate is owned
here. These are pure chronological features over the existing observed panel.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import features as f
from dynamics import relative_dynamics
from evaluate import account,write_json


def cohort_state(features,prefix='',window=21):
    if window<1:raise ValueError('Finite support memory required')
    required=[prefix+s for s in ['peer_valid','peer_above20','peer_return_21','peer_return_5','peer_low_pressure_change','peer_repair']]
    if not set(required).issubset(features.columns):raise ValueError('Missing context fields')
    rows=[];last_repair=None
    for i,(_,row) in enumerate(features.iterrows()):
        get=lambda k:row[prefix+k]
        known=bool(pd.notna(get('peer_valid')) and get('peer_valid'))
        known=known and all(pd.notna(get(k)) for k in ['peer_above20','peer_return_21','peer_return_5','peer_low_pressure_change'])
        if not known:
            last_repair=None;rows.append({'cohort_known':False,'cohort_healthy':False,'cohort_supported':False,
                                         'repair_age':np.nan,'cohort_state':'UNKNOWN'});continue
        invalid=bool(get('peer_return_5')<0 and get('peer_above20')<.5 and get('peer_low_pressure_change')>0)
        impulse=bool(pd.notna(get('peer_repair')) and get('peer_repair'))
        if invalid:last_repair=None
        elif impulse:last_repair=i
        age=i-last_repair if last_repair is not None else np.nan
        healthy=bool(get('peer_above20')>=.5 and get('peer_return_21')>0)
        recent=last_repair is not None and i-last_repair<window
        supported=healthy or recent
        state='SUPPORTED_HEALTHY' if healthy else 'REPAIR_WINDOW' if recent else 'DETERIORATING' if invalid else 'UNCONFIRMED'
        rows.append({'cohort_known':True,'cohort_healthy':healthy,'cohort_supported':supported,'repair_age':age,'cohort_state':state})
    return pd.DataFrame(rows,index=features.index)


def slow_state(features):
    keys=['w2_hist','w2_hist_delta','alternate_w2_hist','alternate_w2_hist_delta']
    if not set(keys).issubset(features):raise ValueError('Both fixed pairings required')
    known=features[keys].notna().all(axis=1)
    level=(features.w2_hist+features.alternate_w2_hist)/2
    change=(features.w2_hist_delta+features.alternate_w2_hist_delta)/2
    disagreement=(features.w2_hist_delta>0)!=(features.alternate_w2_hist_delta>0)
    return pd.DataFrame({'slow_known':known,'slow_mean_hist':level.where(known),'slow_mean_change':change.where(known),
       'slow_phase_disagreement':disagreement&known,'slow_supported':known&((level>0)|(change>0))},index=features.index)


def state_policies(features,total,family):
    own=features[family].fillna(False).astype(bool);slow=slow_state(features)
    economic=cohort_state(features);behavior=cohort_state(features,'beh_')
    relative=relative_dynamics(total,features.peer_return_1)
    impulse=own&features.slow_improving.fillna(False)&features.peer_repair.fillna(False)
    combo=own&slow.slow_supported&economic.cohort_supported
    return {'raw':own,'original_impulse':impulse,'slow_state':own&slow.slow_supported,
      'cohort_state':own&economic.cohort_supported,'slow_cohort_state':combo,
      'slow_cohort_state_acceleration':combo&relative.relative_accelerating,
      'slow_behavior_state':own&slow.slow_supported&behavior.cohort_supported},slow,economic,behavior


def main(root):
    root=Path(root);dest=root/'state_results';dest.mkdir(exist_ok=False)
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text());rows=[];case=[]
    for segment in ['pre','post']:
        price,total,_,_=f.load_segment(root,segment)
        for group,names in manifest['groups'].items():
            for symbol in names:
                x=pd.read_parquet(root/'enriched'/segment/f'{symbol}.parquet')
                valid=x.eligible.fillna(False).astype(bool)
                index=(x.index>='2001-01-01')&(x.index<='2019-12-31') if segment=='pre' else (x.index>='2025-06-01')&(x.index<='2026-11-06')
                for family in ['dot','rsi_macd_3d_cross']:
                    variants,slow,economic,behavior=state_policies(x,total[symbol],family)
                    if symbol=='MCD' and segment=='post':
                        for at in x.index[variants['raw']&valid&(x.index>='2026-01-01')]:
                            case.append({'date':str(at.date()),'family':family,'price':price[symbol].loc[at],**slow.loc[at].to_dict(),
                                **economic.loc[at].to_dict(),'behavioral_state':behavior.loc[at,'cohort_state'],
                                **{'selected_'+k:bool(v.loc[at]) for k,v in variants.items()}})
                        continue
                    for policy,signal in variants.items():
                        for h in [21,63]:
                            for cost in [.0005,.002]:
                                a=account(total[symbol].loc[index],signal.loc[index],valid.loc[index],h,cost)
                                if a is None:continue
                                name=f'{segment}__{symbol}__{family}__{policy}__{h}__{int(cost*10000)}';a['curve'].to_parquet(dest/(name+'.parquet'))
                                rows.append({'segment':segment,'symbol':symbol,'group':group,'family':family,'policy':policy,'horizon':h,'cost_bp':cost*10000,'curve':name+'.parquet',**a['metrics']})
                print('STATE_POLICY_TESTED',segment,symbol,flush=True)
    pd.DataFrame(rows).to_csv(dest/'accounts.csv',index=False);pd.DataFrame(case).to_csv(dest/'MCD_EXPOSED_STATES.csv',index=False)
    write_json(dest/'receipt.json',{'status':'COMPLETE','accounts':len(rows),'exposed_case_events':len(case),
      'outcome_guided_exploratory':True,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'may_trade':False})
    print('STATE_STUDY_COMPLETE',len(rows),len(case),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));main(ap.parse_args().root)
