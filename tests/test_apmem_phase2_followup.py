import unittest
import numpy as np
import pandas as pd
from research.apmem_shadow.phase2.followup import scale_calibrate,open_interval_labels,execution_quantiles,options_ablation
from research.apmem_shadow.phase2.forecasts import Settings
from research.apmem_shadow.phase2.targets import prepare_prices


class FollowupTests(unittest.TestCase):
    def test_scalar_calibration_recovers_constant_scale(self):
        out=scale_calibrate(np.full(100,4.),np.ones(100),5,window=20,minimum=10)
        np.testing.assert_allclose(out[20:],4)
    def test_scalar_no_unmatured_label(self):
        y=np.linspace(1,2,100);f=np.ones(100)
        a=scale_calibrate(y,f,20,window=20,minimum=10)
        b=scale_calibrate(y[:70],f[:70],20,window=20,minimum=10)
        np.testing.assert_allclose(a[:70],b,equal_nan=True)
    def test_open_clock_labels(self):
        p=pd.DataFrame({'open':[100,110,121,133.1],'distributions':[0,0,0,0]})
        np.testing.assert_allclose(open_interval_labels(p),[np.log(1.1),np.log(1.1),np.nan,np.nan],equal_nan=True)
    def test_open_clock_dividend_owner(self):
        p=pd.DataFrame({'open':[100,100,100,100],'distributions':[0,50,10,0]})
        np.testing.assert_allclose(open_interval_labels(p),[np.log(1.1),0,np.nan,np.nan],equal_nan=True)
    def test_future_open_not_in_calibration(self):
        rng=np.random.default_rng(15);o=100*np.exp(np.cumsum(rng.normal(0,.02,100)))
        p=pd.DataFrame({'open':o,'distributions':np.zeros(100)})
        _,a,_=execution_quantiles(p,np.full(100,.0004),.05,window=30,minimum=20)
        change=p.copy();change.loc[70:,'open']*=.01
        _,b,_=execution_quantiles(change,np.full(100,.0004),.05,window=30,minimum=20)
        np.testing.assert_allclose(a[:70],b[:70],equal_nan=True)
        self.assertNotEqual(a[70],b[70])
    def test_lag2_missing_case_does_not_fill(self):
        from unittest.mock import patch
        n=130;idx=pd.bdate_range('2010-01-01',periods=n);c=100*np.exp(np.arange(n)*.001)
        raw=pd.DataFrame({'open':c,'high':c+1,'low':c-1,'close':c,'dividends':0.,'stock_splits':0.},index=idx)
        p=prepare_prices(raw);o=pd.DataFrame({'iv30':.2,'net_gex_bn':2.,'root':'QQQ'},index=p.index)
        o=o.drop(o.index[90]);original={k:np.ones((len(p),3)) for k in ('apmem','har_extended','har_options','equal_blend')}
        seen=[]
        def fake(features,v,h,config):
            seen.append(features.copy());return np.ones(len(v)),[]
        with patch('research.apmem_shadow.phase2.followup.direct_har',side_effect=fake):
            options_ablation(p,o,'QQQ',original,Settings(minimum=64,window=100))
        self.assertTrue(np.isnan(seen[6][92,-2]));self.assertTrue(np.isnan(seen[0][91,-1]))


if __name__=='__main__':unittest.main()
