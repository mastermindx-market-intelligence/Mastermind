"""Frozen, causal 3-RTH-hour no-ignition research exit.

Only a *completed* 5-minute close strictly below the original opening
purchase price at first 3-hour deadline initiates a sell at the *next* known
bar's open. Original 1.5% hard emergency stop is never suppressed or widened.
"""
import math

class TimerOnly:
    def __init__(self,max_rth_hours=52.):
        if not (isinstance(max_rth_hours,(float,int)) and 0<max_rth_hours<1000):
            raise ValueError("invalid timer")
        self.max_rth_hours=float(max_rth_hours)
        self.last_age=-1.
    def _age(self,state):
        age=state["age_hours"]
        if not isinstance(age,(float,int)) or not math.isfinite(age) or age<self.last_age-1e-8:
            raise ValueError("backwards or non-finite elapsed RTH")
        self.last_age=age
        return age
    def __call__(self,state,bar):
        age=self._age(state)
        if age>=self.max_rth_hours:
            return dict(sell=state["remaining"],reason="scheduled_next_open")
        return {}

class NoIgnitionOnce(TimerOnly):
    def __init__(self,probe_rth_hours=3.):
        super().__init__(max_rth_hours=52.)
        if probe_rth_hours!=3.0:raise ValueError("only the predeclared 3h diagnostic is allowed")
        self.probe_rth_hours=3.
        self.checked=False
        self.checks=0
        self.close_at_check=None
        self.failed_at_check=None
    def __call__(self,state,bar):
        default=super().__call__(state,bar)
        age=state["age_hours"]
        if not self.checked and age>=self.probe_rth_hours:
            self.checked=True
            self.checks+=1
            self.close_at_check=float(bar["close"])
            px=float(state["px"])
            self.failed_at_check=self.close_at_check<px
            if self.failed_at_check and not default:
                return dict(sell=state["remaining"],reason="no_ignition_after_3h")
        return default