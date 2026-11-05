"""LP-EVENT-03A: documented IEX displayed executions, not a reconstructed book.
Read-only inputs; explicit source-send decision clock; full outcomes stay private.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,struct
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp,softmax

NAMES=['AAPL','MSFT','NVDA','AMD','MU','INTC','SPY','XLV']
BASE=['ret1','median_momentum','ret20','vol20','range20','logvolume','logelapsed','loglastdt','logmedsize','clock']+['is_'+s for s in NAMES[1:]]
NEW=['repeat_volume','hhi','largest_order_share','seen_fraction','logseen_age','repeat_change','repeat_x_momentum']
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def clock(s):return int(pd.Timestamp('2026-10-05 '+s,tz='America/New_York').tz_convert('UTC').value)
def load(p):
 dtypes={k:'uint64' for k in ['timestamp_ns','sequence','send_ns','capture_ticks','order_id','trade_id','price_1e4']}
 x=pd.read_csv(p,dtype=dtypes)
 if x.sequence.duplicated().any() or not x.sequence.is_monotonic_increasing:raise ValueError('bad sequence')
 if (x.send_ns<x.timestamp_ns).any() or not x.send_ns.is_monotonic_increasing:raise ValueError('bad source time')
 if (x.price_1e4<=0).any() or (x['size']<=0).any():raise ValueError('bad executions')
 return x

def make_rows(x,labels=True,shuffle=False):
 rows=[];stats={};rng=np.random.default_rng(20261015)
 for symbol in NAMES:
  g=x[(x.ticker==symbol)&(x.sale_flags==0)&(x.send_ns>=clock('09:45'))&(x.send_ns<=clock('15:45'))]
  ts=g.send_ns.to_numpy(dtype=np.uint64);px=g.price_1e4.to_numpy(dtype=np.uint64);sz=g['size'].to_numpy(dtype=np.float64);ids=g.order_id.to_numpy(dtype=np.uint64)
  if shuffle:ids=rng.permutation(ids) # frozen nondeployable diagnostic, not a candidate forecast feature
  first={};seen=np.zeros(len(g));age=np.zeros(len(g));stats[symbol]={'eligible_executions':len(g),'warmup':20,'future_unavailable':0}
  for i,(t,oid) in enumerate(zip(ts,ids)):
   key=int(oid);ti=int(t);seen[i]=float(key in first);first.setdefault(key,ti);age[i]=(ti-first[key])/1e9
   if i<20:continue
   w=slice(i-19,i+1);ps=px[w].astype(float);qs=sz[w];os=ids[w];last5=float(np.median(px[i-4:i+1]));prev5=float(np.median(px[i-9:i-4]));mom=np.log(last5/prev5)
   agg=collections.defaultdict(float);cnt=collections.Counter(int(o) for o in os)
   for oid,q in zip(os,qs):agg[int(oid)]+=float(q)
   weights=np.asarray(list(agg.values()))/qs.sum();repeat=sum(v for o,v in agg.items() if cnt[o]>1)/qs.sum()
   r={'ticker':symbol,'decision_ns':ti,'sequence':int(g.sequence.iloc[i]),'ret1':float(np.log(float(px[i])/float(px[i-1]))),'median_momentum':float(mom),'ret20':float(np.log(ps[-1]/ps[0])),'vol20':float(np.std(np.diff(np.log(ps)))),'range20':float(np.log(ps.max()/ps.min())),'logvolume':float(np.log1p(qs.sum())),'logelapsed':float(np.log1p((ti-int(ts[i-19]))/1e9)),'loglastdt':float(np.log1p((ti-int(ts[i-1]))/1e9)),'logmedsize':float(np.log1p(np.median(qs))),'clock':(ti-clock('09:45'))/1e9,'repeat_volume':float(repeat),'hhi':float(np.dot(weights,weights)),'largest_order_share':float(weights.max()),'seen_fraction':float(seen[w].mean()),'logseen_age':float(np.log1p(np.median(age[w]))),'repeat_change':float(seen[i-4:i+1].mean()-seen[i-19:i-4].mean()),'repeat_x_momentum':float(repeat*mom),'source_kind':'IEX_DISPLAYED_EXECUTIONS_ONLY'}
   for name in NAMES[1:]:r['is_'+name]=float(name==symbol)
   if labels:
    j=int(np.searchsorted(ts,ti+1_000_000_000,side='left'));k=j+4
    if k>=len(ts) or int(ts[k])-ti>900_000_000_000:stats[symbol]['future_unavailable']+=1;continue
    future=float(np.median(px[j:k+1]));r['label_end_ns']=int(ts[k]);r['horizon_seconds']=(int(ts[k])-ti)/1e9;r['class']=0 if future<last5 else (2 if future>last5 else 1)
   rows.append(r)
 return pd.DataFrame(rows),stats

def fit(tr,te,cols):
 y=tr['class'].to_numpy(int);target=np.eye(3)[y];a=tr[cols].to_numpy(float);b=te[cols].to_numpy(float);mu=a.mean(0);sd=a.std(0);sd[sd<1e-12]=1
 a=np.c_[np.ones(len(a)),np.clip((a-mu)/sd,-5,5)];b=np.c_[np.ones(len(b)),np.clip((b-mu)/sd,-5,5)]
 def fg(v):
  w=v.reshape(a.shape[1],3);q=a@w;p=softmax(q,axis=1);loss=np.mean(logsumexp(q,axis=1)-q[np.arange(len(y)),y])+.005*np.sum(w[1:]**2);grad=a.T@(p-target)/len(a);grad[1:]+=.01*w[1:];return loss,grad.ravel()
 f=minimize(fg,np.zeros(a.shape[1]*3),jac=True,method='L-BFGS-B',options={'maxiter':500,'ftol':1e-12,'gtol':1e-8})
 if not f.success:raise ValueError('optimizer: '+str(f.message))
 return softmax(b@f.x.reshape(a.shape[1],3),axis=1),{'iterations':int(f.nit),'converged':True,'n_columns':len(cols)}
def scores(y,p):
 y=np.asarray(y,int);t=np.eye(3)[y];loss=np.sum((p-t)**2,axis=1);pred=p.argmax(1)
 recall={str(k):float(np.mean(pred[y==k]==k)) if (y==k).any() else None for k in range(3)}
 return {'n':len(y),'class_counts':np.bincount(y,minlength=3).tolist(),'brier':float(loss.mean()),'logloss':float(-np.log(np.clip(p[np.arange(len(y)),y],1e-12,1)).mean()),'accuracy':float(np.mean(pred==y)),'class_recall':recall,'mean_probability':p.mean(0).tolist()},loss

def study(x,shuffle=False):
 z,cov=make_rows(x,shuffle=shuffle);cols=BASE+NEW
 if not np.isfinite(z[cols]).all().all():raise ValueError('nonfinite feature')
 tr=z[(z.decision_ns<clock('12:00'))&(z.label_end_ns<clock('12:00'))];te=z[(z.decision_ns>=clock('13:00'))&(z.decision_ns<=clock('15:30'))&(z.label_end_ns<=clock('15:45'))].copy()
 if len(tr)<200 or len(te)<200:raise ValueError('insufficient observations')
 assert tr.label_end_ns.max()<te.decision_ns.min()
 freq=np.bincount(tr['class'],minlength=3)/len(tr);constant=np.tile(freq,(len(te),1));pb,fb=fit(tr,te,BASE);pn,fn=fit(tr,te,cols);y=te['class'].to_numpy(int)
 report={'training_n':len(tr),'evaluation_n':len(te),'training_last_label_ns':str(int(tr.label_end_ns.max())),'evaluation_first_decision_ns':str(int(te.decision_ns.min())),'coverage':cov,'models':{},'fit':{'baseline':fb,'order_history':fn},'horizon_seconds':{'median':float(te.horizon_seconds.median()),'p90':float(te.horizon_seconds.quantile(.9))},'by_ticker':{}}
 losses={}
 for name,p in [('constant',constant),('baseline',pb),('order_history',pn)]:report['models'][name],losses[name]=scores(y,p)
 te['brier_gain']=losses['baseline']-losses['order_history'];te['block']=(te.decision_ns.astype('int64')-clock('13:00'))//300_000_000_000
 blocks=te.groupby('block').brier_gain.agg(['sum','count']);rng=np.random.default_rng(20261015);boots=[]
 for _ in range(1000):
  ix=rng.integers(len(blocks),size=len(blocks));b=blocks.iloc[ix];boots.append(float(b['sum'].sum()/b['count'].sum()))
 report['paired_gain']={'mean':float(te.brier_gain.mean()),'block_ci95':np.quantile(boots,[.025,.975]).tolist(),'n_5minute_blocks':len(blocks),'replicates':1000,'not_independent_days':True}
 for name,g in te.groupby('ticker'):report['by_ticker'][name]={'n':len(g),'gain':float(g.brier_gain.mean()),'horizon_median_seconds':float(g.horizon_seconds.median())}
 report['candidate_gate']=bool(report['paired_gain']['mean']>=.002 and report['paired_gain']['block_ci95'][0]>0 and sum(a['n']>=30 and a['gain']>0 for a in report['by_ticker'].values())>=5)
 for i,k in enumerate(['down','same','up']):te['baseline_'+k]=pb[:,i];te['order_history_'+k]=pn[:,i]
 return report,te

def verify_raw(raw,frame):
 actual=[]
 with open(raw,'rb') as f:
  if f.read(8)!=b'DPLSRAW1':raise ValueError('wrong selected raw envelope')
  while True:
   h=f.read(34)
   if not h:break
   if len(h)!=34:raise ValueError('truncated envelope')
   seq,send,cap,ch,sess,n=struct.unpack('<QQQIIH',h);m=f.read(n)
   if len(m)!=n:raise ValueError('truncated source message')
   if m[:1]!=b'L':continue
   typ,flag,ts,sym,oid,qty,price,tid=struct.unpack('<BBQ8sQIqQ',m[:46]);actual.append((sym.decode().strip(),ts,seq,send,cap,ch,sess,oid,qty,price,tid,flag))
 expected=list(frame[['ticker','timestamp_ns','sequence','send_ns','capture_ticks','channel','session','order_id','size','price_1e4','trade_id','sale_flags']].itertuples(index=False,name=None))
 if actual!=expected:raise ValueError('independent raw decoding mismatch')
 return len(actual)

def main():
 a=argparse.ArgumentParser();a.add_argument('--scan',type=Path,required=True);a.add_argument('--out',type=Path,required=True);args=a.parse_args()
 if args.out.exists():raise ValueError('output already exists; never overwrite study')
 p=args.scan/'executions.csv.gz';h=digest(p);x=load(p);n=verify_raw(args.scan/'selected_messages.bin',x)
 whole,_=make_rows(x,labels=False);prefix,_=make_rows(x[x.send_ns<=clock('12:00')],labels=False);expected=whole[whole.decision_ns<=clock('12:00')]
 np.testing.assert_allclose(prefix[BASE+NEW].to_numpy(),expected[BASE+NEW].to_numpy(),rtol=0,atol=0)
 primary,pred=study(x);control,_=study(x,shuffle=True);assert digest(p)==h
 report={'id':'LP-EVENT-03A','status':'RESEARCH_ONLY_SINGLE_DAY_PRINT_PROXY_NOT_QUOTE_RECOVERY_OR_ALPHA','created_at':datetime.now(timezone.utc).isoformat(),'input_sha256':h,'source_sha256':digest(__file__),'raw_reference_matched_records':n,'tests':{'prefix_exact_equality':True,'label_purge':True,'lossless_large_integers':True,'input_unchanged':True},'primary':primary,'shuffled_order_id_diagnostic':control}
 args.out.mkdir();pred.to_csv(args.out/'predictions.csv.gz',index=False,compression='gzip');report['private_predictions_sha256']=digest(args.out/'predictions.csv.gz');(args.out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 print(json.dumps({'status':report['status'],'matched':n,'tests':report['tests'],'primary':primary,'shuffle_gain':control['paired_gain']},indent=2))
if __name__=='__main__':main()
