"""Original, time-qualified nested-cycle and cohort research features.

Research only. Never emits an order, entry permission, or calibrated probability.
Native oscillator math is injected from the previously qualified source loader.
"""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
from native_replay import frame, dots, load_math

RESERVED_START = pd.Timestamp('2020-01-01')
RESERVED_END = pd.Timestamp('2023-05-31')
ANCHOR = pd.Timestamp('1990-01-05')


def validate_index(index):
    if (not isinstance(index, pd.DatetimeIndex) or not index.is_unique
            or not index.is_monotonic_increasing or index.hasnans):
        raise ValueError('Unique increasing dated observations required')
    if ((index >= RESERVED_START) & (index <= RESERVED_END)).any():
        raise ValueError('Reserved observations are not research inputs')
    if (index < RESERVED_START).any() and (index > RESERVED_END).any():
        raise ValueError('Feature state may not cross the protected gap')


def load_segment(root, segment):
    if segment not in ('pre', 'post'): raise ValueError('Unknown segment')
    root = Path(root); m = json.loads((root/'INPUT_MANIFEST.json').read_text())
    p, t, v = {}, {}, {}
    for symbol, info in m['sources'].items():
        if info.get('missing'): continue
        path = root/'private'/f'{symbol}_{segment}.parquet'
        import hashlib
        if hashlib.sha256(path.read_bytes()).hexdigest() != info['segments'][segment]['sha256']:
            raise ValueError('Input snapshot changed: '+symbol)
        d = pd.read_parquet(path)
        d.index = pd.DatetimeIndex(d.index).as_unit('ns')
        validate_index(d.index)
        if symbol in ('VIX', 'VVIX'):
            v[symbol] = d['vvix' if symbol=='VVIX' else 'close_price'].astype(float)
        else:
            p[symbol] = d['close_price'].astype(float)
            t[symbol] = d['close'].astype(float)
            for x in (p[symbol], t[symbol]):
                z = x.dropna().to_numpy()
                if (z<=0).any() or not np.isfinite(z).all(): raise ValueError('Invalid prices')
    index = p['SPY'].index
    return (pd.DataFrame(p).reindex(index), pd.DataFrame(t).reindex(index),
            pd.DataFrame(v).reindex(index), m)


def causal_rank(s, window=756, minimum=252):
    """Current value's rank against past observations only; no full-sample rank."""
    a = s.to_numpy(float); out = np.full(len(a), np.nan)
    for i, value in enumerate(a):
        past = a[max(0,i-window):i]; past = past[np.isfinite(past)]
        if np.isfinite(value) and len(past)>=minimum:
            out[i] = (np.sum(past<value)+.5*np.sum(past==value))/len(past)
    return pd.Series(out,index=s.index)


