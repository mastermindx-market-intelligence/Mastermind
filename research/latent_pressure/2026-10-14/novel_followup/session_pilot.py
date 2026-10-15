"""LP-NOVEL-02 internal exploratory later-vintage test, NOT PIT/admission proof.
Uses the incumbent experiment's unchanged deterministic fitter and metric functions.
No network, source data modifications, trades, or production effects.
"""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util,json,hashlib
import numpy as np
import pandas as pd
O=Path(__file__).parent
old=O.parent/'pilot.py';s=importlib.util.spec_from_file_location('accepted_math',old);math=importlib.util.module_from_spec(s);s.loader.exec_module(math)
B=['mom1','mom5','mom20','mom60','rs1','rs5','rs20','rs60','vol20','trend200','rvol','obv20','beta60','market_mom20','market_vol20','ticker_dummy'];C=['component5','component20'];S=['signed_cancel20','release5'];ALL=B+C+S
MODELS={'baseline':B,'components':B+C,'sequence':ALL}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def build(c,o,v,labels=True):
 r=np.log(c).diff();night=np.log(o/c.shift());day=np.log(c/o);rs=np.log(c.div(c.SPY,axis=0));out=[]
 np.testing.assert_allclose(night+day,r,rtol=1e-8,atol=1e-12,equal_nan=True)
 for t in ['ACN','AMAT']:
  z=pd.DataFrame(index=c.index);sd=r[t].rolling(20).std();beta=(r[t].rolling(60).cov(r.SPY)/r.SPY.rolling(60).var()).shift()
  for w in [1,5,20,60]:z[f'mom{w}']=np.log(c[t]).diff(w);z[f'rs{w}']=rs[t].diff(w)
  z['vol20']=sd;z['trend200']=np.log(c[t]/c[t].rolling(200).mean());z['rvol']=v[t]/v[t].rolling(20).mean();z['obv20']=(np.sign(r[t])*v[t]).rolling(20).sum()/v[t].rolling(20).sum();z['beta60']=beta;z['market_mom20']=np.log(c.SPY).diff(20);z['market_vol20']=r.SPY.rolling(20).std();z['ticker_dummy']=float(t=='AMAT')
  dr=day[t]-beta*day.SPY;nr=night[t]-beta*night.SPY;ds=dr.rolling(20).sum();ns=nr.rolling(20).sum();d5=dr.rolling(5).sum();n5=nr.rolling(5).sum()
  z['component5']=(d5-n5)/(sd*np.sqrt(5));z['component20']=(ds-ns)/(sd*np.sqrt(20));mass=np.minimum(ds.abs(),ns.abs()).where(ds*ns<0,0)/(sd*np.sqrt(20));z['signed_cancel20']=np.sign(ds)*mass;z['release5']=mass*np.sign(ds)*(d5+n5)/(sd*np.sqrt(5));z['cancel_degree']=1-(ds+ns).abs()/(ds.abs()+ns.abs()+1e-12);z['gross_component']=ds.abs()+ns.abs();z['ticker']=t
  if labels:
   z['fwd']=np.log(c[t].shift(-5)/o[t].shift(-1))-np.log(c.SPY.shift(-5)/o.SPY.shift(-1));z['label_end']=pd.Series(c.index,index=c.index).shift(-5)
  out.append(z.reset_index(names='date'))
 return pd.concat(out,ignore_index=True)
def inference(g):
 rng=np.random.default_rng(20421014);ans={}
 for m in ['components','sequence']:
  v=g.assign(delta=(g.p_baseline-g.y)**2-(g['p_'+m]-g.y)**2).groupby('date').delta.mean().to_numpy();n=len(v);mu=v.mean();bs=[]
  for _ in range(1000):
   starts=rng.integers(n,size=int(np.ceil(n/60)));ix=((starts[:,None]+np.arange(60))%n).ravel()[:n];bs.append(v[ix].mean())
  bs=np.array(bs);ans[m]={'gain':float(mu),'ci95':np.quantile(bs,[.025,.975]).tolist(),'p':float((1+(np.abs(bs-mu)>=abs(mu)).sum())/1001),'n_dates':n}
 order=sorted(ans,key=lambda m:ans[m]['p']);prev=0
 for i,m in enumerate(order):prev=max(prev,min(1,(2-i)*ans[m]['p']));ans[m]['holm_p']=prev
 return ans
