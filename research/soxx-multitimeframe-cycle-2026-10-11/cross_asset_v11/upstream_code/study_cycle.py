"""Frozen-entry, point-in-time cycle-failure falsification and harm attribution."""
from pathlib import Path
import collections, datetime as dt, hashlib, json, statistics, sys
import frozen_audit as a
import nested_pivots as n
from cycle_failure import MODES, CyclePolicy, make_cycle_panels
from engine_v6 import simulate
from policies_v6 import Policy, make_panels
from lifecycle_v6 import WindowPolicy
from time_nextopen import TimedDecision
from intrabar_audit import replay

class Joined:
    def __init__(self,first,second):self.first,self.second=first,second
    def __call__(self,st,b):
        x=self.first(st,b);y=self.second(st,b)
        return x if x.get('sell',0) else y

def make_policy(ctx,c,mode,clock=52,buffer=.1):
    raw=ctx['raw'];e=c['entry'];monitor=None
    if mode=='time':pol=Policy(dict(kind='time',tf=180),raw,ctx['_panels'],e)
    elif mode=='slow':pol=Policy(dict(kind='legacy_joint',tf=180),raw,ctx['_panels'],e)
    elif mode=='old_guard':pol=WindowPolicy(dict(grace=3,expiry=6.5,retain=.5),raw,ctx['_panels'],e)
    else:
        base=mode.removesuffix('+slow');monitor=CyclePolicy(base,ctx,ctx['_cycle'],c,buffer)
        pol=monitor
        if mode.endswith('+slow'):pol=Joined(monitor,Policy(dict(kind='legacy_joint',tf=180),raw,ctx['_panels'],e))
    return TimedDecision(pol,clock),monitor

def execute(ctx,cs,mode,fraction,gaps,*,clock=52,buffer=.1,shadow=False,cost=5,engine='replay'):
    raw=ctx['raw'];results=[];records=[];phase=None;last=-1
    for c in cs:
        if phase!=c['phase']:phase=c['phase'];last=-1
        en=c['entry']
        if not shadow and en<=last:continue
        pol,mon=make_policy(ctx,c,mode,clock,buffer)
        if engine=='replay':t=replay(raw,en,c['stop'],decision=pol,partial=fraction,fee=cost,horizon=100000,order='OLHC')
        else:t=simulate(raw,en,c['stop'],decision=pol,partials=[(2,fraction)] if fraction else [],cost_bps=cost,horizon=100000)
        if t is None:t=dict(status='right_censored',entry_idx=en);last=len(raw)-1
        else:
            last=t['exit_idx'];bad=a.intersecting_gaps(gaps,raw[en]['start'],t['exit_time'])
            t['status']='unobserved_session_path' if bad else 'resolved'
            if phase=='prior' and raw[last]['day']>=n.b.YEAR_START:t['status']='period_boundary'
            t.update(exit_ET=dt.datetime.fromtimestamp(t['exit_time'],n.b.ET).isoformat(),missing=bad)
        t.update(entry_ET=c['entry_ET'],phase=phase,episode=c['episode'],profile=c['profile'],mode=mode,fraction=fraction)
        results.append(t)
        if mon:
            for r in mon.records:records.append(dict(entry_ET=c['entry_ET'],phase=phase,mode=mode,fraction=fraction,**r))
    return results,records

def pair(candidate,reference):
    ref={t['entry_ET']:t for t in reference if t['status']=='resolved'};rows=[]
    for t in candidate:
        q=ref.get(t['entry_ET'])
        if q is None or t['status']!='resolved':continue
        lift=t['net_pct']-q['net_pct']
        rows.append(dict(entry=t['entry_ET'],baseline=q['net_pct'],cycle=t['net_pct'],lift=lift,
             baseline_exit=q['exit_ET'],exit=t['exit_ET'],reason=t['reason'],early=t['exit_time']<q['exit_time'],
             improved=lift>1e-8,harmed=lift<-1e-8,winner_harmed=q['net_pct']>0 and lift<-1e-8,
             loser_helped=q['net_pct']<0 and lift>1e-8))
    if not rows:return dict(n=0),rows
    z=dict(n=len(rows),mean_lift=statistics.mean(r['lift'] for r in rows),
        improved=sum(r['improved'] for r in rows),harmed=sum(r['harmed'] for r in rows),
        winner_harmed=sum(r['winner_harmed'] for r in rows),loser_helped=sum(r['loser_helped'] for r in rows),
        savings=sum(max(0,r['lift']) for r in rows),sacrificed=sum(max(0,-r['lift']) for r in rows))
    return z,rows

