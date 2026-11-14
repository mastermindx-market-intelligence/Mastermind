"""Fixed, chronological, shrinkage-regularized conditional research models.

Features/targets remain distinct. These probabilities have no production authority.
"""
from __future__ import annotations
import argparse,hashlib,json,warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from evaluate import write_json

PRICE=['return_21','return_63','drawdown_63','drawdown_252','low_distance21','price_above200','rv21','rv126','efficiency252']
CYCLE=['w2_hist','w2_hist_delta','w2_depth_rank','month_hist_delta','drawdown_rank',
       'log_episode_age','log_prior_failures','failed_cycle_repair','monthly_conflict']
COHORT=['peer_return_5','peer_return_21','peer_breadth_change','peer_low_pressure_change','relative_resilience21',
        'market_resilience21','down_market_resilience21','residual_vol_ratio','market_beta',
        'beh_peer_return_21','beh_peer_breadth_change','beh_relative_resilience21','repair_interaction']
VOL=['market_return21','vix_level','vix_trend','vvix_level','vvix_trend']
SETS={'price':PRICE,'cycle':PRICE+CYCLE,'cohort':PRICE+CYCLE+COHORT,'volatility':PRICE+CYCLE+COHORT+VOL}
TARGETS=['positive_net','positive_peer_excess','low_held']


def transform(frame):
    z=frame.copy()
    z['log_episode_age']=np.log1p(z.episode_age.clip(lower=0))
    z['log_prior_failures']=np.log1p(z.prior_failed_attempts.clip(lower=0))
    z['failed_cycle_repair']=(z.prior_failed_attempts>0).astype(float)*z.w2_hist_delta
    z['monthly_conflict']=((z.month_hist_delta<0)&(z.w2_hist_delta>0)).astype(float)
    z['repair_interaction']=z.w2_hist_delta*z.peer_breadth_change
    return z


def training_rows(frame,at,target,horizon):
    cutoff=pd.Timestamp(at)
    return frame.loc[(frame.horizon==horizon)&(frame.outcome_status=='COMPLETE')&
       (pd.to_datetime(frame.end_date)<cutoff)&~frame.exposed_design_case&frame[target].notna()].copy()


def date_weights(frame):
    counts=frame.groupby('origin').event_id.transform('count').to_numpy(float)
    w=1/counts
    return w/w.mean()


class ConditionalLogit:
    def __init__(self,columns,penalty=.01):
        self.columns=list(columns);self.penalty=penalty;self.fitted=False
    def _matrix(self,frame,fit=False):
        raw=frame[self.columns].to_numpy(dtype=float,copy=True);raw[~np.isfinite(raw)]=np.nan
        if fit:
            self.median=np.array([np.nanmedian(raw[:,j]) if np.isfinite(raw[:,j]).any() else 0. for j in range(raw.shape[1])])
            filled=np.where(np.isfinite(raw),raw,self.median)
            self.scale=np.std(filled,axis=0);self.scale[self.scale<1e-8]=1.
            self.levels={key:sorted(frame[key].astype(str).unique()) for key in ['group','family','symbol']}
        missing=~np.isfinite(raw)
        numeric=np.clip((np.where(missing,self.median,raw)-self.median)/self.scale,-8,8)
        blocks=[np.ones((len(frame),1)),numeric,missing.astype(float)]
        penalties=[np.zeros(1),np.ones(len(self.columns)),np.ones(len(self.columns))*2]
        for key in ['group','family','symbol']:
            vals=frame[key].astype(str).to_numpy()
            blocks.append(np.column_stack([vals==v for v in self.levels[key]]).astype(float))
            penalties.append(np.ones(len(self.levels[key]))*(5 if key=='symbol' else 2))
        self.penalty_vector=np.concatenate(penalties)
        return np.concatenate(blocks,axis=1)
    def fit(self,frame,target):
        y=frame[target].to_numpy(float)
        if len(frame)<100 or len(np.unique(y))<2:raise ValueError('Insufficient mature labels')
        x=self._matrix(frame,True);w=date_weights(frame);den=w.sum()
        penalty=self.penalty*self.penalty_vector
        def objective(beta):
            logits=x@beta
            value=np.sum(w*(np.logaddexp(0,logits)-y*logits))/den+.5*np.sum(penalty*beta*beta)
            grad=x.T@(w*(expit(logits)-y))/den+penalty*beta
            return value,grad
        result=minimize(objective,np.zeros(x.shape[1]),jac=True,method='L-BFGS-B',options={'maxiter':300,'ftol':1e-10,'gtol':1e-7})
        if not result.success or not np.isfinite(result.x).all():raise RuntimeError('Conditional fit did not converge')
        self.beta=result.x;self.fitted=True;self.last_training_end=pd.to_datetime(frame.end_date).max();return self
    def predict(self,frame):
        if not self.fitted:raise ValueError('Unfitted model')
        return np.clip(expit(self._matrix(frame)@self.beta),1e-6,1-1e-6)


