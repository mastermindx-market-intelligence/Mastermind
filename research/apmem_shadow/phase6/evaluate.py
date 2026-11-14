"""Chronological event outcomes and self-financing paper comparisons.

Not a trading executor. Entry permissions remain outside this research module.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import features as f

HORIZONS=(21,63,126)
FAMILIES=('dot','rsi_macd_3d_cross')


def clean_json(x):
    if isinstance(x,dict):return {str(k):clean_json(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean_json(v) for v in x]
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(np.bool_,)):return bool(x)
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    if isinstance(x,(pd.Timestamp,datetime.datetime)):return x.isoformat()
    return x


def write_json(path,value):
    Path(path).write_text(json.dumps(clean_json(value),indent=2,allow_nan=False))


def fixed_policies(features,family):
    if family not in FAMILIES:raise ValueError('Unknown entry family')
    raw=features[family].fillna(False).astype(bool)
    slow=features.slow_improving.fillna(False).astype(bool)
    peer=features.peer_repair.fillna(False).astype(bool)
    rel=features.resilience_positive.fillna(False).astype(bool)
    p={'raw':raw,'slow':raw&slow,'peer':raw&peer,'slow_peer':raw&slow&peer,'slow_peer_relative':raw&slow&peer&rel}
    if family=='dot':p['phase_neutral']=features.persistent_dot.fillna(False).astype(bool)
    if 'beh_peer_repair' in features:
        behavior=features.beh_peer_repair.fillna(False).astype(bool)
        p['slow_behavior']=raw&slow&behavior
        p['slow_behavior_relative']=raw&slow&behavior&(features.beh_relative_resilience21>0)
    return p


def outcome(price,total,idx,symbol,members,origin,horizon,cost=.0005):
    if horizon<1 or not 0<=cost<.1:raise ValueError('Invalid outcome contract')
    i=int(origin);entry=i+1;end=entry+horizon
    result={'origin':idx[i],'horizon':horizon,'outcome_status':'NOT_MATURED'}
    if end>=len(idx):return result
    result.update(entry_date=idx[entry],end_date=idx[end])
    p=price[symbol].iloc[entry:end+1];t=total[symbol].iloc[entry:end+1]
    if p.isna().any() or t.isna().any():result['outcome_status']='MISSING_PATH';return result
    low=price[symbol].iloc[max(0,i-20):i+1].min()
    gross=t.iloc[-1]/t.iloc[0];net=gross*(1-cost)/(1+cost)-1
    peers=[s for s in members if s!=symbol and pd.notna(total[s].iloc[i]) and total[s].iloc[:i+1].notna().sum()>=63]
    excess=np.nan;peer_return=np.nan
    if len(peers)>=2:
        left=total[peers].iloc[entry];right=total[peers].iloc[end]
        if left.notna().all() and right.notna().all():
            peer_return=(right/left).mean()*(1-cost)/(1+cost)-1;excess=net-peer_return
    below=np.flatnonzero(p.to_numpy()<low)
    result.update(outcome_status='COMPLETE',net_return=net,positive_net=int(net>0),peer_return=peer_return,
      peer_excess=excess,positive_peer_excess=int(excess>0) if np.isfinite(excess) else np.nan,
      low_held=int(not len(below)),first_low_break_session=int(below[0]) if len(below) else None,
      reference_low=low,entry_price=p.iloc[0],close_mae=p.min()/p.iloc[0]-1,close_mfe=p.max()/p.iloc[0]-1)
    return result


def metrics(equity,exposure,trades):
    eq=np.asarray(equity,float);g=np.asarray(exposure,float)
    if len(eq)<2 or (eq<=0).any() or not np.isfinite(eq).all():raise ValueError('Invalid account')
    r=np.diff(eq)/eq[:-1];sd=r.std(ddof=1);years=len(r)/252
    return {'cagr':(eq[-1]/eq[0])**(1/years)-1,'total_return':eq[-1]/eq[0]-1,
      'sharpe':r.mean()/sd*np.sqrt(252) if sd>0 else None,'annual_vol':sd*np.sqrt(252),
      'maximum_drawdown':np.min(eq/np.maximum.accumulate(eq)-1),
      'worst_5pct_daily_mean':np.sort(r)[:max(1,int(np.ceil(len(r)*.05)))].mean(),
      'mean_exposure':g.mean(),'closed_trades':len(trades),'sessions':len(eq)}


def account(total,signal,eligible,horizon,cost=.0005,extra_delay=0,scale=1.,exit_support=None):
    """One unlevered sleeve. Unknown marks carry last observed value, not new signals."""
    if not signal.index.equals(total.index) or not eligible.index.equals(total.index):raise ValueError('Clock mismatch')
    f.validate_index(total.index)
    if horizon<1 or not 0<=cost<.1 or not 0<scale<=1 or extra_delay<0:raise ValueError('Invalid policy')
    tr=total.to_numpy(float);sig=signal.to_numpy(bool);ok=eligible.to_numpy(bool)
    if np.isfinite(tr).sum()<100:return None
    cash=1.;units=0.;expiry=-1;at=-1;paid=0.;last=np.nan;eq=[];gross=[];trades=[];stale=0
    for i,quote in enumerate(tr):
        actual=np.isfinite(quote) and quote>0
        if actual:last=quote
        if units and not actual:stale+=1
        exit_now=(i>=expiry or i==len(tr)-1 or (exit_support is not None and i>0 and bool(exit_support.iloc[i-1])))
        if units and actual and exit_now:
            received=units*quote*(1-cost);cash+=received
            trades.append({'entry':total.index[at],'exit':total.index[i],'return':received/paid-1,'held':i-at})
            units=0.;expiry=-1
        origin=i-1-extra_delay
        # End truncation is a fixed study boundary, not future outcome screening.
        if actual and units==0 and origin>=0 and ok[origin] and sig[origin] and i+horizon<len(tr):
            paid=cash*scale;units=paid/(1+cost)/quote;cash-=paid;expiry=i+horizon;at=i
        value=units*last if units else 0.;wealth=cash+value
        if cash<-1e-10 or wealth<=0:raise AssertionError('Capital accounting violation')
        eq.append(wealth);gross.append(value/wealth)
    result=metrics(eq,gross,trades);result.update(stale_mark_sessions=stale,open_at_end=bool(units))
    return {'metrics':result,'curve':pd.DataFrame({'equity':eq,'gross':gross},index=total.index),'trades':trades}


def era_mask(index,segment):
    if segment=='pre':return (index>='2001-01-01')&(index<='2019-12-31')
    return index>='2025-06-01'


def main(root):
    root=Path(root);dest=root/'event_results';dest.mkdir(exist_ok=False)
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text());events=[];accounts=[];groups={};cases=[]
    for group,members in manifest['groups'].items():
        for s in members:groups[s]=(group,members)
    for seg in ['pre','post']:
        price,total,vol,_=f.load_segment(root,seg);idx=price.index
        for symbol,(group,members) in groups.items():
            x=pd.read_parquet(root/'enriched'/seg/f'{symbol}.parquet');valid=x.eligible.fillna(False)&era_mask(idx,seg)
            exposed=(symbol=='MCD')&(idx>='2026-01-01')
            for family in FAMILIES:
                masks=fixed_policies(x,family)
                for i in np.flatnonzero(masks['raw'].to_numpy()&valid.to_numpy()):
                    features=x.iloc[i].to_dict()
                    if family=='rsi_macd_3d_cross':
                        features['prior_attempts']=features['cross_prior_attempts'];features['prior_failed_attempts']=features['cross_prior_failed_attempts']
                    for h in HORIZONS:
                        o=outcome(price,total,idx,symbol,members,i,h)
                        row={**features,**o,'symbol':symbol,'group':group,'segment':seg,'family':family,
                          'event_id':f'{symbol}:{family}:{idx[i].date()}', 'exposed_design_case':bool(symbol=='MCD' and (exposed[i] or (o.get('end_date',idx[i])>=pd.Timestamp('2026-01-01')))),
                          'state':f.interpretation(features)}
                        for policy,mask in masks.items():row['policy_'+policy]=bool(mask.iloc[i])
                        events.append(row)
                        if row['exposed_design_case']:cases.append(row)
                if seg=='post' and symbol=='MCD':
                    continue  # exposed case never contributes an aggregate account
                for h in (21,63):
                    for cost in (.0005,.002):
                        for policy,signal in masks.items():
                            for period,start,end in [('all','2001-01-01','2019-12-31')] if seg=='pre' else [('post','2025-06-01','2026-11-06')]:
                                ix=(idx>=start)&(idx<=end)
                                # MCD 2026 remains a displayed case, not aggregate qualification.
                                elig=valid&~pd.Series(exposed,index=idx)
                                result=account(total[symbol].loc[ix],signal.loc[ix],elig.loc[ix],h,cost)
                                if result is None:continue
                                name=f'{seg}__{symbol}__{family}__{policy}__{h}__{int(cost*10000)}'
                                result['curve'].to_parquet(dest/(name+'.parquet'))
                                accounts.append({'segment':seg,'symbol':symbol,'group':group,'family':family,'policy':policy,
                                  'horizon':h,'cost_bp':cost*10000,'curve':name+'.parquet',**result['metrics']})
            print('EVALUATED',seg,symbol,flush=True)
    event_frame=pd.DataFrame(events);event_frame.to_parquet(dest/'events.parquet',index=False)
    event_frame.drop(columns=['research_anchor'],errors='ignore').to_csv(dest/'events_private.csv',index=False)
    pd.DataFrame(accounts).to_csv(dest/'accounts.csv',index=False)
    # Case readout is descriptive; future maturity is kept visible rather than filled.
    fields=['event_id','origin','family','horizon','outcome_status','entry_price','net_return','close_mae','low_held',
      'w2_hist','w2_hist_delta','month_hist','month_hist_delta','peer_return_21','peer_breadth_change',
      'relative_resilience21','prior_failed_attempts','state','history_reset']
    pd.DataFrame(cases).reindex(columns=fields).to_csv(dest/'MCD_2026_EXPOSED_CASE.csv',index=False)
    summary=event_frame.loc[(event_frame.outcome_status=='COMPLETE')&~event_frame.exposed_design_case].groupby(['segment','group','family','horizon']).agg(
       events=('event_id','size'),dates=('origin','nunique'),net_return=('net_return','mean'),low_held=('low_held','mean'),peer_excess=('peer_excess','mean'),mae=('close_mae','mean')).reset_index()
    summary.to_csv(dest/'event_summary.csv',index=False)
    write_json(dest/'receipt.json',{'status':'COMPLETE','accounts':len(accounts),'event_horizon_rows':len(events),'design_case_rows':len(cases),
       'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'may_rank':False,'may_trade':False})
    print('EVENT_EVALUATION_COMPLETE',len(accounts),len(events),len(cases),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));main(ap.parse_args().root)
