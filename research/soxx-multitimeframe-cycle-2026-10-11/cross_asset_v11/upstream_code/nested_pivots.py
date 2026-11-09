#!/usr/bin/env python3
"""Nested pivot research: completed bars only; one attempted entry per extreme."""
from __future__ import annotations
import bisect,collections,csv,datetime as dt,hashlib,json,math,statistics,sys
from pathlib import Path
import research_v2 as b
PROFILES={'2h_classic':(120,(12,26,9),14),'3h_medium':(180,(8,21,5),14),'4h_fast':(240,(5,13,4),14)}
LOWERS={'fast':((5,13,4),7),'balanced':((8,21,5),14)}
TRIGGERS=['stoch20','stoch30','rsi40','pivot_turn','pivot_break','macd_cross']
STATES=['armed','turn','recovered']
RISKS=['tight','wide','micro','atr']
COMMON_START='2026-08-17'
EXPIRY_SECONDS=26*3600
HOLD_SECONDS=19.5*3600

def asof(ends,now):return bisect.bisect_right(ends,now)-1

def market_clock(raw):
    out=[0]
    for r in raw:out.append(out[-1]+r['end']-r['start'])
    return out

def raw_rsi(close,p=14):
    delta=[c-a for a,c in zip(close,close[1:])]
    g=b.wilder([max(x,0) for x in delta],p);l=b.wilder([max(-x,0) for x in delta],p)
    return [None]+[None if x is None else 50. if x==0 and y==0 else 100. if y==0 else 100-100/(1+x/y) for x,y in zip(g,l)]

def confirmed_pivots(bars,side,left=2,right=1):
    result=[];last=None
    for i in range(len(bars)):
        j=i-right
        if j>=left:
            xs=bars[j-left:i+1]
            if all(x.get('complete',True) for x in xs):
                key='low' if side==1 else 'high';v=bars[j][key]
                if side==1:ok=all(v<x[key] for x in bars[j-left:j]) and all(v<=x[key] for x in bars[j+1:i+1])
                else:ok=all(v>x[key] for x in bars[j-left:j]) and all(v>=x[key] for x in bars[j+1:i+1])
                if ok:last=j
        result.append(last)
    return result

def risk_levels(px,side,model,anchor,av,cap=.03):
    if model not in RISKS+['structure8']:raise ValueError('unknown risk model')
    if not av or px<=0 or av<=0:return None
    if model=='tight':return px*(1-side*.015),px*(1+side*.02)
    if model=='wide':return px*(1-side*.03),px*(1+side*.04)
    risk=1.5*av if model=='atr' else side*(px-anchor)+.25*av
    limit=.08 if model=='structure8' else cap
    if not .003<=risk/px<=limit:return None
    return px-side*risk,px+side*2*risk

def load_minutes(path,minutes,end_day=b.YEAR_END):
    d=json.loads(Path(path).read_text())['chart']['result'][0];q=d['indicators']['quote'][0]
    closes={};rows=[];reject=collections.Counter()
    for p in b._periods(d['meta'].get('tradingPeriods',[])):
        t=dt.datetime.fromtimestamp(p['start'],b.ET)
        if (t.hour,t.minute)==(9,30):closes[t.date().isoformat()]=p['end']
    for i,t in enumerate(d['timestamp']):
        z=dt.datetime.fromtimestamp(t,b.ET);day=z.date().isoformat()
        if day>end_day or not 570<=z.hour*60+z.minute<960:continue
        vals={k:q[k][i] for k in ['open','high','low','close','volume']}
        if any(v is None for v in vals.values()):reject['null']+=1;continue
        if vals['volume']<=0:reject['zero_volume']+=1;continue
        if not (0<vals['low']<=min(vals['open'],vals['close'])<=max(vals['open'],vals['close'])<=vals['high']):
            reject['bad_ohlc']+=1;continue
        end=min(t+minutes*60,closes.get(day,int(z.replace(hour=16,minute=0).timestamp())))
        if end<=t:reject['invalid_duration']+=1;continue
        rows.append(dict(idx=len(rows),start=t,end=end,local=z.isoformat(),day=day,complete=True,**vals))
    if len({r['start'] for r in rows})!=len(rows):raise ValueError('duplicate timestamp')
    return rows,closes,dict(reject)

