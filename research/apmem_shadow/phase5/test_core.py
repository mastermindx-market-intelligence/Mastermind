import unittest
import numpy as np
import pandas as pd
import test_experiment as fixtures
from core_complement import settle,target_weights,core_account,mixture

class CoreTests(unittest.TestCase):
    def test_buy_cost_funded(self):
        val,cash,fee=settle(np.zeros(3),1.,np.ones(3)/3,.001)
        self.assertAlmostEqual(val.sum(),1/1.001,places=12);self.assertAlmostEqual(cash,0.,places=12)
        self.assertAlmostEqual(fee,1-1/1.001,places=12)
    def test_exit_cost_funded(self):
        val,cash,fee=settle(np.array([.2,.3]),.5,np.zeros(2),.002)
        self.assertEqual(val.sum(),0);self.assertAlmostEqual(cash,.999);self.assertAlmostEqual(fee,.001)
    def test_refuse_leverage_and_nan(self):
        for w in [np.array([.8,.8]),np.array([np.nan,.2]),np.array([-.1,.5])]:
            with self.assertRaises(ValueError):settle(np.zeros(2),1,w,.001)
    def test_target_prefix_invariance(self):
        p,t,v=fixtures.MechanicsTests().panel()
        for kind in ['top3','top3_trend','top3_trend_risk','equal_trend']:
            a=target_weights(p,t,kind);b=target_weights(p.iloc[:650],t.iloc[:650],kind)
            pd.testing.assert_frame_equal(a.iloc[:650],b)
            self.assertLessEqual(a.sum(axis=1).max(),1.0000000001)
    def test_core_next_close_execution(self):
        p,t,v=fixtures.MechanicsTests().panel(200);t[:]=100.;t.iloc[21:]=200.
        w=pd.DataFrame(1/9,index=t.index,columns=t.columns[:-1]);valid=np.arange(len(t))>=20
        m,c,r=core_account(t,w,valid,0)
        self.assertAlmostEqual(m['total_return'],0.,places=12)
        self.assertEqual(r[0]['executed'],str(t.index[21].date()))
    def test_cash_mixture_identity(self):
        a=pd.DataFrame({'equity':[1.,2.,1.5],'gross':[0.,1.,1.]})
        m,c=mixture(a)
        np.testing.assert_allclose(c.equity,[1.,1.5,1.25]);self.assertAlmostEqual(c.gross.iloc[-1],.6)
    def test_mixture_wrong_clock_refused(self):
        a=pd.DataFrame({'equity':[1.,1.1],'gross':[0.,1.]})
        b=a.copy();b.index=[2,3]
        with self.assertRaises(ValueError):mixture(a,b)
    def test_nonfinite_cash_refused(self):
        for cash in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):settle(np.zeros(2),cash,np.array([.5,.5]),.001)
    def test_zero_fee_balance(self):
        val,cash,fee=settle(np.array([.7,.3]),.2,np.array([.25,.25]),0)
        self.assertAlmostEqual(val.sum()+cash,1.2);self.assertEqual(fee,0.)

if __name__=='__main__':unittest.main()
