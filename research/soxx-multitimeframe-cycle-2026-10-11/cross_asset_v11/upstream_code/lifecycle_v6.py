"""Separate early rebound failure from mature trend management; research only.
The window was designed after inspecting false exits, so all results are retrospective.
"""
import datetime as dt,hashlib,json,sys
from pathlib import Path
import nested_pivots as n
import study_v6 as s
from policies_v6 import Policy,make_panels
from hybrid_v6 import failed_profit_guard
from engine_v6 import simulate

def early_failure_active(age,grace,expiry):
    if expiry<grace:raise ValueError('inverted early window')
    return grace<=age<=expiry

class WindowPolicy:
    def __init__(self,plan,raw,panels,entry):
        self.plan=plan;self.panels=panels;self.last=-1
        self.base=Policy(dict(kind='legacy_joint',tf=180,arm=2),raw,panels,entry)
    def __call__(self,st,b):
        action=self.base(st,b);p=self.plan;f=self.panels[60][st['j']]
        if f is None or not f['valid'] or f['i']==self.last:return action
        self.last=f['i']
        if early_failure_active(st['age_hours'],p['grace'],p['expiry']):
            gain=100*(b['close']/st['px']-1);peak=100*(st['peak']/st['px']-1)
            if failed_profit_guard(st['age_hours'],peak,gain,f['rsi'],b['close']<f['ema10'],p['grace'],p['retain']):
                action.update(sell=st['remaining'],reason='early_rebound_failure')
        return action

def registry():
    out=[]
    for grace in [2,3,4]:
        for expiry in [4.5,6.5,9.75,13]:
            for retain in [.25,.5,.75]:
                for fraction in [0,.25,.5]:
                    out.append(dict(id='L'+str(len(out))+'_window',kind='early_failure_window',grace=grace,expiry=expiry,
                                    retain=retain,partial=fraction,horizon=65))
    return out

def evaluate(ctx,panels,cs,plan,*,delay=1,cost=5,stop_slippage=0,amb='stop_first',shadow=False,limit_buffer=0):
    raw=ctx['raw'];out=[];last=-1;phase=None
    for c in cs:
        if phase!=c['phase']:phase=c['phase'];last=-1
        if not shadow and c['entry']<=last:continue
        parts=[(2,plan['partial'])] if plan['partial'] else []
        t=simulate(raw,c['entry'],c['stop'],horizon=plan.get('horizon',65),partials=parts,
            decision=WindowPolicy(plan,raw,panels,c['entry']),cost_bps=cost,delay=delay,
            stop_slippage_bps=stop_slippage,ambiguity=amb,limit_buffer_bps=limit_buffer)
        if t is None:raise RuntimeError('missing horizon')
        t.update(phase=c['phase'],entry_ET=c['entry_ET'],entry_day=raw[c['entry']]['day'],episode=c['episode'],profile=c['profile'],
                 exit_ET=dt.datetime.fromtimestamp(t['exit_time'],n.b.ET).isoformat())
        out.append(t);last=t['exit_idx']
    return out

def run(inputs,root):
    root=Path(root);out=root/'lifecycle_results'
    if out.exists():raise ValueError('output exists')
    out.mkdir();book=registry();grid=[];trades=[]
    (out/'design.json').write_text(json.dumps(dict(retrospective=True,derived_after_false_exit_review=True,
       hypothesis='A fast failure rule should expire after initial follow-through; persistent application mistakes mature retracements for failed starts.',plans=book),indent=2))
    for recent in [False,True]:
        ctx=n.build_context(inputs,recent);panels=make_panels(ctx);cohort='recent' if recent else 'annual'
        for label,(cs,risk) in s.entry_sets(ctx).items():
            cs,_=s.common_candidates(ctx,cs,risk)
            for p in book:
                ts=evaluate(ctx,panels,cs,p);grid.append(s.row_of(label,p,ts,cohort))
                for t in ts:trades.append(dict(cohort=cohort,label=label,id=p['id'],**{k:v for k,v in t.items() if k not in ['marks','actions','fills']}))
    (out/'grid.json').write_text(json.dumps(grid));s.write_csv(out/'grid.csv',grid);s.write_csv(out/'trades.csv',trades)
    print('LIFECYCLE_DONE',len(book),len(grid),len(trades),hashlib.sha256((out/'grid.json').read_bytes()).hexdigest())
    for r in grid:
        if r['cohort']=='annual' and r['label']=='3H_1H_pivot' and r['grace']==3 and r['expiry']==6.5 and r['retain']==.5:
            print('DEFAULT',{k:r.get(k) for k in ['id','partial','prior_n','prior_mean','prior_ex_best','year_n','year_win','year_mean','year_cum','year_mdd','year_ex_best','year_stress']})
    print('NEIGHBORS_GRACE_RETENTION_HALF')
    for r in grid:
        if r['cohort']=='annual' and r['label']=='3H_1H_pivot' and r['expiry']==6.5 and r['partial']==.5:
            print({k:r.get(k) for k in ['id','grace','retain','prior_mean','prior_ex_best','year_mean','year_mdd']})
if __name__=='__main__':run(*sys.argv[1:])