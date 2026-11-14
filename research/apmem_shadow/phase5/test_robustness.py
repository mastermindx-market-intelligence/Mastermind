import unittest
import numpy as np
import pandas as pd
import experiment as ex
from analyze import block_mean_interval,holm
from robustness import static_match,extended_context
import test_experiment as fixtures

class FollowupTests(unittest.TestCase):
    def test_null_block_bootstrap(self):
        m,ci,p=block_mean_interval(np.zeros(200));self.assertEqual(m,0);self.assertEqual(ci,[0,0]);self.assertEqual(p,1)
    def test_holm_adjustment(self):
        np.testing.assert_allclose(holm([.01,.03,.04]),[.03,.06,.06])
    def test_static_match_cash_identity(self):
        c=pd.DataFrame({'equity':np.ones(100),'gross':np.ones(100)*.5})
        a,m,eq,g=static_match(c,.25);self.assertAlmostEqual(a,.5);self.assertAlmostEqual(m['mean_exposure'],.25)
    def test_loo_not_changed_by_focal(self):
        p,t,v=fixtures.MechanicsTests().panel();c=ex.context(p,t,v);a=extended_context(p,t,c)
        p2=p.copy();t2=t.copy();p2.XLK=p2.XLK*1.2;t2.XLK=t2.XLK*(1+np.arange(len(t))*.0001)
        b=extended_context(p2,t2,ex.context(p2,t2,v))
        pd.testing.assert_series_equal(a['loo_repair'].XLK,b['loo_repair'].XLK)
        pd.testing.assert_series_equal(a['loo_stress'].XLK,b['loo_stress'].XLK)
    def test_support_context_prefix_invariance(self):
        p,t,v=fixtures.MechanicsTests().panel();a=extended_context(p,t,ex.context(p,t,v))
        b=extended_context(p.iloc[:650],t.iloc[:650],ex.context(p.iloc[:650],t.iloc[:650],v.iloc[:650]))
        for k in a:
            if isinstance(a[k],pd.DataFrame):pd.testing.assert_frame_equal(a[k].iloc[:650],b[k])
            else:pd.testing.assert_series_equal(a[k].iloc[:650],b[k])
    def test_ongoing_exit_uses_next_close(self):
        p,t,v=fixtures.MechanicsTests().panel(100);t[:]=100.
        s=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);s.iloc[10,0]=True
        x=pd.Series(False,index=p.index);x.iloc[15]=True
        a=ex.account(t,s,np.ones(100,bool),21,0,exit_condition=x)
        self.assertEqual(a['trades'][0]['exit'],str(p.index[16].date()))
    def test_ongoing_empty_matches_original(self):
        p,t,v=fixtures.MechanicsTests().panel(100);s=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);s.iloc[10]=True
        a=ex.account(t,s,np.ones(100,bool),21,.0005)
        b=ex.account(t,s,np.ones(100,bool),21,.0005,exit_condition=pd.Series(False,index=p.index))
        pd.testing.assert_frame_equal(a['curve'],b['curve'])
    def test_exit_wrong_calendar_refused(self):
        p,t,v=fixtures.MechanicsTests().panel(100);s=pd.DataFrame(False,index=p.index,columns=ex.SECTORS)
        with self.assertRaises(ValueError):ex.account(t,s,np.ones(100,bool),21,exit_condition=pd.Series(False,index=p.index[:-1]))

if __name__=='__main__':unittest.main()
