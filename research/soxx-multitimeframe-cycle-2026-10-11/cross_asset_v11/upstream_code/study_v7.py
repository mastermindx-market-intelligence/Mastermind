"""SOXX frozen-exit audit and bounded re-entry study. Offline research only.
Native signals are not rejected because of future data quality; indeterminate
outcomes are retained as such. A common-65h sample separately reproduces v6.
"""
import bisect, collections, datetime as dt, hashlib, json, statistics, sys
from pathlib import Path
import nested_pivots as n
import momentum_study as m
import study_v6 as old
from policies_v6 import Policy, make_panels
from lifecycle_v6 import WindowPolicy
from engine_v6 import simulate
from reentry_core import quantities, path_known, recovers, combine

def spec_book():
    out=[dict(id='fixed2',type='fixed',partial=0),dict(id='time65',type='time',partial=0)]
    for p in [.25,.5]:
        out.extend([dict(id=f'slow_p{p}',type='slow',partial=p),dict(id=f'guard_p{p}',type='guard',partial=p)])
        for mode in ['reclaim','break2','two_closes']:
            for wait in [6.5,13]:out.append(dict(id=f'reentry_{mode}_w{wait}_p{p}',type='reentry',partial=p,mode=mode,wait=wait))
    return out

def prepared(ctx,label):
    source=m.get_entries(ctx,ctx['recent'])
    if label not in source:source.update(old.entry_sets(ctx))
    cs,risk=source[label];raw=ctx['raw'];out=[]
    for c in sorted(cs,key=lambda c:(c['entry'],c['profile'])):
        lev=n.risk_levels(raw[c['entry']]['open'],1,risk,c['anchor'],c['atr'])
        if lev is None:continue
        out.append(dict(c,stop=lev[0],entry_ET=raw[c['entry']]['local'],phase='year' if raw[c['entry']]['day']>=n.b.YEAR_START else 'prior'))
    return out,risk

def recovery(ctx,panels,c,first,plan,fee):
    raw,clock=ctx['raw'],ctx['clock'];en=c['entry'];x=first['exit_idx']
    remaining=65-(clock[x]-clock[en])/3600
    watch=min(plan['wait'],remaining)
    until=min(len(raw)-1,bisect.bisect_left(clock,clock[x]+watch*3600)-1)
    signal=[a['j'] for a in first['actions'] if a.get('reason')=='early_rebound_failure'][-1]
    threshold=max(raw[signal]['high'],raw[en]['open'])
    previous={f['i']:f for f in panels[60] if f}
    last_i=panels[60][x-1]['i'] if x and panels[60][x-1] else -1
    for j in range(x,min(until,len(raw)-2)+1):
        age=(clock[j+1]-clock[x])/3600
        if age>watch:break
        f=panels[60][j]
        if not f or f['i']==last_i:continue
        last_i=f['i'];p=previous.get(f['i']-1)
        if not recovers(plan['mode'],ctx['lower'][60],f['i'],f,p,threshold):continue
        buy=j+1
        if (clock[buy]-clock[x])/3600>watch:break
        if raw[buy]['start']<raw[j]['end']:raise AssertionError('reentry before signal known')
        fill=first['fills'][-1]
        q=quantities(fill['q'],fill['price'],raw[buy]['open'],first['net_pct'],first['entry_price'],first['initial_risk_pct'],fee)
        if q<1e-9:return None,until,'risk_budget'
        hours=65-(clock[buy]-clock[en])/3600
        if hours<=0:return None,until,'horizon'
        policy=Policy(dict(kind='legacy_joint',tf=180),raw,panels,buy)
        leg=simulate(raw,buy,raw[buy]['open']*.985,horizon=hours,decision=policy,cost_bps=fee)
        if leg is None:return None,until,'reentry_right_censored'
        result=combine(first,leg,q)
        result.update(exit_idx=leg['exit_idx'],exit_time=leg['exit_time'],reentry_idx=buy,reentry_signal=j,
            reentry_ET=raw[buy]['local'],reentry_return=leg['net_pct'],reentry_quantity=q,
            additional_gain=result['net_pct']-first['net_pct'],first_exit_idx=x,first_net=first['net_pct'],
            reason='reentry_'+leg['reason'],reentered=True,hold_hours=first['hold_hours']+leg['hold_hours'])
        assert q<=fill['q']+1e-10
        assert q*raw[buy]['open']*(1+fee/10000)<=fill['q']*fill['price']*(1-fee/10000)+1e-8
        return result,leg['exit_idx'],'ok'
    return first,until,'no_reentry'

