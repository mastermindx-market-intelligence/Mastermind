from __future__ import annotations
import unittest
import numpy as np
import pandas as pd
import evaluate as e

class ExecutionTests(unittest.TestCase):
    def data(self,n=150):
        idx=pd.bdate_range('2010-01-04',periods=n)
        total=pd.Series(100*np.exp(np.arange(n)*.001),index=idx)
        sig=pd.Series(False,index=idx);sig.iloc[5]=True
        valid=pd.Series(True,index=idx)
        return total,sig,valid
    def test_next_close_not_signal_close(self):
        t,s,v=self.data();r=e.account(t,s,v,21,0)
        self.assertEqual(r['trades'][0]['entry'],t.index[6]);self.assertEqual(r['trades'][0]['exit'],t.index[27])
        self.assertAlmostEqual(r['trades'][0]['return'],t.iloc[27]/t.iloc[6]-1)
    def test_costs_reduce_identical_path(self):
        t,s,v=self.data();a=e.account(t,s,v,21,.0005);b=e.account(t,s,v,21,.002)
        self.assertGreater(a['metrics']['total_return'],b['metrics']['total_return'])
    def test_flat_price_pays_both_costs(self):
        t,s,v=self.data();t[:]=100.;r=e.account(t,s,v,21,.001)
        self.assertAlmostEqual(r['metrics']['total_return'],.999/1.001-1)
    def test_no_signal_no_return(self):
        t,s,v=self.data();s[:]=False;r=e.account(t,s,v,21)
        self.assertEqual(r['metrics']['total_return'],0);self.assertEqual(r['metrics']['mean_exposure'],0)
    def test_no_pyramiding(self):
        t,s,v=self.data();s.iloc[5:10]=True;r=e.account(t,s,v,21,0);self.assertEqual(r['metrics']['closed_trades'],1)
    def test_unknown_entry_not_filled(self):
        t,s,v=self.data();t.iloc[6]=np.nan;r=e.account(t,s,v,21,0);self.assertEqual(r['metrics']['closed_trades'],0)
    def test_future_exit_missing_is_not_entry_filter(self):
        t,s,v=self.data();t.iloc[27]=np.nan;r=e.account(t,s,v,21,0)
        self.assertEqual(r['trades'][0]['entry'],t.index[6]);self.assertEqual(r['trades'][0]['exit'],t.index[28]);self.assertEqual(r['metrics']['stale_mark_sessions'],1)
    def test_extra_delay_is_applied(self):
        t,s,v=self.data();r=e.account(t,s,v,21,0,extra_delay=2);self.assertEqual(r['trades'][0]['entry'],t.index[8])
    def test_scale_reduces_initial_allocation(self):
        t,s,v=self.data();r=e.account(t,s,v,21,0,scale=.4);self.assertAlmostEqual(r['curve'].gross.iloc[6],.4)
    def test_inconsistent_clock_refused(self):
        t,s,v=self.data()
        with self.assertRaises(ValueError):e.account(t,s.iloc[1:],v,21)
    def test_unsupported_family_refused(self):
        with self.assertRaises(ValueError):e.fixed_policies(pd.DataFrame(),'invented')
    def test_outcome_censoring_not_failure(self):
        t,s,v=self.data();p=pd.DataFrame({'A':t,'B':t,'C':t})
        out=e.outcome(p,p,p.index,'A',['A','B','C'],140,21)
        self.assertEqual(out['outcome_status'],'NOT_MATURED');self.assertNotIn('low_held',out)
    def test_reference_low_and_reward_are_different(self):
        t,s,v=self.data();t[:]=100.;t.iloc[70:]=101.;p=pd.DataFrame({'A':t,'B':t,'C':t})
        out=e.outcome(p,p,p.index,'A',['A','B','C'],80,21)
        self.assertEqual(out['low_held'],1);self.assertEqual(out['positive_net'],0)
    def test_missing_future_peer_not_replaced(self):
        t,s,v=self.data();p=pd.DataFrame({'A':t,'B':t,'C':t});p.loc[p.index[102],'B']=np.nan
        out=e.outcome(p,p,p.index,'A',['A','B','C'],80,21)
        self.assertTrue(np.isnan(out['peer_excess']))

if __name__=='__main__':unittest.main()
