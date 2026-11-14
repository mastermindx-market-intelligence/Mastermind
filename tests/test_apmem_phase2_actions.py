import unittest
import numpy as np
import pandas as pd
from research.apmem_shadow.phase2.corporate_actions import qualify_constant_share_units, SPLIT_DATE
from research.apmem_shadow.phase2.targets import prepare_prices


def fixture():
    dates = pd.bdate_range("2023-01-01", "2026-11-12")
    n=len(dates)
    close=100+np.arange(n)*.01
    p=pd.DataFrame({"open":close,"high":close+1,"low":close-1,"close":close,
                    "dividends":0.,"stock_splits":0.,"capital_gains":0.},index=dates)
    p.loc[SPLIT_DATE,"stock_splits"]=2.
    div=p.columns.get_loc("dividends")
    for i in (50,150,250,350,450,550,650,750):p.iloc[i,div]=.1
    factor=np.ones(n)
    for i in range(1,n):factor[i]=factor[i-1]/(1-p.dividends.iloc[i]/p.close.iloc[i-1])
    p["adj_close"]=p.close*factor
    raw=p[["open","high","low","close"]].copy()
    raw.loc[raw.index<SPLIT_DATE]*=2
    return p,raw


class CorporateActionTests(unittest.TestCase):
    def test_admits_without_rewriting_prices(self):
        p,r=fixture();out,rec=qualify_constant_share_units("XLB",p,r)
        pd.testing.assert_frame_equal(out[p.columns.drop("stock_splits")],p[p.columns.drop("stock_splits")])
        self.assertEqual(out.source_stock_splits.sum(),2);self.assertEqual(out.stock_splits.sum(),0)
        self.assertFalse(rec["prices_modified"]);prepare_prices(out)
    def test_original_not_mutated(self):
        p,r=fixture();old=p.copy();qualify_constant_share_units("XLB",p,r)
        pd.testing.assert_frame_equal(p,old)
    def test_xlf_refused(self):
        p,r=fixture()
        with self.assertRaises(ValueError):qualify_constant_share_units("XLF",p,r)
    def test_extra_event_refused(self):
        p,r=fixture();p.iloc[40,p.columns.get_loc("stock_splits")]=2
        with self.assertRaises(ValueError):qualify_constant_share_units("XLB",p,r)
    def test_unadjusted_source_refused(self):
        p,r=fixture();p[["open","high","low","close"]]=r
        with self.assertRaises(ValueError):qualify_constant_share_units("XLB",p,r)
    def test_double_adjustment_refused(self):
        p,r=fixture();p.loc[p.index<SPLIT_DATE,["open","high","low","close"]]*=.5
        with self.assertRaises(ValueError):qualify_constant_share_units("XLB",p,r)
    def test_distribution_mismatch_refused(self):
        p,r=fixture();p["dividends"]*=2
        with self.assertRaises(ValueError):qualify_constant_share_units("XLB",p,r)
    def test_sparse_reference_refused(self):
        p,r=fixture()
        with self.assertRaises(ValueError):qualify_constant_share_units("XLB",p,r.iloc[-40:])
    def test_constant_share_scale_invariance(self):
        p,r=fixture();q,_=qualify_constant_share_units("XLB",p,r)
        a=prepare_prices(q)
        z=q.copy();z[["open","high","low","close","dividends","capital_gains"]]*=3
        b=prepare_prices(z)
        for col in ("variance","return_log","range_var","gap_var","total_index"):
            np.testing.assert_allclose(a[col],b[col],atol=1e-12)


if __name__=="__main__":unittest.main()
