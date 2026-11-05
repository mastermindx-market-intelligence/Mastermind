"""Causal recovery-cycle invalidation hypotheses, not a fitted trading model.
Price structure is mandatory for confirmed exits; negative momentum alone is a control.
No networking, brokerage actions or fitted parameters. All inputs must be close-known.
"""
from dataclasses import dataclass, asdict
import bisect
import nested_pivots as n

MODES=('fast_weak_control','pivot_break','failed_reclaim','no_ignition',
       'structural_cycle','sequential_cycle','momentum_reset')

@dataclass(frozen=True)
class Evidence:
    age: float
    parent_hours: float
    close: float
    price: float
    atr: float
    pivot: float
    defended: float
    rsi: float
    hist: float
    prev_hist: float
    prev2_hist: float
    ema10: float
    parent_hist: float
    parent_prev: float
    parent_prev2: float
    parent_rsi: float
    peak_atr: float
    reclaimed: bool
    lost_reclaim: int
    fast_was_positive: bool
    parent_was_positive: bool
    established: bool

def failure_components(e, buffer=.1):
    if e.atr<=0:raise ValueError('ATR must be positive')
    down=e.hist<e.prev_hist<e.prev2_hist
    weak=down and e.rsi<45
    parent_down=(e.parent_hist<e.parent_prev<e.parent_prev2 and e.parent_rsi<50)
    parent_down|=e.parent_was_positive and e.parent_hist<0 and e.parent_rsi<50
    pivot=e.close<e.pivot-buffer*e.atr
    defended=e.established and e.close<e.defended-buffer*e.atr
    loss_value=e.close<e.ema10
    return dict(fast_weak=weak,parent_weak=parent_down,pivot_broken=pivot,
        defended_broken=defended,launch_failure=pivot and weak,
        reclaim_failure=e.reclaimed and e.lost_reclaim>=2 and weak and parent_down,
        no_ignition=e.age>=2*e.parent_hours and e.peak_atr<.5
                    and e.close<e.price-.25*e.atr and weak and parent_down,
        trend_failure=defended and weak and parent_down,
        momentum_reset=e.fast_was_positive and e.hist<0 and weak and loss_value
                       and (pivot or defended or e.lost_reclaim>=2))

def decision_reason(e, mode, buffer=.1):
    if mode not in MODES:raise ValueError('unknown mode')
    z=failure_components(e,buffer)
    if mode=='fast_weak_control':return 'fast_weak_only' if z['fast_weak'] else None
    if mode=='pivot_break':return 'launch_pivot_failure' if z['launch_failure'] else None
    if mode=='failed_reclaim':return 'reclaim_failure' if z['reclaim_failure'] else None
    if mode=='no_ignition':return 'no_ignition' if z['no_ignition'] else None
    if mode=='momentum_reset':return 'momentum_reset' if z['momentum_reset'] else None
    for key,reason in [('launch_failure','launch_pivot_failure'),('reclaim_failure','reclaim_failure'),
                       ('no_ignition','no_ignition'),('trend_failure','defended_swing_failure')]:
        if z[key]:return reason
    return None

class SequentialConfirmation:
    def __init__(self):self.warning=None
    def update(self,i,reason,close,level):
        if reason is None or close>=level:
            self.warning=None;return None
        if self.warning is not None:
            oi,oc,oldreason=self.warning
            if i>oi and close<=oc:return reason+'_confirmed'
        if self.warning is None or i>self.warning[0]:self.warning=(i,close,reason)
        return None

def feature_panel(bars,macd,rawends):
    f=n.enrich(bars,macd,14);ema=n.b.ema([b['close'] for b in bars],10)
    items=[];ends=[]
    for i,b in enumerate(bars):
        if i<2 or not b.get('complete',True) or f['atr'][i] is None or f['rsi'][i] is None:continue
        pv=f['piv1'][i]
        items.append(dict(i=i,end=b['end'],start=b['start'],close=b['close'],high=b['high'],low=b['low'],
            rsi=f['rsi'][i],hist=f['hist'][i],prev_hist=f['hist'][i-1],prev2_hist=f['hist'][i-2],
            ema10=ema[i],atr=f['atr'][i],k=f['k'][i],d=f['d'][i],
            pivot_start=bars[pv]['start'] if pv is not None else None,
            pivot_low=bars[pv]['low'] if pv is not None else None,
            pivot_confirmation=b['end'] if pv is not None and i==pv+1 else None))
        ends.append(b['end'])
    return [items[k] if (k:=bisect.bisect_right(ends,t)-1)>=0 else None for t in rawends]

