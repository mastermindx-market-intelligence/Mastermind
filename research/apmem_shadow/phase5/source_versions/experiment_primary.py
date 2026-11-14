"""Frozen sector recovery experiment. Research only; no trading authority.

Run on hash-bound, already cropped private snapshots. Next-close execution,
explicit fixed horizons, no stop optimization, no future/protected-window data.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from native_replay import load_math, dots

SECTORS = ['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
HORIZONS = (21, 63)
PROTECTED_START = pd.Timestamp('2020-01-01')
PROTECTED_END = pd.Timestamp('2023-05-31')


def write_json(path, obj):
    def default(x):
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x).__name__)
    path.write_text(json.dumps(obj, indent=2, default=default, allow_nan=False))


def check_index(index):
    if not isinstance(index, pd.DatetimeIndex) or not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError('Unique ascending economic-session index required')
    if ((index >= PROTECTED_START) & (index <= PROTECTED_END)).any():
        raise ValueError('Reserved interval cannot be consumed')


def load_segment(root, segment, manifest):
    bound = {(x['instrument'], x['segment']): x for x in manifest['inputs']}
    prices, total, vol = {}, {}, {}
    for ticker in SECTORS + ['SPY','VIX','VVIX','VIX3M']:
        p = root/'private'/f'{ticker}_{segment}.parquet'
        if hashlib.sha256(p.read_bytes()).hexdigest() != bound[ticker, segment]['snapshot_sha256']:
            raise ValueError('Snapshot drift: ' + ticker)
        d = pd.read_parquet(p);check_index(d.index)
        if ticker in ['VIX','VVIX','VIX3M']:
            vol[ticker] = d['vvix' if ticker == 'VVIX' else 'close_price']
        else:
            prices[ticker], total[ticker] = d.close_price, d.close
    # SPY is the retained calendar; missing sector rows are a refusal, not interpolation.
    start = max(x.index[0] for x in prices.values())
    end = min(x.index[-1] for x in prices.values())
    calendar = prices['SPY'].loc[start:end].index
    p = pd.DataFrame({k: v.reindex(calendar) for k,v in prices.items()})
    t = pd.DataFrame({k: v.reindex(calendar) for k,v in total.items()})
    if not np.isfinite(p.to_numpy()).all() or not np.isfinite(t.to_numpy()).all():
        raise ValueError('Missing price on a retained market session')
    if (p <= 0).any().any() or (t <= 0).any().any(): raise ValueError('Nonpositive price')
    v = pd.DataFrame({k: x.reindex(calendar) for k,x in vol.items()})
    return p, t, v


def context(price, total, vol):
    check_index(price.index)
    p, t = price[SECTORS], total[SECTORS]
    dd = p/p.rolling(63, min_periods=63).max()-1
    washed = dd.le(-.05).astype(float).where(dd.notna())
    wash_count = washed.sum(axis=1, min_count=9)
    stress = wash_count.rolling(21, min_periods=21).max().ge(5)
    ma = p.rolling(20, min_periods=20).mean()
    count_above = p.gt(ma).astype(float).where(ma.notna()).sum(axis=1, min_count=9)
    market_index = (1+t.pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()
    market5 = market_index/market_index.shift(5)-1
    repair = market5.gt(0) & count_above.gt(count_above.shift(5))
    own5 = t/t.shift(5)-1
    sector_trend = p.gt(p.rolling(126).mean()) & (t/t.shift(63)-1).gt(0)
    breakout = p.gt(p.shift(1).rolling(20).max())
    vv = {}
    for name in ('VIX','VVIX'):
        x = vol[name]
        m10, m30 = x.rolling(10, min_periods=10).mean(), x.rolling(30, min_periods=30).mean()
        valid = m10.notna() & m30.notna() & m10.shift(5).notna()
        vv[name+'_valid'] = valid
        vv[name+'_rising'] = m10.gt(m30) & m10.gt(m10.shift(5))
        vv[name+'_improving'] = m10.lt(m10.shift(5))
    depth_rank = dd.rolling(504, min_periods=252).rank(pct=True)
    return {'drawdown': dd, 'wash_count': wash_count, 'stress': stress,
            'repair': repair, 'own5': own5, 'continuation': sector_trend & breakout,
            'market5': market5, 'above20': count_above, 'depth_pctile': 1-depth_rank,
            'risk21': t.pct_change(fill_method=None).rolling(21).std()*np.sqrt(252), **vv}


def onset(mask, absent=3):
    # An entry is a fresh transition after three absent sessions, not each board day.
    previous = mask.astype(int).shift(1).rolling(absent, min_periods=absent).max()
    return mask & previous.eq(0)


def policies(dot, ctx):
    def across(s): return pd.DataFrame(np.repeat(np.asarray(s)[:,None], len(SECTORS), axis=1), index=dot.index, columns=SECTORS)
    st, rp = across(ctx['stress']), across(ctx['repair'])
    own = ctx['own5'].gt(0)
    common = across(ctx['VIX_valid'] & ctx['VVIX_valid'])
    vx = across(ctx['VIX_valid'] & ~ctx['VIX_rising'])
    vv = across(ctx['VVIX_valid'] & ~ctx['VVIX_rising'])
    easing = across(ctx['VIX_valid'] & ctx['VVIX_valid'] & ctx['VIX_improving'] & ctx['VVIX_improving'])
    memory = dot.rolling(6, min_periods=1).max().eq(1)
    seq = memory & st & rp & own
    raw = {'dot': dot, 'dot_common':dot & common,
           'dot_stress':dot & st, 'dot_repair':dot & rp,
           'dot_stress_repair':dot & st & rp,
           'dot_vix_not_rising':dot & vx & common,
           'dot_vvix_not_rising':dot & vv & common,
           'dot_both_not_rising':dot & vx & vv & common,
           'dot_vol_easing':dot & easing & common,
           'same_day_sequence':dot & st & rp & own,
           'sequence_repair':seq,
           'repair_no_dot':st & rp & own,
           'dot_own_repair_sequence':memory & own,
           'continuation':ctx['continuation'],
           'phase_router':(seq & st) | (ctx['continuation'] & ~st)}
    return {k:onset(v.fillna(False)) for k,v in raw.items()}


def eval_mask(index, segment):
    # Frozen common-vol-history comparison. The post-gap segment has a fresh 504-row warmup.
    if segment == 'pre': return np.asarray(index >= '2007-01-01')
    return np.arange(len(index)) >= 504


def event_outcomes(price, total, signals, valid_origin, ctx, phase, segment):
    idx=price.index; records=[]
    oldlow=price[SECTORS].rolling(21).min()
    last_dot={k:pd.Series(np.where(signals['dot'][k],np.arange(len(idx)),np.nan),index=idx).ffill() for k in SECTORS}
    for policy, mask in signals.items():
        for ticker in SECTORS:
            for origin in np.flatnonzero(mask[ticker].to_numpy() & valid_origin):
                entry=origin+1
                for horizon in HORIZONS:
                    end=entry+horizon
                    if end>=len(idx):continue
                    pp=price[ticker].iloc[entry:end+1].to_numpy(float)
                    gross=float(total[ticker].iloc[end]/total[ticker].iloc[entry]-1)
                    spy=float(total.SPY.iloc[end]/total.SPY.iloc[entry]-1)
                    market=float((total[SECTORS].iloc[end]/total[SECTORS].iloc[entry]-1).mean())
                    records.append({'policy':policy,'ticker':ticker,'segment':segment,'phase':phase,
                      'origin':str(idx[origin].date()),'entry':str(idx[entry].date()),'end':str(idx[end].date()),
                      'remembered_dot_session':str(idx[int(last_dot[ticker].iloc[origin])].date()) if pd.notna(last_dot[ticker].iloc[origin]) else None,
                      'sessions_since_dot':int(origin-last_dot[ticker].iloc[origin]) if pd.notna(last_dot[ticker].iloc[origin]) else None,
                      'horizon':horizon,'gross_return':gross,'net_return':(1+gross)*.9995/1.0005-1,
                      'spy_excess':gross-spy,'sector_excess':gross-market,
                      'mae_close':float((pp/pp[0]-1).min()),'mfe_close':float((pp/pp[0]-1).max()),
                      'prior_low_holds':bool(pp.min()>=oldlow[ticker].iloc[origin]),
                      'stress':bool(ctx['stress'].iloc[origin]),'repair':bool(ctx['repair'].iloc[origin]),
                      'vix_rising':bool(ctx['VIX_rising'].iloc[origin]) if ctx['VIX_valid'].iloc[origin] else None,
                      'vvix_rising':bool(ctx['VVIX_rising'].iloc[origin]) if ctx['VVIX_valid'].iloc[origin] else None,
                      'depth_percentile':float(ctx['depth_pctile'][ticker].iloc[origin]) if pd.notna(ctx['depth_pctile'][ticker].iloc[origin]) else None})
    return pd.DataFrame(records)


def metrics(equity, gross, trades):
    r=np.diff(equity)/equity[:-1];years=max(len(r)/252,1/252)
    sd=float(r.std(ddof=1)) if len(r)>1 else 0.
    vol=sd*np.sqrt(252)
    return {'cagr':float((equity[-1]/equity[0])**(1/years)-1),
      'total_return':float(equity[-1]/equity[0]-1),'annual_vol':vol,
      'sharpe':float(r.mean()/sd*np.sqrt(252)) if sd else None,
      'maximum_drawdown':float(np.min(equity/np.maximum.accumulate(equity)-1)),
      'worst_5pct_mean':float(np.sort(r)[:max(1,int(np.ceil(.05*len(r))))].mean()),
      'mean_exposure':float(np.mean(gross)),'closed_trades':len(trades),'sessions':len(equity)}


def account(total, signal, valid_origin, horizon, cost=.0005, extra_delay=0, scale=1.):
    if horizon<1 or not (0<=cost<.1) or not (0<scale<=1):raise ValueError('Invalid research policy')
    ids=np.flatnonzero(valid_origin)
    if len(ids)<70:return None
    start,end=int(ids[0]),int(ids[-1]);tr=total[SECTORS].to_numpy(float);n=len(SECTORS)
    cash=np.ones(n)/n;units=np.zeros(n);exit_at=np.full(n,-1);entry_at=np.full(n,-1);spent=np.zeros(n)
    wealth=[];gross=[];trades=[];turnover=0.
    s=signal[SECTORS].to_numpy(bool)
    for i in range(start,end+1):
        vals=units*tr[i]
        for j in range(n):
            if units[j] and (i==exit_at[j] or i==end):
                proceeds=vals[j]*(1-cost);cash[j]+=proceeds;turnover+=vals[j]
                trades.append({'ticker':SECTORS[j],'entry':str(total.index[entry_at[j]].date()),
                  'exit':str(total.index[i].date()),'net_return':float(proceeds/spent[j]-1)})
                units[j]=0.;exit_at[j]=-1
        origin=i-1-extra_delay
        if origin>=start and valid_origin[origin] and i+horizon<=end:
            for j in range(n):
                if units[j]==0 and s[origin,j]:
                    invested=cash[j]*scale/(1+cost)
                    spent[j]=invested*(1+cost);cash[j]-=spent[j];units[j]=invested/tr[i,j]
                    entry_at[j]=i;exit_at[j]=i+horizon;turnover+=invested
        value=units*tr[i];eq=float(cash.sum()+value.sum())
        if cash.min()<-1e-10 or eq<=0:raise AssertionError('Accounting violation')
        wealth.append(eq);gross.append(float(value.sum()/eq))
    m=metrics(np.array(wealth),gross,trades);m['turnover_equity_units']=float(turnover)
    return {'metrics':m,'curve':pd.DataFrame({'equity':wealth,'gross':gross},index=total.index[start:end+1]),'trades':trades}


def buyhold(total, valid, cost=.0005):
    ix=np.flatnonzero(valid);x=total[SECTORS].iloc[ix]
    values=x.div(x.iloc[0]).sum(axis=1)/len(SECTORS)/(1+cost)
    values.iloc[0]=1.;values.iloc[-1]*=(1-cost)
    return metrics(values.to_numpy(),np.ones(len(values)),[{}]*len(SECTORS))


def run(root, output):
    if output.exists():raise ValueError('Output exists; recover the original run instead of replaying')
    output.mkdir();(output/'private').mkdir()
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text())
    c,mask=load_math(root/'source',manifest)
    summary=[];event_tables=[];receipts=[];forecasts=[]
    started=datetime.now(timezone.utc).isoformat()
    for segment in ('pre','post'):
        price,total,vol=load_segment(root,segment,manifest);ctx=context(price,total,vol);valid=eval_mask(price.index,segment)
        for phase in (0,1,2):
            dd=pd.DataFrame(False,index=price.index,columns=SECTORS)
            native=[]
            for ticker in SECTORS:
                dd[ticker],obs=dots(price[ticker],c,mask,phase)
                native.extend({'ticker':ticker,**o} for o in obs)
            ss=policies(dd,ctx)
            native_df=pd.DataFrame(native);native_df.to_csv(output/'private'/f'native_{segment}_{phase}.csv',index=False)
            ev=event_outcomes(price,total,ss,valid,ctx,phase,segment)
            ev.to_parquet(output/'private'/f'events_{segment}_{phase}.parquet');event_tables.append(ev)
            for h in HORIZONS:
                costs=(.0005,.002) if phase==0 else (.0005,)
                for cost in costs:
                    for policy,signal in ss.items():
                        result=account(total,signal,valid,h,cost)
                        if result is None:continue
                        name=f'{segment}_p{phase}_h{h}_c{int(cost*10000)}_{policy}'
                        result['curve'].to_csv(output/'private'/(name+'.csv'))
                        pd.DataFrame(result['trades']).to_csv(output/'private'/(name+'_trades.csv'),index=False)
                        summary.append({'segment':segment,'phase':phase,'horizon':h,'cost_bp':cost*10000,'policy':policy,**result['metrics']})
            receipts.append({'segment':segment,'phase':phase,'rows':len(price),'eval_rows':int(valid.sum()),'native_dots':len(native),'event_rows':len(ev),
                 'vix_missing':int(vol.VIX.isna().sum()),'vvix_missing':int(vol.VVIX.isna().sum()),'protected_rows':0})
            print('EXPERIMENT_PHASE_FINISHED',segment,phase,'native_dots',len(native),'events',len(ev),flush=True)
        summary.append({'segment':segment,'phase':0,'horizon':0,'cost_bp':5,'policy':'equal_weight_buyhold',**buyhold(total,valid)})
    a=pd.DataFrame(summary);a.to_csv(output/'portfolio_metrics.csv',index=False)
    e=pd.concat(event_tables,ignore_index=True)
    group=e.groupby(['segment','phase','horizon','policy'],dropna=False)
    g=group.agg(events=('ticker','size'),dates=('origin','nunique'),mean_net=('net_return','mean'),median_net=('net_return','median'),
      mean_spy_excess=('spy_excess','mean'),mean_sector_excess=('sector_excess','mean'),mean_mae_close=('mae_close','mean'),
      mean_mfe_close=('mfe_close','mean'),prior_low_hold_rate=('prior_low_holds','mean'))
    g.to_csv(output/'event_summary.csv')
    write_json(output/'RUN_RECEIPT.json',{'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),
      'status':'COMPLETE','dataset_manifest_sha256':hashlib.sha256((root/'INPUT_MANIFEST.json').read_bytes()).hexdigest(),
      'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'experiment.py',root/'native_replay.py']},
      'runs':receipts,'accounts':len(a),'event_rows':len(e),'results_are_exploratory':True,'prospective_outcomes':0,'may_trade':False})
    print('INDEPENDENT_EXPERIMENT_COMPLETE',len(a),'accounts',len(e),'event-family-horizon rows',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();run(args.root,args.output)