def frequency(train,test,target):
    global_rate=(train[target].sum()+1)/(len(train)+2)
    group=train.groupby(['symbol','family'])[target].agg(['sum','count'])
    values=[]
    for s,fam in zip(test.symbol,test.family):
        if (s,fam) in group.index:
            row=group.loc[(s,fam)];values.append((row['sum']+20*global_rate)/(row['count']+20))
        else:values.append(global_rate)
    return np.asarray(values)


def losses(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float)
    if (p<=0).any() or (p>=1).any() or not np.isfinite(p).all():raise ValueError('Invalid probability')
    return {'log_loss':-(y*np.log(p)+(1-y)*np.log(1-p)),'brier':(p-y)**2}


def block_interval(dates,values,repetitions=999,seed=6):
    dates=pd.DatetimeIndex(dates);values=np.asarray(values,float)
    # Calendar quarters keep same-date names together and approximate overlapping horizons.
    keys=dates.to_period('Q').astype(str);groups=[values[np.asarray(keys==k)] for k in sorted(set(keys))]
    if len(groups)<8:return {'difference':float(np.mean(values)),'lower':None,'upper':None,'p_raw':None,'blocks':len(groups)}
    rng=np.random.default_rng(seed);boot=[]
    for _ in range(repetitions):
        chosen=rng.integers(0,len(groups),len(groups));a=np.concatenate([groups[j] for j in chosen]);boot.append(a.mean())
    boot=np.asarray(boot);p=min(1.,2*min((1+np.sum(boot<=0))/(repetitions+1),(1+np.sum(boot>=0))/(repetitions+1)))
    return {'difference':float(np.mean(values)),'lower':float(np.quantile(boot,.025)),'upper':float(np.quantile(boot,.975)),'p_raw':p,'blocks':len(groups)}


def holm(frame,key='p_raw'):
    out=np.full(len(frame),np.nan);valid=np.flatnonzero(frame[key].notna())
    order=valid[np.argsort(frame.iloc[valid][key].to_numpy())];prior=0.
    for rank,i in enumerate(order):
        prior=max(prior,min(1.,float(frame.iloc[i][key])*(len(order)-rank)));out[i]=prior
    return out


