"""Causal, fraction-aware research exit engine. Offline; no broker/API effects.
All strategy decisions are close-known; market orders and stop amendments act later.
Stop/limit ambiguity is conservative by default; opening executable orders act first.
"""
import math

def simulate(raw,entry,initial_stop,*,horizon=65,target=0,partials=(),decision=None,
             cost_bps=5,delay=1,ambiguity='stop_first',stop_slippage_bps=0,limit_buffer_bps=0):
    if not 0<=entry<len(raw):raise ValueError('entry')
    px=raw[entry]['open']
    if not 0<initial_stop<px:raise ValueError('invalid long stop')
    if horizon<=0 or delay<1:raise ValueError('horizon/delay')
    if any(p<=0 or q<=0 for p,q in partials) or sum(q for p,q in partials)>=1:
        raise ValueError('invalid partials')
    if ambiguity not in ['stop_first','limit_first']:raise ValueError('ambiguity')
    cash=0.;left=1.;stop=initial_stop;elapsed=0.;pending=None;hits=set()
    fills=[];marks=[];actions=[];peak=px;peakclose=px;lastpeak=entry;amb=0;seen2=False
    limit=px*(1+target/100) if target else math.inf
    orders=sorted((px*(1+p/100),q,k) for k,(p,q) in enumerate(partials))
    def sell(j,q,price,why,at_open):
        nonlocal cash,left
        q=min(q,left)
        if q<=1e-12:return
        cash+=q*price;left-=q
        if left<1e-12:left=0.
        fills.append(dict(j=j,q=q,price=price,reason=why,at_open=at_open))
    for j in range(entry,len(raw)):
        b=raw[j];duration=b['end']-b['start']
        if duration<=0:raise ValueError('nonpositive duration')
        at_open=False;reason=None
        if b['open']<=stop:
            sell(j,left,b['open']*(1-stop_slippage_bps/10000),'stop_gap',True)
            at_open=True;reason='stop_gap'
        else:
            for level,q,k in orders:
                if k not in hits and b['open']>=level*(1+limit_buffer_bps/10000):
                    sell(j,q,level,'partial_open',True);hits.add(k);seen2|=level>=px*1.02
            if pending is not None and j>=pending[0]:
                _,q,why=pending;sell(j,q,b['open'],why,True);pending=None
                if left==0:reason=why;at_open=True
            if left and b['open']>=limit*(1+limit_buffer_bps/10000):
                sell(j,left,limit,'target_gap',True);reason='target_gap';at_open=True;seen2|=target>=2
        if left:
            touched=b['low']<=stop
            order_touch=b['high']>=limit*(1+limit_buffer_bps/10000) or any(k not in hits and b['high']>=lev*(1+limit_buffer_bps/10000) for lev,q,k in orders)
            if touched and order_touch:amb+=1
            if touched and (ambiguity=='stop_first' or not order_touch):
                sell(j,left,stop*(1-stop_slippage_bps/10000),'stop',False);reason='stop'
            else:
                for level,q,k in orders:
                    if k not in hits and b['high']>=level*(1+limit_buffer_bps/10000):
                        sell(j,q,level,'partial',False);hits.add(k);seen2|=level>=px*1.02
                if b['high']>=limit*(1+limit_buffer_bps/10000):
                    sell(j,left,limit,'target',False);reason='target';seen2|=target>=2
                elif touched:
                    sell(j,left,stop*(1-stop_slippage_bps/10000),'stop',False);reason='stop'
        if left:
            if b['high']>peak:peak=b['high'];lastpeak=j
            peakclose=max(peakclose,b['close']);seen2|=b['high']>=px*1.02
            elapsed+=duration
            if elapsed>=horizon*3600:
                sell(j,left,b['close'],'time',False);reason='time'
            elif decision is not None:
                state=dict(j=j,entry=entry,px=px,remaining=left,stop=stop,
                     initial_stop=initial_stop,peak=peak,peak_close=peakclose,last_peak_j=lastpeak,
                     age_hours=elapsed/3600,cash=cash,partial_hits=len(hits),pending=pending is not None)
                action=decision(state,b) or {}
                newstop=action.get('stop')
                if newstop is not None and math.isfinite(newstop) and newstop>stop:
                    if newstop>=b['close']:
                        if pending is None:pending=(j+delay,left,'close_breach')
                    else:
                        stop=newstop;actions.append(dict(j=j,kind='stop',level=stop))
                q=min(left,max(0.,action.get('sell',0.)))
                if q and pending is None:
                    why=action.get('reason','signal');pending=(j+delay,q,why)
                    actions.append(dict(j=j,kind='sell',q=q,reason=why))
        else:
            elapsed+=0 if at_open else duration
        value=cash+left*b['close'];ratio=value/px
        marks.append((j,100*(ratio-1)-cost_bps/100*(1+ratio)))
        if left==0:
            gross=100*(cash/px-1);net=gross-cost_bps/100*(1+cash/px)
            return dict(entry_idx=entry,exit_idx=j,entry_price=px,exit_time=b['start'] if at_open else b['end'],
                gross_pct=gross,net_pct=net,weighted_exit_ratio=cash/px,reason=reason,
                hold_hours=elapsed/3600,initial_risk_pct=100*(px-initial_stop)/px,
                net_R=net/(100*(px-initial_stop)/px),ambiguous=amb,fills=fills,marks=marks,actions=actions,
                reached2=seen2,max_close_gain=100*(peakclose/px-1),
                giveback=max(0.,100*(peakclose/px-1)-gross))
    return None