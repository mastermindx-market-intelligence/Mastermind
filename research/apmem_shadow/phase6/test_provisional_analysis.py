import json,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from native_replay import load_math
from provisional import scheduled_end,nowcast,settle_label
from analyze_results import combine_curves,mean_exposure_match

class AnalysisIdentityTests(unittest.TestCase):
    def test_wealth_weighted_exposure(self):
        a=pd.DataFrame({'equity':[1.,2.],'gross':[0.,1.]});b=pd.DataFrame({'equity':[1.,1.],'gross':[0.,0.]})
        x=combine_curves([a,b]);self.assertAlmostEqual(x.equity.iloc[-1],1.5);self.assertAlmostEqual(x.gross.iloc[-1],2/3)
    def test_wrong_clocks_refused(self):
        a=pd.DataFrame({'equity':[1.,2.],'gross':[0.,1.]});b=a.copy();b.index=[1,2]
        with self.assertRaises(ValueError):combine_curves([a,b])
    def test_exposure_match_no_implicit_leverage(self):
        a=pd.DataFrame({'equity':[1.,2.],'gross':[1.,1.]});b=pd.DataFrame({'equity':[1.,1.5],'gross':[.4,.4]})
        self.assertIsNone(mean_exposure_match(a,b))
    def test_exposure_match_respects_target(self):
        a=pd.DataFrame({'equity':[1.,1.1,1.3],'gross':[0.,.2,.3]});b=pd.DataFrame({'equity':[1.,1.3,1.5],'gross':[0.,.7,.8]})
        m=mean_exposure_match(a,b);self.assertAlmostEqual(m['mean_exposure'],a.gross.mean(),places=10)
    def test_schedule_month_is_not_observed_close(self):
        self.assertEqual(scheduled_end('2019-08-29','1M'),pd.Timestamp('2019-08-31'))
    def test_fixed_two_week_schedule_prefix_independent(self):
        for date in ['2019-01-01','2019-01-04','2019-01-08']:
            self.assertGreaterEqual(scheduled_end(date,'2W'),pd.Timestamp(date))

class NativeProvisionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).parent
        if not (root/'INPUT_MANIFEST.json').exists():raise unittest.SkipTest('Private source fixture unavailable')
        m=json.loads((root/'INPUT_MANIFEST.json').read_text());cls.c,_=load_math(root/'source',m)
        rng=np.random.default_rng(81)
        cls.close=pd.Series(100*np.exp(np.cumsum(rng.normal(0,.01,1500))),index=pd.bdate_range('2010-01-04',periods=1500))
    def test_current_prefix_only(self):
        p=self.close.copy();at=p.index[1200]
        a=nowcast(p,self.c,at);p.iloc[1201:]*=1000;b=nowcast(p,self.c,at)
        self.assertEqual(a,b)
    def test_nowcast_keeps_future_period_end(self):
        p=self.close;at=p.index[1201];r=nowcast(p,self.c,at)
        self.assertEqual(r['observed_at'],at);self.assertEqual(r['provisional'],r['scheduled_period_end']>at)
    def test_unobserved_session_refused(self):
        with self.assertRaises(ValueError):nowcast(self.close,self.c,'2015-12-27')
    def test_survival_requires_future_maturity(self):
        p=self.close.iloc[:1201];r=nowcast(p,self.c,p.index[-1],'1M')
        if r['provisional']:self.assertEqual(settle_label(p,self.c,r,'1M')['settlement_status'],'NOT_MATURED')
    def test_completed_value_equals_settlement(self):
        p=self.close;at=p.index[1200];r=nowcast(p,self.c,at,'1M');settled=settle_label(p,self.c,r,'1M')
        self.assertEqual(settled['settlement_status'],'COMPLETE');self.assertGreaterEqual(settled['settlement_known_at'],r['scheduled_period_end'])

if __name__=='__main__':unittest.main()