def run():
 out=O/'private_results'
 if out.exists():raise ValueError('Results already exist; never silently overwrite')
 census=json.loads((O/'eod_census_private.json').read_text());frames={};receipts=[]
 for t in ['ACN','AMAT','SPY']:
  a=sorted([a for a in census if t in a['symbols']],key=lambda a:(-a['rows'],a['ref']))[0];p=Path(a['ref'])
  if sha(p)!=a['file_sha256']:raise ValueError('Source hash changed')
  x=pd.read_parquet(p);x['date']=pd.to_datetime(x.market_date);x=x.set_index('date').sort_index().loc['2005-01-01':'2025-12-31']
  if x.index.duplicated().any():raise ValueError('Duplicate dates')
  for col in ['open_tradj','close_tradj','open_raw','close_raw']:
   if not np.isfinite(x[col]).all() or (x[col]<=0).any():raise ValueError('Invalid prices '+col)
  np.testing.assert_allclose(x.open_tradj/x.open_raw,x.close_tradj/x.close_raw,rtol=1e-8,atol=1e-10)
  frames[t]=x;receipts.append({'ticker':t,'relative_path':str(p.relative_to('/Volumes/Mastermind/market-data/tiingo/normalized/eod-bars')),'file_sha256':a['file_sha256'],'rows_used':len(x),'first':str(x.index.min().date()),'last':str(x.index.max().date()),'flags':{k:x[k].unique().tolist() for k in ['pit_backtest_eligible','source_rights_admitted','dataos_identity_admitted']}})
 c=pd.DataFrame({t:x.close_tradj for t,x in frames.items()}).reindex(frames['SPY'].index);o=pd.DataFrame({t:x.open_tradj for t,x in frames.items()}).reindex(c.index);v=pd.DataFrame({t:x.volume_vendor_adjusted for t,x in frames.items()}).reindex(c.index)
 z=build(c,o,v);pre=build(c.loc[:'2020-12-31'],o.loc[:'2020-12-31'],v.loc[:'2020-12-31'],False)
 np.testing.assert_allclose(pre[ALL],z[z.date<='2020-12-31'][ALL],equal_nan=True,rtol=1e-8,atol=1e-9)
 z=z.replace([np.inf,-np.inf],np.nan).dropna(subset=ALL+['fwd','label_end']);z=z[z.date>='2006-01-01'].copy();z['y']=(z.fwd>0).astype(int);preds=[];fits=[]
 for year in range(2018,2026):
  cut=pd.Timestamp(f'{year}-01-01');tr=z[(z.date<cut)&(z.label_end<cut)];te=z[z.date.dt.year==year].copy();assert len(tr)>1000 and tr.label_end.max()<te.date.min()
  for m,cols in MODELS.items():te['p_'+m],_=math.fit_predict(tr,te,cols)
  te['p_constant']=te.ticker.map(tr.groupby('ticker').y.mean());preds.append(te);fits.append({'year':year,'train_n':len(tr),'test_n':len(te),'last_train_label':str(tr.label_end.max().date())})
 q=pd.concat(preds,ignore_index=True);res={'id':'LP-NOVEL-02','run_at':datetime.now(timezone.utc).isoformat(),'status':'EXPLORATORY_LATER_VINTAGE_ONLY_NOT_PIT_OR_DATAOS_ADMISSION','n_predictions':len(q),'sources':receipts,'fit_receipts':fits,'models':{},'inference':{},'checks':{'prefix_invariance':True,'actual_return_decomposition':True,'same_day_adjustment_multiplier':True,'strict_label_purge':True},'method_dependency_sha256':sha(old),'new_source_sha256':sha(__file__)}
 for period,g in [('development',q[q.date<'2023-01-01']),('evaluation',q[q.date>='2023-01-01'])]:
  res['models'][period]={m:math.metrics(g.y.to_numpy(),g['p_'+m].to_numpy()) for m in ['constant']+list(MODELS)};res['inference'][period]=inference(g);a=(g.cancel_degree>=.8)&(g.gross_component>=.02);res[period+'_cancellation']={'n':len(g),'observed_windows':int(a.sum()),'fraction':float(a.mean()),'definition':'20sessionresidualday/nightcomponentscancel>=80percent;gross>=2logpercent;overlappingdescriptivewindows'}
 res['annual_brier']={str(y):{m:float(((g['p_'+m]-g.y)**2).mean()) for m in MODELS} for y,g in q.groupby(q.date.dt.year)};g=q[q.date>='2023-01-01'];res['evaluation_tickers']={t:{m:float(((a['p_'+m]-a.y)**2).mean()) for m in MODELS} for t,a in g.groupby('ticker')}
 for a in receipts:assert sha(Path('/Volumes/Mastermind/market-data/tiingo/normalized/eod-bars')/a['relative_path'])==a['file_sha256']
 out.mkdir();q.to_csv(out/'predictions.csv.gz',index=False,compression='gzip');res['private_prediction_sha256']=sha(out/'predictions.csv.gz');(O/'SESSION_PILOT_RESULTS.json').write_text(json.dumps(res,indent=2,allow_nan=False)+'\n')
 print(json.dumps({'n':len(q),'metrics':{p:{m:{k:v for k,v in x.items() if k in ['brier','auc','n','base_rate']} for m,x in ms.items()} for p,ms in res['models'].items()},'inference':res['inference'],'cancellation':res['evaluation_cancellation'],'years':res['annual_brier'],'tickers':res['evaluation_tickers']},indent=2))
if __name__=='__main__':run()