def period_bars(close, unit='2W', parity=0):
    """Completed calendar periods, conservatively known at their calendar end.

    A holiday-period ending is not advanced to an earlier trading date. This
    conservatism is explicit; no exact chart-calendar parity is asserted.
    """
    validate_index(close.index)
    if parity not in (0,1): raise ValueError('Invalid two-week parity')
    idx = close.index
    if unit == '2W':
        friday = idx + pd.to_timedelta((4-idx.weekday)%7,unit='D')
        week = ((friday-ANCHOR).days//7).to_numpy()
        group = np.floor_divide(week+parity,2)
        end = ANCHOR+pd.to_timedelta((2*group+1-parity)*7,unit='D')
    elif unit == '1M':
        end = idx.to_period('M').to_timestamp(how='end').normalize()
    else: raise ValueError('Unsupported calendar period')
    b = pd.DataFrame({'close':close.to_numpy(float),'end':end,'last_input':idx})
    b = b.groupby('end',sort=True).agg(close=('close','last'),last_input=('last_input','last'),observations=('close','count'))
    return b.loc[b.index<=idx[-1]]


def map_known(observations, index):
    """As-of map; a value cannot appear before its known calendar date."""
    if not observations.index.is_unique: raise ValueError('Duplicate known dates')
    target = pd.DataFrame({'date':pd.DatetimeIndex(index).as_unit('ns')})
    source = observations.copy()
    source.index = pd.DatetimeIndex(source.index).as_unit('ns')
    source = source.rename_axis('date').reset_index()
    if source.empty: return pd.DataFrame(index=index,columns=observations.columns,dtype=float)
    out = pd.merge_asof(target,source,on='date',direction='backward',allow_exact_matches=True)
    return out.set_index('date')


def slow_features(close,c,unit,parity=0):
    b=period_bars(close,unit,parity); x=b.close
    if x.empty:return pd.DataFrame(index=close.index)
    macd,signal=c.rsi_macd(x); hist=macd-signal
    nmin=26 if unit=='2W' else 12
    z=pd.DataFrame({'macd':macd,'signal':signal,'hist':hist,'hist_delta':hist.diff(),
                    'macd_delta':macd.diff(),'depth_rank':causal_rank(macd,104 if unit=='2W' else 60,nmin),
                    'rsi':c.rsi(x,14),'bars':np.arange(1,len(x)+1)},index=x.index)
    return map_known(z,close.index).add_prefix('w2_' if unit=='2W' else 'month_')


def confirmed_phase_onset(signals, window=6, required=3):
    if required not in (1,2,3) or window<1:raise ValueError('Invalid phase consensus')
    a=np.asarray(signals,dtype=bool)
    if a.ndim!=2 or a.shape[1]!=3:raise ValueError('Three phase signals required')
    seen=pd.DataFrame(a).rolling(window,min_periods=1).max().sum(axis=1)>=required
    return (seen & ~seen.shift(1,fill_value=False)).to_numpy(bool)


def episode_features(close,raw_dot,threshold=.05):
    """Observable drawdown episode and failed-attempt memory, never future lows."""
    validate_index(close.index)
    if not raw_dot.index.equals(close.index):raise ValueError('Event calendar mismatch')
    if not 0<threshold<1:raise ValueError('Invalid drawdown threshold')
    values=close.to_numpy(float); lows=close.rolling(21,min_periods=21).min().to_numpy()
    peak=float(values[0]); peak_pos=0; active=False; ep_start=0; ep_number=0; attempts=[]
    rows=[]
    for i,price in enumerate(values):
        if price>=peak:
            peak=float(price);peak_pos=i;active=False;attempts=[]
        if not active and price/peak-1<=-threshold:
            active=True;ep_start=i;ep_number+=1;attempts=[]
        for old in attempts:
            if not old['failed'] and price<old['low']:old['failed']=True
        failed=sum(x['failed'] for x in attempts)
        rows.append({'episode_number':ep_number if active else 0,'episode_age':i-ep_start if active else 0,
          'episode_peak_age':i-peak_pos,'episode_drawdown':price/peak-1,
          'prior_attempts':len(attempts),'prior_failed_attempts':failed,
          'episode_start':str(close.index[ep_start].date()) if active else None})
        # Current event is not a prior attempt and cannot fail before its own issue.
        if active and bool(raw_dot.iloc[i]) and np.isfinite(lows[i]):
            attempts.append({'low':float(lows[i]),'failed':False})
    return pd.DataFrame(rows,index=close.index)


def own_features(close,c,native_mask,phases=True):
    close=close.dropna();validate_index(close.index)
    if len(close)<300: return pd.DataFrame(index=close.index)
    f=pd.DataFrame(index=close.index);r=close.pct_change(fill_method=None)
    for n in [5,21,63,126,252]:f[f'return_{n}']=close/close.shift(n)-1
    for n in [63,252]:f[f'drawdown_{n}']=close/close.rolling(n,min_periods=n).max()-1
    f['low_distance21']=close/close.rolling(21,min_periods=21).min()-1
    f['price_above200']=close/close.rolling(200,min_periods=200).mean()-1
    f['rv21']=r.rolling(21,min_periods=21).std()*np.sqrt(252)
    f['rv126']=r.rolling(126,min_periods=126).std()*np.sqrt(252)
    f['efficiency252']=np.log(close/close.shift(252)).abs()/np.log1p(r).abs().rolling(252,min_periods=252).sum()
    f['drawdown_rank']=causal_rank(f.drawdown_252)
    ds=[]
    for phase in range(3 if phases else 1):
        flags,_=dots(close,c,native_mask,phase);ds.append(flags.to_numpy(bool));f[f'dot_phase{phase}']=flags
    f['dot']=f['dot_phase0']
    if phases:f['persistent_dot']=confirmed_phase_onset(np.column_stack(ds))
    sig=frame(close,c,0)
    if not sig.empty:
        idx=close.index.get_indexer(pd.DatetimeIndex(sig.known_ts))
        sig=sig.loc[(idx%3)==0]
        fast=pd.DataFrame({'fast_macd':sig.macd.to_numpy(),'fast_hist':(sig.macd-sig.sig).to_numpy(),
                           'fast_k':sig.k.to_numpy(),'fast_d':sig.d.to_numpy()},index=pd.DatetimeIndex(sig.known_ts))
        fast['fast_hist_delta']=fast.fast_hist.diff()
        fast['fast_cross']=((fast.fast_hist>0)&(fast.fast_hist.shift(1)<=0)).astype(float)
        f=f.join(map_known(fast,close.index))
        f['rsi_macd_3d_cross']=False
        at=fast.index[fast.fast_cross>0]
        f.loc[f.index.intersection(at),'rsi_macd_3d_cross']=True
    else:
        f['rsi_macd_3d_cross']=False
    f=f.join(slow_features(close,c,'2W')).join(slow_features(close,c,'1M'))
    f=f.join(episode_features(close,f['dot']))
    other=episode_features(close,f.rsi_macd_3d_cross)
    f['cross_prior_attempts']=other.prior_attempts
    f['cross_prior_failed_attempts']=other.prior_failed_attempts
    f['slow_improving']=(f.w2_hist_delta>0)&f.w2_hist.notna()
    f['slow_crossed']=(f.w2_hist>0)&f.w2_hist.notna()
    f['monthly_improving']=(f.month_hist_delta>0)&f.month_hist.notna()
    f['source_valid']=close.notna()
    return f


def peer_context(price,total,symbol,members):
    """Leave-one-name-out peers. Missing members never become bearish votes."""
    members=[s for s in members if s!=symbol]
    if len(members)<2:raise ValueError('At least two other cohort members required')
    p=price[members];t=total[members];eligible=p.expanding().count()>=63
    above=p>p.rolling(20,min_periods=20).mean()
    low=p<=p.rolling(20,min_periods=20).min()
    valid=eligible&p.notna()&p.shift(5).notna()
    count=valid.sum(axis=1);den=eligible.sum(axis=1)
    coverage=count/den.replace(0,np.nan)
    ok=(count>=2)&(coverage>=.6)
    rets=t.pct_change(fill_method=None).where(valid)
    daily=rets.mean(axis=1).where(ok)
    # A cohort index is only an arithmetic research basket; not an actual fund.
    ret5=np.expm1(np.log1p(daily).rolling(5,min_periods=5).sum())
    ret21=np.expm1(np.log1p(daily).rolling(21,min_periods=21).sum())
    share=above.where(valid).sum(axis=1)/count.replace(0,np.nan)
    lows=low.where(valid).sum(axis=1)/count.replace(0,np.nan)
    share=share.where(ok);lows=lows.where(ok)
    pressure=lows.rolling(5,min_periods=5).mean()-lows.shift(5).rolling(5,min_periods=5).mean()
    out=pd.DataFrame({'peer_return_1':daily,'peer_return_5':ret5,'peer_return_21':ret21,
       'peer_above20':share,'peer_breadth_change':share-share.shift(5),'peer_low_pressure_change':pressure,
       'peer_coverage':coverage,'peer_count':count,'peer_valid':ok},index=price.index)
    out['peer_repair']=(out.peer_return_5>0)&(out.peer_breadth_change>0)&ok
    out['peer_pressure_easing']=(pressure<0)&ok
    return out


def context_features(price,total,vol,symbol,members,own):
    peer=peer_context(price,total,symbol,members)
    f=own.reindex(price.index).join(peer)
    ownret=total[symbol].pct_change(fill_method=None);market=total.SPY.pct_change(fill_method=None)
    beta=(ownret.rolling(126,min_periods=63).cov(market)/market.rolling(126,min_periods=63).var()).shift(1)
    residual=ownret-beta*market
    f['market_beta']=beta
    f['market_resilience21']=residual.rolling(21,min_periods=21).sum()
    f['relative_resilience21']=(total[symbol]/total[symbol].shift(21)-1)-f.peer_return_21
    f['down_market_resilience21']=residual.where(market<0,0).rolling(21,min_periods=21).sum()
    f['residual_vol_ratio']=residual.rolling(126,min_periods=63).std()/ownret.rolling(126,min_periods=63).std()
    f['market_return21']=total.SPY/total.SPY.shift(21)-1
    for key in ('VIX','VVIX'):
        x=vol[key];ma20=x.rolling(20,min_periods=20).mean()
        f[key.lower()+'_level']=x
        f[key.lower()+'_trend']=x.rolling(5,min_periods=5).mean()/ma20-1
        f[key.lower()+'_slope']=ma20/ma20.shift(5)-1
    f['resilience_positive']=f.relative_resilience21>0
    return f


def policies(f):
    raw=f['dot'].fillna(False).astype(bool);slow=f.slow_improving.fillna(False).astype(bool)
    peer=f.peer_repair.fillna(False).astype(bool);relative=f.resilience_positive.fillna(False).astype(bool)
    return {'dot':raw,'persistent_dot':f.persistent_dot.fillna(False).astype(bool),
      'dot_slow':raw&slow,'dot_peer':raw&peer,'dot_slow_peer':raw&slow&peer,
      'dot_slow_peer_relative':raw&slow&peer&relative}


def interpretation(row):
    """Descriptive state, not a buy/sell gate or a durable-bottom declaration."""
    def finite(k):return k in row and pd.notna(row[k]) and np.isfinite(float(row[k]))
    if not all(finite(k) for k in ['w2_hist','w2_hist_delta','peer_coverage','peer_return_21']):
        return 'CONTEXT_INCOMPLETE'
    slow=row['w2_hist_delta']>0;cohort=bool(row.get('peer_repair',False));relative=row.get('relative_resilience21',np.nan)>0
    if not slow:return 'FAST_TURN_WITH_SLOW_PRESSURE'
    if not cohort:return 'LOCAL_REPAIR_WITHOUT_COHORT_CONFIRMATION'
    if not relative:return 'COHORT_REPAIR_WITHOUT_RELATIVE_RESILIENCE'
    return 'REPAIR_WITH_RELATIVE_RESILIENCE'