def aggregate_minutes(raw,minutes,closes):
    groups=collections.defaultdict(list)
    for r in raw:
        z=dt.datetime.fromtimestamp(r['start'],b.ET);slot=(z.hour*60+z.minute-570)//minutes
        origin=int(z.replace(hour=9,minute=30,second=0).timestamp())+slot*minutes*60
        end=min(origin+minutes*60,closes.get(r['day'],int(z.replace(hour=16,minute=0,second=0).timestamp())))
        if r['start']<origin or r['end']>end:raise ValueError('cannot split a source candle across a target boundary')
        groups[(origin,end)].append(r)
    out=[]
    for (start,end),xs in sorted(groups.items()):
        complete=xs[0]['start']==start and xs[-1]['end']==end and all(x['end']==y['start'] for x,y in zip(xs,xs[1:]))
        out.append(dict(idx=len(out),start=start,end=end,day=xs[0]['day'],firstidx=xs[0]['idx'],lastidx=xs[-1]['idx'],
                        open=xs[0]['open'],high=max(x['high'] for x in xs),low=min(x['low'] for x in xs),close=xs[-1]['close'],
                        volume=sum(x['volume'] for x in xs),complete=complete,duration_hours=(end-start)/3600))
    return out

def enrich(bars,m,p):
    f=b.features(bars,m,p);f['rsi']=raw_rsi([x['close'] for x in bars],14)
    for side in [1,-1]:f['piv'+str(side)]=confirmed_pivots(bars,side)
    return f

def lower_trigger(bars,f,i,side,method):
    if i<3 or not bars[i]['complete']:return False
    k,d,h,r=f['k'],f['d'],f['hist'],f['rsi']
    if None in [k[i],d[i],k[i-1],d[i-1],r[i],r[i-1]]:return False
    slope=side*(h[i]-h[i-1])>0
    aligned=side*(k[i]-d[i])>=0
    if method in ['stoch20','stoch30']:
        z=int(method[5:]);v=[x for x in k[i-2:i+1] if x is not None]
        zone=min(v)<=z if side==1 else max(v)>=100-z
        return zone and slope and side*(k[i]-d[i])>0 and side*(k[i-1]-d[i-1])<=0
    if method=='rsi40':
        threshold=40 if side==1 else 60
        return side*(r[i]-threshold)>0 and side*(r[i-1]-threshold)<=0 and slope and aligned
    if method=='macd_cross':
        return side*h[i]>0 and side*h[i-1]<=0 and aligned and (k[i]>=20 if side==1 else k[i]<=80)
    pivot=f['piv'+str(side)][i]
    if pivot is None or not 1<=i-pivot<=6:return False
    if method=='pivot_turn':
        recent=[x for x in r[max(0,pivot-2):pivot+1] if x is not None]
        oversold=recent and (min(recent)<=45 if side==1 else max(recent)>=55)
        return i==pivot+1 and bool(oversold) and slope and aligned and side*(r[i]-r[i-1])>0
    if method=='pivot_break':return slope and aligned and b.structure_ok(bars,i,side)
    raise ValueError('unknown lower trigger')

def higher_state(f,i,side,state):
    if state=='armed':return True
    h,k,d=f['hist'],f['k'],f['d']
    if i<1 or None in [k[i],d[i],k[i-1]]:return False
    if state=='turn':return side*h[i]<0 and side*(h[i]-h[i-1])>0 and side*(k[i]-k[i-1])>0 and side*(k[i]-d[i])>=0
    if state=='recovered':return side*h[i]>0 and side*(k[i]-d[i])>=0 and (k[i]>=20 if side==1 else k[i]<=80)
    raise ValueError('unknown higher state')

