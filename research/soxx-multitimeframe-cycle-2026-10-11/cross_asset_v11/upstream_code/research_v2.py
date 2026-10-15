#!/usr/bin/env python3
"""SOXX reversal research, v2. Pure stdlib; no trading or credential operations.

Research-only: the RTH diagnostic is NOT a 24h backtest. Historical selection is
retrospective because the evaluation year was inspected in an earlier run.
True 24h inputs must pass a separate source/coverage gate. Missing night candles
are never manufactured. Public hourly candles cannot be split into finer bars.
"""
from __future__ import annotations
import argparse, bisect, collections, csv, datetime as dt, hashlib, json, math
import random, statistics
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
UTC = dt.timezone.utc
CAL_START = '2024-12-16'
YEAR_START = '2025-10-09'
YEAR_END = '2026-10-08'
STAGES = ['extreme_turn', 'price_dislocation', 'persistent_oversold',
          'momentum_fade', 'price_reclaim', 'trend_aligned',
          'multi_timeframe', 'divergence', 'full_stack']
MACDS = [(5,13,4),(8,21,5),(12,26,9),(16,34,9)]
STOCHS = [7,14,21]

def prior_rms(values: list[float], window: int) -> list[float | None]:
    if window < 1: raise ValueError('window must be positive')
    out = [None] * len(values)
    total = 0.0
    for i, x in enumerate(values):
        if i >= window:
            out[i] = math.sqrt(max(total / window, 0.0))
            total -= values[i-window] ** 2
        total += x*x
    return out

def ema(values, period):
    out=[]; value=None; a=2/(period+1)
    for x in values:
        value=x if value is None else a*x+(1-a)*value
        out.append(value)
    return out

def wilder(values, period):
    out=[None]*len(values)
    if len(values)<period: return out
    v=sum(values[:period])/period
    for i in range(period-1,len(values)):
        if i>=period: v=(v*(period-1)+values[i])/period
        out[i]=v
    return out

def sma_missing(values, period):
    out=[None]*len(values)
    for i in range(period-1,len(values)):
        xs=values[i-period+1:i+1]
        if all(x is not None for x in xs): out[i]=sum(xs)/period
    return out

def stoch_rsi(close, period):
    changes=[close[i]-close[i-1] for i in range(1,len(close))]
    gains=wilder([max(x,0) for x in changes],period)
    losses=wilder([max(-x,0) for x in changes],period)
    rsi=[None]
    for g,l in zip(gains,losses):
        rsi.append(None if g is None else 50.0 if g==0 and l==0 else
                   100.0 if l==0 else 100-100/(1+g/l))
    raw=[None]*len(close)
    for i in range(period-1,len(close)):
        xs=rsi[i-period+1:i+1]
        if any(x is None for x in xs): continue
        lo,hi=min(xs),max(xs)
        # A flat RSI range is undefined; never fabricate an oversold crossover.
        if hi>lo: raw[i]=100*(rsi[i]-lo)/(hi-lo)
    k=sma_missing(raw,3)
    return k,sma_missing(k,3)

def atr(bars, period=14):
    tr=[]
    for i,b in enumerate(bars):
        prev=bars[i-1]['close'] if i else b['close']
        tr.append(max(b['high']-b['low'],abs(b['high']-prev),abs(b['low']-prev)))
    return wilder(tr,period)

def structure_ok(bars, i, side):
    if i<2: return False
    a,b,c=bars[i-2:i+1]
    if side==1:
        return c['close']>max(a['high'],b['high']) and c['low']>b['low'] and c['close']>c['open']
    return c['close']<min(a['low'],b['low']) and c['high']<b['high'] and c['close']<c['open']

def purge_before(trades, cutoff):
    return [t for t in trades if t['exit_time']<cutoff]

def coverage_24h(rows):
    night=[r for r in rows if r.get('session')=='overnight']
    native=[r for r in night if r.get('feed') in ('boats','tiingo_boats','alpaca_boats','ibkr_overnight')]
    day=[r for r in rows if r.get('session') in ('rth','premarket','postmarket')]
    # A nonempty sample is still not full-period coverage or quote/execution proof.
    return {'admitted':False,'overnight_rows':len(night),'provenance_tagged_night_rows':len(native),
            'day_rows':len(day),'reason':'missing_overnight_venue_data' if not native else
            'requires_calendar_coverage_corporate_action_and_quote_validation'}

