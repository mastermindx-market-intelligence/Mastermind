"""Source/calendar guards around reuse of existing forecasts."""
import unittest
import numpy as np
import pandas as pd
from research.apmem_shadow.phase3.data import prepare_prices
from research.apmem_shadow.phase3.run_etf_transfer import adapt_inputs

class EtfReuseTests(unittest.TestCase):
    def inputs(self):
        ix=pd.bdate_range('2020-01-01',periods=80)
        raw=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':1e6,
                          'dividends':0.,'capital_gains':0.,'stock_splits':0.},index=ix)
        p=raw[['open','high','low','close','volume']].copy();p['dividend']=0.;p['split']=1.
        prepared=prepare_prices(p).iloc[1:]
        saved={'mem_delta1':np.ones((79,3))*.0002,'ewma94':np.ones((79,3))*.0003}
        return raw,prepared,saved
    def test_exact_dates_and_values_reused(self):
        raw,p,s=self.inputs();out,f=adapt_inputs(raw,p,s)
        self.assertEqual(len(out),80);self.assertTrue(np.isnan(f.mem_h1.iloc[0]))
        np.testing.assert_array_equal(f.mem_h5.iloc[1:],s['mem_delta1'][:,1])
    def test_no_double_split(self):
        raw,p,s=self.inputs();raw.loc[raw.index[10],'stock_splits']=2
        with self.assertRaises(ValueError):adapt_inputs(raw,p,s)
    def test_wrong_target_refused(self):
        raw,p,s=self.inputs();p=p.copy();p['variance']*=2
        with self.assertRaises(ValueError):adapt_inputs(raw,p,s)
    def test_wrong_calendar_refused(self):
        raw,p,s=self.inputs();p=p.copy();p.index=p.index+pd.Timedelta(days=1)
        with self.assertRaises(ValueError):adapt_inputs(raw,p,s)
    def test_wrong_shape_refused(self):
        raw,p,s=self.inputs();s['mem_delta1']=np.ones((80,3))
        with self.assertRaises(ValueError):adapt_inputs(raw,p,s)

if __name__=='__main__':unittest.main()
