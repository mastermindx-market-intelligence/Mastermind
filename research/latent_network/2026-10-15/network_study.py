"""LP-NETWORK-08: causal statistical-network propagation research.

No brokerage/network calls, production schema, or investor-identity claims.
Requires private hash-matched public-source archives supplied with --inputs.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parent
HORIZONS = (5, 21)
SEEDS = (80261015, 80261016, 80261017, 80261018)
BASE = ([f'mom{k}' for k in (5,21,63,126,252)] + [f'rs{k}' for k in (5,21,63,126,252)] +
        ['accel21','relvol63','vol21','vol63','drawdown63','drawup63','trend63','trend252',
         'rank21','market21','marketvol63','SMB21','HML21','other5','other21','other63',
         'dispersion21','ownres5','ownres21','ownres63','otherres5','otherres21','otherres63','resvol63'])
NET = ('peer5','peer21','peer63','peer_positive21','peer_gap21','peer_disp21','edge_strength','edge_coverage')
GRAPHS = ('correlation','directed','placebo0','placebo1','placebo2','placebo3')
MODELS = ('baseline',) + GRAPHS


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(lines: list[str], start: int) -> pd.DataFrame:
    while start < len(lines) and not lines[start].strip():
        start += 1
    end = start + 1
    while end < len(lines) and re.match(r'^\s*\d{8},', lines[end]):
        end += 1
    frame = pd.read_csv(io.StringIO('\n'.join(lines[start:end])), index_col=0)
    frame.columns = frame.columns.str.strip()
    frame.index = pd.to_datetime(frame.index.astype(str), format='%Y%m%d')
    if not frame.index.is_monotonic_increasing or frame.index.duplicated().any():
        raise ValueError('SOURCE_DATE_ORDER')
    return frame.replace([-99.99,-999], np.nan) / 100.0


def read_inputs(inputs: Path, manifest_path: Path) -> tuple[pd.DataFrame,pd.DataFrame]:
    text = {}
    for spec in json.loads(manifest_path.read_text()):
        path = inputs / spec['filename']
        if sha(path) != spec['sha256']:
            raise ValueError('SOURCE_HASH_CHANGED: ' + path.name)
        with zipfile.ZipFile(path) as archive:
            if len(archive.namelist()) != 1:
                raise ValueError('EXPECTED_SINGLE_SOURCE_TABLE')
            text[path.name] = archive.read(archive.namelist()[0]).decode('utf-8-sig').splitlines()
    a = text['49_Industry_Portfolios_daily_CSV.zip']
    start = next(i for i,line in enumerate(a) if 'Average Value Weighted Returns' in line)
    values = section(a,start+1)
    b = text['F-F_Research_Data_Factors_daily_CSV.zip']
    factors = section(b,next(i for i,line in enumerate(b) if 'Mkt-RF' in line))
    dates = values.index.intersection(factors.index)
    dates = dates[dates >= pd.Timestamp('1963-07-01')]
    values,factors = values.loc[dates],factors.loc[dates]
    if len(values.columns) != 49 or factors.isna().any().any() or (values <= -1).any().any():
        raise ValueError('SOURCE_COVERAGE_OR_INVALID_RETURNS')
    return values, factors


def innovations(values: pd.DataFrame, factors: pd.DataFrame, window: int=252) -> pd.DataFrame:
    """Realized response minus prior-only OLS fitted factor expectation.

    Fixed 1e-12 numerical diagonal stabilization; no in-sample residual backfill.
    """
    x = factors[['Mkt-RF','SMB','HML']]
    mx = x.rolling(window,min_periods=window).mean().shift(1).to_numpy()
    my = values.rolling(window,min_periods=window).mean().shift(1).to_numpy()
    cov = np.empty((len(x),3,3)); cross = np.empty((len(x),3,len(values.columns)))
    for j in range(3):
        for k in range(3):
            cov[:,j,k] = (x.iloc[:,j]*x.iloc[:,k]).rolling(window,min_periods=window).mean().shift(1).to_numpy() - mx[:,j]*mx[:,k]
        cross[:,j,:] = values.mul(x.iloc[:,j],axis=0).rolling(window,min_periods=window).mean().shift(1).to_numpy() - mx[:,j,None]*my
    beta = np.full_like(cross,np.nan)
    ok = np.isfinite(cov).all(axis=(1,2))
    inverse = np.linalg.inv(cov[ok] + np.eye(3)[None,:,:]*1e-12)
    beta[ok] = np.einsum('tij,tjk->tik',inverse,cross[ok])
    expected = my + np.einsum('tji,tj->ti',beta,x.to_numpy()-mx)
    return pd.DataFrame(values.to_numpy()-expected,index=values.index,columns=values.columns)


def cross_correlation(target: np.ndarray, source: np.ndarray) -> np.ndarray:
    a = target-target.mean(axis=0); b = source-source.mean(axis=0)
    den = np.sqrt(np.sum(a*a,axis=0)[:,None]*np.sum(b*b,axis=0)[None,:])
    return np.divide(a.T@b,den,out=np.zeros_like(den),where=den>1e-20)


def top_graph(score: np.ndarray, k: int=5) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    score = np.asarray(score,float).copy()
    if score.ndim!=2 or score.shape[0]!=score.shape[1] or not np.isfinite(score).all():
        raise ValueError('INVALID_GRAPH_SCORE')
    np.fill_diagonal(score,0)
    weights = np.zeros_like(score); strength = np.zeros(len(score)); coverage=np.zeros(len(score))
    for i in range(len(score)):
        order = np.argsort(-score[i],kind='stable')
        chosen = [j for j in order if j != i and score[i,j] > 0][:k]
        if chosen:
            raw=score[i,chosen];weights[i,chosen]=raw/raw.sum();strength[i]=raw.mean();coverage[i]=len(chosen)/k
    return weights,strength,coverage


def estimate_graph(history: np.ndarray) -> dict[str,tuple[np.ndarray,np.ndarray,np.ndarray]]:
    n = history.shape[1]; valid = np.isfinite(history).all(axis=0)
    valid &= np.nanstd(history,axis=0)>1e-10
    corr=np.zeros((n,n));directed=np.zeros((n,n))
    if valid.sum()>=2:
        h=history[:,valid];subcorr=cross_correlation(h,h)
        sums=np.cumsum(h,axis=0);blocks=sums[4:]-np.vstack([np.zeros((1,h.shape[1])),sums[:-5]])
        lag=cross_correlation(blocks[5:],blocks[:-5]);asymmetry=lag-lag.T
        corr[np.ix_(valid,valid)]=subcorr;directed[np.ix_(valid,valid)]=asymmetry
    result={'correlation':top_graph(corr),'directed':top_graph(directed)}
    w,s,c=result['directed']
    for j,seed in enumerate(SEEDS):
        permutation=np.random.default_rng(seed).permutation(n)
        result[f'placebo{j}']=(w[np.ix_(permutation,permutation)],s[permutation],c[permutation])
    return result


def make_graphs(residual: pd.DataFrame,lookback: int=756):
    graphs={};receipts=[]
    for year in sorted(set(residual.index.year)):
        beginning=pd.Timestamp(f'{year}-01-01')
        past=residual.loc[residual.index<beginning].tail(lookback)
        if len(past)<lookback:continue
        graphs[year]=estimate_graph(past.to_numpy())
        receipts.append({'year':int(year),'last_source_date':str(past.index[-1].date()),
                         'first_source_date':str(past.index[0].date()),'rows':len(past),
                         'graph_sha256':{g:hashlib.sha256(v[0].astype('<f8').tobytes()).hexdigest() for g,v in graphs[year].items()}})
    return graphs,receipts


def build_features(values:pd.DataFrame,factors:pd.DataFrame):
    r=np.log1p(values);market=np.log1p(factors['Mkt-RF']+factors.RF)
    cumulative=r.cumsum();relative=r.sub(market,axis=0);rc=relative.cumsum()
    residual=innovations(r,factors);graphs,receipts=make_graphs(residual)
    eligible=(r.notna().rolling(756,min_periods=756).sum()==756)
    rank21=rc.diff(21).where(eligible).rank(axis=1,pct=True)
    own={k:rc.diff(k) for k in (5,21,63)}
    sums={k:residual.rolling(k,min_periods=k).sum() for k in (5,21,63)}
    sd=residual.rolling(63,min_periods=63).std().clip(lower=1e-5)
    network={g:{key:np.full(values.shape,np.nan) for key in NET} for g in GRAPHS}
    for year,group in graphs.items():
        mask=values.index.year==year;idx=np.flatnonzero(mask)
        d={k:sums[k].iloc[idx].to_numpy() for k in (5,21,63)};scale=sd.iloc[idx].to_numpy()
        for name,(w,strength,coverage) in group.items():
            # Unknown peer observations invalidate a row, rather than silently act as zero return.
            for k in (5,21,63):
                missing=(~np.isfinite(d[k])).astype(float)@(w>0).T>0
                weighted=np.nan_to_num(d[k],nan=0)@w.T
                weighted[missing]=np.nan
                network[name][f'peer{k}'][idx]=weighted/(scale*np.sqrt(k))
            positive=(d[21]>0).astype(float)@w.T
            means=np.nan_to_num(d[21],nan=0)@w.T
            second=np.nan_to_num(d[21]**2,nan=0)@w.T
            miss=(~np.isfinite(d[21])).astype(float)@(w>0).T>0
            positive[miss]=np.nan;means[miss]=np.nan;second[miss]=np.nan
            network[name]['peer_positive21'][idx]=positive
            network[name]['peer_gap21'][idx]=(means-d[21])/(scale*np.sqrt(21))
            network[name]['peer_disp21'][idx]=np.sqrt(np.maximum(second-means**2,0))/(scale*np.sqrt(21))
            network[name]['edge_strength'][idx]=np.tile(strength,(len(idx),1))
            network[name]['edge_coverage'][idx]=np.tile(coverage,(len(idx),1))
    rows=[]
    for i,name in enumerate(values.columns):
        z=pd.DataFrame(index=values.index)
        for k in (5,21,63,126,252):z[f'mom{k}']=cumulative[name].diff(k);z[f'rs{k}']=rc[name].diff(k)
        z['accel21']=z.rs21.diff(5);z['relvol63']=relative[name].rolling(63).std()
        for k in (21,63):z[f'vol{k}']=r[name].rolling(k).std()
        z['drawdown63']=cumulative[name]-cumulative[name].rolling(63).max()
        z['drawup63']=cumulative[name]-cumulative[name].rolling(63).min()
        for k in (63,252):z[f'trend{k}']=cumulative[name]-cumulative[name].rolling(k).mean()
        z['rank21']=rank21[name];z['market21']=market.rolling(21).sum();z['marketvol63']=market.rolling(63).std()
        z['SMB21']=factors.SMB.rolling(21).sum();z['HML21']=factors.HML.rolling(21).sum()
        for k in (5,21,63):
            z[f'other{k}']=own[k].drop(columns=name).mean(axis=1)
            z[f'ownres{k}']=sums[k][name]/(sd[name]*np.sqrt(k))
            z[f'otherres{k}']=sums[k].drop(columns=name).mean(axis=1)/(sd[name]*np.sqrt(k))
        z['resvol63']=sd[name];z['dispersion21']=own[21].std(axis=1)
        for g in GRAPHS:
            for key in NET:z[g+'_'+key]=network[g][key][:,i]
        z['industry']=name;z['eligible']=eligible[name];z['position']=np.arange(len(z));rows.append(z.reset_index(names='date'))
    return pd.concat(rows,ignore_index=True),receipts,residual


def attach_labels(features:pd.DataFrame,values:pd.DataFrame,factors:pd.DataFrame,horizon:int):
    r=np.log1p(values);market=np.log1p(factors['Mkt-RF']+factors.RF)
    cum=r.cumsum();mc=market.cumsum();relcum=cum.sub(mc,axis=0);rs=relcum.diff(21)
    labels=[];missing=0
    for row in features.itertuples(index=False):
        p=int(row.position);end=p+horizon+1;start=p+1
        if end>=len(values) or not r[row.industry].iloc[start:end+1].notna().all():missing+=1;continue
        target=float((cum[row.industry].iloc[end]-cum[row.industry].iloc[start])-(mc.iloc[end]-mc.iloc[start]))
        raw=float(np.expm1(cum[row.industry].iloc[end]-cum[row.industry].iloc[start]))
        bench=float(np.expm1(mc.iloc[end]-mc.iloc[start]))
        early=-int(np.sign(row.rs21)) if row.rs21*row.rs63>0 else 0
        confirmation=None
        if early:
            path=rs[row.industry].to_numpy()
            for j in range(p+1,end-1):
                if np.isfinite(path[j-1:j+3]).all() and path[j-1]*early<=0 and np.all(path[j:j+3]*early>0):
                    confirmation=j+2-p;break
        labels.append({'date':row.date,'industry':row.industry,'horizon':horizon,'future_relative_log':target,
                       'future_relative_arithmetic':raw-bench,'label_end':values.index[end],
                       'entry_date':values.index[start],'early_direction':early,
                       'confirmation_delay':confirmation})
    if not labels:return features.iloc[:0].copy(),missing
    z=features.merge(pd.DataFrame(labels),on=['date','industry'],validate='one_to_one')
    ranks=z.groupby('date').future_relative_log.rank(method='average')
    n=z.groupby('date').industry.transform('count')
    z['target']=2*((ranks-.5)/n-.5)
    return z,missing


def columns(name:str):
    return BASE if name=='baseline' else BASE+[name+'_'+key for key in NET]


def ridge(train:pd.DataFrame,test:pd.DataFrame,cols:list[str]):
    a=train[cols].to_numpy(float);b=test[cols].to_numpy(float)
    mean=a.mean(0);sd=a.std(0);sd[sd<1e-12]=1
    a=np.c_[np.ones(len(a)),np.clip((a-mean)/sd,-5,5)]
    b=np.c_[np.ones(len(b)),np.clip((b-mean)/sd,-5,5)]
    penalty=np.eye(a.shape[1])*.01;penalty[0,0]=0
    beta=np.linalg.solve(a.T@a/len(a)+penalty,a.T@train.target.to_numpy()/len(a))
    return b@beta,{'n_train':len(train),'n_test':len(test),'features':len(cols),
                   'last_train_label':str(train.label_end.max().date()),
                   'coefficients_sha256':hashlib.sha256(beta.astype('<f8').tobytes()).hexdigest()}


def correlation(x,y):
    a=rankdata(x);b=rankdata(y);a-=a.mean();b-=b.mean();den=np.sqrt(a@a*(b@b))
    return float(a@b/den) if den>0 else 0.0


def daily_metrics(frame:pd.DataFrame,model:str):
    rows=[]
    for date,g in frame.groupby('date',sort=True):
        prediction=g[model].to_numpy();n=len(g);k=max(1,int(np.ceil(.2*n)))
        ordered=g.sort_values([model,'industry'],kind='stable')
        spread=float(ordered.tail(k).future_relative_arithmetic.mean()-ordered.head(k).future_relative_arithmetic.mean())
        rows.append({'date':date,'ic':correlation(prediction,g.future_relative_log),'loss':float(np.mean((prediction-g.target)**2)),
                     'spread':spread,'n':n})
    return pd.DataFrame(rows).set_index('date')


def block_interval(values,seed=80261015):
    v=np.asarray(values,float);n=len(v);mean=float(v.mean())
    if n<104:return {'mean':mean,'ci95':None,'p':None,'dates':n,'inference':'INSUFFICIENT_BLOCKS_DESCRIPTIVE_ONLY'}
    rng=np.random.default_rng(seed);bs=np.empty(1000)
    for i in range(1000):
        starts=rng.integers(n,size=int(np.ceil(n/26)));idx=((starts[:,None]+np.arange(26))%n).ravel()[:n]
        bs[i]=v[idx].mean()
    return {'mean':mean,'ci95':np.quantile(bs,[.025,.975]).tolist(),
            'p':float((1+(np.abs(bs-mean)>=abs(mean)).sum())/1001),'dates':n,'block_weeks':26}


def early_alerts(frame:pd.DataFrame,model:str):
    h=frame[frame.early_direction!=0].copy()
    if h.empty:return {'eligible':0}
    h['score']=h.early_direction*h[model]
    h['correct']=h.early_direction*h.future_relative_log>0
    selected=[]
    for _,g in h.groupby('date'):
        k=max(1,int(np.ceil(.2*len(g))))
        selected.append(g.sort_values(['score','industry'],ascending=[False,True],kind='stable').head(k))
    s=pd.concat(selected).sort_values(['date','industry']);last={};ids=[]
    for row in s.itertuples():
        if int(row.position)-last.get(row.industry,-999)<=int(row.horizon):continue
        last[row.industry]=int(row.position);ids.append(row.Index)
    e=s.loc[ids];good=e[e.correct];confirmed=good[good.confirmation_delay.notna()]
    return {'eligible':len(h),'base_direction_success_rate':float(h.correct.mean()),
            'matched_weekly_alerts':len(s),'matched_weekly_precision':float(s.correct.mean()),
            'matched_weekly_false_alarms':int((~s.correct).sum()),'nonoverlap_episodes':len(e),
            'episode_correct':len(good),'episode_precision':float(e.correct.mean()),
            'correct_and_confirmed':len(confirmed),'median_lead_to_confirmed_rs_turn':float(confirmed.confirmation_delay.median()) if len(confirmed) else None,
            'mean_episode_signed_relative_bps':float((e.early_direction*e.future_relative_arithmetic).mean()*1e4),
            'note':'Prediction of forward relative-return sign, not a calibrated pivot probability. Conditional lead includes its denominator.'}


def summarize(predictions:pd.DataFrame):
    result={};all_tests={}
    for horizon in HORIZONS:
        sub=predictions[predictions.horizon==horizon];output={}
        for period,start,end in [('development','1990-01-01','2009-12-31'),('primary','2010-01-01','2025-12-31'),('reserve','2026-01-01','2026-12-31')]:
            g=sub[(sub.date>=start)&(sub.date<=end)&(sub.label_end<=end)].copy()
            if g.empty:continue
            daily={m:daily_metrics(g,m) for m in MODELS}
            o={'n':len(g),'dates':g.date.nunique(),'industries':g.industry.nunique(),
               'models':{},'comparisons':{},'alerts':{},'eras':{},'placebo_specificity':{}}
            for m,d in daily.items():
                o['models'][m]={'mean_ic':float(d.ic.mean()),'rank_mse':float(d.loss.mean()),
                               'mean_horizon_top_bottom_bps':float(d.spread.mean()*1e4),
                               'after30bp':float(d.spread.mean()*1e4-30),'after100bp':float(d.spread.mean()*1e4-100),
                               'return_is_overlapping_horizon_diagnostic_not_portfolio_CAGR':True}
            for m in ('correlation','directed'):
                diff=daily[m].ic-daily['baseline'].ic
                o['comparisons'][m]={'ic_gain':block_interval(diff),'rank_mse_gain':block_interval(daily['baseline'].loss-daily[m].loss)}
                if period=='primary':all_tests[f'{horizon}:{m}']=o['comparisons'][m]['ic_gain']
            controls={m:float(d.ic.mean()) for m,d in daily.items() if m.startswith('placebo')}
            strongest=max(controls,key=controls.get)
            o['placebo_specificity']={'best_control':strongest,'best_control_mean_ic':controls[strongest],
                                      'directed_minus_best_control_ic':float(daily['directed'].ic.mean()-controls[strongest]),
                                      'paired_interval':block_interval(daily['directed'].ic-daily[strongest].ic),
                                      'selection_of_strongest_control_is_diagnostic_not_preselected_null':True}
            for m in ('baseline','correlation','directed',strongest):o['alerts'][m]=early_alerts(g,m)
            if period=='primary':
                for a,b in ((2010,2014),(2015,2019),(2020,2025)):
                    mask=daily['baseline'].index.year>=a;mask&=daily['baseline'].index.year<=b
                    o['eras'][f'{a}-{b}']={m:float((daily[m].ic-daily['baseline'].ic)[mask].mean()) for m in ('correlation','directed')}
                o['per_industry']={name:{m:float(np.mean((x['baseline']-x.target)**2-(x[m]-x.target)**2)) for m in ('correlation','directed')}
                                   for name,x in g.groupby('industry')}
            output[period]=o
        result[str(horizon)]=output
    order=sorted(all_tests,key=lambda k:all_tests[k]['p']);previous=0
    for i,k in enumerate(order):
        previous=max(previous,min(1,(len(order)-i)*all_tests[k]['p']));all_tests[k]['holm4']=previous
    gates={}
    for horizon in HORIZONS:
        p=result[str(horizon)]['primary']
        for name in ('correlation','directed'):
            ic=p['comparisons'][name]['ic_gain'];mse=p['comparisons'][name]['rank_mse_gain']
            candidate=bool(ic['mean']>=.01 and ic['ci95'][0]>0 and ic['holm4']<.05 and mse['mean']>=.0005 and
                           sum(e[name]>0 for e in p['eras'].values())>=2 and
                           p['alerts'][name]['matched_weekly_precision']>=p['alerts']['baseline']['matched_weekly_precision'])
            if name=='directed':candidate&=p['placebo_specificity']['directed_minus_best_control_ic']>0
            gates[f'{horizon}:{name}']=candidate
    return {'horizons':result,'research_promising_gate':gates,'authority':'NONE_RESEARCH_ONLY'}


def run(inputs:Path,out:Path):
    if out.exists():raise ValueError('OUTPUT_EXISTS_NO_OVERWRITE')
    values,factors=read_inputs(inputs,ROOT/'SOURCE_MANIFEST.json')
    features,graph_receipts,_=build_features(values,factors)
    cutoff=pd.Timestamp('1995-12-29');mask=values.index<=cutoff
    prefix,_,_=build_features(values.loc[mask],factors.loc[mask])
    needed=BASE+[g+'_'+k for g in GRAPHS for k in NET]
    expected=features[features.date<=cutoff]
    np.testing.assert_allclose(prefix[needed],expected[needed],rtol=1e-8,atol=1e-9,equal_nan=True)
    z=features[(features.date.dt.weekday==4)&(features.date>='1970-01-01')&features.eligible].replace([np.inf,-np.inf],np.nan)
    original_rows=len(z);z=z.dropna(subset=needed)
    out.mkdir(parents=True);predictions=[];receipts=[];omissions={}
    for horizon in HORIZONS:
        panel,missing=attach_labels(z,values,factors,horizon);omissions[str(horizon)]=missing
        for year in range(1990,2027):
            start=pd.Timestamp(f'{year}-01-01')
            train=panel[(panel.date>=start-pd.DateOffset(years=20))&(panel.label_end<start)]
            test=panel[panel.date.dt.year==year].copy()
            if test.empty:continue
            if len(train)<1000 or not train.label_end.max()<test.date.min():raise ValueError('TRAINING_BOUNDARY')
            receipt={'horizon':horizon,'year':year,'models':{}}
            for model in MODELS:test[model],receipt['models'][model]=ridge(train,test,columns(model))
            keep=['date','industry','position','horizon','target','future_relative_log','future_relative_arithmetic','label_end','early_direction','confirmation_delay']+list(MODELS)
            predictions.append(test[keep]);receipts.append(receipt)
            print('FIT',horizon,year,len(train),len(test),flush=True)
            (out/'progress.json').write_text(json.dumps({'horizon':horizon,'year':year,'completed_fits':len(receipts)*len(MODELS),'accepted_result':False}))
    predictions=pd.concat(predictions,ignore_index=True)
    predictions.to_csv(out/'predictions.csv.gz',index=False,compression='gzip')
    result={'id':'LP-NETWORK-08','created_at':datetime.now(timezone.utc).isoformat(),'n_predictions':len(predictions),
            'source_sha256':sha(Path(__file__)),'protocol_sha256':sha(ROOT/'PROTOCOL.json'),
            'source_manifest':json.loads((ROOT/'SOURCE_MANIFEST.json').read_text()),'fit_receipts':receipts,
            'graph_receipts':graph_receipts,'rows_omitted_for_features':original_rows-len(z),'missing_future_outcomes':omissions,
            'checks':{'future_prefix_invariance':True,'graph_source_before_year':True,'complete_label_purge':True,'same_models_same_rows':True},
            'private_predictions_sha256':sha(out/'predictions.csv.gz'),**summarize(predictions)}
    read_inputs(inputs,ROOT/'SOURCE_MANIFEST.json')
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('COMPLETED',result['n_predictions'],json.dumps(result['research_promising_gate']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();run(args.inputs,args.out)
