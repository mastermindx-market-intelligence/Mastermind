"""Synthetic-only tests. No vendor rows, history fitting, or provider access."""
import importlib.util
import math
from pathlib import Path
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'research/soxx-multitimeframe-cycle-2026-10-11/prospective_validation_v26/utility.py'
M = None
if MODULE.exists():
    spec = importlib.util.spec_from_file_location('soxx_v26_utility', MODULE)
    M = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = M
    spec.loader.exec_module(M)

T = datetime(2026, 10, 12, 13, 30, tzinfo=timezone.utc)

class ProspectiveAccountingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(M, 'The new prospective accounting implementation is absent')

    def label(self, **changes):
        values = dict(episode='sample', decision_at=T-timedelta(days=3),
                      feature_available_at=T-timedelta(days=3),
                      baseline_end_at=T+timedelta(days=5),
                      intervention_end_at=T-timedelta(days=2),
                      outcome_available_at=T+timedelta(days=5, seconds=1))
        values.update(changes)
        return M.TrainingLabel(**values)

    def filled(self, key='a', **changes):
        values = dict(episode=key, state='FILLED', baseline_pp=-1.5,
                      intervention_pp=-.5, sold_fraction=.75, sale_to_entry=.99)
        values.update(changes)
        return M.PairedOutcome(**values)

    def summary(self, rows, **kw):
        return M.summarize([r.episode for r in rows], rows, **kw)

    def test_prior_entry_week_does_not_make_future_outcome_available(self):
        self.assertLess('2026-10-05', '2026-10-12')  # old split admits this case
        self.assertEqual(M.mature_training_labels([self.label()], T), [])

    def test_both_counterfactual_paths_must_have_completed(self):
        r = self.label(baseline_end_at=T-timedelta(hours=1),
                       intervention_end_at=T+timedelta(hours=1),
                       outcome_available_at=T+timedelta(hours=2))
        self.assertEqual(M.mature_training_labels([r], T), [])

    def test_capture_latency_is_not_backdated_to_market_event(self):
        r = self.label(baseline_end_at=T-timedelta(hours=2),
                       intervention_end_at=T-timedelta(hours=1),
                       outcome_available_at=T+timedelta(seconds=1))
        self.assertEqual(M.mature_training_labels([r], T), [])

    def test_strict_maturity_boundary(self):
        r = self.label(baseline_end_at=T-timedelta(hours=2),
                       intervention_end_at=T-timedelta(hours=1), outcome_available_at=T)
        self.assertEqual(M.mature_training_labels([r], T), [])
        self.assertEqual(M.mature_training_labels([r], T+timedelta(microseconds=1)), [r])

    def test_unknown_label_availability_is_ineligible(self):
        self.assertEqual(M.mature_training_labels([self.label(outcome_available_at=None)], T), [])

    def test_label_available_before_path_end_rejected(self):
        with self.assertRaises(ValueError):
            self.label(outcome_available_at=T)

    def test_future_feature_rejected(self):
        with self.assertRaises(ValueError):
            self.label(feature_available_at=T)

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            M.mature_training_labels([], T.replace(tzinfo=None))

    def test_duplicate_labels_rejected(self):
        with self.assertRaises(ValueError):
            M.mature_training_labels([self.label(), self.label()], T)

    def test_no_same_timestamp_instant_execution(self):
        with self.assertRaises(ValueError):
            M.check_decision_clocks(T, T, T, T, T)
        M.check_decision_clocks(T, T, T, T, T+timedelta(seconds=1))

    def test_unavailable_features_cannot_be_recorded_earlier(self):
        with self.assertRaises(ValueError):
            M.check_decision_clocks(T, T+timedelta(seconds=1), T, T, T+timedelta(minutes=5))

    def test_all_original_episodes_remain_in_denominator(self):
        rows = [self.filled(), M.PairedOutcome('b', 'NO_ACTION', baseline_preserved=True),
                M.PairedOutcome('c', 'VERIFIED_NO_FILL', baseline_preserved=True)]
        s = self.summary(rows)
        self.assertEqual(s['original_episodes'], 3)
        self.assertAlmostEqual(s['mean_delta_pp'], 1/3)
        self.assertEqual(s['discretionary_fills'], 1)

    def test_one_large_false_exit_can_overwhelm_many_saved_losses(self):
        rows = [self.filled(str(i)) for i in range(8)]
        rows.append(self.filled('winner', baseline_pp=12., intervention_pp=0.))
        s = self.summary(rows)
        self.assertAlmostEqual(s['mean_delta_pp'], -4/9)
        self.assertEqual(s['resolved_components']['baseline_loser_improvement_pp'], 8.)
        self.assertEqual(s['resolved_components']['baseline_winner_sacrifice_pp'], 12.)

    def test_baseline_sign_and_delta_sign_are_separate(self):
        rows = [self.filled('saved'), self.filled('improved', baseline_pp=2., intervention_pp=3.),
                self.filled('sacrificed', baseline_pp=3., intervention_pp=1.),
                self.filled('deepened', baseline_pp=-1., intervention_pp=-4.)]
        s = self.summary(rows)
        self.assertAlmostEqual(s['mean_delta_pp'], -.75)
        self.assertEqual(s['resolved_components'], dict(baseline_loser_improvement_pp=1., baseline_winner_improvement_pp=1.,
            baseline_winner_sacrifice_pp=2., baseline_loser_deterioration_pp=3.,
            zero_baseline_benefit_pp=0., zero_baseline_harm_pp=0.))

    def test_remaining_position_slippage_not_charged_to_full_position(self):
        s = self.summary([self.filled()], extra_sell_slippage_bps=50.)
        self.assertAlmostEqual(s['mean_delta_pp'], 1.-.75*.99*.5)

    def test_unknown_execution_is_not_zero_or_dropped(self):
        s = self.summary([self.filled(), M.PairedOutcome('u', 'UNRESOLVED')])
        self.assertEqual(s['original_episodes'], 2)
        self.assertEqual(s['unresolved_episodes'], 1)
        self.assertIsNone(s['mean_delta_pp'])
        self.assertIsNone(s['mean_delta_lower_pp'])
        self.assertFalse(s['positive_under_supplied_bounds'])

    def test_explicit_unknown_bounds_keep_full_denominator(self):
        s = self.summary([self.filled(), M.PairedOutcome('u', 'UNRESOLVED', delta_bounds=(-3., 1.))])
        self.assertEqual(s['mean_delta_lower_pp'], -1.)
        self.assertEqual(s['mean_delta_upper_pp'], 1.)
        self.assertIsNone(s['mean_delta_pp'])

    def test_uncertain_bounds_must_cover_requested_execution_stress(self):
        r = M.PairedOutcome('u', 'UNRESOLVED', delta_bounds=(-3.,1.))
        with self.assertRaises(ValueError): self.summary([r], extra_sell_slippage_bps=25.)
        r = M.PairedOutcome('u', 'UNRESOLVED', delta_bounds=(-3.,1.), bounds_cover_slippage_bps=25.)
        self.assertEqual(self.summary([r], extra_sell_slippage_bps=25.)['mean_delta_lower_pp'], -3.)

    def test_nofill_requires_evidence_of_unchanged_baseline_controls(self):
        with self.assertRaises(ValueError): M.PairedOutcome('a', 'VERIFIED_NO_FILL')

    def test_nofill_cannot_sneak_in_a_return_difference(self):
        with self.assertRaises(ValueError):
            M.PairedOutcome('a', 'NO_ACTION', baseline_pp=1., intervention_pp=2., baseline_preserved=True)

    def test_missing_parent_duplicate_and_extra_rows_rejected(self):
        r = self.filled()
        for ids, rows in [(['a','b'],[r]), (['a'],[r,r]), (['x'],[r]), (['a','a'],[r])]:
            with self.subTest(ids=ids, rows=len(rows)):
                with self.assertRaises(ValueError): M.summarize(ids, rows)

    def test_empty_cohort_does_not_become_zero_performance(self):
        with self.assertRaises(ValueError): M.summarize([], [])

    def test_nonfinite_values_and_bad_quantity_rejected(self):
        for x in [math.nan, math.inf, -math.inf, True]:
            with self.subTest(value=x):
                with self.assertRaises(ValueError): self.filled(baseline_pp=x)
        for q in [-.1, 0., 1.01]:
            with self.assertRaises(ValueError): self.filled(sold_fraction=q)

    def test_invalid_or_unbounded_cost_rejected(self):
        for cost in [-1., math.nan, True]:
            with self.assertRaises(ValueError): self.summary([self.filled()], extra_sell_slippage_bps=cost)

    def test_breakeven_is_action_conditional_not_all_opportunity_frequency(self):
        self.assertAlmostEqual(M.break_even_share(2., 10.), 10/12)
        self.assertAlmostEqual(M.break_even_share(2., 10., decision_cost_pp=.5), 10.5/12)
        self.assertGreaterEqual(M.break_even_share(2., 10., decision_cost_pp=2.), 1.)

    def test_overlap_clusters_do_not_count_correlated_names_as_new_units(self):
        xs = [('SOXX',T,T+timedelta(days=8)), ('SMH',T+timedelta(days=3),T+timedelta(days=10)),
              ('QQQ',T+timedelta(days=9),T+timedelta(days=15)),
              ('next',T+timedelta(days=15),T+timedelta(days=16))]
        groups = M.overlap_components(xs)
        self.assertEqual(groups, [['SOXX','SMH','QQQ'],['next']])

    def test_all_unresolved_stays_unknown_without_hidden_selection(self):
        s = self.summary([M.PairedOutcome('a','UNRESOLVED'), M.PairedOutcome('b','UNRESOLVED')])
        self.assertEqual(s['resolved_episodes'],0)
        self.assertIsNone(s['mean_delta_pp'])
        self.assertEqual(s['evidence_claim'],'ACCOUNTING_ONLY_NOT_STRATEGY_ACCEPTANCE')

    def test_mutable_input_bounds_are_frozen_at_validation(self):
        bounds = [-3., 1.]
        row = M.PairedOutcome('u','UNRESOLVED',delta_bounds=bounds)
        bounds[0] = 99.
        self.assertEqual(self.summary([row])['mean_delta_lower_pp'], -3.)

    def test_zero_crossings_split_avoided_loss_from_new_profit(self):
        s = self.summary([self.filled(baseline_pp=-2.,intervention_pp=3.)])
        self.assertEqual(s['resolved_economic_bridge'], dict(loss_reduction_pp=2.,
            profit_increase_pp=3.,profit_surrender_pp=0.,loss_increase_pp=0.))

    def test_zero_crossings_split_sacrificed_profit_from_new_loss(self):
        s = self.summary([self.filled(baseline_pp=3.,intervention_pp=-2.)])
        self.assertEqual(s['resolved_economic_bridge'], dict(loss_reduction_pp=0.,
            profit_increase_pp=0.,profit_surrender_pp=3.,loss_increase_pp=2.))

    def test_economic_bridge_equals_stressed_increment(self):
        rows = [self.filled('a'),self.filled('b',baseline_pp=-2.,intervention_pp=3.),
                self.filled('c',baseline_pp=3.,intervention_pp=-2.)]
        s = self.summary(rows,extra_sell_slippage_bps=25.)
        self.assertIn('resolved_economic_bridge',s)
        b=s['resolved_economic_bridge']
        net=b['loss_reduction_pp']+b['profit_increase_pp']-b['profit_surrender_pp']-b['loss_increase_pp']
        self.assertAlmostEqual(net/3,s['mean_delta_pp'])

if __name__ == '__main__': unittest.main()
