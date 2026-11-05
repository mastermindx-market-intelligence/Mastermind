"""Frozen SOXX exit falsification: coverage, delay and chart-anchor checks.
Research only. No network, credentials, production writes or broker operations.
"""
import bisect, collections, copy, datetime as dt, hashlib, json, statistics, sys
from pathlib import Path
import nested_pivots as n
import study_v7 as v7
from engine_v6 import simulate
from policies_v6 import Policy, make_panels
from lifecycle_v6 import WindowPolicy
from time_nextopen import TimedDecision

def session_gaps(raw, closes):
    days=collections.defaultdict(list)
    for r in raw:days[r['day']].append(r)
    gaps=[]
    for day, close in sorted(closes.items()):
        opening=int(dt.datetime.fromisoformat(day).replace(hour=9,minute=30,tzinfo=n.b.ET).timestamp())
        cursor=opening;rows=sorted(days[day],key=lambda r:r['start'])
        for r in rows:
            lo=max(opening,r['start']);hi=min(close,r['end'])
            if hi<=opening or lo>=close:continue
            if lo>cursor:gaps.append(dict(day=day,start=cursor,end=lo,seconds=lo-cursor,kind='session_head' if cursor==opening else 'intraday'))
            cursor=max(cursor,hi)
        if cursor<close:gaps.append(dict(day=day,start=cursor,end=close,seconds=close-cursor,kind='session_tail' if rows else 'whole_session'))
    return gaps

def intersecting_gaps(gaps, start, end):
    return [g for g in gaps if g['start']<end and g['end']>start]

def delayed_candidate(raw,c,delay,risk):
    if not isinstance(delay,int) or delay<0 or not 0<risk<100:raise ValueError('invalid delay/risk')
    entry=c['entry']+delay
    if entry>=len(raw):return None
    if raw[entry]['start']<c['signal_time']:raise ValueError('entry before signal availability')
    return dict(c,entry=entry,stop=raw[entry]['open']*(1-risk/100),entry_ET=raw[entry]['local'],
                origin_entry_ET=raw[c['entry']]['local'],origin_entry=c['entry'],
                phase='year' if raw[entry]['day']>=n.b.YEAR_START else 'prior')

def shifted_bars(raw,minutes,closes,offset):
    if minutes<=0 or offset<0 or offset>=minutes:raise ValueError('invalid anchor')
    groups=collections.defaultdict(list)
    for r in raw:
        day=dt.datetime.fromtimestamp(r['start'],n.b.ET)
        op=int(day.replace(hour=9,minute=30,second=0).timestamp());cl=closes[r['day']]
        anchor=op+offset*60;slot=(r['start']-anchor)//(minutes*60)
        lo=max(op,anchor+slot*minutes*60);hi=min(cl,anchor+(slot+1)*minutes*60)
        if r['start']<lo or r['end']>hi:raise ValueError('cannot split source bar')
        groups[lo,hi].append(r)
    out=[]
    for (lo,hi),rs in sorted(groups.items()):
        complete=rs[0]['start']==lo and rs[-1]['end']==hi and all(a['end']==b['start'] for a,b in zip(rs,rs[1:]))
        out.append(dict(idx=len(out),start=lo,end=hi,day=rs[0]['day'],firstidx=rs[0]['idx'],lastidx=rs[-1]['idx'],
          open=rs[0]['open'],high=max(r['high'] for r in rs),low=min(r['low'] for r in rs),close=rs[-1]['close'],
          volume=sum(r['volume'] for r in rs),complete=complete,duration_hours=(hi-lo)/3600))
    return out

def context_from_source(path):
    raw,closes,rejected=n.b.load_rth(path)
    high={m:n.aggregate_minutes(raw,m,closes) for m in [120,180,240]}
    low={60:n.aggregate_minutes(raw,60,closes)}
    return dict(raw=raw,closes=closes,rejected=rejected,high=high,
        hf={name:n.enrich(high[tf],mac,p) for name,(tf,mac,p) in n.PROFILES.items()},
        lower=low,lf={(60,name):n.enrich(low[60],mac,p) for name,(mac,p) in n.LOWERS.items()},
        clock=n.market_clock(raw),rawends=[r['end'] for r in raw],rawstarts=[r['start'] for r in raw],recent=False,first=n.b.CAL_START)

PLANS=['fixed2','slow_p0.25','guard_p0.25','guard_p0.5','guard_timer52','plain_timer52']

def policy_for(plan,raw,panels,en):
    fraction=.5 if plan=='guard_p0.5' else .25
    if plan.startswith('guard'):
        pol=WindowPolicy(dict(grace=3,expiry=6.5,retain=.5),raw,panels,en)
    else:pol=Policy(dict(kind='legacy_joint' if plan.startswith('slow') else 'time',tf=180),raw,panels,en)
    horizon=65
    if plan.endswith('timer52'):
        if plan.startswith('guard'):pol.base=Policy(dict(kind='time',tf=180),raw,panels,en)
        pol=TimedDecision(pol,52);horizon=100000
    parts=[] if plan=='fixed2' else [(2,fraction)]
    return pol,horizon,parts