def build_context(root,recent=False,rebuild_high=False):
    old,oldclose,oldrej=b.load_rth(Path(root)/'rth_original.json')
    raw,closes,rej=load_minutes(Path(root)/'15m_60d.json',15) if recent else (old,oldclose,oldrej)
    highraw=old
    if recent and rebuild_high:
        first=raw[0]['day'];highraw=[r.copy() for r in old if r['day']<first]+[r.copy() for r in raw]
        for j,r in enumerate(highraw):r['idx']=j
    hb={h:aggregate_minutes(highraw,h,{**oldclose,**closes}) for h in [120,180,240]}
    hf={name:enrich(hb[h],m,p) for name,(h,m,p) in PROFILES.items()}
    lower_minutes=[15,30,45,60] if recent else [60]
    lb={m:aggregate_minutes(raw,m,closes) for m in lower_minutes}
    lf={(m,name):enrich(lb[m],mac,p) for m in lower_minutes for name,(mac,p) in LOWERS.items()}
    return dict(raw=raw,closes=closes,rejected=rej,high=hb,hf=hf,lower=lb,lf=lf,
                clock=market_clock(raw),rawends=[x['end'] for x in raw],rawstarts=[x['start'] for x in raw],
                recent=recent,first=COMMON_START if recent else b.CAL_START)

def candidates(ctx,profile,lm,lp,state,method,side,expiry=EXPIRY_SECONDS,level=2):
    raw,clock=ctx['raw'],ctx['clock'];h=PROFILES[profile][0];hb=ctx['high'][h];hf=ctx['hf'][profile]
    lb=ctx['lower'][lm];lf=ctx['lf'][lm,lp];lends=[r['end'] for r in lb];hends=[r['end'] for r in hb]
    out=[];warm=5*LOWERS[lp][0][1]
    for ep in b.setup_episodes(hb,hf,side,level):
        arm=ep['arm'];at=hb[arm]['end']
        if hb[arm]['day']>b.YEAR_END or at<raw[0]['start']:continue
        ai=bisect.bisect_left(ctx['rawends'],at)
        if ai>=len(raw):continue
        armclock=clock[ai+1] if raw[ai]['end']==at else clock[ai]
        for i in range(max(warm,bisect.bisect_left(lends,at)),len(lb)):
            q=lb[i];si=asof(ctx['rawends'],q['end']);elapsed=clock[si+1]-armclock
            if elapsed>expiry:break
            if q['day']<ctx['first'] or not q['complete']:continue
            hi=asof(hends,q['end'])
            if hi<arm or not hb[hi]['complete']:continue
            if method=='higher_only':
                ok=hi>=1 and hf['hist'][hi]*side>0 and hf['hist'][hi-1]*side<=0 and higher_state(hf,hi,side,'recovered')
                ok=ok and q['end']==hb[hi]['end']
            else:ok=higher_state(hf,hi,side,state) and lower_trigger(lb,lf,i,side,method)
            if not ok:continue
            en=bisect.bisect_left(ctx['rawstarts'],q['end'])
            if en>=len(raw):continue
            if raw[en]['day']<ctx['first']:continue
            if raw[en]['start']<q['end'] or hb[hi]['end']>q['end']:raise AssertionError('future signal leakage')
            pv=lf['piv'+str(side)][i]
            if pv is not None and i-pv<=8:
                anchor=lb[pv]['low'] if side==1 else lb[pv]['high'];anchor_kind='confirmed_pivot'
            else:
                xs=lb[max(0,i-4):i+1];anchor=min(x['low'] for x in xs) if side==1 else max(x['high'] for x in xs);anchor_kind='five_bar_extreme'
            episode_xs=raw[max(0,ai):si+1]
            episode_anchor=(min(r['low'] for r in episode_xs) if side==1 else max(r['high'] for r in episode_xs)) if episode_xs else anchor
            out.append(dict(profile=profile,episode=f'{profile}:{ep["episode"]}',side=side,entry=en,signal_idx=si,
                signal_time=q['end'],higher_time=hb[hi]['end'],arm_time=at,arm_day=hb[arm]['day'],
                higher_index=hi,lower_index=i,lower_minutes=lm,lower_params=lp,state=state,trigger=method,
                anchor=anchor,anchor_kind=anchor_kind,episode_anchor=episode_anchor,atr=lf['atr'][i],
                lower_k=lf['k'][i],lower_rsi=lf['rsi'][i],high_z_at_arm=hf['z'][arm],
                arm_to_entry_rth_hours=(clock[en]-armclock)/3600,arm_shortened=hb[arm]['duration_hours']*60<h,
                lower_shortened=q['duration_hours']*60<lm,pivot_index=pv))
            break
    return out