def fixed_24h_bars(bars,hours,anchor_epoch=0):
    """Fixed elapsed-time bins, rejecting straddling source candles.
    Production ET anchoring must supply actual session anchors/calendar separately.
    An incomplete bin remains incomplete; this helper does not forward-fill.
    """
    width=hours*3600; groups=collections.defaultdict(list)
    for b in bars:
        key=math.floor((b['start']-anchor_epoch)/width)
        edge=anchor_epoch+(key+1)*width
        if b['end']>edge: raise ValueError('source candle straddles target boundary; finer input required')
        groups[key].append(b)
    result=[]
    for key,xs in sorted(groups.items()):
        xs=sorted(xs,key=lambda x:x['start'])
        start=anchor_epoch+key*width; end=start+width
        complete=xs[0]['start']==start and xs[-1]['end']==end and all(a['end']==b['start'] for a,b in zip(xs,xs[1:]))
        result.append(dict(start=start,end=end,open=xs[0]['open'],high=max(x['high'] for x in xs),
                           low=min(x['low'] for x in xs),close=xs[-1]['close'],complete=complete))
    return result

def full_horizon_available(bars, entry, hold_seconds):
    return sum(b['end']-b['start'] for b in bars[entry:]) >= hold_seconds

def exit_path(bars,entry,side,stop,target,hold_seconds,fee_bps=5):
    """OHLC approximation: stop-first when order is unknown; no target gap windfall.
    No overnight path is implied for a RTH input. Stops can gap beyond their price.
    """
    if not (0<=entry<len(bars)): raise ValueError('entry out of range')
    px=bars[entry]['open']; elapsed=0
    reason=None; price=None; exit_idx=None
    for j in range(entry,len(bars)):
        b=bars[j]
        elapsed += b['end']-b['start']
        gap_stop=side*(b['open']-stop)<=0
        gap_target=side*(b['open']-target)>=0
        stop_touch=b['low']<=stop if side==1 else b['high']>=stop
        target_touch=b['high']>=target if side==1 else b['low']<=target
        if gap_stop: price,reason=b['open'],'stop_gap'
        elif gap_target: price,reason=target,'target_gap'
        elif stop_touch: price,reason=stop,'stop'
        elif target_touch: price,reason=target,'target'
        elif elapsed>=hold_seconds: price,reason=b['close'],'time'
        if reason is not None: exit_idx=j; break
    if exit_idx is None: return None
    gross=side*100*(price/px-1)
    fees=fee_bps/100*(1+price/px)
    return dict(entry_idx=entry,exit_idx=exit_idx,entry_price=px,exit_price=price,
                entry_time=bars[entry]['start'],exit_time=bars[exit_idx]['end'],
                gross_pct=gross,net_pct=gross-fees,reason=reason,
                hold_market_hours=elapsed/3600,fee_bps_per_side=fee_bps)

def _periods(x):
    if isinstance(x,dict):
        if 'start' in x and 'end' in x: yield x
        else:
            for v in x.values(): yield from _periods(v)
    elif isinstance(x,list):
        for v in x: yield from _periods(v)

