"""Numerical chronology tests on synthetic prices, without private market data."""
from __future__ import annotations
import unittest
import numpy as np
import pandas as pd
from research.apmem_shadow.phase2.forecasts import Settings
from research.apmem_shadow.phase3 import data, risk


class ForecastChronologyTests(unittest.TestCase):
    def panel(self,n=210):
        rng=np.random.default_rng(183)
        c=100*np.exp(np.cumsum(rng.normal(0,.01,n)))
        o=np.r_[c[0],c[:-1]]*np.exp(rng.normal(0,.002,n))
        p=pd.DataFrame({'open':o,'high':np.maximum(o,c)*1.003,'low':np.minimum(o,c)*.997,
                        'close':c,'volume':1e6,'dividend':0.,'split':1.},
                       index=pd.bdate_range('2020-01-01',periods=n))
        return data.prepare_prices(p)

    def test_future_data_cannot_change_prior_forecasts(self):
        p=self.panel();cfg=Settings(minimum=64,window=128,apmem_refit=63)
        a,receipt=risk.forecasts(p.iloc[:150],cfg)
        p.loc[p.index[155]:,'variance']*=15
        p.loc[p.index[155]:,'return_log']=-.1
        b,_=risk.forecasts(p,cfg)
        cols=[c for c in a if not c.startswith('future_')]
        np.testing.assert_allclose(a[cols],b.loc[a.index,cols],rtol=1e-12,atol=1e-14,equal_nan=True)
        self.assertTrue(receipt['initial_unobserved_gap_row_excluded'])
        for fit in receipt['fits']:
            self.assertEqual(fit['origin_session'],fit['train_end_session'])

    def test_future_target_not_feature(self):
        p=self.panel();ix=p.index
        f=pd.DataFrame({'mem_h1':.0001,'mem_h5':.0002,'mem_h20':.0003,'ewma_h5':.0002,
                        'future_variance_h5':999.},index=ix)
        a=risk.features(p,f,p)
        self.assertEqual(float(a.relative_momentum.dropna().iloc[-1]),0.)
        self.assertAlmostEqual(a.stop_noise5.iloc[-1],.05/np.sqrt(.001))
        for cols in risk.FEATURE_GROUPS.values():
            self.assertNotIn('future_variance_h5',cols)

    def test_forecast_instrument_date_mismatch_rejected(self):
        p=self.panel();f=pd.DataFrame(index=p.index[:-1])
        with self.assertRaises(ValueError):risk.features(p,f,p)


if __name__=='__main__':unittest.main()
