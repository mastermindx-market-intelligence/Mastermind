import unittest
import numpy as np
import pandas as pd
from credit_check import credit_features

class CreditTests(unittest.TestCase):
    def fixture(self):
        idx=pd.bdate_range('2007-01-02',periods=150)
        return pd.Series(5+.01*np.arange(150),index=idx),idx
    def test_future_credit_cannot_change_prior_signal(self):
        s,i=self.fixture();a=credit_features(s,i,2);ss=s.copy();ss.iloc[110:]=100
        b=credit_features(ss,i,2);pd.testing.assert_frame_equal(a.iloc[:112],b.iloc[:112])
    def test_two_session_lag_not_today(self):
        s,i=self.fixture();s[:]=5.;s.iloc[100:]=20
        f=credit_features(s,i,2)
        self.assertTrue(f.not_rising.iloc[101]);self.assertFalse(f.not_rising.iloc[102])
    def test_missing_credit_not_low_risk(self):
        s,i=self.fixture();s.iloc[80]=np.nan;f=credit_features(s,i,2)
        self.assertFalse(f.valid.iloc[82]);self.assertFalse(f.not_rising.iloc[82]);self.assertFalse(f.easing.iloc[82])
    def test_reserved_calendar_refused(self):
        s=pd.Series(5.,index=pd.bdate_range('2020-01-01',periods=40))
        with self.assertRaises(ValueError):credit_features(s,s.index,2)
    def test_unregistered_lag_refused(self):
        s,i=self.fixture()
        with self.assertRaises(ValueError):credit_features(s,i,0)
    def test_increasing_credit_is_not_easing(self):
        s,i=self.fixture();f=credit_features(s,i,2)
        self.assertFalse(f.easing.iloc[50:].any());self.assertFalse(f.not_rising.iloc[50:].any())

if __name__=='__main__':unittest.main()
