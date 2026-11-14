import unittest
import numpy as np
import pandas as pd
import experiment as ex
import test_experiment as fixtures
from phase_selection import selection_weights,market_account

class PhaseSelectionTests(unittest.TestCase):
    def test_rank_prefix_invariant(self):
        p,t,v=fixtures.MechanicsTests().panel()
        a=selection_weights(t);b=selection_weights(t.iloc[:650])
        for key in a:pd.testing.assert_frame_equal(a[key].iloc[:650],b[key])
    def test_nonoverlap_of_leaders_and_laggards(self):
        p,t,v=fixtures.MechanicsTests().panel();w=selection_weights(t)
        self.assertFalse(((w['leaders_equal']>0)&(w['laggards_equal']>0)).to_numpy().any())
        self.assertTrue((w['all_equal'].iloc[126:].sum(axis=1)-1).abs().max()<1e-12)
    def test_no_same_close_fill(self):
        p,t,v=fixtures.MechanicsTests().panel(200);t[:]=100.;t.iloc[11:]=200.
        s=pd.Series(False,index=t.index);s.iloc[10]=True;w=pd.DataFrame(1/9,index=t.index,columns=ex.SECTORS)
        m,c,r=market_account(t,s,w,np.ones(len(t),bool),21,0)
        self.assertAlmostEqual(m['total_return'],0.);self.assertEqual(r[0]['entry'],str(t.index[11].date()))
    def test_scalar_roundtrip_fee_and_return(self):
        p,t,v=fixtures.MechanicsTests().panel(200);t[:]=100.;t.iloc[12:,0]=110.
        s=pd.Series(False,index=t.index);s.iloc[10]=True;w=pd.DataFrame(0.,index=t.index,columns=ex.SECTORS);w.iloc[:,0]=1.
        m,c,r=market_account(t,s,w,np.ones(len(t),bool),21,.0005)
        self.assertAlmostEqual(1+m['total_return'],1.1*.9995/1.0005,places=12)
    def test_partial_risk_cash_and_no_overlap(self):
        p,t,v=fixtures.MechanicsTests().panel(200);t[:]=100.
        s=pd.Series(True,index=t.index);w=pd.DataFrame(.5/9,index=t.index,columns=ex.SECTORS)
        m,c,r=market_account(t,s,w,np.ones(len(t),bool),21,0)
        self.assertAlmostEqual(m['total_return'],0.,places=12);self.assertLessEqual(c.gross.max(),.500000001)
        self.assertLessEqual(len(r),9)
    def test_mismatched_observation_refused(self):
        p,t,v=fixtures.MechanicsTests().panel(200);s=pd.Series(False,index=t.index[:-1]);w=pd.DataFrame(0.,index=t.index,columns=ex.SECTORS)
        with self.assertRaises(ValueError):market_account(t,s,w,np.ones(len(t),bool),21,.0005)

if __name__=='__main__':unittest.main()
