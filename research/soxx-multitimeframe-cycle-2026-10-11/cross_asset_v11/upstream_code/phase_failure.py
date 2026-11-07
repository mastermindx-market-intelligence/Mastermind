"""Second hypothesis: failed initial impulse vs a mature defended structure.
Defined after the first cycle test, before this test's outcomes. Retrospective.
"""
from dataclasses import fields
from cycle_failure import CyclePolicy, Evidence, failure_components, make_cycle_panels

PHASE_MODES=('impulse_only','phase_failure','phase_trim')

def phase_components(e, micro_low, buffer=.1):
    gain=(e.close-e.price)/e.atr
    young=not e.established and e.peak_atr<2
    fast_reversal=e.hist<e.prev_hist and e.rsi<50 and e.close<e.ema10
    price_break=e.close<micro_low-buffer*e.atr
    initial=young and e.peak_atr>=.5 and gain<.5*e.peak_atr and price_break and fast_reversal
    no_launch=not e.established and e.peak_atr<.5 and e.age>=e.parent_hours and gain<-.25 \
        and price_break and fast_reversal and e.rsi<45
    mature=e.established and e.close<e.defended-buffer*e.atr and e.close<e.ema10 \
        and e.hist<e.prev_hist and e.parent_hist<e.parent_prev
    return dict(initial_impulse_failure=initial,adverse_no_ignition=no_launch,
                mature_structure_failure=mature,launch_pivot_failure=failure_components(e,buffer)['launch_failure'])

def phase_reason(e,micro_low,mode,buffer=.1):
    if mode not in PHASE_MODES:raise ValueError('unknown phase mode')
    z=phase_components(e,micro_low,buffer)
    keys=['initial_impulse_failure'] if mode=='impulse_only' else [
        'launch_pivot_failure','initial_impulse_failure','adverse_no_ignition','mature_structure_failure']
    return next((key for key in keys if z[key]),None)

def make_phase_panels(ctx,lower_minutes=60):
    p=make_cycle_panels(ctx,lower_minutes);bs=ctx['lower'][lower_minutes]
    p['lower']=[dict(f,micro_low=min(x['low'] for x in bs[max(0,f['i']-2):f['i']])) if f else None for f in p['lower']]
    return p

class PhasePolicy(CyclePolicy):
    def __init__(self,mode,ctx,panels,c,buffer=.1):
        super().__init__('structural_cycle',ctx,panels,c,buffer)
        self.phase_mode=mode;self.trimmed=False
    def __call__(self,st,b):
        count=len(self.records);super().__call__(st,b)
        if len(self.records)==count:return {}
        r=self.records[-1];e=Evidence(**{f.name:r[f.name] for f in fields(Evidence)})
        micro=self.panels['lower'][st['j']]['micro_low']
        reason=phase_reason(e,micro,self.phase_mode,self.buffer)
        r.update(strict_reason=r['reason'],reason=reason,micro_low=micro,
                 **phase_components(e,micro,self.buffer))
        if not reason:return {}
        if self.phase_mode=='phase_trim' and reason=='initial_impulse_failure':
            if self.trimmed:return {}
            self.trimmed=True;return dict(sell=st['remaining']*.5,reason='initial_failure_trim')
        return dict(sell=st['remaining'],reason=reason)