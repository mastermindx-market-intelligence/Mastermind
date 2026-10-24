import unittest
import numpy as np,pandas as pd
from event_study import make_rows,clock,BASE,NEW

def fixture(n=100,step=2_000_000_000):
 t=np.arange(n,dtype=np.uint64)*np.uint64(step)+np.uint64(clock('10:00'))
 return pd.DataFrame({'ticker':'AAPL','sale_flags':0,'send_ns':t,'sequence':np.arange(n,dtype=np.uint64)+1,'price_1e4':np.asarray([1000000+(i%7)*100 for i in range(n)],dtype=np.uint64),'size':100,'order_id':np.asarray([2**60+i//3 for i in range(n)],dtype=np.uint64)})
class TestStudy(unittest.TestCase):
 def test_future_orders_cannot_change_past(self):
  x=fixture();a,_=make_rows(x.iloc[:60],labels=False);b,_=make_rows(x,labels=False)
  np.testing.assert_array_equal(a[BASE+NEW],b[b.decision_ns<=int(x.send_ns.iloc[59])][BASE+NEW])
 def test_large_order_ids_not_rounded(self):
  x=fixture();r,_=make_rows(x,labels=False);self.assertTrue((r.seen_fraction>0).all());self.assertTrue((r.hhi<.25).all())
 def test_future_horizon_and_embargo(self):
  x=fixture();r,_=make_rows(x);self.assertTrue((r.label_end_ns>r.decision_ns).all());self.assertTrue((r.horizon_seconds>=1).all())
 def test_same_class_not_dropped(self):
  x=fixture();x.price_1e4=1000000;r,_=make_rows(x);self.assertTrue((r['class']==1).all());self.assertGreater(len(r),0)
 def test_missing_suffix_is_not_flat(self):
  x=fixture(25);r,c=make_rows(x);self.assertTrue(r.empty);self.assertEqual(c['AAPL']['future_unavailable'],5)
 def test_sparse_outcome_censored(self):
  x=fixture(60,step=300_000_000_000);r,c=make_rows(x);self.assertTrue(r.empty);self.assertGreater(c['AAPL']['future_unavailable'],0)
 def test_unsupported_flags_filtered(self):
  x=fixture();x.sale_flags=128;r,c=make_rows(x);self.assertTrue(r.empty);self.assertEqual(c['AAPL']['eligible_executions'],0)
if __name__=='__main__':unittest.main(verbosity=2)
