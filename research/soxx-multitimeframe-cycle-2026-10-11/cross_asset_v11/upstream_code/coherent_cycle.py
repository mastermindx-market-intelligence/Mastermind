"""Entry/invalidation consistency and confirmed continuation protection.
Research-only primitives. No I/O, networking or brokerage operations.
"""
from dataclasses import dataclass
import math

def assess_entry(price, pivot, atr, *, max_risk_pct=1.5, min_risk_pct=.3, buffer_atr=.1):
    values=(price,pivot,atr,max_risk_pct,min_risk_pct,buffer_atr)
    if not all(math.isfinite(x) for x in values) or min(price,pivot,atr)<=0:
        raise ValueError('nonpositive or nonfinite input')
    if not 0<=min_risk_pct<=max_risk_pct<100 or buffer_atr<0:
        raise ValueError('invalid risk bounds')
    stop=pivot-buffer_atr*atr
    if stop<=0:raise ValueError('nonpositive stop')
    risk_pct=100*(price-stop)/price
    if price<=pivot:reason='pivot_lost'
    elif risk_pct<min_risk_pct-1e-10:reason='too_tight'
    elif risk_pct>max_risk_pct+1e-10:reason='too_far'
    else:reason='accepted'
    return dict(accepted=reason=='accepted',reason=reason,stop=stop,risk_pct=risk_pct,
                maximum_entry=stop/(1-max_risk_pct/100),minimum_entry=stop/(1-min_risk_pct/100),
                pivot=pivot,price=price,atr=atr)

@dataclass
class DefendedSwing:
    level: float
    stop: float
    buffer_atr: float=.1
    pending: tuple|None=None
    last_observation: int=-1
    promotions: int=0

    def __post_init__(self):
        if not 0<self.stop<self.level or self.buffer_atr<0:raise ValueError('invalid initial structure')

    def propose(self, confirmation_index, pivot_low, breakout_level, atr):
        if min(pivot_low,breakout_level,atr)<=0 or breakout_level<pivot_low:
            raise ValueError('invalid candidate pivot')
        if pivot_low>self.level:
            self.pending=(confirmation_index,pivot_low,breakout_level)

    def observe(self,index,close,low,atr):
        if index<=self.last_observation:raise ValueError('nonmonotonic observation')
        self.last_observation=index
        promoted=False
        if self.pending:
            confirmed,pivot,breakout=self.pending
            if low<pivot:self.pending=None
            elif index>confirmed and close>breakout:
                self.level=max(self.level,pivot)
                self.stop=max(self.stop,pivot-self.buffer_atr*atr)
                self.pending=None;self.promotions+=1;promoted=True
        return promoted