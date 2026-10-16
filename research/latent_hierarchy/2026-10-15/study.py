"""LP-HIERARCHY-09: parent pivot prediction from SIC-pure child participation.

Research-only and source-vintage qualified. Never executes trades, creates alerts,
mutates source archives, reads restricted results or publishes per-date returns.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import argparse, hashlib, json, io, re, zipfile
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import rankdata
from mapping import mapping

ROOT=Path(__file__).resolve().parent
BASE=['rs5','rs21','rs63','rs126','mom5','mom21','mom63','vol21','vol63','rs_accel5','trend63','drawdown63','market_rs21','market_vol63','SMB21','HML21','parent_ewvw5','parent_ewvw21','parent_ewvw63','rankparent21','is_negative_rs','known_rollover_next5','known_rollover_margin','known_rollover_confirmed','known_rollover_first_day']
CHILD=['breadth5','breadth21','improving','bottom_recover','top_fade','mean_child_parent_gap','dispersion21','opposite_parent5','child_coverage']
SEEDS=[9101526,9101527,9101528,9101529]
LAMBDA=.01

def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

def section(lines,header):
    i=header
    while i<len(lines) and not lines[i].strip():i+=1
    end=i+1
    while end<len(lines) and re.match(r'^\s*\d{8},',lines[end]):end+=1
    if end<=i+1:raise ValueError('source empty section')
    frame=pd.read_csv(io.StringIO('\n'.join(lines[i:end])),index_col=0)
    frame.columns=frame.columns.str.strip()
    frame.index=pd.to_datetime(frame.index.astype(str),format='%Y%m%d')
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:raise ValueError('date ordering')
    frame=frame.apply(pd.to_numeric,errors='raise').replace([-99.99,-999.],np.nan)/100
    if (frame<=-1).any().any():raise ValueError('impossible total-return base')
    return frame

def read_data(root:Path=ROOT):
    manifest=json.loads((root/'SOURCE_MANIFEST.json').read_text());tables={}
    for meta in manifest:
        file=root/'private'/meta['name']
        if sha(file)!=meta['sha256']:raise ValueError('source hash changed '+file.name)
        with zipfile.ZipFile(file) as z:
            if z.namelist()!=meta['contents']:raise ValueError('contained path changed')
            tables[file.name]=z.read(meta['contents'][0]).decode('utf-8-sig').splitlines()
    def industry(n):
        lines=tables[f'{n}_Industry_Portfolios_daily_CSV.zip']
        heads=[i for i,s in enumerate(lines) if s.strip().startswith('Average')]
        if len(heads)!=2:raise ValueError('expected VW/EW daily sections')
        return section(lines,heads[0]+1),section(lines,heads[1]+1)
    vw10,ew10=industry(10);vw49,ew49=industry(49)
    lines=tables['F-F_Research_Data_Factors_daily_CSV.zip'];h=next(i for i,s in enumerate(lines) if 'Mkt-RF' in s)
    ff=section(lines,h)
    dates=vw10.index.intersection(ew10.index).intersection(vw49.index).intersection(ew49.index).intersection(ff.index)
    dates=dates[dates>=pd.Timestamp('1963-07-01')]
    vw10,ew10,vw49,ew49,ff=(x.loc[dates] for x in (vw10,ew10,vw49,ew49,ff))
    maps=mapping(root)
    if not set(maps['retained'])<=set(vw10.columns) or not set(sum(maps['retained'].values(),[]))<=set(vw49.columns):raise ValueError('mapped source column mismatch')
    if ff[['Mkt-RF','SMB','HML','RF']].isna().any().any():raise ValueError('FF factor missing')
    return vw10,ew10,vw49,ff,maps

def rollover(past21:np.ndarray,sign:int,barrier:float=.005,vol:float=.01):
    """Known old returns leaving RS21 under hypothetical future ZERO relative returns.

    Not an oracle for future returns. If a projected sign flip emerges from solely
    forgetting negative/positive history, baseline receives that fact at decision t.
    """
    a=np.asarray(past21,float)
    if a.shape!=(21,) or not np.isfinite(a).all() or type(sign) not in [int,np.int64] or sign not in [-1,1]:raise ValueError('valid 21 known returns and nonzero sign required')
    projected=a.sum()-np.cumsum(a) # future h=1..21, last point 0
    margins=sign*projected[:19] # need 3 consecutive after first day by horizon21
    confirm=None
    for j in range(17):
        if (margins[j:j+3]<=-barrier).all():confirm=j+3;break
    norm=max(float(vol),1e-5)*np.sqrt(21)
    return {'known_rollover_next5':float(sign*(projected[4]-a.sum())/norm),
            'known_rollover_margin':float(np.min(margins)/norm),
            'known_rollover_confirmed':float(confirm is not None),
            'known_rollover_first_day':float(confirm if confirm is not None else 22)}

def _child_values(children:list[str],rel49:pd.DataFrame,sign:pd.Series,relative_parent:pd.Series):
    r=rel49[children]
    ready=(r.notna().rolling(504,min_periods=504).sum()==504)
    s5=r.rolling(5,min_periods=5).sum().where(ready)
    s21=r.rolling(21,min_periods=21).sum().where(ready)
    accel=s5-s5.shift(5)
    count=s21.notna().sum(axis=1)
    denom=count.replace(0,np.nan)
    parent_sign=np.sign(relative_parent)
    # Every proportion denominator is the contemporaneously available children count.
    out=pd.DataFrame(index=r.index)
    out['breadth5']=(s5>0).where(s5.notna()).sum(axis=1)/denom
    out['breadth21']=(s21>0).where(s21.notna()).sum(axis=1)/denom
    out['improving']=(accel>0).where(accel.notna()).sum(axis=1)/denom
    out['bottom_recover']=((s21<0)&(s5>0)).where(s21.notna()&s5.notna()).sum(axis=1)/denom
    out['top_fade']=((s21>0)&(s5<0)).where(s21.notna()&s5.notna()).sum(axis=1)/denom
    out['mean_child_parent_gap']=s21.mean(axis=1)-relative_parent
    out['dispersion21']=s21.std(axis=1,ddof=0)
    out['opposite_parent5']=(s5.mul(parent_sign,axis=0)<0).where(s5.notna()).sum(axis=1)/denom
    out['child_coverage']=count/len(children)
    out=out.where(count>=2)
    return out

def shuffle_maps(maps,seed:int):
    groups=maps['retained'];parents=list(groups)
    values=sum((groups[p] for p in parents),[])
    perm=np.random.default_rng(seed).permutation(values).tolist()
    sizes=[len(groups[p]) for p in parents];result={};i=0
    for parent,n in zip(parents,sizes):result[parent]=sorted(perm[i:i+n]);i+=n
    if i!=len(values) or sorted(sum(result.values(),[]))!=sorted(values):raise ArithmeticError('membership permutation lost source identities')
    return result

def features(vw10,ew10,vw49,ff,maps):
    market=np.log1p(ff['Mkt-RF']+ff.RF)
    r10=np.log1p(vw10);r49=np.log1p(vw49)
    rel10=r10.sub(market,axis=0);rel49=r49.sub(market,axis=0)
    parent_rs21=rel10.rolling(21,min_periods=21).sum()
    rank21=parent_rs21.rank(axis=1,pct=True)
    all_maps={'real':maps['retained']}
    all_maps.update({f'placebo{i}':shuffle_maps(maps,seed) for i,seed in enumerate(SEEDS)})
    rows=[]
    for parent in maps['retained']:
        z=pd.DataFrame(index=vw10.index)
        rel=rel10[parent];raw=r10[parent];sigma=rel.rolling(63,min_periods=63).std()
        for n in [5,21,63,126]:z[f'rs{n}']=rel.rolling(n,min_periods=n).sum()
        for n in [5,21,63]:z[f'mom{n}']=raw.rolling(n,min_periods=n).sum()
        z['vol21']=raw.rolling(21).std();z['vol63']=raw.rolling(63).std()
        z['rs_accel5']=z.rs21-z.rs21.shift(5)
        cumul=raw.fillna(0).cumsum()
        z['trend63']=cumul-cumul.rolling(63).mean();z['drawdown63']=cumul-cumul.rolling(63).max()
        z['market_rs21']=market.rolling(21).sum();z['market_vol63']=market.rolling(63).std()
        z['SMB21']=ff.SMB.rolling(21).sum();z['HML21']=ff.HML.rolling(21).sum()
        spread=np.log1p(ew10[parent])-np.log1p(vw10[parent])
        for n in [5,21,63]:z[f'parent_ewvw{n}']=spread.rolling(n,min_periods=n).sum()
        z['rankparent21']=rank21[parent];z['is_negative_rs']=(z.rs21<0).astype(float)
        z['pos']=np.arange(len(z));z['parent']=parent;z['sigma_rel63']=sigma
        mech=[]
        for i in range(len(z)):
            vals=rel.iloc[i-20:i+1].to_numpy(float) if i>=20 else np.array([])
            s=z.rs21.iloc[i];v=sigma.iloc[i]
            if len(vals)!=21 or not np.isfinite(s) or not np.isfinite(v) or abs(s)<.005:mech.append({c:np.nan for c in BASE if c.startswith('known_rollover_')});continue
            mech.append(rollover(vals,1 if s>0 else -1,vol=v))
        t=pd.DataFrame(mech,index=z.index)
        for col in t:z[col]=t[col]
        for family,group in all_maps.items():
            child=_child_values(group[parent],rel49,np.sign(z.rs21),z.rs21)
            for col in CHILD:z[f'{family}_{col}']=child[col]
        # As-of feature eligibility. We do not choose parents using future outcomes.
        z['eligible_parent']=(rel.notna().rolling(504,min_periods=504).sum()==504)
        rows.append(z.reset_index(names='date'))
    return pd.concat(rows,ignore_index=True)

def attach_labels(panel,vw10,ff):
    market=np.log1p(ff['Mkt-RF']+ff.RF)
    relative=np.log1p(vw10).sub(market,axis=0)
    rolling=relative.rolling(21,min_periods=21).sum()
    result=[];skipped=Counter()
    for row in panel.itertuples(index=False):
        i=int(row.pos);p=row.parent
        if i+21>=len(vw10):skipped['future_horizon_missing']+=1;continue
        future=relative[p].iloc[i+1:i+22]
        status=rolling[p].iloc[i+1:i+22]
        if not (future.notna().all() and status.notna().all()):skipped['missing_future_return']+=1;continue
        s0=float(row.rs21)
        if not np.isfinite(s0) or abs(s0)<.005:skipped['initial_rs_under_threshold']+=1;continue
        direction=1 if s0>0 else -1
        ahead=(status.to_numpy(float)*direction)
        duration=None
        for j in range(19):
            if np.all(ahead[j:j+3]<=-.005):duration=j+3;break
        # First trading day after forecast is entry close and not counted as a tradable return.
        fwd=float(future.iloc[1:].sum())
        result.append({'date':row.date,'parent':p,'class':int(duration is not None),
                       'confirmation_delay':duration,'label_end':vw10.index[i+21],
                       'entry_date':vw10.index[i+1],'forward_signed_logrel':-direction*fwd,
                       'initial_parent_direction':direction})
    if not result:raise ValueError('no label observations')
    labels=pd.DataFrame(result)
    return panel.merge(labels,on=['date','parent'],validate='one_to_one'),dict(skipped)

def _matrices(train,test,cols):
    x=train[cols].to_numpy(float);y=test[cols].to_numpy(float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('nonfinite fitted features')
    mu=x.mean(axis=0);sd=x.std(axis=0);sd[sd<1e-12]=1.
    a=np.clip((x-mu)/sd,-5,5);b=np.clip((y-mu)/sd,-5,5)
    return a,b

def _minimize(fun,size,initial=None):
    start=np.zeros(size) if initial is None else np.asarray(initial,float)
    fit=minimize(fun,start,jac=True,method='L-BFGS-B',options={'maxiter':500,'ftol':1e-11,'gtol':1e-8})
    if not fit.success:raise RuntimeError('optimization failed '+str(fit.message))
    return fit.x,int(fit.nit)

def frozen_baseline(train,test):
    a,b=_matrices(train,test,BASE)
    aa=np.c_[np.ones(len(a)),a];bb=np.c_[np.ones(len(b)),b]
    truth=train['class'].to_numpy(float)
    def fg(w):
        z=aa@w;v=np.mean(np.logaddexp(0,z)-truth*z)+.5*LAMBDA*np.dot(w[1:],w[1:])
        grad=aa.T@(expit(z)-truth)/len(truth);grad[1:]+=LAMBDA*w[1:]
        return v,grad
    w,niter=_minimize(fg,aa.shape[1]);offtrain=aa@w;offtest=bb@w
    # Matched calibration intercept: trained on the very same training rows.
    def intercept_fg(c):
        z=offtrain+c[0]
        return float(np.mean(np.logaddexp(0,z)-truth*z)),np.array([np.mean(expit(z)-truth)])
    intercept,ncal=_minimize(intercept_fg,1)
    offtrain+=intercept[0];offtest+=intercept[0]
    return aa,bb,offtrain,offtest,{'baseline_iterations':niter,'calibration_iterations':ncal,'calibration_intercept':float(intercept[0]),'baseline_coeff_sha256':hashlib.sha256(w.astype('<f8').tobytes()).hexdigest()}

def conditional_candidate(train,test,model,aa,bb,offtrain,offtest):
    prefix=model+'_';names=[prefix+k for k in CHILD]
    ztrain,ztest=_matrices(train,test,names)
    # Project transformed candidate into transformed baseline span on TRAINING only.
    projection=np.linalg.lstsq(aa,ztrain,rcond=1e-12)[0]
    residual=ztrain-aa@projection
    rms=np.sqrt(np.mean(residual**2,axis=0));keep=rms>1e-9
    receipt={'n_raw_features':len(CHILD),'n_independent_training_features':int(keep.sum()),'training_projection_only':True}
    if not np.any(keep):return expit(offtest),receipt
    u=residual[:,keep]/rms[keep]
    t=(ztest-bb@projection)[:,keep]/rms[keep]
    truth=train['class'].to_numpy(float)
    def fg(w):
        z=offtrain+u@w
        loss=np.mean(np.logaddexp(0,z)-truth*z)+.5*LAMBDA*np.dot(w,w)
        grad=u.T@(expit(z)-truth)/len(truth)+LAMBDA*w
        return loss,grad
    w,niter=_minimize(fg,u.shape[1]);receipt.update({'iterations':niter,'coeff_sha256':hashlib.sha256(w.astype('<f8').tobytes()).hexdigest(),'max_training_linear_cross_moment':float(np.max(np.abs(aa.T@residual/len(train))))})
    return expit(offtest+t@w),receipt

def fit_year(train,test):
    y=train['class'].to_numpy(int)
    if len(train)<500 or len(test)==0 or len(set(y))<2:raise ValueError('insufficient class-diverse fit')
    aa,bb,offtrain,offtest,receipt=frozen_baseline(train,test)
    const=float((y.sum()+1)/(len(y)+2))
    pred={'constant':np.full(len(test),const),'baseline':expit(offtest)}
    for model in ['real']+[f'placebo{k}' for k in range(len(SEEDS))]:
        pred[model],receipt[model]=conditional_candidate(train,test,model,aa,bb,offtrain,offtest)
    for name,p in pred.items():
        if not np.isfinite(p).all() or np.any((p<0)|(p>1)):raise ValueError('invalid forecast probability '+name)
    return pred,receipt

def binary_auc(y,p):
    y=np.asarray(y,bool);n1=y.sum();n0=len(y)-n1
    if not n1 or not n0:return None
    return float((rankdata(p)[y].sum()-n1*(n1+1)/2)/(n1*n0))

def score(g,name):
    y=g['class'].to_numpy(int);p=np.clip(g[name].to_numpy(float),1e-12,1-1e-12)
    bins=[]
    for k in range(5):
        mask=(p>=k/5)&(p<(k+1)/5)
        if mask.any():bins.append({'lower':k/5,'n':int(mask.sum()),'pred':float(p[mask].mean()),'obs':float(y[mask].mean())})
    return {'n':len(g),'events':int(y.sum()),'prevalence':float(y.mean()),'brier':float(np.mean((p-y)**2)),
            'logloss':float(-np.mean(y*np.log(p)+(1-y)*np.log1p(-p))),'auc':binary_auc(y,p),'calibration':bins}

def interval(g,compare='real'):
    y=g['class'].to_numpy(int)
    base=(g.baseline.to_numpy()-y)**2;new=(g[compare].to_numpy()-y)**2
    bydate=pd.Series(base-new,index=g.date).groupby(level=0).mean().to_numpy()
    mean=float(bydate.mean());n=len(bydate)
    if n<104:return {'mean_date_brier_gain':mean,'ci95':None,'p':None,'dates':n,'inference':'DESCRIPTIVE_ONLY_FEWER_THAN_FOUR_26W_BLOCKS'}
    rng=np.random.default_rng(910152026);bs=[]
    for _ in range(1000):
        starts=rng.integers(n,size=int(np.ceil(n/26)));ix=((starts[:,None]+np.arange(26))%n).ravel()[:n]
        bs.append(bydate[ix].mean())
    bs=np.asarray(bs)
    return {'mean_date_brier_gain':mean,'ci95':np.quantile(bs,[.025,.975]).tolist(),
            'p_centered_two_sided':float((1+(np.abs(bs-mean)>=abs(mean)).sum())/1001),
            'dates':n,'block_weeks':26,'independent_units':'WEEKLY_ORIGIN_DATES_NOT_PARENT_ROWS'}

def alerts(g,model):
    chosen=[]
    for _,a in g.groupby('date'):
        k=max(1,int(np.ceil(.2*len(a))))
        chosen.append(a.sort_values([model,'parent'],ascending=[False,True]).head(k))
    s=pd.concat(chosen).sort_values(['date','parent']);last={};events=[]
    for r in s.itertuples():
        if int(r.pos)-last.get(r.parent,-999)<21:continue
        last[r.parent]=int(r.pos);events.append(r.Index)
    e=s.loc[events];hits=e[e['class']==1];lead=hits.confirmation_delay.dropna()
    utility=e.forward_signed_logrel
    return {'weekly_alerts':len(s),'correct':int(s['class'].sum()),'false_alarms':int((s['class']==0).sum()),
            'weekly_precision':float(s['class'].mean()),'weekly_alert_mean_predicted':float(s[model].mean()),
            'declustered_episodes':len(e),'episode_precision':float(e['class'].mean()) if len(e) else None,
            'confirmed_episode_count':len(hits),'median_confirmed_lead_sessions':float(lead.median()) if len(lead) else None,
            'conditional_lead_denominator':len(hits),'mean_signed_relative_log_bps':float(utility.mean()*1e4),
            'after30bps':float(utility.mean()*1e4-30),
            'note':'Not executable, no spread/borrow/tax assumptions; lead conditional on hit is NOT standalone timing skill.'}

def summarize(q):
    out={}
    for name,start,end in [('development','2000-01-01','2009-12-31'),('primary','2010-01-01','2025-12-31'),('reserve','2026-01-01','2026-12-31')]:
        g=q[(q.date>=start)&(q.date<=end)&(q.label_end<=end)].copy()
        if g.empty:continue
        d={'first_date':str(g.date.min().date()),'last_date':str(g.date.max().date()),'dates':int(g.date.nunique()),'parents':sorted(g.parent.unique()),'metrics':{},'gains':{},'alerts':{},'eras':{},'direction_states':{}}
        for m in ['constant','baseline','real']+[f'placebo{i}' for i in range(4)]:
            d['metrics'][m]=score(g,m);d['alerts'][m]=alerts(g,m)
            if m not in ('constant','baseline'):d['gains'][m]=interval(g,m)
        for sign,label in [(1,'initial_positive'),(-1,'initial_negative')]:
            gg=g[g.initial_parent_direction==sign]
            d['direction_states'][label]={'n':len(gg),'event_rate':float(gg['class'].mean()),'gain':float(np.mean((gg.baseline-gg['class'])**2-(gg.real-gg['class'])**2))}
        if name=='primary':
            for a,b in [(2010,2014),(2015,2019),(2020,2025)]:
                h=g[g.date.dt.year.between(a,b)]
                d['eras'][f'{a}-{b}']={'n':len(h),'real_mean_brier_gain':float(np.mean((h.baseline-h['class'])**2-(h.real-h['class'])**2))}
            d['by_parent']={p:{'n':len(x),'event_rate':float(x['class'].mean()),'mean_gain':float(np.mean((x.baseline-x['class'])**2-(x.real-x['class'])**2))} for p,x in g.groupby('parent')}
        out[name]=d
    p=out['primary'];gain=p['gains']['real'];precision=p['alerts'];has_events=p['metrics']['baseline']['events']>=100
    out['research_promising_gate']=bool(has_events and gain['mean_date_brier_gain']>=.002 and gain['ci95'][0]>0 and
        sum(v['real_mean_brier_gain']>0 for v in p['eras'].values())>=2 and
        precision['real']['weekly_precision']-precision['baseline']['weekly_precision']>=.02 and
        p['metrics']['real']['logloss']<=p['metrics']['baseline']['logloss'] and
        gain['mean_date_brier_gain']>max(p['gains'][f'placebo{i}']['mean_date_brier_gain'] for i in range(4)))
    out['authority']='RESEARCH_ONLY_NO_AUTOMATIC_RANK_ALERT_SIZE_OR_TRADE'
    return out

def run(root:Path):
    dest=root/'private'/'run01'
    if dest.exists():raise ValueError('original output exists; no rerun or overwrite')
    vw10,ew10,vw49,f,maps=read_data(root)
    complete=features(vw10,ew10,vw49,f,maps)
    # Prefix causality: later appended data must not change ANY prior feature.
    cutoff=pd.Timestamp('2005-12-30');mask=vw10.index<=cutoff
    prefix=features(vw10.loc[mask],ew10.loc[mask],vw49.loc[mask],f.loc[mask],maps)
    cols=BASE+[a+'_'+b for a in ['real']+[f'placebo{i}' for i in range(4)] for b in CHILD]
    expected=complete[complete.date<=cutoff]
    np.testing.assert_allclose(prefix[cols],expected[cols],equal_nan=True,atol=1e-9,rtol=1e-9)
    z=complete[(complete.date.dt.weekday==4)&(complete.date>='1980-01-01')&complete.eligible_parent]
    excluded_for_features=len(z)
    z=z.replace([np.inf,-np.inf],np.nan).dropna(subset=cols)
    excluded_for_features-=len(z)
    z,omitted=attach_labels(z,vw10,f)
    records=[];receipts=[]
    dest.mkdir(parents=True)
    for year in range(2000,2027):
        cut=pd.Timestamp(f'{year}-01-01')
        train=z[(z.date>=cut-pd.DateOffset(years=20))&(z.label_end<cut)]
        test=z[z.date.dt.year==year].copy()
        if test.empty:continue
        if len(train)<1000 or train.label_end.max()>=test.date.min():raise ValueError('not enough purged training')
        p,receipt=fit_year(train,test)
        for k,x in p.items():test[k]=x
        receipt.update({'year':year,'train_n':len(train),'test_n':len(test),'train_last_label':str(train.label_end.max().date()),'test_first':str(test.date.min().date())})
        receipts.append(receipt)
        keep=['date','parent','pos','label_end','entry_date','class','confirmation_delay','initial_parent_direction','forward_signed_logrel']+list(p)
        records.append(test[keep]);print('FIT',year,'train',len(train),'test',len(test),flush=True)
        (dest/'progress.json').write_text(json.dumps({'year':year,'status':'RUNNING_NOT_ACCEPTED'}))
    pred=pd.concat(records,ignore_index=True)
    pred.to_csv(dest/'predictions.csv.gz',index=False,compression='gzip')
    output={'id':'LP-HIERARCHY-09','run_at':datetime.now(timezone.utc).isoformat(),'n_predictions':len(pred),
      'source_sha256':sha(Path(__file__)),'protocol_sha256':sha(root/'PROTOCOL.json'),'mapping_sha256':sha(root/'MAPPING_AUDIT.json'),
      'sources':json.loads((root/'SOURCE_MANIFEST.json').read_text()),'omitted':{'missing_baseline_or_child_inputs':excluded_for_features,**omitted},
      'fit_receipts':receipts,'tests':{'feature_prefix_invariance':True,'label_horizon_embargo':True,'common_origin_sample':True,'price_float_conversion_not_used_in_event_label':True},
      'private_predictions_sha256':sha(dest/'predictions.csv.gz'),**summarize(pred)}
    read_data(root)
    (dest/'results.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print('RESULT_AGGREGATED',output['n_predictions'],'GATE',output['research_promising_gate'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    run(parser.parse_args().root)