def run(root):
    root=Path(root);out=root/'results';out.mkdir(exist_ok=False)
    modes=['time','slow','old_guard',*MODES,'structural_cycle+slow','sequential_cycle+slow']
    (out/'test_matrix.json').write_text(json.dumps(dict(modes=modes,fractions=[0,.25],horizon=52,
        primary_comparison='same entry, same initial stop, same fraction vs time and slow controls',
        retrospective=True,mode_selection_not_out_of_sample=True),indent=2))
    summary=[];ledger=[];pairs=[];audits={};checks=[];allrecords=[]
    for symbol,file,labels in [('SOXX','rth_original.json',['3H_1H_pivot','anyHTF_1H_pivot']),('SMH','SMH_60m.json',['3H_1H_pivot'])]:
        ctx=a.context_from_source(root/'inputs'/file);ctx['_panels']=make_panels(ctx);ctx['_cycle']=make_cycle_panels(ctx)
        audit=a.source_audit(ctx);audits[symbol]=audit
        for label in labels:
            cs,_=a.v7.prepared(ctx,label);book={}
            for fraction in [0,.25]:
                for mode in modes:
                    ts,recs=execute(ctx,cs,mode,fraction,audit['gaps']);book[mode,fraction]=ts
                    if symbol=='SOXX' and label=='3H_1H_pivot':
                        shadow,_=execute(ctx,cs,mode,fraction,audit['gaps'],engine='engine')
                        for x,y in zip(ts,shadow):
                            if 'net_pct' in x and 'net_pct' in y:checks.append(abs(x['net_pct']-y['net_pct']))
                        allrecords.extend(recs)
                    for ph in ['prior','year']:
                        subset=[r for r in ts if r['phase']==ph]
                        summary.append(dict(symbol=symbol,label=label,mode=mode,fraction=fraction,phase=ph,**a.v7.summarize(subset)))
                    for t in ts:ledger.append(dict(symbol=symbol,label=label,**{k:v for k,v in t.items() if k not in ['marks','fills','actions']}))
                for mode in modes:
                    for ref in ['time','slow']:
                        for ph in ['prior','year']:
                            target=[t for t in book[mode,fraction] if t['phase']==ph];control=[t for t in book[ref,fraction] if t['phase']==ph]
                            z,prs=pair(target,control)
                            for r in prs:pairs.append(dict(symbol=symbol,label=label,mode=mode,fraction=fraction,phase=ph,reference=ref,**r))
    for name,rows in [('summary',summary),('trades',ledger),('pairs',pairs),('state_records',allrecords)]:
        a.v7.old.write_csv(out/(name+'.csv'),rows)
    proof=dict(execution_parity_cases=len(checks),max_return_difference=max(checks),
        sources={f:hashlib.sha256((root/'inputs'/f).read_bytes()).hexdigest() for f in ['rth_original.json','SMH_60m.json']},
        missing_paths_not_imputed=True,retrospective=True)
    (out/'proof.json').write_text(json.dumps(proof,indent=2));(out/'audit.json').write_text(json.dumps(audits))
    (out/'summary.json').write_text(json.dumps(summary))
    print('COMPLETE',len(modes),'methods',len(summary),'summary rows','parity',proof)
    for r in summary:
        if r['symbol']=='SOXX' and r['label']=='3H_1H_pivot' and r['phase']=='year':
            print('MAIN',json.dumps({k:r.get(k) for k in ['mode','fraction','candidates','resolved','mean','win','cum','mdd']}))
if __name__=='__main__':run(sys.argv[1])