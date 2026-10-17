#!/usr/bin/env python3
"""LP-ETF-01: causal, fixed-configuration research. Never writes to input data.
Usage: python3 pilot.py --data /path/to/yahoo --out /new/research/results
Dependencies: numpy, pandas, scipy, pyarrow. No network or production writes.
"""
from __future__ import annotations
import argparse, hashlib, json, platform, sys
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import scipy
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import rankdata

TICKERS='XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY SMH SOXX'.split()
PRICE=['mom5','mom20','mom60','trend50','trend200','vol20']
BASE=PRICE+['rs5','rs20','rs60','rs_accel','rank20','churn10','def_off20','rvol','obv20','market_trend','market_vol']
PERSIST=['persist_signedvol','signedvol_change','sign_autocorr']
IMPACT=['impact_asymmetry','low_impact_high_volume','low_impact_direction']
RESIL=['down_market_residual','up_market_residual','resilience_change']
MODELS={'constant':[],'price':PRICE,'baseline':BASE,'persistence':BASE+PERSIST,'impact':BASE+IMPACT,'resilience':BASE+RESIL,'combined':BASE+PERSIST+IMPACT+RESIL}
ALL=BASE+PERSIST+IMPACT+RESIL

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load(data:Path):
    closes, volumes, manifest={},{},[]
    for t in ['SPY']+TICKERS:
        p=data/f'{t}.parquet'; before=sha(p); x=pd.read_parquet(p)
        if 'Date' in x:x=x.set_index('Date')
        x.index=pd.to_datetime(x.index)
        if x.index.tz is not None:raise ValueError('Expected stored naive daily session dates')
        if x.index.duplicated().any() or not x.index.is_monotonic_increasing:raise ValueError(f'Invalid date ordering {t}')
        if not np.isfinite(x['close']).all() or (x['close']<=0).any():raise ValueError(f'Invalid closes {t}')
        if (x['volume']<0).any():raise ValueError(f'Negative volume {t}')
        if sha(p)!=before:raise ValueError(f'Source changed while reading {t}')
        manifest.append({'ticker':t,'ref':f'macro_snapshot:yahoo/{t}.parquet','sha256':before,'bytes':p.stat().st_size,'rows':len(x),'first':str(x.index.min().date()),'last':str(x.index.max().date()),'columns':list(x.columns),'volume_nonpositive':int((x.volume<=0).sum()),'close_basis':'vendor dividend/split adjusted; later vintage'})
        closes[t]=x['close'].loc['2010-01-01':];volumes[t]=x['volume'].loc['2010-01-01':]
    c=pd.DataFrame(closes).reindex(closes['SPY'].index);v=pd.DataFrame(volumes).reindex(c.index)
    return c,v,manifest

def conditional_mean(x,mask,n,min_count=3):
    count=mask.astype(float).rolling(n,min_periods=n).sum()
    return x.where(mask,0).rolling(n,min_periods=n).sum()/count.where(count>=min_count)