def episode(ctx,panels,c,plan,fee=5):
    raw=ctx['raw'];kind=plan['type'];en=c['entry']
    if kind in ('guard','reentry'):
        policy=WindowPolicy(dict(grace=3,expiry=6.5,retain=.5),raw,panels,en)
    else:policy=Policy(dict(kind='legacy_joint' if kind=='slow' else 'time',tf=180),raw,panels,en)
    t=simulate(raw,en,c['stop'],horizon=65,target=2 if kind=='fixed' else 0,
        partials=[(2,plan['partial'])] if plan['partial'] else [],decision=policy,cost_bps=fee)
    if t is None:return dict(status='right_censored',entry_idx=en),len(raw)-1
    blocked=t['exit_idx'];t.update(reentered=False,additional_gain=0.,first_net=t['net_pct'])
    if not path_known(raw,en,t['exit_time']):return dict(t,status='unobserved_intraday_path'),blocked
    if kind=='reentry' and t['reason']=='early_rebound_failure':
        result,blocked,note=recovery(ctx,panels,c,t,plan,fee)
        if result is None:return dict(t,status=note),blocked
        t=result;t['reentry_note']=note
        if not path_known(raw,en,raw[min(blocked,len(raw)-1)]['end']):
            return dict(t,status='unobserved_reentry_path'),blocked
    status='resolved' if path_known(raw,en,t['exit_time']) else 'unobserved_intraday_path'
    if c['phase']=='prior' and raw[t['exit_idx']]['day']>=n.b.YEAR_START:status='period_boundary'
    return dict(t,status=status),blocked

def summarize(rows):
    known=[r for r in rows if r['status']=='resolved'];vs=[r['net_pct'] for r in known]
    out=dict(candidates=len(rows),resolved=len(vs),status_counts=dict(collections.Counter(r['status'] for r in rows)),
        reentries=sum(r.get('reentered',False) for r in known))
    if not vs:return out
    equity=peak=1.;drawdown=0.
    for r in known:
        for j,value in r['marks']:
            mark=equity*(1+value/100);peak=max(peak,mark);drawdown=min(drawdown,mark/peak-1)
        equity*=1+r['net_pct']/100;peak=max(peak,equity);drawdown=min(drawdown,equity/peak-1)
    out.update(mean=statistics.mean(vs),win=100*sum(v>0 for v in vs)/len(vs),median=statistics.median(vs),
        cum=100*(equity-1) if len(known)==len(rows) else None,mdd=drawdown*100 if len(known)==len(rows) else None,
        without_best=(sum(vs)-max(vs))/(len(vs)-1) if len(vs)>1 else None,
        reentry_gain=sum(r.get('additional_gain',0) for r in known))
    return out

def run(inputs,output):
    output=Path(output)
    if output.exists():raise ValueError('output exists; inspect before replay')
    output.mkdir();ctx=n.build_context(inputs);panels=make_panels(ctx);grid=[];allrows=[];audits=[]
    books=spec_book();(output/'rules.json').write_text(json.dumps(books,indent=2))
    for label in ['3H_1H_pivot','anyHTF_1H_pivot','ungated_1H']:
        native,risk=prepared(ctx,label);common,reject=old.common_candidates(ctx,native,risk)
        audits.append(dict(label=label,native=len(native),common=len(common),excluded=reject))
        for sample,cs in [('common65',common),('native',native)]:
            for fee in [5,15]:
                for plan in books:
                    rows=[];last=-1;phase=None
                    for c in cs:
                        if phase!=c['phase']:phase=c['phase'];last=-1
                        if c['entry']<=last:continue
                        t,last=episode(ctx,panels,c,plan,fee)
                        t.update(label=label,sample=sample,plan=plan['id'],fee=fee,phase=c['phase'],entry_ET=c['entry_ET'],episode=c['episode'])
                        if 'exit_time' in t:t['exit_ET']=dt.datetime.fromtimestamp(t['exit_time'],n.b.ET).isoformat()
                        rows.append(t)
                    for phase in ['prior','year']:
                        grid.append(dict(label=label,sample=sample,plan=plan['id'],fee=fee,phase=phase,**summarize([r for r in rows if r['phase']==phase])))
                    allrows.extend(rows)
    old.write_csv(output/'summary.csv',grid)
    old.write_csv(output/'trades.csv',[{k:v for k,v in r.items() if k not in ['marks','fills','actions']} for r in allrows])
    (output/'results.json').write_text(json.dumps(dict(grid=grid,audits=audits,rows=allrows)))
    print('FINISHED',len(grid),len(allrows),hashlib.sha256((output/'results.json').read_bytes()).hexdigest())
    for r in grid:
        if r['label']=='3H_1H_pivot' and r['sample']=='common65' and r['phase']=='year' and r['fee']==5:print('MAIN',r)
    for r in grid:
        if r['label']=='3H_1H_pivot' and r['sample']=='native' and r['phase']=='year' and r['fee']==5 and r['plan'] in ['slow_p0.25','guard_p0.25','fixed2']:print('NATIVE',r)

if __name__=='__main__':run(*sys.argv[1:])