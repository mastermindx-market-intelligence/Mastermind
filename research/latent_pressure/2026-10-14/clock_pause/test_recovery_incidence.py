import copy
from fractions import Fraction
import importlib.util
from pathlib import Path
import unittest
from recovery_incidence import Episode, competing_incidence, summarize_book

p = Path(__file__).resolve().parent.parent / 'event_recovery' / 'book_recovery.py'
spec = importlib.util.spec_from_file_location('retained_recovery', p)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Event, RecoveryBook = module.Event, module.RecoveryBook


class IncidenceTests(unittest.TestCase):
    def test_exact_four_episode_example(self):
        result = competing_incidence([Episode(1,'RECOVERED'), Episode(8,'RECOVERED'),
                                      Episode(2,'LEVEL_DEPLETED'), Episode(3,'PENDING')])
        e = result['terminal_estimate']
        self.assertEqual(e['recovery_incidence'], .75)
        self.assertEqual(e['depletion_incidence'], .25)
        self.assertEqual(e['unresolved_survival_estimate'], 0)
        self.assertEqual(result['median_completed_recovery_ns'], 4.5)
        self.assertEqual(result['median_recovery_incidence_ns'], 8)
        self.assertEqual([x['at_risk_before'] for x in result['curve']], [4,3,2,1])

    def test_competing_event_not_treated_as_censor(self):
        e = competing_incidence([Episode(1,'RECOVERED'), Episode(2,'LEVEL_DEPLETED'),
                                 Episode(3,'RECOVERED')])['terminal_estimate']
        self.assertAlmostEqual(e['recovery_incidence'], 2/3)
        self.assertAlmostEqual(e['depletion_incidence'], 1/3)

    def test_events_before_censors_at_tie(self):
        r = competing_incidence([Episode(2,'RECOVERED'), Episode(2,'LEVEL_DEPLETED'),
                                 Episode(2,'PENDING')])
        for v in r['terminal_estimate'].values(): self.assertAlmostEqual(v, 1/3)
        self.assertEqual(r['curve'][0]['at_risk_before'], 3)

    def test_all_censored_not_zero_risk_claim(self):
        r = competing_incidence([Episode(1,'PENDING'), Episode(5,'SOURCE_GAP_CENSORED')])
        self.assertEqual(r['terminal_estimate']['unresolved_survival_estimate'], 1)
        self.assertIsNone(r['median_recovery_incidence_ns'])
        self.assertEqual(r['followup_end_ns'], 5)

    def test_empty_not_zero_forecast(self):
        r = competing_incidence([])
        self.assertIsNone(r['terminal_estimate'])
        self.assertEqual(r['status'], 'NO_OBSERVED_EPISODES')

    def test_permutation_invariant_tied_risk_sets(self):
        e=[Episode(1,'RECOVERED'),Episode(1,'PENDING'),Episode(2,'LEVEL_DEPLETED')]
        self.assertEqual(competing_incidence(e),competing_incidence(list(reversed(e))))

    def test_exact_fraction_reference(self):
        events = [(1,'RECOVERED'),(1,'PENDING'),(2,'RECOVERED'),(3,'LEVEL_DEPLETED'),
                  (5,'SOURCE_GAP_CENSORED'),(6,'RECOVERED')]
        S=Fraction(1);F=Fraction(0);G=Fraction(0)
        for t in sorted(set(t for t,_ in events)):
            risk=sum(u>=t for u,_ in events)
            rec=sum(u==t and k=='RECOVERED' for u,k in events)
            dep=sum(u==t and k=='LEVEL_DEPLETED' for u,k in events)
            F+=S*Fraction(rec,risk);G+=S*Fraction(dep,risk);S*=1-Fraction(rec+dep,risk)
        r=competing_incidence(Episode(t,k) for t,k in events)['terminal_estimate']
        self.assertAlmostEqual(r['recovery_incidence'], float(F))
        self.assertAlmostEqual(r['depletion_incidence'], float(G))
        self.assertAlmostEqual(r['unresolved_survival_estimate'], float(S))

    def test_invalid_duration_or_state_refused(self):
        for t in [-1,True,1.5]:
            with self.assertRaises(ValueError): Episode(t,'RECOVERED')
        with self.assertRaises(ValueError): Episode(1,'PROFITABLE')

    def test_zero_duration_preserved(self):
        r=competing_incidence([Episode(0,'PENDING'),Episode(1,'RECOVERED')])
        self.assertEqual(r['curve'][1]['at_risk_before'],1)
        self.assertEqual(r['terminal_estimate']['recovery_incidence'],1)

    def book(self):
        b=RecoveryBook(horizon_ns=20)
        b.apply(Event(1,1,'ADD',2**60+1,1,100,100))
        b.apply(Event(2,2,'EXECUTE',2**60+1,1,100,60))
        return b

    def test_pending_and_cutoff_no_future_recovery(self):
        b=self.book();r=summarize_book(b,5)
        self.assertEqual(r['bid']['observed_counts']['censored'],1)
        self.assertIsNone(r['bid']['median_completed_recovery_ns'])
        self.assertIsNone(r['forecast_probability'])

    def test_nonmutating_and_prefix(self):
        b=self.book();before=copy.deepcopy(b.__dict__);r=summarize_book(b,5)
        self.assertEqual(before,b.__dict__)
        b.apply(Event(3,9,'ADD',2**60+2,1,100,60))
        with self.assertRaises(ValueError): summarize_book(b,5)
        current=summarize_book(b,9)
        self.assertEqual(current['bid']['median_completed_recovery_ns'],7)
        self.assertEqual(r['bid']['observed_counts']['censored'],1)

    def test_depletion_is_competing_observation(self):
        b=self.book();b.apply(Event(3,4,'DELETE',2**60+1,1,100,0));r=summarize_book(b,5)
        self.assertEqual(r['bid']['observed_counts']['depleted'],1)
        self.assertEqual(r['bid']['terminal_estimate']['depletion_incidence'],1)
        self.assertIsNone(r['forecast_probability'])

    def test_sides_are_separate(self):
        b=self.book();r=summarize_book(b,5)
        self.assertEqual(r['bid']['n'],1);self.assertEqual(r['ask']['n'],0)

    def test_source_gap_censors_at_last_verified_clock(self):
        b=self.book();b.invalidate();r=summarize_book(b,8)
        self.assertFalse(r['source_integrity'])
        self.assertEqual(r['bid']['followup_end_ns'],0)
        self.assertEqual(r['bid']['observed_counts']['censored'],1)

    def test_horizon_censor_preserves_unresolved_tail(self):
        b=self.book();r=summarize_book(b,100)
        self.assertEqual(r['bid']['followup_end_ns'],20)
        self.assertEqual(r['bid']['terminal_estimate']['unresolved_survival_estimate'],1)
        self.assertEqual(b.pending[1].state,'PENDING')

    def test_actual_adapter_stays_closed(self):
        with self.assertRaises(NotImplementedError): module.decode_iex_book_event(b'not-qualified')


if __name__ == '__main__': unittest.main(verbosity=2)