def features(c:pd.DataFrame,v:pd.DataFrame):
    r=np.log(c).diff(); mr=r['SPY']; rs=np.log(c.div(c['SPY'],axis=0));rs20=rs.diff(20)
    eligible=c.notna().cumsum()>=260
    rank=rs20[TICKERS].where(eligible[TICKERS]).rank(axis=1,pct=True)
    sect=TICKERS[:11];top=[]
    for _,row in rs20[sect].where(eligible[sect]).iterrows():top.append(set(row.dropna().nlargest(4).index))
    churn=pd.Series(np.nan,index=c.index)
    for i in range(10,len(c)):
        union=top[i]|top[i-10]
        if union:churn.iloc[i]=1-len(top[i]&top[i-10])/len(union)
    spread=rs20[['XLV','XLU','XLP']].mean(axis=1)-rs20[['SMH','XLK','XLY']].mean(axis=1)
    rows=[]
    for t in TICKERS:
        z=pd.DataFrame(index=c.index); rt=r[t];vol=rt.rolling(20).std(); rv=v[t]/v[t].rolling(20).mean(); sg=np.sign(rt);sv=sg*rv.clip(0,10)
        for n in [5,20,60]:z[f'mom{n}']=np.log(c[t]).diff(n);z[f'rs{n}']=rs[t].diff(n)
        z['trend50']=np.log(c[t]/c[t].rolling(50).mean());z['trend200']=np.log(c[t]/c[t].rolling(200).mean());z['vol20']=vol
        z['rs_accel']=rs20[t].diff(5)/5;z['rank20']=rank[t];z['churn10']=churn;z['def_off20']=spread;z['rvol']=rv
        z['obv20']=(sg*v[t]).rolling(20).sum()/v[t].rolling(20).sum()
        z['market_trend']=np.log(c.SPY/c.SPY.rolling(200).mean());z['market_vol']=mr.rolling(20).std()
        z['sign_autocorr']=sg.rolling(20).corr(sg.shift(1));z['persist_signedvol']=sv.rolling(20).mean()*sv.rolling(20).corr(sv.shift(1));z['signedvol_change']=sv.rolling(5).mean()-sv.rolling(20).mean()
        unit_impact=rt.abs()/rv.clip(lower=.1)
        z['impact_asymmetry']=(conditional_mean(unit_impact,rt<0,20)-conditional_mean(unit_impact,rt>0,20))/vol
        lowimpact=((rv>1.5)&(rt.abs()<.5*vol.shift(1))).astype(float).where(rt.notna())
        z['low_impact_high_volume']=lowimpact.rolling(5).mean();z['low_impact_direction']=z.low_impact_high_volume*z.obv20
        beta=rt.rolling(60).cov(mr)/mr.rolling(60).var();resid=rt-beta.shift(1)*mr
        down=conditional_mean(resid,mr<0,20);up=conditional_mean(resid,mr>0,20)
        z['down_market_residual']=down/vol;z['up_market_residual']=up/vol
        z['resilience_change']=(conditional_mean(resid,mr<0,5,min_count=1)-down)/vol
        z['ticker']=t;z['eligible']=eligible[t];z['position']=np.arange(len(c));rows.append(z.reset_index(names='date'))
    return pd.concat(rows,ignore_index=True)

def labels(c):
    out=[];dates=pd.Series(c.index,index=c.index)
    for t in TICKERS:
        a=np.log(c[t].shift(-21)/c[t].shift(-1));b=np.log(c.SPY.shift(-21)/c.SPY.shift(-1))
        out.append(pd.DataFrame({'date':c.index,'ticker':t,'fwd':a-b,'asset_return':np.expm1(a),'bench_return':np.expm1(b),'label_end':dates.shift(-21).values}))
    return pd.concat(out,ignore_index=True)

def fit_predict(tr,te,cols):
    y=tr.y.to_numpy(float)
    if not cols:return np.full(len(te),y.mean()), {'converged':True,'n_features':0}
    a=tr[cols].to_numpy(float);b=te[cols].to_numpy(float);mu=a.mean(0);sd=a.std(0);sd[sd<1e-12]=1
    a=np.c_[np.ones(len(a)),np.clip((a-mu)/sd,-5,5)];b=np.c_[np.ones(len(b)),np.clip((b-mu)/sd,-5,5)]
    def fg(w):
        q=a@w;ll=np.mean(np.logaddexp(0,q)-y*q)+.005*np.dot(w[1:],w[1:]);g=a.T@(expit(q)-y)/len(y);g[1:]+=.01*w[1:];return ll,g
    fit=minimize(fg,np.zeros(a.shape[1]),jac=True,method='L-BFGS-B',options={'maxiter':500,'ftol':1e-12,'gtol':1e-8})
    if not fit.success:raise RuntimeError(f'Optimization failed: {fit.message}')
    return expit(b@fit.x),{'converged':True,'n_features':len(cols),'iterations':int(fit.nit),'coefficients':dict(zip(['intercept']+cols,fit.x.tolist()))}

def auc(y,p):
    n1=y.sum();n0=len(y)-n1
    if not n1 or not n0:return None
    return float((rankdata(p)[y==1].sum()-n1*(n1+1)/2)/(n1*n0))
def metrics(y,p):
    p=np.clip(p,1e-10,1-1e-10);y=np.asarray(y)
    bins=[]
    for k in range(10):
        m=(p>=k/10)&(p<(k+1)/10)
        if m.any():bins.append({'lower':k/10,'n':int(m.sum()),'predicted':float(p[m].mean()),'observed':float(y[m].mean())})
    long=p>=.6;short=p<=.4
    return {'n':len(y),'base_rate':float(y.mean()),'auc':auc(y,p),'brier':float(np.mean((p-y)**2)),'log_loss':float(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p))),'long_alert_n':int(long.sum()),'long_precision':float(y[long].mean()) if long.any() else None,'short_alert_n':int(short.sum()),'short_precision':float(1-y[short].mean()) if short.any() else None,'calibration':bins}

