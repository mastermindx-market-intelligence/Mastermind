"""Bounded group/family response extension and continuous-payoff evaluation."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit
from modeling import ConditionalLogit,SETS,transform,training_rows,date_weights,frequency,losses,block_interval,holm
from support_state import slow_state,cohort_state
from dynamics import relative_dynamics,cross_cycle
from evaluate import write_json
import features as f

EXTRA=['slow_mean_change','cohort_supported','relative_log5','relative_acceleration','cross_cycle_slow_improvement','cross_cycle_divergence']
COLUMNS=SETS['cohort']+EXTRA
RESPONSES=['w2_hist_delta','month_hist_delta','peer_breadth_change','relative_resilience21',
           'slow_mean_change','cohort_supported','relative_acceleration','drawdown_rank']


class ConditionalResponse(ConditionalLogit):
    def __init__(self,columns=COLUMNS,penalty=.01,heterogeneous=False):
        super().__init__(columns,penalty);self.heterogeneous=heterogeneous
    def _matrix(self,frame,fit=False):
        base=super()._matrix(frame,fit);penalty=self.penalty_vector.copy()
        if not self.heterogeneous:return base
        indexes=[1+self.columns.index(k) for k in RESPONSES if k in self.columns]
        blocks=[base];penalties=[penalty]
        for key in ['group','family']:
            for value in self.levels[key]:
                mask=(frame[key].astype(str).to_numpy()==value).astype(float)
                blocks.append(base[:,indexes]*mask[:,None]);penalties.append(np.full(len(indexes),5.))
        for a,b in [('slow_mean_change','efficiency252'),('cohort_supported','market_beta'),('relative_acceleration','rv126')]:
            if a in self.columns and b in self.columns:
                blocks.append((base[:,1+self.columns.index(a)]*base[:,1+self.columns.index(b)])[:,None]);penalties.append(np.array([5.]))
        self.penalty_vector=np.concatenate(penalties)
        return np.concatenate(blocks,axis=1)
    def fit_mean(self,frame,target):
        if len(frame)<100:raise ValueError('Insufficient mature payoffs')
        x=self._matrix(frame,True);y=frame[target].to_numpy(float);w=date_weights(frame);den=w.sum()
        if not np.isfinite(y).all():raise ValueError('Nonfinite training payoff')
        matrix=x.T@(x*w[:,None])/den+np.diag(self.penalty*self.penalty_vector)
        vector=x.T@(y*w)/den
        self.beta=np.linalg.solve(matrix,vector);self.fitted=True;self.last_training_end=pd.to_datetime(frame.end_date).max()
        return self
    def predict_mean(self,frame):
        if not self.fitted:raise ValueError('Unfitted model')
        return self._matrix(frame)@self.beta


def augment(root,events):
    all_frames={};parts=[]
    for segment in ['pre','post']:
        p,t,_,m=f.load_segment(root,segment)
        for symbol in sum(m['groups'].values(),[]):
            x=pd.read_parquet(root/'enriched'/segment/f'{symbol}.parquet')
            slow=slow_state(x);econ=cohort_state(x);relative=relative_dynamics(t[symbol],x.peer_return_1)
            base=pd.concat([slow[['slow_mean_change']],econ[['cohort_supported']],relative[['relative_log5','relative_acceleration']]],axis=1)
            for family in ['dot','rsi_macd_3d_cross']:
                cycle=cross_cycle(p[symbol],x[family].fillna(False),x.w2_hist,x.episode_number)
                z=base.join(cycle[['cross_cycle_slow_improvement','cross_cycle_divergence']]);z.index.name='origin'
                z=z.reset_index();z['symbol']=symbol;z['segment']=segment;z['family']=family;parts.append(z)
    added=pd.concat(parts,ignore_index=True)
    out=events.merge(added,on=['origin','symbol','segment','family'],how='left',validate='many_to_one')
    out['log_net']=np.log1p(out.net_return)
    out['log_peer_excess']=np.log1p(out.net_return)-np.log1p(out.peer_return)
    return out


def mean_prior(train,test,target):
    mean=float(train[target].mean());group=train.groupby(['symbol','family'])[target].agg(['sum','count'])
    return np.asarray([(group.loc[(s,fam),'sum']+20*mean)/(group.loc[(s,fam),'count']+20) if (s,fam) in group.index else mean for s,fam in zip(test.symbol,test.family)])


def main(root):
    root=Path(root);dest=root/'response_results';dest.mkdir(exist_ok=False)
    events=transform(pd.read_parquet(root/'event_results/events.parquet'))
    for key in ['origin','entry_date','end_date']:events[key]=pd.to_datetime(events[key])
    events=augment(root,events);events.to_parquet(dest/'augmented_events.parquet',index=False)
    eligible=events.loc[(events.origin>='2013-01-01')&events.horizon.isin([21,63])]
    dates=sorted(eligible.origin.unique());issued=[];fit_log=[]
    for horizon in [21,63]:
        for target in ['positive_net','positive_peer_excess','low_held','log_net','log_peer_excess']:
            continuous=target.startswith('log_');models={};train=None;refit=pd.Timestamp.min;fit_at=None
            for at in dates:
                at=pd.Timestamp(at);test=eligible.loc[(eligible.origin==at)&(eligible.horizon==horizon)]
                if test.empty:continue
                if at>=refit:
                    train=training_rows(events,at,target,horizon);models={};fit_at=at;refit=at+pd.offsets.BDay(63)
                    if len(train)<200 or train.origin.nunique()<60:continue
                    if not continuous and (train[target].nunique()<2 or train[target].value_counts().min()<25):continue
                    for name,heterogeneous in [('shared',False),('conditional_response',True)]:
                        try:
                            model=ConditionalResponse(heterogeneous=heterogeneous)
                            models[name]=model.fit_mean(train,target) if continuous else model.fit(train,target)
                        except (ValueError,RuntimeError,np.linalg.LinAlgError) as exc:
                            fit_log.append({'at':at,'horizon':horizon,'target':target,'model':name,'status':'FAILED','error':str(exc)})
                    fit_log.append({'at':at,'horizon':horizon,'target':target,'rows':len(train),'models':list(models),'last_label_end':train.end_date.max(),'status':'FIT'})
                if train is None or len(models)!=2:continue
                predictions={'baseline':mean_prior(train,test,target) if continuous else frequency(train,test,target)}
                predictions.update({name:model.predict_mean(test) if continuous else model.predict(test) for name,model in models.items()})
                for name,values in predictions.items():
                    for (_,row),value in zip(test.iterrows(),values):
                        issued.append({'event_id':row.event_id,'origin':at,'horizon':horizon,'target':target,'model':name,'prediction':value,
                            'outcome':row[target],'outcome_status':row.outcome_status,'symbol':row.symbol,'group':row.group,'family':row.family,
                            'segment':row.segment,'exposed_design_case':row.exposed_design_case,'fit_at':fit_at,'last_training_end':train.end_date.max()})
            print('RESPONSE_MODEL_COMPLETE',horizon,target,flush=True)
    pred=pd.DataFrame(issued);pred.to_parquet(dest/'predictions.parquet',index=False);write_json(dest/'fit_log.json',fit_log)
    q=pred.loc[~pred.exposed_design_case&(pred.outcome_status=='COMPLETE')&pred.outcome.notna()].copy();q['loss']=np.nan
    for target,part in q.groupby('target'):
        q.loc[part.index,'loss']=(part.prediction-part.outcome)**2 if target.startswith('log_') else losses(part.outcome,part.prediction)['log_loss']
    q.groupby(['horizon','target','model']).agg(events=('event_id','size'),dates=('origin','nunique'),loss=('loss','mean')).reset_index().to_csv(dest/'scores.csv',index=False)
    q.groupby(['horizon','target','group','model']).agg(events=('event_id','size'),loss=('loss','mean')).reset_index().to_csv(dest/'group_scores.csv',index=False)
    tests=[]
    for (h,target),part in q.groupby(['horizon','target']):
        pivot=part.pivot(index=['event_id','origin'],columns='model',values='loss')
        for high,low in [('shared','baseline'),('conditional_response','shared'),('conditional_response','baseline')]:
            d=(pivot[high]-pivot[low]).dropna().groupby(level='origin').mean()
            tests.append({'horizon':h,'target':target,'contrast':high+' - '+low,**block_interval(d.index,d.to_numpy())})
    test=pd.DataFrame(tests);test['p_holm_family']=holm(test);test.to_csv(dest/'paired_tests.csv',index=False)
    pred.loc[pred.exposed_design_case].to_csv(dest/'MCD_EXPOSED_PREDICTIONS.csv',index=False)
    write_json(dest/'receipt.json',{'status':'COMPLETE','prediction_rows':len(pred),'unique_issued_events':pred.event_id.nunique(),
      'paired_tests':len(test),'corrected_rejections':int((test.p_holm_family<.05).sum()),'outcome_guided_exploratory':True,
      'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'may_rank':False,'may_size':False,'may_trade':False})
    print('CONDITIONAL_RESPONSE_COMPLETE',len(pred),len(test),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));main(ap.parse_args().root)