def main(root):
    root=Path(root);dest=root/'model_results';dest.mkdir(exist_ok=False)
    events=transform(pd.read_parquet(root/'event_results/events.parquet'))
    for c in ['origin','entry_date','end_date']:events[c]=pd.to_datetime(events[c])
    issued=[];fit_log=[]
    eligible=events.loc[(events.origin>='2013-01-01') & (events.horizon.isin([21,63]))]
    dates=sorted(eligible.origin.unique())
    for horizon in [21,63]:
        for target in TARGETS:
            models={};train=None;refit_after=pd.Timestamp.min;fit_date=None
            for at in dates:
                at=pd.Timestamp(at);test=eligible.loc[(eligible.origin==at)&(eligible.horizon==horizon)]
                if test.empty:continue
                if at>=refit_after:
                    train=training_rows(events,at,target,horizon);models={};fit_date=at
                    refit_after=at+pd.offsets.BDay(63)
                    if len(train)<200 or train.origin.nunique()<60 or train[target].value_counts().min()<25:
                        fit_log.append({'at':at,'horizon':horizon,'target':target,'status':'INSUFFICIENT','rows':len(train)});continue
                    for name,columns in SETS.items():
                        try:models[name]=ConditionalLogit(columns).fit(train,target)
                        except (ValueError,RuntimeError) as exc:fit_log.append({'at':at,'horizon':horizon,'target':target,'model':name,'status':'FAILED','reason':str(exc)})
                    fit_log.append({'at':at,'horizon':horizon,'target':target,'status':'FIT','rows':len(train),'last_label_end':train.end_date.max(),'models':list(models)})
                if train is None or len(models)!=len(SETS):continue
                if not train.end_date.max()<at:raise AssertionError('Outcome available after fit clock')
                predictions={'frequency':frequency(train,test,target),**{name:model.predict(test) for name,model in models.items()}}
                for name,probs in predictions.items():
                    for (_,row),prob in zip(test.iterrows(),probs):
                        issued.append({'event_id':row.event_id,'origin':at,'symbol':row.symbol,'family':row.family,'group':row.group,
                          'segment':row.segment,'horizon':horizon,'target':target,'model':name,'probability':prob,
                          'outcome':row.get(target),'outcome_status':row.outcome_status,'end_date':row.end_date,
                          'exposed_design_case':row.exposed_design_case,'fit_date':fit_date,'last_training_end':train.end_date.max()})
            print('CONDITIONAL_MODEL_COMPLETE',horizon,target,flush=True)
    pred=pd.DataFrame(issued);pred.to_parquet(dest/'predictions.parquet',index=False);write_json(dest/'fit_log.json',fit_log)
    qualified=pred.loc[~pred.exposed_design_case&(pred.outcome_status=='COMPLETE')&pred.outcome.notna()].copy()
    for name,values in losses(qualified.outcome,qualified.probability).items():qualified[name]=values
    scores=qualified.groupby(['horizon','target','model']).agg(events=('event_id','size'),dates=('origin','nunique'),log_loss=('log_loss','mean'),brier=('brier','mean'),mean_probability=('probability','mean'),actual_rate=('outcome','mean')).reset_index()
    scores.to_csv(dest/'scores.csv',index=False)
    qualified.groupby(['horizon','target','group','model']).agg(events=('event_id','size'),log_loss=('log_loss','mean'),brier=('brier','mean')).reset_index().to_csv(dest/'group_scores.csv',index=False)
    contrasts=[]
    for (h,target),z in qualified.groupby(['horizon','target']):
        for high,base in [('price','frequency'),('cycle','price'),('cohort','cycle'),('volatility','cohort')]:
            for metric in ['log_loss','brier']:
                pivot=z.pivot(index=['event_id','origin'],columns='model',values=metric).dropna(subset=[high,base])
                bydate=(pivot[high]-pivot[base]).groupby(level='origin').mean()
                contrasts.append({'horizon':h,'target':target,'contrast':high+' - '+base,'metric':metric,**block_interval(bydate.index,bydate.to_numpy())})
    checks=pd.DataFrame(contrasts);checks['p_holm_family']=holm(checks);checks.to_csv(dest/'paired_tests.csv',index=False)
    pred.loc[pred.exposed_design_case].to_csv(dest/'MCD_EXPOSED_PREDICTIONS.csv',index=False)
    write_json(dest/'receipt.json',{'status':'COMPLETE','prediction_rows':len(pred),'qualified_event_horizon_target_model_rows':len(qualified),
       'unique_issued_events':pred.event_id.nunique(),'contrasts':len(checks),'holm_below_05':int((checks.p_holm_family<.05).sum()),
       'unvalidated_probabilities':True,'may_rank':False,'may_size':False,'may_trade':False,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    print('MODEL_STUDY_COMPLETE',len(pred),len(qualified),len(checks),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));main(ap.parse_args().root)