def evaluate(ctx,cs,risk,side,cap=.03,hold=HOLD_SECONDS,cooldown=0):
    raw,clock=ctx['raw'],ctx['clock'];last=-1;phase=None;ts=[];reject=collections.Counter()
    for c in sorted(cs,key=lambda z:(z['entry'],z['profile'])):
        en=c['entry'];current='year' if raw[en]['day']>=b.YEAR_START else 'prior'
        if current!=phase:last=-1;phase=current
        if en<=last or (last>=0 and clock[en]-clock[last+1]<cooldown):reject['overlap_or_cooldown']+=1;continue
        if clock[-1]-clock[en]<hold:reject['right_censored']+=1;continue
        lev=risk_levels(raw[en]['open'],side,risk,c['episode_anchor'] if risk=='structure8' else c['anchor'],c['atr'],cap)
        if lev is None:reject['risk_bounds']+=1;continue
        t=b.exit_path(raw,en,side,*lev,hold)
        if t is None:reject['no_exit']+=1;continue
        if current=='prior' and raw[t['exit_idx']]['day']>=b.YEAR_START:reject['purged_boundary']+=1;continue
        path=raw[en:t['exit_idx']+1]
        if any(x['day']==y['day'] and x['end']!=y['start'] for x,y in zip(path,path[1:])):
            reject['missing_intraday_execution_path']+=1;continue
        t.update(c);t['initial_risk_pct']=100*side*(t['entry_price']-lev[0])/t['entry_price'];t['R']=t['net_pct']/t['initial_risk_pct']
        t.update(entry_day=raw[en]['day'],entry_ET=raw[en]['local'],exit_ET=dt.datetime.fromtimestamp(t['exit_time'],b.ET).isoformat(),risk_model=risk)
        for seconds,name in [(6.5*3600,'forward_1day'),(19.5*3600,'forward_3day')]:
            j=bisect.bisect_left(clock,clock[en]+seconds)-1
            t[name]=side*100*(raw[j]['close']/raw[en]['open']-1)-.1 if 0<=j<len(raw) else None
        ts.append(t);last=t['exit_idx']
    return ts,dict(reject)

def summary(ts,ctx,side):
    s=b.summarize(ts,ctx['raw'],side)
    if not ts:return s
    s.update(mean_risk_pct=round(statistics.mean(t['initial_risk_pct'] for t in ts),4),mean_R=round(statistics.mean(t['R'] for t in ts),4),
             mean_wait_hours=round(statistics.mean(t['arm_to_entry_rth_hours'] for t in ts),3),
             forward_1day=round(statistics.mean(t['forward_1day'] for t in ts),4),forward_3day=round(statistics.mean(t['forward_3day'] for t in ts),4))
    return s

def split_summary(ts,ctx,side):
    prior=[t for t in ts if t['entry_day']<b.YEAR_START]
    year=[t for t in ts if t['entry_day']>=b.YEAR_START]
    a,z=summary(prior,ctx,side),summary(year,ctx,side)
    result={'prior_n':a['n'],'prior_mean':a.get('mean_pct')}
    for k in ['n','win_pct','mean_pct','cum_pct','profit_factor','hour_close_mdd_pct','mean_risk_pct','mean_R','mean_wait_hours','stress_15bps_mean_pct','without_best_mean_pct','forward_1day','forward_3day']:
        result[k]=z.get(k)
    return result

