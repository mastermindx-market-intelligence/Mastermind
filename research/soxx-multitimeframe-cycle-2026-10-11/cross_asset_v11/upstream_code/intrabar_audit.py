"""Independent OHLC route replay for frozen long exits. Research scenarios,
not tick reconstruction or limits on the unobserved overnight path."""
import collections, json, hashlib, sys
from pathlib import Path
import frozen_audit as a

def replay(raw,entry,stop,*,decision=None,partial=0,target=0,horizon=65,order='OHLC',fee=5,entry_fill=None):
    if order not in ['OHLC','OLHC']:raise ValueError('unknown path')
    px=raw[entry]['open'] if entry_fill is None else entry_fill;left=1.;cash=0.;elapsed=0.;pending=None;partial_done=False
    fills=[];marks=[];actions=[];peak=px;peakclose=px;lastpeak=entry;initial_stop=stop
    def mark(j,price):
        ratio=(cash+left*price)/px;marks.append((j,100*(ratio-1)-fee/100*(1+ratio)))
    def sell(j,q,price,reason,at_open):
        nonlocal left,cash
        q=min(q,left);cash+=q*price;left-=q
        if left<1e-12:left=0.
        fills.append(dict(j=j,q=q,price=price,reason=reason,at_open=at_open));mark(j,price)
    def finish(j,reason,at_open):
        ratio=cash/px
        return dict(entry_idx=entry,exit_idx=j,entry_price=px,exit_time=raw[j]['start'] if at_open else raw[j]['end'],
                    net_pct=100*(ratio-1)-fee/100*(1+ratio),gross_pct=100*(ratio-1),marks=marks,fills=fills,actions=actions,
                    reason=reason,hold_hours=elapsed/3600,initial_risk_pct=100*(px-initial_stop)/px)
    for j in range(entry,len(raw)):
        b=raw[j];o=b['open'];mark(j,o)
        if o<=stop:
            sell(j,left,o,'stop_gap',True);return finish(j,'stop_gap',True)
        if partial and not partial_done and o>=px*1.02:
            sell(j,partial,px*1.02,'partial_open',True);partial_done=True
        if pending is not None:
            q,why=pending;sell(j,q,o,why,True);pending=None
            if not left:return finish(j,why,True)
        if target and o>=px*(1+target/100):
            sell(j,left,px*(1+target/100),'target_gap',True);return finish(j,'target_gap',True)
        path=[o,b['high'],b['low'],b['close']] if order=='OHLC' else [o,b['low'],b['high'],b['close']]
        for x,y in zip(path,path[1:]):
            if y>x:
                levels=[]
                if partial and not partial_done and x<=px*1.02<=y:levels.append((px*1.02,partial,'partial'))
                if target and x<=px*(1+target/100)<=y:levels.append((px*(1+target/100),left,'target'))
                for price,q,why in sorted(levels):
                    mark(j,price);sell(j,q,price,why,False)
                    if why=='partial':partial_done=True
                    if not left:
                        elapsed+=b['end']-b['start'];return finish(j,why,False)
            elif y<=stop<=x:
                mark(j,stop);sell(j,left,stop,'stop',False)
                elapsed+=b['end']-b['start'];return finish(j,'stop',False)
            mark(j,y)
        elapsed+=b['end']-b['start']
        if b['high']>peak:peak=b['high'];lastpeak=j
        peakclose=max(peakclose,b['close'])
        if elapsed>=horizon*3600:
            sell(j,left,b['close'],'time',False);return finish(j,'time',False)
        if decision:
            st=dict(j=j,entry=entry,px=px,remaining=left,stop=stop,initial_stop=initial_stop,peak=peak,peak_close=peakclose,
                    last_peak_j=lastpeak,age_hours=elapsed/3600,cash=cash,partial_hits=int(partial_done),pending=False)
            act=decision(st,b) or {}
            if act.get('stop') is not None:raise ValueError('not a fixed-stop policy')
            if act.get('sell',0)>0:
                pending=min(left,act['sell']),act.get('reason','signal');actions.append(dict(j=j,**act))
    return None

def run(root):
    root=Path(root);out=root/'intrabar';out.mkdir(exist_ok=False)
    ctx=a.context_from_source(root/'inputs/rth_original.json');ctx['_panels']=a.make_panels(ctx);raw=ctx['raw']
    cs,_=a.v7.prepared(ctx,'3H_1H_pivot');gaps=a.source_audit(ctx)['gaps'];rows=[];trades=[];parity=[]
    for plan in a.PLANS:
        references=a.evaluate(ctx,cs,plan,gaps);ref={r['entry_ET']:r for r in references}
        for order in ['OHLC','OLHC']:
            results=[];last=-1;phase=None
            for c in cs:
                en=c['entry']
                if phase!=c['phase']:phase=c['phase'];last=-1
                if en<=last:continue
                pol,hz,parts=a.policy_for(plan,raw,ctx['_panels'],en)
                t=replay(raw,en,c['stop'],decision=pol,partial=parts[0][1] if parts else 0,target=2 if plan=='fixed2' else 0,horizon=hz,order=order)
                if t is None:raise RuntimeError('unresolved tail in main cohort')
                last=t['exit_idx'];status='unobserved_session_path' if a.intersecting_gaps(gaps,raw[en]['start'],t['exit_time']) else 'resolved'
                t.update(status=status,phase=c['phase'],entry_ET=c['entry_ET']);results.append(t)
                old=ref[c['entry_ET']]
                parity.append(dict(plan=plan,order=order,entry=c['entry_ET'],net_delta=t['net_pct']-old['net_pct'],exit_same=t['exit_time']==old['exit_time']))
            for ph in ['prior','year']:rows.append(dict(plan=plan,order=order,phase=ph,**a.v7.summarize([t for t in results if t['phase']==ph])))
            for t in results:trades.append(dict(plan=plan,order=order,**{k:v for k,v in t.items() if k not in ['marks','fills','actions']}))
    a.v7.old.write_csv(out/'summary.csv',rows);a.v7.old.write_csv(out/'trade_parity.csv',parity)
    proof=dict(scenarios='OHLC and OLHC; interpolated thresholds, not actual trade sequence',replays=len(parity),
               max_return_difference=max(abs(p['net_delta']) for p in parity),exit_time_disagreements=sum(not p['exit_same'] for p in parity))
    (out/'proof.json').write_text(json.dumps(proof,indent=2));print('PROOF',proof)
    for r in rows:
        if r['phase']=='year':print('INTRABAR',{k:r.get(k) for k in ['plan','order','resolved','mean','win','cum','mdd']})
if __name__=='__main__':run(sys.argv[1])