"""Match timed-exit execution to next-open indicator exits; no same-close fills."""
import json,sys
from pathlib import Path
import study_v7 as s
import nested_pivots as n
from policies_v6 import Policy
from lifecycle_v6 import WindowPolicy
from engine_v6 import simulate
from reentry_core import path_known

class TimedDecision:
    def __init__(self,base,hours):self.base,self.hours=base,hours
    def __call__(self,st,b):
        action=self.base(st,b)
        if st['age_hours']>=self.hours:action.update(sell=st['remaining'],reason='scheduled_next_open')
        return action

def run(root):
    root=Path(root);dest=root/'validation/time_nextopen.csv'
    if dest.exists():raise ValueError('existing timer output')
    ctx=n.build_context(root/'inputs');raw=ctx['raw'];pn=s.make_panels(ctx);cs,_=s.prepared(ctx,'3H_1H_pivot');out=[];trades=[]
    for horizon in [13,19.5,26,32.5,39,52,65]:
        rows=[];last=-1;phase=None
        for c in cs:
            if phase!=c['phase']:phase=c['phase'];last=-1
            if c['entry']<=last:continue
            guard=WindowPolicy(dict(grace=3,expiry=6.5,retain=.5),raw,pn,c['entry'])
            guard.base=Policy(dict(kind='time',tf=180),raw,pn,c['entry'])
            t=simulate(raw,c['entry'],c['stop'],horizon=100000,partials=[(2,.25)],decision=TimedDecision(guard,horizon),cost_bps=5)
            if t is None:t=dict(status='right_censored',entry_idx=c['entry']);last=len(raw)-1
            else:
                last=t['exit_idx'];t['status']='resolved' if path_known(raw,c['entry'],t['exit_time']) else 'unobserved_intraday_path'
                if c['phase']=='prior' and raw[t['exit_idx']]['day']>=n.b.YEAR_START:t['status']='period_boundary'
            t.update(phase=c['phase'],horizon=horizon,entry_ET=c['entry_ET']);rows.append(t)
        for phase in ['prior','year']:out.append(dict(horizon=horizon,phase=phase,**s.summarize([r for r in rows if r['phase']==phase])))
        trades.extend([{k:v for k,v in t.items() if k not in ['marks','fills','actions']} for t in rows])
    s.old.write_csv(dest,out);s.old.write_csv(root/'validation/time_nextopen_trades.csv',trades)
    for r in out:print('MATCHED_FILL_TIMER',r)

if __name__=='__main__':run(sys.argv[1])