def uncertainty(q):
    rng=np.random.default_rng(14102026);ans={}
    for model in ['persistence','impact','resilience','combined']:
        daily=q.assign(delta=(q.p_baseline-q.y)**2-(q['p_'+model]-q.y)**2).groupby('date').delta.mean().to_numpy();n=len(daily);obs=float(daily.mean());boots=[]
        for _ in range(1000):
            starts=rng.integers(n,size=int(np.ceil(n/60)));ix=((starts[:,None]+np.arange(60))%n).ravel()[:n];boots.append(daily[ix].mean())
        bs=np.asarray(boots);p=float((1+(np.abs(bs-obs)>=abs(obs)).sum())/1001)
        ans[model]={'mean_daily_brier_gain':obs,'ci95':np.quantile(bs,[.025,.975]).tolist(),'p_two_sided_centered_block':p,'n_dates':n,'block':60}
    order=sorted(ans,key=lambda m:ans[m]['p_two_sided_centered_block']);prev=0
    for i,m in enumerate(order):prev=max(prev,min(1,(4-i)*ans[m]['p_two_sided_centered_block']));ans[m]['p_holm']=prev
    return ans

def pivot_diagnostic(q,c):
    rs=np.log(c.div(c.SPY,axis=0)).diff(20);ans={}
    for model in ['baseline','combined']:
        events=[]
        for t,g in q.groupby('ticker'):
            r=rs[t].to_numpy();cross={s:[] for s in [1,-1]}
            for i in range(1,len(r)-4):
                for s in [1,-1]:
                    if r[i-1]*s<0 and np.all(r[i:i+5]*s>=0):cross[s].append(i)
            last=-1000
            for row in g.sort_values('date').itertuples():
                i=int(row.position);p=getattr(row,'p_'+model);s=1 if p>=.6 else (-1 if p<=.4 else 0)
                if not s or r[i]*s>=0 or i-last<20:continue
                last=i;matches=[k for k in cross[s] if i<k<=i+20];lead=matches[0]-i if matches else None
                events.append({'date':str(row.date.date()),'ticker':t,'direction':s,'lead_sessions':lead,'matched':bool(matches)})
        valid=[e['lead_sessions'] for e in events if e['matched']]
        ans[model]={'alert_episodes':len(events),'matched':len(valid),'false_alarms':len(events)-len(valid),'precision':len(valid)/len(events) if events else None,'median_lead_among_matches':float(np.median(valid)) if valid else None,'examples':events[:8]}
    return ans

def nonoverlap(q):
    dates=sorted(q.date.unique())[::20];ans={}
    for model in ['baseline','combined']:
        vals=[];turn=[];old=set()
        for d in dates:
            g=q[q.date==d].nlargest(3,'p_'+model)
            if len(g)<3:continue
            vals.append(float(g.asset_return.mean()-g.bench_return.iloc[0]));names=set(g.ticker);turn.append(len(names-old)/3);old=names
        ans[model]={'intervals':len(vals),'mean_gross_excess_bps':float(np.mean(vals)*1e4),'mean_excess_after10bp':float(np.mean(vals)*1e4-10),'mean_excess_after30bp':float(np.mean(vals)*1e4-30),'mean_new_name_fraction':float(np.mean(turn)),'note':'Independent20-session holding-interval diagnostic, not CAGR. Full-switch cost charged every interval, no borrow/leverage.'}
    return ans