def write_csv(path,rows):
    if not rows:return
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def run(root,out):
    root,out=Path(root),Path(out)
    if out.exists():raise ValueError('output already exists; inspect original before replay')
    out.mkdir()
    spec=dict(study='nested higher-timeframe extreme and lower-timeframe pivot',retrospective=True,no_live_trades=True,
              annual_window=[b.YEAR_START,b.YEAR_END],recent_window=[COMMON_START,b.YEAR_END],higher_profiles=PROFILES,
              lower_profiles=LOWERS,states=STATES,triggers=TRIGGERS,risk_models=RISKS,expiry_rth_hours=26,
              max_hold_rth_hours=19.5,fees_bps_per_side=5,stress_bps_per_side=15,
              pivot_left_right=[2,1],micro_stop_cap_pct=3,entry='next source-bar open; never on pivot low',
              lower_warmup='five slow-EMA periods',higher_data='frozen original 60m snapshot',
              source_shas={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['rth_original.json','15m_60d.json']},
              code_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),protected_sha='326c8469a21d7f50fc9ecb1848196bf1c6e66685',
              direct_reason='PRINCIPAL_JUDGMENT; bounded statistical research without live operational delegation')
    (out/'specification.json').write_text(json.dumps(spec,indent=2))
    records=[];trades=[];audit={};signal_ledger=[]
    for cohort,recent in [('year60',False),('recent15',True)]:
        ctx=build_context(root,recent)
        audit[cohort]=dict(rows=len(ctx['raw']),first=ctx['raw'][0]['local'],last=ctx['raw'][-1]['local'],rejected=ctx['rejected'],
            lower_counts={k:len(v) for k,v in ctx['lower'].items()},year_setup_counts={name:{str(side):sum(hb[ep['arm']]['day']>=ctx['first'] for ep in b.setup_episodes(hb,ctx['hf'][name],side)) for side in [1,-1]} for name,(h,m,p) in PROFILES.items() for hb in [ctx['high'][h]]})
        for lm in ctx['lower']:
          for lp in LOWERS:
           for side in [1,-1]:
            for state in STATES:
             for method in TRIGGERS:
                sets={name:candidates(ctx,name,lm,lp,state,method,side) for name in PROFILES}
                unique={}
                for name in PROFILES:
                    for c in sets[name]:unique.setdefault(c['entry'],c)
                sets['union']=list(unique.values())
                for name,cs in sets.items():
                  signal_ledger.extend([dict(cohort=cohort,selection=name,**c) for c in cs])
                  for risk in RISKS:
                    ts,rej=evaluate(ctx,cs,risk,side)
                    key=f'{cohort}|{name}|{lm}|{lp}|{side}|{state}|{method}|{risk}'
                    row=dict(strategy=key,cohort=cohort,profile=name,lower_minutes=lm,lower_params=lp,side=side,state=state,trigger=method,risk=risk,candidate_n=len(cs))
                    row.update(split_summary(ts,ctx,side));row['rejections']=json.dumps(rej,sort_keys=True);records.append(row)
                    for t in ts:trades.append(dict(strategy=key,cohort=cohort,**t))
        for side in [1,-1]:
            sets={name:candidates(ctx,name,60,'balanced','recovered','higher_only',side) for name in PROFILES}
            unique={}
            for name in PROFILES:
                for c in sets[name]:unique.setdefault(c['entry'],c)
            sets['union']=list(unique.values())
            for name,cs in sets.items():
              for risk in RISKS+['structure8']:
                ts,rej=evaluate(ctx,cs,risk,side)
                key=f'{cohort}|{name}|60|balanced|{side}|recovered|higher_only|{risk}'
                row=dict(strategy=key,cohort=cohort,profile=name,lower_minutes=60,lower_params='balanced',side=side,state='recovered',trigger='higher_only',risk=risk,candidate_n=len(cs))
                row.update(split_summary(ts,ctx,side));row['rejections']=json.dumps(rej,sort_keys=True);records.append(row)
                for t in ts:trades.append(dict(strategy=key,cohort=cohort,**t))
        print('COHORT_COMPLETED',cohort,len(records),len(trades),flush=True)
    write_csv(out/'grid.csv',records);write_csv(out/'trades.csv',trades);write_csv(out/'signals.csv',signal_ledger)
    (out/'grid.json').write_text(json.dumps(records));(out/'audit.json').write_text(json.dumps(audit,indent=2))
    print('COMPLETED',len(records),len(trades),hashlib.sha256((out/'grid.json').read_bytes()).hexdigest())

if __name__=='__main__':run(sys.argv[1],sys.argv[2])