"""Chronological, non-trading calibration check of three distinct entry outcomes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
import experiment as ex
from analyze import block_mean_interval,holm

FEATURES=['log_risk21','drawdown63','own5_scaled','momentum126_21','relative_momentum',
          'market5','above20_fraction','above20_change','washout_fraction','low_pressure_change',
          'log_vix','vix_trend','vvix_trend','term_structure']
MODELS={'price':5,'context':12,'vol_extension':14}
TARGETS=['positive_net','positive_sector_relative','closing_low_holds']


def fit_logistic(x,y):
    x=np.asarray(x,float);y=np.asarray(y,float)
    if x.ndim!=2 or len(x)!=len(y) or len(y)<150 or not np.isfinite(x).all():raise ValueError('Invalid training rows')
    if not np.isin(y,[0,1]).all() or min(np.sum(y==0),np.sum(y==1))<20:raise ValueError('Thin training classes')
    center=x.mean(axis=0);scale=x.std(axis=0);scale=np.where(scale<1e-10,1.,scale)
    z=np.clip((x-center)/scale,-6,6);a=np.c_[np.ones(len(z)),z]
    def fun(beta):
        linear=a@beta
        value=np.logaddexp(0,linear).sum()-y@linear+.5*np.square(beta[1:]).sum()
        grad=a.T@(expit(linear)-y);grad[1:]+=beta[1:]
        return float(value),grad
    initial=np.zeros(a.shape[1]);p=(y.sum()+.5)/(len(y)+1);initial[0]=np.log(p/(1-p))
    result=minimize(fun,initial,method='L-BFGS-B',jac=True,options={'maxiter':1000,'ftol':1e-12,'gtol':1e-7})
    if not result.success or not np.isfinite(result.fun):raise ValueError('Logistic fit did not converge')
    return {'center':center,'scale':scale,'beta':result.x,'n':len(y),'success':True}


def predict_logistic(fit,x):
    x=np.asarray(x,float)
    if x.ndim!=2 or not np.isfinite(x).all():raise ValueError('Invalid prediction input')
    z=np.clip((x-fit['center'])/fit['scale'],-6,6)
    return np.clip(expit(np.c_[np.ones(len(z)),z]@fit['beta']),1e-8,1-1e-8)


def feature_frame(price,total,vol,ctx,ticker):
    p=price[ex.SECTORS];t=total[ex.SECTORS]
    daily=t.pct_change(fill_method=None);sigma=daily.rolling(21).std()
    momentum=t.shift(21)/t.shift(126)-1
    market_momentum=total.SPY.shift(21)/total.SPY.shift(126)-1
    low=p.le(p.shift(1).rolling(20).min()).astype(float).mean(axis=1).rolling(5).mean()
    f=pd.DataFrame(index=p.index)
    f['log_risk21']=np.log(sigma[ticker]*np.sqrt(252))
    f['drawdown63']=ctx['drawdown'][ticker]
    f['own5_scaled']=ctx['own5'][ticker]/(sigma[ticker]*np.sqrt(5))
    f['momentum126_21']=momentum[ticker]
    f['relative_momentum']=momentum[ticker]-market_momentum
    f['market5']=ctx['market5'];f['above20_fraction']=ctx['above20']/9
    f['above20_change']=ctx['above20'].diff(5)/9
    f['washout_fraction']=ctx['wash_count']/9
    f['low_pressure_change']=low.diff(5)
    f['log_vix']=np.log(vol.VIX)
    f['vix_trend']=vol.VIX.rolling(10,min_periods=10).mean()/vol.VIX.rolling(30,min_periods=30).mean()-1
    f['vvix_trend']=vol.VVIX.rolling(10,min_periods=10).mean()/vol.VVIX.rolling(30,min_periods=30).mean()-1
    f['term_structure']=np.log(vol.VIX/vol.VIX3M)
    return f[FEATURES].replace([np.inf,-np.inf],np.nan)


def build_events(root):
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text());rows=[];cal=[];missing=[]
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,manifest);ctx=ex.context(p,t,v);cal.extend(p.index)
        e=pd.read_parquet(root/'primary_results/private'/f'events_{segment}_0.parquet')
        e=e[e.policy.eq('dot')&e.horizon.eq(21)].copy()
        frames={k:feature_frame(p,t,v,ctx,k) for k in ex.SECTORS}
        for row in e.itertuples():
            x=frames[row.ticker].loc[pd.Timestamp(row.origin)]
            if not np.isfinite(x.to_numpy()).all():
                missing.append({'origin':row.origin,'ticker':row.ticker,'reason':'COMMON_FEATURE_SUPPORT_MISSING'});continue
            rows.append({'event_id':segment+':'+row.ticker+':'+row.origin,'segment':segment,'origin':row.origin,'end':row.end,
               'ticker':row.ticker,'positive_net':int(row.net_return>0),'positive_sector_relative':int(row.sector_excess>0),
               'closing_low_holds':int(row.prior_low_holds),**x.to_dict()})
    e=pd.DataFrame(rows).sort_values(['origin','ticker']).reset_index(drop=True)
    return e,pd.DatetimeIndex(sorted(set(cal))),missing


def walk_forward(events,calendar):
    events=events.sort_values(['origin','ticker']).reset_index(drop=True)
    origins=pd.to_datetime(events.origin);ends=pd.to_datetime(events.end)
    predictions=[];fits=[];cache={};last_fit=None
    for day in sorted(origins.unique()):
        day=pd.Timestamp(day);ordinal=int(calendar.get_loc(day))
        train=ends<day;today=origins.eq(day);tx=events.loc[train,FEATURES].to_numpy();xx=events.loc[today,FEATURES].to_numpy()
        due=last_fit is None or ordinal-last_fit>=63
        if due:
            cache={};last_fit=ordinal
            for target in TARGETS:
                y=events.loc[train,target].to_numpy()
                if len(y)<150 or min(np.sum(y==0),np.sum(y==1))<20:
                    fits.append({'origin':str(day.date()),'target':target,'n':len(y),'status':'INSUFFICIENT_MATURED_LABELS'});continue
                package={'frequency':float((y.sum()+.5)/(len(y)+1))}
                try:
                    for model,n in MODELS.items():package[model]=fit_logistic(tx[:,:n],y)
                except ValueError as err:
                    fits.append({'origin':str(day.date()),'target':target,'n':len(y),'status':'FIT_FAILED','reason':str(err)});continue
                package['fit_date']=str(day.date());package['label_end_max']=str(ends[train].max().date());cache[target]=package
                fits.append({'origin':str(day.date()),'target':target,'n':len(y),'label_end_max':package['label_end_max'],'status':'COMPLETE'})
        for target,package in cache.items():
            probs={'frequency':np.full(len(xx),package['frequency'])}
            for model,n in MODELS.items():probs[model]=predict_logistic(package[model],xx[:,:n])
            for j,i in enumerate(np.flatnonzero(today.to_numpy())):
                y=int(events.loc[i,target])
                for model,p in probs.items():
                    q=float(p[j]);loss=-y*np.log(q)-(1-y)*np.log(1-q)
                    predictions.append({'event_id':events.loc[i,'event_id'],'origin':str(day.date()),'segment':events.loc[i,'segment'],
                        'ticker':events.loc[i,'ticker'],'target':target,'model':model,'outcome':y,'probability':q,
                        'log_loss':float(loss),'brier':float((q-y)**2),'fit_date':package['fit_date'],'training_last_outcome':package['label_end_max']})
    return pd.DataFrame(predictions),fits


def main(root):
    out=root/'prediction_results'
    if out.exists():raise ValueError('Prediction-check output exists')
    out.mkdir();(out/'private').mkdir()
    events,calendar,missing=build_events(root);pred,fit=walk_forward(events,calendar)
    pred.to_parquet(out/'private/predictions.parquet');ex.write_json(out/'fit_receipts.json',fit)
    ex.write_json(out/'missing_common_support.json',missing)
    summaries=pred.groupby(['target','model']).agg(predictions=('outcome','size'),dates=('origin','nunique'),
       log_loss=('log_loss','mean'),brier=('brier','mean'),mean_probability=('probability','mean'),observed_rate=('outcome','mean'))
    summaries.to_csv(out/'prediction_scores.csv')
    pred.groupby(['segment','target','model']).agg(predictions=('outcome','size'),dates=('origin','nunique'),
       log_loss=('log_loss','mean'),brier=('brier','mean')).to_csv(out/'era_prediction_scores.csv')
    tests=[]
    for target in TARGETS:
        for a,b in [('price','frequency'),('context','price'),('vol_extension','context')]:
            for metric in ['log_loss','brier']:
                x=pred[(pred.target==target)&(pred.model==a)].groupby('origin')[metric].mean()
                y=pred[(pred.target==target)&(pred.model==b)].groupby('origin')[metric].mean()
                if not x.index.equals(y.index):raise AssertionError('Not common prediction dates')
                # No fabricated outcome rows fill non-event days. Calendar block sampling
                # preserves zero-weight gaps, and samples numerator/denominator together.
                ix=calendar[(calendar>=pd.Timestamp(x.index.min()))&(calendar<=pd.Timestamp(x.index.max()))]
                z=(x-y).rename_axis('date');z.index=pd.to_datetime(z.index);daily=z.reindex(ix)
                n=len(ix);observed=float(daily.mean());a0=daily.fillna(0).to_numpy();w=daily.notna().astype(float).to_numpy()
                rng=np.random.default_rng(20261114);k=int(np.ceil(n/63));est=[]
                for _ in range(2000):
                    starts=rng.integers(0,n,k);idx=((starts[:,None]+np.arange(63))%n).ravel()[:n]
                    if w[idx].sum():est.append(float(a0[idx].sum()/w[idx].sum()))
                vals=np.asarray(est);pv=(1+np.count_nonzero(np.abs(vals-observed)>=abs(observed)))/(len(vals)+1)
                ci=np.quantile(vals,[.025,.975]);tests.append({'target':target,'contrast':a+' - '+b,'metric':metric,'dates':len(x),
                    'difference':observed,'lower':float(ci[0]),'upper':float(ci[1]),'p_raw':float(pv)})
    hp=holm([r['p_raw'] for r in tests])
    for r,pv in zip(tests,hp):r['p_holm_all18']=float(pv)
    pd.DataFrame(tests).to_csv(out/'paired_prediction_tests.csv',index=False)
    bins=pred.copy();bins['bin']=pd.cut(bins.probability,[0,.2,.4,.6,.8,1.],include_lowest=True)
    bins.groupby(['target','model','bin'],observed=True).agg(n=('outcome','size'),mean_probability=('probability','mean'),frequency=('outcome','mean')).to_csv(out/'calibration.csv')
    ex.write_json(out/'RUN_RECEIPT.json',{'status':'COMPLETE','input_events':len(events),'missing_events':len(missing),
       'prediction_rows':len(pred),'unique_issued_events':pred.event_id.nunique(),'issued_dates':pred.origin.nunique(),
       'fits':len(fit),'tests':len(tests),'holm_rejections':int(np.sum(hp<.05)),
       'source_sha256':hashlib.sha256((root/'prediction_check.py').read_bytes()).hexdigest(),
       'outcome_guided_retrospective':True,'may_rank':False,'may_size':False,'may_trade':False})
    print('CONDITIONAL_PREDICTION_COMPLETE',len(events),len(pred),pred.event_id.nunique(),int(np.sum(hp<.05)),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();main(a.root)
