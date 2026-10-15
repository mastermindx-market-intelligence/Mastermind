"""Independent OHLC route replay with close-known stop amendments. Research scenarios,
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
            amend=act.get('stop')
            if amend is not None and amend>stop:
                if amend>=b['close']:pending=(left,'close_breach')
                else:stop=amend;actions.append(dict(j=j,kind='stop',level=stop))
            if act.get('sell',0)>0 and pending is None:
                pending=min(left,act['sell']),act.get('reason','signal');actions.append(dict(j=j,**act))
    return None