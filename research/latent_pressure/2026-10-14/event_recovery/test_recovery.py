import unittest,json
from pathlib import Path
from book_recovery import Event,RecoveryBook,decode_iex_book_event

def event(n,t,k,oid=1,side=1,price=100,qty=0):return Event(n,t,k,oid,side,price,qty)
class TestRecovery(unittest.TestCase):
 def setup_book(self):
  b=RecoveryBook(horizon_ns=10,shock_fraction=.5);b.apply(event(1,0,'ADD',qty=10));b.apply(event(2,1,'EXECUTE',qty=5));return b
 def test_pending_is_not_future_recovery(self):
  b=self.setup_book();s=b.snapshot(5);self.assertEqual(s['sides']['bid']['elapsed_ns'],4);self.assertIsNone(s['sides']['bid']['median_completed_recovery_ns'])
  b.apply(event(3,8,'ADD',oid=2,qty=5));self.assertEqual(b.snapshot(8)['sides']['bid']['median_completed_recovery_ns'],7)
 def test_prefix_exact(self):
  a=self.setup_book();first=a.snapshot(5);a.apply(event(3,8,'ADD',oid=2,qty=5));b=self.setup_book();self.assertEqual(first,b.snapshot(5))
 def test_no_historical_query_on_future_state(self):
  b=self.setup_book();b.apply(event(3,8,'ADD',oid=2,qty=5));self.assertRaises(ValueError,b.snapshot,5)
 def test_cancel_depletes_not_trade_break(self):
  b=self.setup_book();b.apply(event(3,3,'DELETE'));self.assertEqual(b.history[-1].state,'LEVEL_DEPLETED');self.assertIsNone(b.snapshot(3)['forecast_probability'])
 def test_censored(self):
  b=self.setup_book();s=b.snapshot(12);self.assertEqual(s['sides']['bid']['right_censored'],1);self.assertIsNone(s['sides']['bid']['median_completed_recovery_ns'])
 def test_inclusive_deadline(self):
  b=self.setup_book();b.apply(event(3,11,'ADD',oid=2,qty=5));self.assertEqual(b.history[-1].state,'RECOVERED')
 def test_after_deadline(self):
  b=self.setup_book();b.apply(event(3,12,'ADD',oid=2,qty=5));self.assertEqual(b.history[-1].state,'HORIZON_ENDED_UNRECOVERED')
 def test_no_phantom_decrement(self):
  b=self.setup_book();self.assertEqual(b.depth(1,100),5);b.apply(event(3,2,'EXECUTE',qty=2));self.assertEqual(b.depth(1,100),3)
 def test_unknown_order(self):self.assertRaises(ValueError,self.setup_book().apply,event(3,2,'DELETE',oid=55))
 def test_overfill_atomic(self):
  b=self.setup_book();before=b.snapshot(2);self.assertRaises(ValueError,b.apply,event(3,2,'EXECUTE',qty=6));self.assertEqual(before,b.snapshot(2))
 def test_side_separation(self):
  b=self.setup_book();b.apply(event(3,2,'ADD',oid=3,side=-1,price=101,qty=10));b.apply(event(4,3,'EXECUTE',oid=3,side=-1,price=101,qty=5));self.assertEqual(set(b.pending),{1,-1})
 def test_reprice(self):
  b=self.setup_book();b.apply(event(3,2,'MODIFY',price=99,qty=5));self.assertEqual(b.history[-1].state,'LEVEL_DEPLETED');self.assertEqual(b.best(1),99)
 def test_gap_invalidates(self):
  b=self.setup_book();b.invalidate();self.assertFalse(b.snapshot(2)['source_integrity']);self.assertRaises(ValueError,b.apply,event(3,3,'ADD',oid=3,qty=5))
 def test_real_adapter_fail_closed(self):self.assertRaises(NotImplementedError,decode_iex_book_event,b'actual bytes')
 def test_already_broken_not_predictable(self):
  b=RecoveryBook();b.apply(event(1,0,'ADD',qty=5));b.apply(event(2,1,'EXECUTE',qty=5));self.assertFalse(b.pending);self.assertEqual(b.skipped_immediate_depletions,1)
 def test_sequence_backward(self):self.assertRaises(ValueError,self.setup_book().apply,event(1,3,'ADD',oid=3,qty=3))
 def test_snapshot_does_not_mutate(self):
  b=self.setup_book();b.snapshot(12);self.assertTrue(b.pending);self.assertFalse(b.history)
 def test_exact_integers(self):self.assertRaises(ValueError,RecoveryBook().apply,Event(1,2.1,'ADD',1,1,100,10))
if __name__=='__main__':unittest.main(verbosity=2)