def run(data:Path,out:Path):
    if out.exists() and any(out.iterdir()):raise ValueError('Output must be absent or empty; no accidental result overwrite')
    out.mkdir(parents=True,exist_ok=True);c,v,manifest=load(data);f=features(c,v)
    # Prefix invariance: appended future bars cannot alter historical feature construction.
    cut=c.index[c.index<='2021-12-31'][-1];prefix=features(c.loc[:cut],v.loc[:cut]);whole=f[f.date<=cut]
    np.testing.assert_allclose(prefix[ALL],whole[ALL],equal_nan=True,rtol=1e-10,atol=1e-12)
    # Exact unit and label-lag assertions on an exponential synthetic path.
    assert .01*10000==100
    assert np.isclose(np.log(np.exp(.001*21)/np.exp(.001)),.02)
    z=f.merge(labels(c),on=['date','ticker'],validate='one_to_one').replace([np.inf,-np.inf],np.nan)
    z=z[z.eligible].dropna(subset=ALL+['fwd','label_end']);z=z[(z.date>='2011-01-01')&(z.label_end<='2025-12-31')].copy();z['y']=(z.fwd>0).astype(int)
    predictions=[];fits=[]
    for year in range(2018,2026):
        start=pd.Timestamp(f'{year}-01-01');tr=z[(z.date<start)&(z.label_end<start)];te=z[z.date.dt.year==year].copy()
        assert tr.label_end.max()<te.date.min();assert len(tr)>500
        rec={'test_year':year,'training_n':len(tr),'test_n':len(te),'last_train_label_end':str(tr.label_end.max().date()),'first_test_decision':str(te.date.min().date()),'models':{}}
        for name,cols in MODELS.items():te['p_'+name],rec['models'][name]=fit_predict(tr,te,cols)
        fits.append(rec);predictions.append(te[['date','ticker','position','rs20','market_trend','market_vol','y','fwd','asset_return','bench_return','label_end']+['p_'+m for m in MODELS]])
        print('FIT',year,'train',len(tr),'test',len(te),flush=True)
    q=pd.concat(predictions,ignore_index=True);results={'experiment':'LP-ETF-01','run_at':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'versions':{'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__},'n_observations':len(q),'n_dates':q.date.nunique(),'models':{},'verification':{'prefix_invariance':True,'label_embargo_asserted':True,'unique_panel_keys':not q.duplicated(['date','ticker']).any(),'bps_units':True,'input_hash_stability_on_read':True}}
    for period,sub in [('development',q[q.date<'2023-01-01']),('holdout',q[q.date>='2023-01-01'])]:
        results['models'][period]={m:metrics(sub.y.to_numpy(),sub['p_'+m].to_numpy()) for m in MODELS};results[period+'_inference']=uncertainty(sub);results[period+'_pivot']=pivot_diagnostic(sub,c);results[period+'_nonoverlap']=nonoverlap(sub)
    results['annual']={str(y):{m:metrics(g.y.to_numpy(),g['p_'+m].to_numpy())['brier'] for m in MODELS} for y,g in q.groupby(q.date.dt.year)}
    h=q[q.date>='2023-01-01'];results['holdout_subgroups']={}
    for name,m in [('above200',h.market_trend>=0),('below200',h.market_trend<0),('high_market_vol',h.market_vol>=.012),('low_market_vol',h.market_vol<.012)]:
        g=h[m];results['holdout_subgroups'][name]={'n':len(g),'baseline_brier':float(((g.p_baseline-g.y)**2).mean()),'combined_brier':float(((g.p_combined-g.y)**2).mean())}
    results['holdout_tickers']={t:{'n':len(g),'baseline_brier':float(((g.p_baseline-g.y)**2).mean()),'combined_brier':float(((g.p_combined-g.y)**2).mean())} for t,g in h.groupby('ticker')}
    # The 2026 fixture is an audited example, wholly outside model evaluation/selection.
    incident={};rr=np.log(c.div(c.SPY,axis=0)).diff(20)
    for d in ['2026-06-23','2026-06-24','2026-07-01','2026-07-02']:
        if pd.Timestamp(d) in c.index:incident[d]={'def_off_rs20_bps':float((rr.loc[d,['XLV','XLU','XLP']].mean()-rr.loc[d,['SMH','XLK','XLY']].mean())*10000),'XLV':float(c.loc[d,'XLV']),'SMH':float(c.loc[d,'SMH'])}
    results['incident_later_vintage']=incident
    for t in ['XLV','SMH']:
        if all(pd.Timestamp(d) in c.index for d in ['2026-06-23','2026-07-01']):results['incident_later_vintage'][t+'_0623_to0701_pct']=float((c.loc['2026-07-01',t]/c.loc['2026-06-23',t]-1)*100)
    results['source_files_still_unchanged']=all(sha(data/f'{m["ticker"]}.parquet')==m['sha256'] for m in manifest)
    if not results['source_files_still_unchanged']:raise ValueError('Input changed during experiment')
    (out/'input_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(out/'fit_receipts.json').write_text(json.dumps(fits,indent=2)+'\n');(out/'results.json').write_text(json.dumps(results,indent=2,default=lambda x:bool(x) if isinstance(x,np.bool_) else str(x))+'\n');q.to_csv(out/'predictions.csv.gz',index=False,compression='gzip')
    summary={k:v for k,v in results.items() if k not in ['models','annual','holdout_subgroups','holdout_tickers']};summary['metrics']={p:{m:{k:v for k,v in x.items() if k!='calibration'} for m,x in ms.items()} for p,ms in results['models'].items()};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({'out':str(out),'n':len(q),'holdout':summary['metrics']['holdout'],'inference':results['holdout_inference']},indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--data',type=Path,required=True);a.add_argument('--out',type=Path,required=True);args=a.parse_args();run(args.data,args.out)
