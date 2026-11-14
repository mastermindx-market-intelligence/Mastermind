import itertools
import unittest
import numpy as np
import pandas as pd
from phase_neutral import combine,mean_accounts

class PhaseNeutralTests(unittest.TestCase):
    def fixture(self):
        ix=pd.bdate_range('2013-01-02',periods=80)
        p=[pd.DataFrame(False,index=ix,columns=['A','B']) for _ in range(3)]
        p[0].iloc[10,0]=True;p[1].iloc[12,0]=True;p[2].iloc[14,0]=True
        p[0].iloc[35,1]=True;p[2].iloc[39,1]=True
        return p
    def test_phase_label_permutation_invariance(self):
        p=self.fixture();a=combine(p)
        for perm in itertools.permutations(p):
            b=combine(perm)
            for key in a:pd.testing.assert_frame_equal(a[key],b[key])
    def test_confirmation_is_not_backdated(self):
        p=self.fixture();c=combine(p)
        self.assertTrue(c['any_phase'].iloc[10,0])
        self.assertFalse(c['two_phase'].iloc[10,0]);self.assertTrue(c['two_phase'].iloc[12,0])
        self.assertFalse(c['all_phase'].iloc[12,0]);self.assertTrue(c['all_phase'].iloc[14,0])
    def test_future_prefix_cannot_change_past(self):
        p=self.fixture();a=combine(p);b=combine([x.iloc[:13] for x in p])
        for key in a:pd.testing.assert_frame_equal(a[key].iloc[:13],b[key])
    def test_expired_phase_not_a_vote(self):
        p=self.fixture();p[1][:]=False;p[2][:]=False;p[1].iloc[17,0]=True
        c=combine(p);self.assertFalse(c['two_phase'].iloc[:,0].any())
    def test_missing_or_unbound_phase_refused(self):
        p=self.fixture()
        with self.assertRaises(ValueError):combine(p[:2])
        wrong=p.copy();wrong[1]=wrong[1].iloc[:-1]
        with self.assertRaises(ValueError):combine(wrong)
        wrong=[x.copy().astype('boolean') for x in p];wrong[0].iloc[4,0]=pd.NA
        with self.assertRaises(ValueError):combine(wrong)
    def test_phase_portfolio_mixture_identity(self):
        curves=[pd.DataFrame({'equity':[1.,1.+r],'gross':[0.,1.]}) for r in (.1,-.1,.3)]
        m,c=mean_accounts(curves)
        self.assertAlmostEqual(c.equity.iloc[-1],1.1);self.assertAlmostEqual(c.gross.iloc[-1],1.)
        self.assertAlmostEqual(m['total_return'],.1)

if __name__=='__main__':unittest.main()
