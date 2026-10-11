"""Bounded live-data validation of the saved research run (offline replay only)."""
import collections, datetime as dt, hashlib, json, statistics, sys
from pathlib import Path
import study_v7 as s
import nested_pivots as n
from policies_v6 import Policy
from lifecycle_v6 import WindowPolicy
from engine_v6 import simulate
from reentry_core import path_known

def run(inputs,root):
    root=Path(root);dst=root/'validation'
    if dst.exists():raise ValueError('validation target exists')
    dst.mkdir();ctx=n.build_context(inputs);pn=s.make_panels(ctx);raw=ctx['raw']
    result=json.loads((root/'run1/results.json').read_text());book={p['id']:p for p in s.spec_book()}
    cs,_=s.prepared(ctx,'3H_1H_pivot');byentry={c['entry']:c for c in cs}
    cases=[r for r in result['rows'] if r['label']=='3H_1H_pivot' and r['sample']=='native' and r['fee']==5 and r['status']=='resolved']
    seen=set();prefix_checks=0;budget_checks=0
    for t in cases:
        key=(t['entry_idx'],t['plan'])
        if key in seen:continue
        seen.add(key);cut=t['exit_idx']+1
        short=dict(ctx,raw=raw[:cut],clock=ctx['clock'][:cut+1])
        panels={k:v[:cut] for k,v in pn.items()}
        z,_=s.episode(short,panels,byentry[t['entry_idx']],book[t['plan']],5)
        assert 'net_pct' in z and abs(t['net_pct']-z['net_pct'])<1e-10,(key,'future deletion changed resolved return')
        assert t.get('reentered',False)==z.get('reentered',False)
        prefix_checks+=1
        if t.get('reentered'):
            j=t['reentry_signal'];en=t['reentry_idx']
            assert raw[en]['start']>=raw[j]['end'] and en>t['first_exit_idx']
            assert 0<t['reentry_quantity']<=t['fills'][-1]['q']
            assert t['hold_hours']<=65+1e-8
            budget_checks+=1
    timed=[];timetrades=[]
    for guard in [False,True]:
        for horizon in [13,19.5,26,32.5,39,52,65]:
            last=-1;phase=None;rows=[]
            for c in cs:
                if phase!=c['phase']:phase=c['phase'];last=-1
                if c['entry']<=last:continue
                if guard:
                    policy=WindowPolicy(dict(grace=3,expiry=6.5,retain=.5),raw,pn,c['entry'])
                    policy.base=Policy(dict(kind='time',tf=180),raw,pn,c['entry'])
                else:policy=Policy(dict(kind='time',tf=180),raw,pn,c['entry'])
                t=simulate(raw,c['entry'],c['stop'],horizon=horizon,partials=[(2,.25)],decision=policy,cost_bps=5)
                if t is None:t=dict(status='right_censored',entry_idx=c['entry']);last=len(raw)-1
                else:
                    last=t['exit_idx'];t['status']='resolved' if path_known(raw,c['entry'],t['exit_time']) else 'unobserved_intraday_path'
                    if c['phase']=='prior' and raw[t['exit_idx']]['day']>=n.b.YEAR_START:t['status']='period_boundary'
                t.update(phase=c['phase'],entry_ET=c['entry_ET'],horizon=horizon,guard=guard)
                rows.append(t)
            for phase in ['prior','year']:timed.append(dict(guard=guard,horizon=horizon,phase=phase,**s.summarize([r for r in rows if r['phase']==phase])))
            timetrades.extend(rows)
    s.old.write_csv(dst/'time_controls.csv',timed)
    s.old.write_csv(dst/'time_trade_paths.csv',[{k:v for k,v in r.items() if k not in ['marks','fills','actions']} for r in timetrades])
    paired=[]
    for fraction in [.25,.5]:
        for label in ['3H_1H_pivot','anyHTF_1H_pivot','ungated_1H']:
            selected=[r for r in result['rows'] if r['label']==label and r['sample']=='native' and r['fee']==5]
            old={r['entry_idx']:r for r in selected if r['plan']==f'slow_p{fraction}' and r['status']=='resolved'}
            new={r['entry_idx']:r for r in selected if r['plan']==f'guard_p{fraction}' and r['status']=='resolved'}
            for i in sorted(old.keys()&new.keys()):
                a,z=old[i],new[i]
                paired.append(dict(label=label,fraction=fraction,phase=z['phase'],entry=z['entry_ET'],
                  slow=a['net_pct'],guard=z['net_pct'],lift=z['net_pct']-a['net_pct'],
                  slow_exit=dt.datetime.fromtimestamp(a['exit_time'],n.b.ET).isoformat(),
                  guard_exit=dt.datetime.fromtimestamp(z['exit_time'],n.b.ET).isoformat(),guard_reason=z['reason']))
    s.old.write_csv(dst/'paired_guard.csv',paired)
    proof=dict(prefix_checks=prefix_checks,reentry_budget_cases=budget_checks,source_sha256=hashlib.sha256((Path(inputs)/'rth_original.json').read_bytes()).hexdigest(),
      rules_frozen_before_current_run=True,retrospective=True,overnight_execution=False,
      coverage_qualification='Same-day source-bar gaps audited only; no independent quote, exchange-calendar, or tick-path validation.')
    (dst/'proof.json').write_text(json.dumps(proof,indent=2))
    print('PROOF',json.dumps(proof))
    for r in timed:
        if r['phase']=='year':print('TIMER',r)
    for r in result['rows']:
        if r['label']=='3H_1H_pivot' and r['sample']=='native' and r['fee']==5 and r.get('reentered') and 'p0.25' in r['plan']:
            print('REENTRY',{k:r.get(k) for k in ['plan','entry_ET','status','first_net','reentry_ET','reentry_quantity','additional_gain','net_pct','exit_ET']})
    print('VALIDATION_SHA256',hashlib.sha256((dst/'proof.json').read_bytes()).hexdigest())

if __name__=='__main__':run(*sys.argv[1:])