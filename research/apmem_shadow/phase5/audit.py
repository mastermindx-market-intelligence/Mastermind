"""Exact candidate falsifiers: exposure, dates, calendar dependence and losses."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import experiment as ex
from analyze import block_mean_interval,holm
from robustness import static_match,recovered_dot,extended_context


def tail_mean(r):
    return float(np.sort(r)[:max(1,int(np.ceil(.05*len(r))))].mean())


def block_tail_difference(x,y,draws=2000,block=63):
    x,y=np.asarray(x,float),np.asarray(y,float)
    if len(x)!=len(y) or not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('Invalid paired tails')
    n=len(x);rng=np.random.default_rng(20261114);k=int(np.ceil(n/block));vals=[]
    for _ in range(draws):
        starts=rng.integers(0,n,k)
        ix=((starts[:,None]+np.arange(block))%n).ravel()[:n]
        vals.append(tail_mean(x[ix])-tail_mean(y[ix]))
    observed=tail_mean(x)-tail_mean(y);samples=np.asarray(vals)
    p=(1+np.count_nonzero(np.abs(samples-observed)>=abs(observed)))/(draws+1)
    return observed,[float(z) for z in np.quantile(samples,[.025,.975])],float(p)


def curve(root,segment,phase,h,policy):
    folder='primary_results' if policy in ('dot','dot_repair','sequence_repair') else 'followup_results'
    return pd.read_csv(root/folder/'private'/f'{segment}_p{phase}_h{h}_c5_{policy}.csv',index_col=0,parse_dates=True)


def drawdown_episode(c):
    e=c.equity;high=e.cummax();dd=e/high-1
    trough=dd.idxmin();start=e.loc[:trough].idxmax();prior=float(e.loc[start])
    later=e.loc[trough:];recovery=later[later>=prior]
    return {'peak':str(start.date()),'trough':str(trough.date()),'depth':float(dd.loc[trough]),
            'recovery':str(recovery.index[0].date()) if len(recovery) else None,
            'still_unrecovered_at_end':len(recovery)==0}


def run(root):
    out=root/'audit_results'
    if out.exists():raise ValueError('Audit already exists')
    out.mkdir();(out/'private').mkdir()
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text())
    comparisons=[('dot_repair','dot'),('declining_low_pressure','dot_repair'),('ongoing_repair','dot_repair')]
    matched=[];tests=[];annual=[];episodes=[];delay=[];events=[];origins=[]
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,manifest);ctx=ex.context(p,t,v);xt=extended_context(p,t,ctx);valid=ex.eval_mask(p.index,segment)
        for phase in (0,1,2):
            d=recovered_dot(root,p.index,segment,phase);old=ex.policies(d,ctx)
            rep=pd.DataFrame(np.repeat(ctx['repair'].to_numpy()[:,None],9,axis=1),index=d.index,columns=d.columns)
            low=pd.DataFrame(np.repeat(xt['lower_pressure'].to_numpy()[:,None],9,axis=1),index=d.index,columns=d.columns)
            sig={'dot':old['dot'],'dot_repair':old['dot_repair'],'declining_low_pressure':ex.onset(d&rep&low)}
            ev=ex.event_outcomes(p,t,sig,valid,ctx,phase,segment);events.append(ev)
            for h in (21,63):
                for a,b in comparisons:
                    ca,cb=curve(root,segment,phase,h,a),curve(root,segment,phase,h,b)
                    if not ca.index.equals(cb.index):raise ValueError('Comparison calendar mismatch')
                    alpha,m,me,mg=static_match(cb,float(ca.gross.mean()))
                    matched.append({'segment':segment,'phase':phase,'horizon':h,'candidate':a,'control':b,
                       'capital_fraction':alpha,'control_cagr':m['cagr'],'control_sharpe':m['sharpe'],
                       'control_maximum_drawdown':m['maximum_drawdown'],'control_worst_5pct_mean':m['worst_5pct_mean'],
                       'matched_exposure':m['mean_exposure'],'candidate_cagr':ex.metrics(ca.equity.to_numpy(),ca.gross.to_numpy(),[])['cagr'],
                       'not_a_deployable_rule':True})
                    if phase==0:
                        ra=ca.equity.pct_change().iloc[1:].to_numpy();rb=cb.equity.pct_change().iloc[1:].to_numpy()
                        diff,ci,pv=block_mean_interval(ra-rb)
                        tests.append({'segment':segment,'horizon':h,'contrast':a+' - '+b,'metric':'mean_daily_return',
                          'difference':diff,'lower':ci[0],'upper':ci[1],'p_raw':pv})
                        diff,ci,pv=block_tail_difference(ra,rb)
                        tests.append({'segment':segment,'horizon':h,'contrast':a+' - '+b,'metric':'worst_5pct_daily_mean',
                          'difference':diff,'lower':ci[0],'upper':ci[1],'p_raw':pv})
                if phase==0:
                    for name in ('dot','dot_repair','declining_low_pressure','ongoing_repair','sequence_repair'):
                        c=curve(root,segment,phase,h,name);r=c.equity.pct_change().fillna(0)
                        for year,rr in r.groupby(r.index.year):
                            annual.append({'segment':segment,'horizon':h,'policy':name,'year':year,
                              'sessions':len(rr),'calendar_return':float((1+rr).prod()-1)})
                        episodes.append({'segment':segment,'horizon':h,'policy':name,**drawdown_episode(c)})
                    for name in ('declining_low_pressure','ongoing_repair'):
                        s=sig[name] if name in sig else old['dot_repair']
                        result=ex.account(t,s,valid,h,.0005,extra_delay=1,
                            exit_condition=xt['ongoing_exit'] if name=='ongoing_repair' else None)
                        delay.append({'segment':segment,'horizon':h,'policy':name,'extra_entry_sessions':1,**result['metrics']})
                        result['curve'].to_csv(out/'private'/f'{segment}_h{h}_delay1_{name}.csv')
            print('CANDIDATE_AUDIT_PHASE',segment,phase,flush=True)
    adj=holm([x['p_raw'] for x in tests])
    for row,pv in zip(tests,adj):row['p_holm_all24']=float(pv)
    pd.DataFrame(tests).to_csv(out/'paired_tests.csv',index=False)
    pd.DataFrame(matched).to_csv(out/'exposure_matches.csv',index=False)
    pd.DataFrame(annual).to_csv(out/'annual_returns.csv',index=False)
    pd.DataFrame(episodes).to_csv(out/'drawdown_episodes.csv',index=False)
    pd.DataFrame(delay).to_csv(out/'delay_accounts.csv',index=False)
    ev=pd.concat(events,ignore_index=True)
    ev.groupby(['segment','phase','horizon','policy']).agg(events=('ticker','size'),dates=('origin','nunique'),
       mean_net=('net_return','mean'),median_net=('net_return','median'),market_relative=('sector_excess','mean'),
       closing_low_holds=('prior_low_holds','mean'),mean_close_mae=('mae_close','mean')).to_csv(out/'information_decomposition.csv')
    ex.write_json(out/'RUN_RECEIPT.json',{'status':'COMPLETE','comparisons':len(tests),'exposure_matches':len(matched),
       'delay_accounts':len(delay),'holm_rejections':int(np.sum(adj<.05)),'outcome_guided_exploratory':True,'may_trade':False,
       'code_sha256':hashlib.sha256((root/'audit.py').read_bytes()).hexdigest()})
    print('CANDIDATE_AUDIT_COMPLETE',len(tests),len(matched),len(delay),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();run(a.root)
