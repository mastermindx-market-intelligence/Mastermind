"""Before-outcome offline contract tests for the single frozen 3h no-ignition rule."""
import unittest
from no_ignition_v19 import NoIgnitionOnce,TimerOnly
import study_v14 as prior_source_authority
from engine_v6 import simulate

def bars(mode="failing"):
    ret=[]
    for j in range(650):
        close=(99.8 if mode=="failing" else 100.2) if j>=35 else 100.0
        o=100.0 if j<36 else close
        h=max(o,close)+.01
        l=min(o,close)-.01
        if mode=="early_stop" and j==12:l=98.0
        if mode=="late_failure" and j>=36:close=99.0
        ret.append(dict(start=j*300,end=(j+1)*300,open=o,high=max(h,close),
            low=min(l,close),close=close,volume=1))
    return ret

def check(sample):
    return simulate(sample,0,98.5,horizon=100000,
        partials=[(2,.25)],cost_bps=5,
        decision=NoIgnitionOnce(),ambiguity="stop_first")

class FrozenFailureCondition(unittest.TestCase):
    def test_cut_only_after_exact_third_hour_at_next_bar_open(self):
        x=check(bars("failing"))
        self.assertEqual(x["reason"],"no_ignition_after_3h")
        self.assertEqual(x["exit_idx"],36)
        self.assertEqual(x["exit_time"],36*300)
        self.assertEqual(x["fills"][-1]["at_open"],True)
    def test_above_entry_at_three_hours_does_not_cut_later_retrace(self):
        x=check(bars("late_failure"))
        self.assertNotEqual(x["reason"],"no_ignition_after_3h")
    def test_original_stop_precedes_any_new_exit(self):
        x=check(bars("early_stop"))
        self.assertEqual(x["reason"],"stop")
        self.assertEqual(x["exit_idx"],12)
    def test_check_fires_once_at_first_eligible_time(self):
        f=NoIgnitionOnce()
        st=dict(age_hours=3.0,px=100,remaining=.75)
        first=f(st,dict(close=100.2))
        second=f(dict(st,age_hours=3.5),dict(close=98.0))
        self.assertFalse(first.get("sell"))
        self.assertFalse(second.get("sell"))
    def test_time_exit_unchanged(self):
        t=TimerOnly()
        self.assertFalse(t(dict(age_hours=2.9,remaining=.75),dict(close=99)).get("sell"))
        self.assertEqual(t(dict(age_hours=52.,remaining=.75),dict(close=102))["reason"],"scheduled_next_open")
    def test_refuse_impossible_backwards_clock(self):
        f=NoIgnitionOnce()
        f(dict(age_hours=3.,px=100,remaining=1),dict(close=100.))
        with self.assertRaises(ValueError):f(dict(age_hours=2.,px=100,remaining=1),dict(close=90.))

if __name__=="__main__":unittest.main()