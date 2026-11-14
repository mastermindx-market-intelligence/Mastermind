import unittest
import numpy as np
import pandas as pd
from matched_exits import common_eligibility,standalone_path
from evaluate import account

class MatchedExitTests(unittest.TestCase):
    def data(self,n=300):
        index=pd.bdate_range('2018-01-02',periods=n)
        return pd.Series(100*np.exp(np.arange(n)*.001),index=index)
    def test_common_origin_cutoff_not_horizon_specific(self):
        t=self.data();valid=common_eligibility(pd.Series(True,index=t.index))
        signal=pd.Series(False,index=t.index);signal.iloc[[10,200]]=True
        a=account(t,signal,valid,63,0);b=account(t,signal,valid,126,0)
        self.assertEqual(len(a['trades']),1);self.assertEqual(len(b['trades']),1)
        self.assertEqual(a['trades'][0]['entry'],b['trades'][0]['entry'])
    def test_dynamic_exit_observed_previous_session(self):
        t=self.data();ex=pd.Series(False,index=t.index);ex.iloc[20]=True
        p=standalone_path(t,10,126,0,0,ex)
        self.assertEqual(p['entry'],t.index[11]);self.assertEqual(p['exit'],t.index[21])
    def test_latency_applies_entry_and_exit(self):
        t=self.data();ex=pd.Series(False,index=t.index);ex.iloc[20]=True
        p=standalone_path(t,10,126,0,1,ex)
        self.assertEqual(p['entry'],t.index[12]);self.assertEqual(p['exit'],t.index[22])
    def test_exit_before_entry_not_used(self):
        t=self.data();ex=pd.Series(False,index=t.index);ex.iloc[8]=True
        p=standalone_path(t,10,126,0,0,ex)
        self.assertEqual(p['exit_reason'],'maximum_horizon')
    def test_missing_future_not_loss_label(self):
        t=self.data();p=standalone_path(t,250,126)
        self.assertEqual(p['status'],'RIGHT_CENSORED_AT_CAPTURE');self.assertNotIn('net_return',p)
    def test_same_event_account_and_standalone_match(self):
        t=self.data();s=pd.Series(False,index=t.index);s.iloc[10]=True;ex=pd.Series(False,index=t.index);ex.iloc[20]=True
        a=account(t,s,common_eligibility(pd.Series(True,index=t.index)),126,.0005,extra_delay=1,exit_support=ex.shift(1,fill_value=False))
        b=standalone_path(t,10,126,.0005,1,ex)
        self.assertAlmostEqual(a['trades'][0]['return'],b['net_return']);self.assertEqual(a['trades'][0]['exit'],b['exit'])

if __name__=='__main__':unittest.main()
