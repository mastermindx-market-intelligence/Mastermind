"""Predeclared entry-price slippage scenarios; prices are assumptions, not quotes."""
import json,sys
from pathlib import Path
import frozen_audit as a
from intrabar_audit import replay

def run(root):
    root=Path(root);out=root/'entry_fills';out.mkdir(exist_ok=False)
    ctx=a.context_from_source(root/'inputs/rth_original.json');ctx['_panels']=a.make_panels(ctx);raw=ctx['raw']
    cs,_=a.v7.prepared(ctx,'3H_1H_pivot');gaps=a.source_audit(ctx)['gaps'];summary=[];trades=[]
    for bps in [0,5,10,25]:
        for plan in ['fixed2','slow_p0.25','guard_p0.25','guard_p0.5','guard_timer52']:
            for route in ['OHLC','OLHC']:
                rows=[];last=-1;phase=None
                for c in cs:
                    en=c['entry']
                    if c['phase']!=phase:phase=c['phase'];last=-1
                    if en<=last:continue
                    pol,hz,parts=a.policy_for(plan,raw,ctx['_panels'],en);fill=raw[en]['open']*(1+bps/10000)
                    t=replay(raw,en,fill*.985,decision=pol,partial=parts[0][1] if parts else 0,target=2 if plan=='fixed2' else 0,
                             horizon=hz,order=route,entry_fill=fill)
                    if t is None:raise RuntimeError('unexpected missing horizon')
                    last=t['exit_idx'];status='unobserved_session_path' if a.intersecting_gaps(gaps,raw[en]['start'],t['exit_time']) else 'resolved'
                    t.update(status=status,phase=phase,entry_ET=c['entry_ET']);rows.append(t)
                for ph in ['prior','year']:
                    s=a.v7.summarize([r for r in rows if r['phase']==ph]);summary.append(dict(plan=plan,bps=bps,route=route,phase=ph,**s))
                for r in rows:trades.append(dict(plan=plan,bps=bps,route=route,**{k:v for k,v in r.items() if k not in ['marks','fills','actions']}))
    a.v7.old.write_csv(out/'summary.csv',summary);a.v7.old.write_csv(out/'trades.csv',trades)
    for s in summary:
        if s['phase']=='year' and s['route']=='OLHC':print('FILL',{k:s[k] for k in ['plan','bps','resolved','mean','win','mdd']})
if __name__=='__main__':run(sys.argv[1])