def load_rth(path):
    data=json.loads(Path(path).read_text())['chart']['result'][0]
    q=data['indicators']['quote'][0]
    closes={}
    for p in _periods(data['meta'].get('tradingPeriods',[])):
        t=dt.datetime.fromtimestamp(p['start'],ET)
        if t.hour==9 and t.minute==30: closes[t.date().isoformat()]=p['end']
    out=[]; rejected=collections.Counter()
    for i,t in enumerate(data['timestamp']):
        d=dt.datetime.fromtimestamp(t,ET); day=d.date().isoformat()
        if day>YEAR_END or not (570<=d.hour*60+d.minute<960): continue
        values={k:q[k][i] for k in ('open','high','low','close','volume')}
        if any(x is None for x in values.values()): rejected['null']=rejected['null']+1;continue
        if values['volume']<=0: rejected['zero_volume']+=1;continue
        end=min(t+3600,closes.get(day,int(d.replace(hour=16,minute=0).timestamp())))
        if end<=t: rejected['nonpositive_duration']+=1;continue
        if not (0<values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high']):
            rejected['bad_ohlc']+=1;continue
        out.append(dict(idx=len(out),start=t,end=end,day=day,local=d.isoformat(),**values))
    if len({r['start'] for r in out})!=len(out): raise ValueError('duplicate RTH timestamps')
    return out,closes,dict(rejected)

def aggregate_rth(raw,hours,closes):
    groups=collections.defaultdict(list)
    for b in raw:
        d=dt.datetime.fromtimestamp(b['start'],ET)
        k=((d.hour*60+d.minute)-570)//(hours*60)
        groups[(b['day'],k)].append(b)
    out=[]
    for (day,k),xs in sorted(groups.items()):
        d=dt.datetime.fromtimestamp(xs[0]['start'],ET).replace(hour=9,minute=30)
        nominal=int(d.timestamp())+k*hours*3600
        end=min(nominal+hours*3600,closes.get(day,int(d.replace(hour=16,minute=0).timestamp())))
        covered=sum(b['end']-b['start'] for b in xs)
        complete=covered==end-nominal and xs[0]['start']==nominal and xs[-1]['end']==end
        out.append(dict(day=day,start=nominal,end=end,firstidx=xs[0]['idx'],lastidx=xs[-1]['idx'],
                        open=xs[0]['open'],high=max(b['high'] for b in xs),low=min(b['low'] for b in xs),
                        close=xs[-1]['close'],volume=sum(b['volume'] for b in xs),complete=complete,
                        duration_hours=(end-nominal)/3600))
    return out

def features(bars,m,p):
    c=[b['close'] for b in bars]
    fast,slow,sig=m
    a,b=ema(c,fast),ema(c,slow)
    line=[x-y for x,y in zip(a,b)]; signal=ema(line,sig)
    hist=[x-y for x,y in zip(line,signal)]
    rms=prior_rms(hist,80); at=atr(bars)
    k,d=stoch_rsi(c,p)
    return dict(line=line,hist=hist,z=[x/y if y and y>0 else None for x,y in zip(hist,rms)],
                atr=at,k=k,d=d,ema20=ema(c,20))

def daily_regimes(raw,daily_path):
    byday={}
    if daily_path and Path(daily_path).exists():
        x=json.loads(Path(daily_path).read_text())['chart']['result'][0]
        q=x['indicators']['quote'][0]
        for t,c in zip(x['timestamp'],q['close']):
            if c is not None: byday[dt.datetime.fromtimestamp(t,ET).date().isoformat()]=c
    else:
        for b in raw: byday[b['day']]=b['close']
    days=sorted(byday); c=[byday[d] for d in days]
    e50,e200=ema(c,50),ema(c,200)
    regimes={}
    for i,day in enumerate(days):
        if i<205: continue
        # Only the previous completed daily bar enters an intraday decision.
        j=i-1
        regimes[day]=dict(long=c[j]>e200[j] and e50[j]>e50[j-5],
                          short=c[j]<e200[j] and e50[j]<e50[j-5])
    return regimes

def divergence_known(bars,f,i,side):
    candidates=[]
    for j in range(max(2,i-40),i-3):
        neighbours=bars[j-2:j]+bars[j+1:j+3]
        pivot=(all(bars[j]['low']<b['low'] for b in neighbours) if side==1 else
               all(bars[j]['high']>b['high'] for b in neighbours))
        if pivot: candidates.append(j)
    if not candidates:return False
    j=candidates[-1]
    if side==1:return bars[i]['low']<bars[j]['low'] and f['hist'][i]>f['hist'][j]
    return bars[i]['high']>bars[j]['high'] and f['hist'][i]<f['hist'][j]

def setup_episodes(bars,f,side,level=2.0):
    """At most one first rare-extension setup per same-sign histogram lobe."""
    result=[]; armed=False; lobe=-1
    h,z,k=f['hist'],f['z'],f['k']; sign=-side
    for i in range(84,len(bars)):
        if sign*h[i]<=0: armed=False;continue
        if sign*h[i-1]<=0: lobe=i;armed=False
        if armed or z[i] is None or k[i] is None:continue
        if sign*z[i]<level:continue
        recent=[v for v in k[max(0,i-2):i+1] if v is not None]
        zone=min(recent)<=20 if side==1 else max(recent)>=80
        if not zone or not bars[i]['complete']:continue
        armed=True
        result.append(dict(arm=i,lobe=lobe,side=side,episode=f'{side}:{lobe}:{i}'))
    return result

def entry_candidate(ep,stage,bars,f,raw,regimes,peer):
    a=ep['arm']; side=ep['side']; sign=-side; h=f['hist']; k=f['k']; d=f['d']
    av=f['atr'][a]
    if av is None or av<=0:return None,'atr_unavailable'
    displacement=side*(f['ema20'][a]-bars[a]['close'])/av
    require_price=stage!='extreme_turn'
    if require_price and not (sign*f['line'][a]>0 and displacement>=1.0):return None,'no_price_dislocation'
    pastk=[x for x in k[a-2:a+1] if x is not None]
    need_persist=stage not in ('extreme_turn','price_dislocation')
    lowcount=sum(x<=20 if side==1 else x>=80 for x in pastk)
    if need_persist and lowcount<2:return None,'oversold_not_persistent'
    if stage=='divergence' and not divergence_known(bars,f,a,side):return None,'no_confirmed_divergence'
    require_fade=stage not in ('extreme_turn','price_dislocation','persistent_oversold')
    require_structure=stage in ('price_reclaim','trend_aligned','multi_timeframe','divergence','full_stack')
    peak=sign*h[a]
    for i in range(a,min(a+7,len(bars))):
        if sign*h[i]<=0:break
        if not bars[i]['complete']:continue
        peak=max(peak,sign*h[i])
        if None in (k[i],d[i],k[i-1]):continue
        turn=side*(k[i]-k[i-1])>0 and side*(k[i]-d[i])>0 and side*(h[i]-h[i-1])>0
        if not turn:continue
        if require_fade and not (side*(h[i-1]-h[i-2])>0 and (peak-sign*h[i])/peak>=.20):continue
        j0=bars[i]['lastidx']
        candidates=range(j0,min(j0+7,len(raw)-1)) if require_structure else [j0]
        for j in candidates:
            if require_structure and not structure_ok(raw,j,side):continue
            # Only completed peer bars whose last raw index <= j can confirm.
            if stage in ('multi_timeframe','full_stack'):
                pb,pf=peer; idx=bisect.bisect_right([b['lastidx'] for b in pb],j)-1
                if idx<2 or side*(pf['hist'][idx]-pf['hist'][idx-1])<=0:continue
            entry=j+1
            if entry>=len(raw):continue
            if raw[entry]['start']<raw[j]['end']:raise AssertionError('future leakage: entry before signal close')
            day=raw[entry]['day']
            if stage in ('trend_aligned','full_stack'):
                if not regimes.get(day,{}).get('long' if side==1 else 'short',False):continue
            anchor=min(x['low'] for x in raw[bars[a]['firstidx']:j+1]) if side==1 else max(x['high'] for x in raw[bars[a]['firstidx']:j+1])
            if stage=='full_stack' and side*(raw[entry]['open']-anchor)>av:continue
            return dict(episode=ep['episode'],arm=a,signal_agg=i,signal_idx=j,entry=entry,
                        signal_time=raw[j]['end'],anchor=anchor,displacement_at_arm=displacement,
                        hist_z_at_arm=f['z'][a],k_at_arm=k[a]),None
        # A failed break window cannot be repeatedly extended by later crossovers.
        if require_structure:return None,'price_regime_or_peer_confirmation_missing'
    return None,'no_confirmed_turn_within_six_bars'

def wilson(w,n):
    if not n:return [None,None]
    z=1.95996398454;p=w/n;den=1+z*z/n
    mid=(p+z*z/(2*n))/den;radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [round(100*(mid-radius),1),round(100*(mid+radius),1)]

def summarize(trades,raw=None,side=1):
    if not trades:return dict(n=0,win_pct=None,mean_pct=None,cum_pct=0.0)
    rets=[t['net_pct'] for t in trades]; win=sum(x>0 for x in rets)
    pos=sum(max(x,0) for x in rets); neg=-sum(min(x,0) for x in rets)
    eq=1.0;peak=1.0;draw=0.0
    for t in trades:
        before=eq
        if raw is not None:
            for j in range(t['entry_idx'],t['exit_idx']):
                marked=before*(1+side*(raw[j]['close']/t['entry_price']-1)-t['fee_bps_per_side']/10000)
                peak=max(peak,marked);draw=min(draw,marked/peak-1)
        eq=before*(1+t['net_pct']/100);peak=max(peak,eq);draw=min(draw,eq/peak-1)
    return dict(n=len(rets),wins=win,win_pct=round(100*win/len(rets),2),win_95=wilson(win,len(rets)),
                mean_pct=round(statistics.mean(rets),4),median_pct=round(statistics.median(rets),4),
                profit_factor=round(pos/neg,3) if neg>0 else None,cum_pct=round(100*(eq-1),3),
                hour_close_mdd_pct=round(100*draw,3),worst_trade_pct=round(min(rets),3),
                best_trade_pct=round(max(rets),3),without_best_mean_pct=round((sum(rets)-max(rets))/(len(rets)-1),4) if len(rets)>1 else None,
                stress_15bps_mean_pct=round(statistics.mean(t['gross_pct']-.15*(1+t['exit_price']/t['entry_price']) for t in trades),4),
                avg_hold_market_hours=round(statistics.mean(t['hold_market_hours'] for t in trades),2),
                gap_stops=sum(t['reason']=='stop_gap' for t in trades))

def quarter(day):
    d=dt.date.fromisoformat(day);return f'{d.year}Q{(d.month-1)//3+1}'

def month_bootstrap(trades,reps=1000):
    if not trades:return [None,None]
    blocks=collections.defaultdict(list)
    for t in trades:blocks[t['entry_day'][:7]].append(t['net_pct'])
    keys=[f'{y}-{m:02d}' for y in (2025,2026) for m in range(1,13) if '2025-10'<=f'{y}-{m:02d}'<='2026-10']
    rng=random.Random(20261009);means=[]
    for _ in range(reps):
        vals=[v for k in rng.choices(keys,k=len(keys)) for v in blocks[k]]
        if vals:means.append(statistics.mean(vals))
    means.sort()
    return [round(means[int(.025*(len(means)-1))],4),round(means[int(.975*(len(means)-1))],4)]

def audit_public_extended(path):
    x=json.loads(Path(path).read_text())['chart']['result'][0];q=x['indicators']['quote'][0]
    counts=collections.defaultdict(lambda:collections.Counter()); observed=[];byday=collections.defaultdict(list)
    for i,t in enumerate(x['timestamp']):
        d=dt.datetime.fromtimestamp(t,ET);day=d.date().isoformat()
        if not YEAR_START<=day<=YEAR_END:continue
        hm=d.hour*60+d.minute
        s='overnight' if hm>=1200 or hm<240 else 'premarket' if hm<570 else 'rth' if hm<960 else 'postmarket'
        counts[s]['rows']+=1
        if q['close'][i] is None:counts[s]['null']+=1;continue
        counts[s]['priced_rows']+=1
        if not q['volume'][i]:counts[s]['zero_or_missing_volume']+=1
        observed.append({'session':s,'feed':'yahoo'})
        vals={k:q[k][i] for k in ('open','high','low','close')}
        if all(v is not None and v>0 for v in vals.values()):byday[day].append(dict(ts=t,session=s,**vals))
    return {'requested_window':[YEAR_START,YEAR_END],'sessions':{k:dict(v) for k,v in counts.items()},
            'gate':coverage_24h(observed),'qualification':'Public extended-hours audit only; no true overnight execution data.'}

def gap_diagnostic(raw):
    days=collections.defaultdict(list)
    for b in raw:days[b['day']].append(b)
    keys=sorted(days);gaps=[];intraday=[];first=None;last=None
    for i,day in enumerate(keys):
        if not YEAR_START<=day<=YEAR_END:continue
        xs=days[day]
        if i==0:continue
        prev=days[keys[i-1]][-1]['close']
        gaps.append(math.log(xs[0]['open']/prev));intraday.append(math.log(xs[-1]['close']/xs[0]['open']))
        if first is None:first=prev
        last=xs[-1]['close']
    return dict(sessions=len(gaps),close_to_open_compounded_pct=round(100*math.expm1(sum(gaps)),3),
                open_to_close_compounded_pct=round(100*math.expm1(sum(intraday)),3),
                combined_pct=round(100*(last/first-1),3) if first else None,
                mean_absolute_close_to_open_pct=round(statistics.mean(abs(math.expm1(x))*100 for x in gaps),3),
                interpretation='Endpoint decomposition. Close-to-open includes postmarket, overnight and premarket; it does not recover their paths.')

def run(root):
    root=Path(root);raw,closes,rejected=load_rth(root/'rth_original.json')
    daily=root/'daily_warmup.json';regimes=daily_regimes(raw,daily)
    bars={h:aggregate_rth(raw,h,closes) for h in (2,3,4)}
    feats={(h,m,p):features(bars[h],m,p) for h in bars for m in MACDS for p in STOCHS}
    rawatr=atr(raw)
    train_cut=int(dt.datetime(2025,10,9,9,30,tzinfo=ET).timestamp())
    end_cut=int(dt.datetime(2026,10,8,16,tzinfo=ET).timestamp())
    # Freeze planned families BEFORE calculating any result or ranking.
    manifest=dict(version='2.0',protected_sha='7d82b9adb839d54e4ab25378ca333e498dd83fcc',
        evaluation='RETROSPECTIVE, NOT PRISTINE OOS',stages=STAGES,macd=MACDS,stoch=STOCHS,
        extension_rms=2.0,stoch_zone=20,price_distance_atr=1.0,dwell='2 of last 3 bars',
        fade='2 contractions and >=20% off episode histogram peak',episode='one first setup per sign lobe',
        expiry_aggregate_bars=6,structure_wait_rth_hourly_bars=6,fee_bps_per_side=5,
        stress_fee_bps_per_side=15,fixed_stop_target_pct=[1.5,2.0],
        structural_stop='episode low/high plus 0.25 of 1h ATR; 0.3%-3.5% initial risk; target 2R',
        hold_rth_hours=19.5,min_admission_trades=25,min_active_quarters=3,
        true_24h_backtest_completed=False,source_sha256=hashlib.sha256((root/'rth_original.json').read_bytes()).hexdigest())
    (root/'design_manifest.json').write_text(json.dumps(manifest,indent=2))
    allrows=[];ledger=[];rejectrows=[];candidates_by_key={}
    for h in (2,3,4):
      for m in MACDS:
       for p in STOCHS:
        f=feats[h,m,p]
        peerh=4 if h in (2,3) else 2
        peer=(bars[peerh],feats[peerh,(12,26,9),14])
        for side in (1,-1):
         eps=[ep for ep in setup_episodes(bars[h],f,side) if CAL_START<=bars[h][ep['arm']]['day']<=YEAR_END]
         for stage in STAGES:
          candidates=[];reasons=collections.Counter()
          for ep in eps:
            c,reason=entry_candidate(ep,stage,bars[h],f,raw,regimes,peer)
            if c is None: reasons[reason]+=1;continue
            candidates.append(c)
          for risk in ('fixed','structural'):
            label=f'{h}h|{m[0]}/{m[1]}/{m[2]}|{p}|{side}|{stage}|{risk}'
            trades=[];last_exit=-1;rr=reasons.copy();last_phase='train'
            for c in sorted(candidates,key=lambda x:x['entry']):
                en=c['entry'];px=raw[en]['open']
                phase='test' if raw[en]['day']>=YEAR_START else 'train'
                if phase!=last_phase:last_exit=-1;last_phase=phase
                if not full_horizon_available(raw,en,19.5*3600):rr['right_censored']+=1;continue
                if en<=last_exit:rr['position_already_open']+=1;continue
                if risk=='fixed':stop=px*(1-side*.015);target=px*(1+side*.02)
                else:
                    at=rawatr[c['signal_idx']]
                    if not at:rr['no_entry_atr']+=1;continue
                    stop=c['anchor']-side*.25*at;riskfrac=side*(px-stop)/px
                    if not .003<=riskfrac<=.035:rr['structural_risk_out_of_bounds']+=1;continue
                    target=px+side*2*abs(px-stop)
                t=exit_path(raw,en,side,stop,target,19.5*3600,5)
                if t is None or t['exit_time']>end_cut:rr['right_censored']+=1;continue
                t.update(strategy=label,tf=h,macd='/'.join(map(str,m)),stoch=p,side=side,stage=stage,risk_model=risk,
                         entry_day=raw[en]['day'],entry_ET=raw[en]['local'],signal_time=c['signal_time'],
                         arm_day=bars[h][c['arm']]['day'],stop=stop,target=target,
                         hist_z_at_arm=c['hist_z_at_arm'],k_at_arm=c['k_at_arm'],
                         displacement_at_arm=c['displacement_at_arm'],episode=c['episode'])
                trades.append(t);last_exit=t['exit_idx']
            train=purge_before([t for t in trades if CAL_START<=t['entry_day']<YEAR_START],train_cut)
            test=[t for t in trades if YEAR_START<=t['entry_day']<=YEAR_END]
            st,so=summarize(train,raw,side),summarize(test,raw,side)
            quarters={q:summarize([t for t in test if quarter(t['entry_day'])==q]) for q in sorted({quarter(t['entry_day']) for t in test})}
            ci=month_bootstrap(test,400)
            active=len(quarters)
            admitted=(so['n']>=25 and active>=3 and (so.get('profit_factor') or 0)>=1.3 and
                      ci[0] is not None and ci[0]>0 and so.get('stress_15bps_mean_pct',-1)>0 and
                      so.get('without_best_mean_pct',-1)>0 and all(v['mean_pct']>0 for v in quarters.values()))
            row=dict(strategy=label,tf=h,macd='/'.join(map(str,m)),stoch=p,side=side,stage=stage,risk_model=risk,
                     train_n=st['n'],train_mean=st.get('mean_pct'),test_n=so['n'],test_win=so.get('win_pct'),
                     test_mean=so.get('mean_pct'),test_pf=so.get('profit_factor'),test_cum=so['cum_pct'],
                     test_mdd=so.get('hour_close_mdd_pct'),stress_mean=so.get('stress_15bps_mean_pct'),
                     without_best_mean=so.get('without_best_mean_pct'),active_quarters=active,
                     positive_quarters=sum(v['mean_pct']>0 for v in quarters.values()),
                     month_boot_low=ci[0],month_boot_high=ci[1],diagnostic_gate_passed=admitted,
                     calendar_quarters=quarters,test_win_interval=so.get('win_95'))
            allrows.append(row);ledger.extend(trades)
            rejectrows.append(dict(strategy=label,setups=len(eps),candidate_entries=len(candidates),**dict(rr)))
            candidates_by_key[label]=dict(row=row,train=st,test=so)
    # Dataset contamination is a hard gate regardless of descriptive numerical checks.
    for row in allrows:row['production_admitted']=False
    flat=[{k:(json.dumps(v) if isinstance(v,(dict,list)) else v) for k,v in x.items()} for x in allrows]
    with (root/'strategy_ablation.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    with (root/'trade_ledger.csv').open('w',newline='') as f:
        if ledger:w=csv.DictWriter(f,fieldnames=list(ledger[0]));w.writeheader();w.writerows(ledger)
    (root/'rejection_reasons.json').write_text(json.dumps(rejectrows,indent=2))
    refs={2:((12,26,9),14),3:((8,21,5),14),4:((5,13,4),14)}
    reference=[r for r in allrows if (tuple(map(int,r['macd'].split('/'))),r['stoch'])==refs[r['tf']] and r['side']==1]
    selections=[]
    for h in (2,3,4):
      for risk in ('fixed','structural'):
       eligible=[r for r in allrows if r['tf']==h and r['risk_model']==risk and r['side']==1 and r['train_n']>=8 and r['stage']!='extreme_turn']
       if eligible:
        pick=max(eligible,key=lambda r:r['train_mean']*r['train_n']/(r['train_n']+10))
        selections.append(pick)
    public=audit_public_extended(root/'extended_public.json')
    summary=dict(manifest=manifest,raw_rows=len(raw),rejected_rth=rejected,
                 bar_counts={str(h):{'total':len(bs),'incomplete':sum(not b['complete'] for b in bs),
                                   'shortened':sum(b['duration_hours']<h for b in bs)} for h,bs in bars.items()},
                 public_extended_audit=public,gap_diagnostic=gap_diagnostic(raw),
                 models_evaluated=len(allrows),trade_rows=len(ledger),
                 numerical_gate_passes=sum(r['diagnostic_gate_passed'] for r in allrows),
                 production_admitted_models=0,reference_ablation=reference,train_only_selections=selections,
                 model_counts_by_stage={stage:{'models':sum(r['stage']==stage for r in allrows),
                   'median_test_trades':statistics.median(r['test_n'] for r in allrows if r['stage']==stage),
                   'max_test_trades':max(r['test_n'] for r in allrows if r['stage']==stage)} for stage in STAGES})
    (root/'summary_v2.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:summary[k] for k in ('raw_rows','rejected_rth','bar_counts','models_evaluated','trade_rows','numerical_gate_passes','production_admitted_models','public_extended_audit','gap_diagnostic','model_counts_by_stage')},indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);args=ap.parse_args();run(args.root)