def make_cycle_panels(ctx,lower_minutes=60):
    out={'lower':feature_panel(ctx['lower'][lower_minutes],(5,13,4),ctx['rawends'])}
    for name,(tf,mac,p) in n.PROFILES.items():out[name]=feature_panel(ctx['high'][tf],mac,ctx['rawends'])
    return out

class CyclePolicy:
    def __init__(self,mode,ctx,panels,c,buffer=.1):
        self.mode,self.ctx,self.panels,self.c,self.buffer=mode,ctx,panels,c,buffer
        self.last=-1;self.records=[];self.sequence=SequentialConfirmation()
        self.pivot=float(c['anchor']);self.defended=self.pivot
        self.price=ctx['raw'][c['entry']]['open'];self.atr=float(c['atr'])
        self.reclaim=ctx['raw'][c['signal_idx']]['high']
        self.peakclose=self.price;self.pendingpivot=None;self.lastpivot=None
        self.established=False;self.reclaimed=False;self.lost=0;self.fastpos=False;self.parentpos=False
    def __call__(self,st,b):
        j=st['j'];f=self.panels['lower'][j];h=self.panels[self.c['profile']][j]
        if not f or not h or f['i']==self.last:return {}
        if f['end']>b['end'] or h['end']>b['end']:raise AssertionError('future feature')
        self.last=f['i'];priorpeak=self.peakclose;self.peakclose=max(self.peakclose,f['close'])
        # A new low is defended only after confirmation AND a later close above the pre-pivot high.
        if f['pivot_start']!=self.lastpivot and f['pivot_start'] is not None:
            self.lastpivot=f['pivot_start']
            if f['pivot_start']>=self.ctx['raw'][self.c['entry']]['start'] and f['pivot_low']>self.defended:
                self.pendingpivot=(f['pivot_low'],priorpeak,f['i'])
        if self.pendingpivot:
            low,barrier,known=self.pendingpivot
            if f['i']>known and f['close']>barrier+self.buffer*self.atr:
                self.defended=low;self.established=True;self.pendingpivot=None
        self.reclaimed|=f['close']>self.reclaim+self.buffer*self.atr and f['rsi']>=50
        self.lost=self.lost+1 if self.reclaimed and f['close']<self.reclaim-self.buffer*self.atr else 0
        peakatr=(self.peakclose-self.price)/self.atr
        e=Evidence(st['age_hours'],n.PROFILES[self.c['profile']][0]/60,f['close'],self.price,self.atr,
            self.pivot,self.defended,f['rsi'],f['hist'],f['prev_hist'],f['prev2_hist'],f['ema10'],
            h['hist'],h['prev_hist'],h['prev2_hist'],h['rsi'],peakatr,self.reclaimed,self.lost,
            self.fastpos,self.parentpos,self.established)
        reason=decision_reason(e,self.mode,self.buffer)
        if self.mode=='sequential_cycle':
            level=max(self.pivot,self.defended if self.established else self.pivot,
                      self.reclaim if self.lost>=2 else self.pivot)
            reason=self.sequence.update(f['i'],reason,f['close'],level)
        stage='ESTABLISHED' if self.established else 'RECOVERING' if self.reclaimed or peakatr>=1 else 'UNCONFIRMED'
        self.records.append(dict(j=j,time=b['end'],stage=stage,reason=reason,
            lower_end=f['end'],parent_end=h['end'],reclaim_level=self.reclaim,**asdict(e),**failure_components(e,self.buffer)))
        self.fastpos|=f['hist']>0;self.parentpos|=h['hist']>0
        return dict(sell=st['remaining'],reason=reason) if reason else {}