def evaluate(ctx,cs,plan,gaps,*,delay=0,risk=1.5,fee=5):
    raw=ctx['raw'];panels=ctx['_panels'];rows=[];last=-1;phase=None
    for original in cs:
        c=delayed_candidate(raw,original,delay,risk)
        if c is None:continue
        if c['phase']!=phase:phase=c['phase'];last=-1
        en=c['entry']
        if en<=last:continue
        pol,hz,parts=policy_for(plan,raw,panels,en)
        t=simulate(raw,en,c['stop'],horizon=hz,target=2 if plan=='fixed2' else 0,partials=parts,decision=pol,cost_bps=fee)
        if t is None:
            row=dict(status='right_censored',entry_idx=en,phase=phase,entry_ET=c['entry_ET']);last=len(raw)-1
        else:
            last=t['exit_idx'];missing=intersecting_gaps(gaps,raw[en]['start'],t['exit_time'])
            status='unobserved_session_path' if missing else 'resolved'
            if phase=='prior' and raw[last]['day']>=n.b.YEAR_START:status='period_boundary'
            row=dict(t,status=status,phase=phase,entry_ET=c['entry_ET'],origin_entry_ET=c['origin_entry_ET'],
                     episode=c['episode'],missing=missing,exit_ET=dt.datetime.fromtimestamp(t['exit_time'],n.b.ET).isoformat())
        rows.append(row)
    return rows

def source_audit(ctx):
    raw=ctx['raw'];closes={d:t for d,t in ctx['closes'].items() if raw[0]['day']<=d<=n.b.YEAR_END}
    gaps=session_gaps(raw,closes)
    return dict(rows=len(raw),sessions_observed=len(set(r['day'] for r in raw)),scheduled_sessions=len(closes),
                missing_intervals=len(gaps),missing_hours=sum(g['seconds'] for g in gaps)/3600,
                gaps_by_kind=dict(collections.Counter(g['kind'] for g in gaps)),gaps=gaps)

def run(source,out,symbol='SOXX'):
    out=Path(out);out.mkdir(exist_ok=False)
    ctx=context_from_source(source);ctx['_panels']=make_panels(ctx);raw=ctx['raw'];audit=source_audit(ctx)
    cs,_=v7.prepared(ctx,'3H_1H_pivot');rows=[];trades=[]
    # Diagnostics predeclared before outcomes; not an optimized Cartesian grid.
    variants=[('frozen',0,1.5,0),('delay_1bar',1,1.5,0),('delay_2bars',2,1.5,0),
              ('stop_1.25',0,1.25,0),('stop_1.75',0,1.75,0),('entry_anchor_plus60',0,1.5,60),('entry_anchor_plus120',0,1.5,120)] if symbol=='SOXX' else [('frozen',0,1.5,0)]
    for variant,delay,risk,offset in variants:
        selected=cs
        if offset:
            alt=dict(ctx);alt['high']=dict(ctx['high']);alt['hf']=dict(ctx['hf'])
            alt['high'][180]=shifted_bars(raw,180,ctx['closes'],offset)
            alt['hf']['3h_medium']=n.enrich(alt['high'][180],(8,21,5),14)
            selected,_=v7.prepared(alt,'3H_1H_pivot')
        for plan in PLANS:
            rs=evaluate(ctx,selected,plan,audit['gaps'],delay=delay,risk=risk)
            for phase in ['prior','year']:
                subset=[r for r in rs if r['phase']==phase]
                sm=v7.summarize(subset)
                rows.append(dict(symbol=symbol,variant=variant,plan=plan,phase=phase,**sm))
            for r in rs:
                trades.append(dict(symbol=symbol,variant=variant,plan=plan,**{k:v for k,v in r.items() if k not in ['marks','fills','actions']}))
    # Raw gap audit is independent of whether a candidate stops early.
    n.write_csv(out/'summary.csv',rows)
    v7.old.write_csv(out/'trades.csv',trades)
    (out/'audit.json').write_text(json.dumps(audit,indent=2))
    (out/'results.json').write_text(json.dumps(dict(symbol=symbol,source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),audit=audit,summary=rows,trades=trades)))
    print('COMPLETE',symbol,'configs',len(rows)//2,'candidates',len(cs),'audit', {k:v for k,v in audit.items() if k!='gaps'})
    for r in rows:
        if r['phase']=='year' and r['plan'] in ['fixed2','guard_p0.25','guard_p0.5','guard_timer52']:
            print('RESULT',json.dumps({k:r.get(k) for k in ['variant','plan','candidates','resolved','mean','win','cum','mdd','status_counts']}))
    print('DIGEST',hashlib.sha256((out/'results.json').read_bytes()).hexdigest())
if __name__=='__main__':run(*sys.argv[1:])