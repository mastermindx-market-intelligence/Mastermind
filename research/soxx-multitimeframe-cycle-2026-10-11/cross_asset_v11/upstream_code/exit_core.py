"""Deterministic long-only OHLC exit research; no API, broker, or credential effects.
Indicator decisions are close-known and execute on the next observed source-bar open.
Stops/limits already in force can execute intrabar; ambiguous touches are stop-first.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class ExitSpec:
    name:str
    horizon_hours:float=19.5
    target_pct:float=0.0
    protection:str='none'
    partial:float=0.0
    min_signal_gain:float=-100.0

def simulate(raw,entry,stop,spec,arm=None,trigger=None,atr=None,fees_bps=5):
    if not 0<=entry<len(raw): raise ValueError('entry index')
    px=raw[entry]['open']
    if not 0<stop<px: raise ValueError('invalid long stop')
    if not (0<=spec.partial<1 and spec.horizon_hours>0):raise ValueError('invalid exit specification')
    if spec.protection not in ['none','breakeven','trail2atr','trail3atr','half_giveback']:
        raise ValueError('unknown protection')
    arm=arm if arm is not None else [False]*len(raw)
    trigger=trigger if trigger is not None else [False]*len(raw)
    target=px*(1+spec.target_pct/100) if spec.target_pct else float('inf')
    remaining=1.;cash=0.;elapsed=0.;armed=False;pending=None;signal_idx=None
    peak=px;max_close=0.;seen2=False;partial_done=False;ambiguous=0
    initial_stop=stop;marks=[];fills=[]
    for j in range(entry,len(raw)):
        r=raw[j];elapsed+=r['end']-r['start']
        reason=None;fill=None;at_open=False
        # Known opening prices are evaluated before any high/low for this candle.
        if r['open']<=stop:fill,reason,at_open=r['open'],'stop_gap',True
        else:
            # An already executable opening partial limit precedes later intrabar lows.
            if spec.partial and not partial_done and r['open']>=px*1.02:
                cash+=spec.partial*px*1.02;remaining-=spec.partial;partial_done=True;seen2=True
                fills.append((j,spec.partial,px*1.02,'partial_open_2pct'))
            if pending is not None:fill,reason,at_open=r['open'],'momentum',True
            elif r['open']>=target:fill,reason,at_open=target,'target_gap',True
        if reason is None:
            stop_touch=r['low']<=stop;target_touch=r['high']>=target
            partial_touch=spec.partial>0 and not partial_done and r['high']>=px*1.02
            if stop_touch and (target_touch or partial_touch):ambiguous+=1
            if stop_touch:fill,reason=stop,'stop'
            elif target_touch:fill,reason=target,'target'
        if reason is not None:
            cash+=remaining*fill;fills.append((j,remaining,fill,reason));remaining=0.
        else:
            peak=max(peak,r['high']);max_close=max(max_close,100*(r['close']/px-1))
            if r['high']>=px*1.02:seen2=True
            if spec.partial and not partial_done and r['high']>=px*1.02:
                cash+=spec.partial*px*1.02;remaining-=spec.partial;partial_done=True
                fills.append((j,spec.partial,px*1.02,'partial_2pct'))
            # Time exits at the known closing price; no unobserved intrabar timestamp claimed.
            if elapsed>=spec.horizon_hours*3600:
                fill,reason=r['close'],'time'
                cash+=remaining*fill;fills.append((j,remaining,fill,reason));remaining=0.
            else:
                if arm[j]:armed=True
                if armed and trigger[j] and 100*(r['close']/px-1)>=spec.min_signal_gain:pending=j;signal_idx=j
                # Revisions are effective on the NEXT candle, never retroactively.
                if seen2:
                    if spec.protection=='breakeven':stop=max(stop,px)
                    elif spec.protection=='half_giveback':stop=max(stop,px+(peak-px)*.5)
                    elif spec.protection.startswith('trail') and atr is not None and atr[j]:
                        multiple=2 if spec.protection=='trail2atr' else 3
                        stop=max(stop,peak-multiple*atr[j])
        liquid=cash+remaining*r['close'] if remaining else cash
        netmark=100*(liquid/px-1)-fees_bps/100*(1+liquid/px)
        marks.append((j,netmark))
        if reason is not None:
            gross=100*(cash/px-1);net=gross-fees_bps/100*(1+cash/px)
            return dict(entry_idx=entry,exit_idx=j,entry_price=px,exit_price=fill,
                entry_time=raw[entry]['start'],exit_time=r['start'] if at_open else r['end'],
                signal_idx=signal_idx,gross_pct=gross,net_pct=net,reason=reason,
                hold_market_hours=(elapsed-(r['end']-r['start']) if at_open else elapsed)/3600,
                fee_bps_per_side=fees_bps,weighted_exit_ratio=cash/px,
                initial_risk_pct=100*(px-initial_stop)/px,net_R=net/(100*(px-initial_stop)/px),
                partial_done=partial_done,reached_2pct_before_exit=seen2 or reason in ['target','target_gap'] and spec.target_pct>=2,
                max_close_gain_pct=max_close,giveback_from_max_close_pct=max(0,max_close-gross),
                ambiguous_bars=ambiguous,fills=fills,marks=marks)
    return None