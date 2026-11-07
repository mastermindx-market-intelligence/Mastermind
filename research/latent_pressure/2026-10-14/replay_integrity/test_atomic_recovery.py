"""Constructed normalized events; no exchange-specific grouping is inferred."""
import copy
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import random
import sys
import unittest

FILE = Path(__file__).resolve().parents[1] / 'event_recovery' / 'book_recovery.py'
spec = importlib.util.spec_from_file_location('atomic_recovery_subject', FILE)
m = importlib.util.module_from_spec(spec);sys.modules[spec.name] = m;spec.loader.exec_module(m)
Event, RecoveryBook = m.Event, m.RecoveryBook

class AtomicRecovery(unittest.TestCase):
    def base(self):
        b=RecoveryBook(horizon_ns=20)
        b.apply(Event(1,1,'ADD',1,1,100,100))
        b.apply(Event(2,2,'EXECUTE',1,1,100,60))
        return b

    def test_atomic_delete_readd_never_publishes_intermediate_depletion(self):
        b=self.base()
        b.apply_batch([Event(3,4,'DELETE',1,1,100,0),Event(4,5,'ADD',2,1,100,100)],available_ns=6)
        self.assertEqual([x.state for x in b.history],['RECOVERED'])
        self.assertEqual(b.history[0].completed_ns,6)
        self.assertEqual(b.history[0].completion_sequence,4)
        self.assertEqual(b.depth(1,100),100)

    def test_serial_delete_readd_remains_two_observations(self):
        b=self.base();b.apply(Event(3,5,'DELETE',1,1,100,0));b.apply(Event(4,5,'ADD',2,1,100,100))
        self.assertEqual([x.state for x in b.history],['LEVEL_DEPLETED'])

    def test_invalid_tail_rolls_back_everything(self):
        b=self.base();before=copy.deepcopy(b.__dict__)
        with self.assertRaises(ValueError):
            b.apply_batch([Event(3,4,'ADD',2,1,100,60),Event(4,5,'DELETE',999,1,100,0)],available_ns=6)
        self.assertEqual(b.__dict__,before)

    def test_partial_batch_cannot_expire_old_response(self):
        b=self.base();before=copy.deepcopy(b.__dict__)
        with self.assertRaises(ValueError): b.apply_batch([Event(3,50,'EXECUTE',1,1,100,1000)],available_ns=50)
        self.assertEqual(b.__dict__,before)

    def test_batch_effect_known_only_after_complete_receipt(self):
        b=self.base();b.apply_batch([Event(3,4,'ADD',2,1,100,60)],available_ns=9)
        self.assertEqual(b.history[0].completed_ns,9)
        self.assertEqual(b.time,9)
        with self.assertRaises(ValueError): b.snapshot(5)

    def test_same_batch_recovery_does_not_create_a_forecast(self):
        b=RecoveryBook();b.apply(Event(1,1,'ADD',1,1,100,100))
        b.apply_batch([Event(2,2,'EXECUTE',1,1,100,60),Event(3,3,'ADD',2,1,100,60)],available_ns=4)
        self.assertFalse(b.pending);self.assertFalse(b.history)
        self.assertEqual(b.same_batch_resolved_shocks,1)

    def test_batch_aggregates_small_consumptions_at_initial_best(self):
        b=RecoveryBook();b.apply(Event(1,1,'ADD',1,1,100,100))
        b.apply_batch([Event(2,2,'EXECUTE',1,1,100,30),Event(3,3,'EXECUTE',1,1,100,30)],available_ns=4)
        self.assertEqual(b.pending[1].shock_quantity,60)
        self.assertEqual(b.pending[1].initial_remaining,40)
        self.assertEqual(b.pending[1].start_ns,4)

    def test_total_depletion_is_already_observed_not_predicted(self):
        b=RecoveryBook();b.apply(Event(1,1,'ADD',1,1,100,100))
        b.apply_batch([Event(2,2,'EXECUTE',1,1,100,100)],available_ns=3)
        self.assertFalse(b.pending);self.assertEqual(b.skipped_immediate_depletions,1)

    def test_recovery_after_deadline_stays_censored(self):
        b=self.base();b.apply_batch([Event(3,21,'ADD',2,1,100,60)],available_ns=23)
        self.assertEqual(b.history[0].state,'HORIZON_ENDED_UNRECOVERED')
        self.assertEqual(b.history[0].completed_ns,22)
        self.assertEqual(b.history[0].outcome_observed_ns,23)

    def test_recovery_at_inclusive_deadline(self):
        b=self.base();b.apply_batch([Event(3,21,'ADD',2,1,100,60)],available_ns=22)
        self.assertEqual(b.history[0].state,'RECOVERED')

    def test_received_after_commit_refused(self):
        b=self.base()
        with self.assertRaises(ValueError): b.apply_batch([Event(3,10,'ADD',2,1,100,1)],available_ns=9)

    def test_negative_or_boolean_identity_refused(self):
        for oid in [0,-1,True,2**64]:
            with self.assertRaises(ValueError): RecoveryBook().apply(Event(1,1,'ADD',oid,1,100,10))

    def test_bad_horizon_types_refused(self):
        for h in [True,1.5,0,-1,float('inf')]:
            with self.assertRaises(ValueError):RecoveryBook(horizon_ns=h)

    def test_bad_fraction_refused(self):
        for f in [True,0,-1,1.01,float('nan'),float('inf'),'half']:
            with self.assertRaises(ValueError):RecoveryBook(shock_fraction=f)

    def test_backward_within_batch_refused_atomically(self):
        b=self.base();before=copy.deepcopy(b.__dict__)
        with self.assertRaises(ValueError):b.apply_batch([Event(3,5,'ADD',2,1,100,1),Event(4,4,'ADD',3,1,100,1)],available_ns=6)
        self.assertEqual(b.__dict__,before)

    def test_json_nested_clocks_lossless(self):
        n=2**60;b=RecoveryBook();b.apply(Event(n,n,'ADD',n,1,100,100));b.apply(Event(n+1,n+1,'EXECUTE',n,1,100,60))
        s=json.loads(json.dumps(b.snapshot(n+2)))['sides']['bid']['pending']
        self.assertEqual(s['start_ns'],str(n+1));self.assertEqual(s['start_sequence'],str(n+1))

    def test_fraction_threshold_exact_for_large_quantities(self):
        q=2**60+1;b=RecoveryBook(shock_fraction=.5);b.apply(Event(1,1,'ADD',1,1,100,q))
        b.apply(Event(2,2,'EXECUTE',1,1,100,q//2))
        self.assertFalse(b.pending)

    def test_mutable_input_copied_and_no_batch_retained(self):
        b=RecoveryBook();batch=[Event(1,1,'ADD',1,1,100,100)];b.apply_batch(batch,available_ns=1);batch.clear()
        self.assertEqual(b.depth(1,100),100)

    def test_empty_batch_is_not_a_coverage_heartbeat(self):
        with self.assertRaises(ValueError):RecoveryBook().apply_batch([],available_ns=1)

    def test_random_order_conservation_against_independent_dictionary(self):
        for seed in range(40):
            rng=random.Random(seed);b=RecoveryBook();ref={};seq=0;oid=1
            for batch_index in range(80):
                events=[];expected=copy.deepcopy(ref)
                for _ in range(rng.randint(1,5)):
                    seq+=1
                    if not expected or rng.random()<.35:
                        side=rng.choice([-1,1]);price=rng.randint(95,105);quantity=rng.randint(1,200)
                        expected[oid]=(side,price,quantity);events.append(Event(seq,seq,'ADD',oid,side,price,quantity));oid+=1
                    else:
                        key=rng.choice(list(expected));side,price,quantity=expected[key];kind=rng.choice(['MODIFY','DELETE','EXECUTE'])
                        if kind=='MODIFY':
                            p=rng.randint(95,105);q=rng.randint(0,200);events.append(Event(seq,seq,kind,key,side,p,q))
                            if q:expected[key]=(side,p,q)
                            else:del expected[key]
                        elif kind=='DELETE':events.append(Event(seq,seq,kind,key,side,price,0));del expected[key]
                        else:
                            q=rng.randint(1,quantity);events.append(Event(seq,seq,kind,key,side,price,q))
                            if q<quantity:expected[key]=(side,price,quantity-q)
                            else:del expected[key]
                b.apply_batch(events,available_ns=seq);ref=expected
                self.assertEqual(b.orders,ref)
                for side in [-1,1]:
                    for price in range(95,106):self.assertEqual(b.depth(side,price),sum(q for s,p,q in ref.values() if s==side and p==price))
                self.assertIsNone(b.snapshot(seq)['forecast_probability'])

if __name__=='__main__':unittest.main(verbosity=2)
