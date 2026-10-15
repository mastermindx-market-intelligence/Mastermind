"""Synthetic temporal and scoring checks; never a substitute for a market test."""
import unittest
import numpy as np
import pandas as pd
from clock_study import (BASE, NEW, SECOND, clock, combine, label_at, median_twice,
                         metrics, panel, prefix_feature, count_window, paired_interval)


def fixture():
    t = clock('10:00')
    return pd.DataFrame([{'ticker': 'AAPL', 'send_ns': t - (20 - i) * 5 * SECOND,
                          'timestamp_ns': t - (20 - i) * 5 * SECOND - 1,
                          'sequence': i + 1, 'order_id': 2**60 + i % 3,
                          'trade_id': 2**61 + i, 'price_1e4': 1000000 + i,
                          'size': 100, 'sale_flags': 0} for i in range(20)])


def append_at(frame, at, *, price=1000100, flag=0):
    r = frame.iloc[-1].to_dict()
    r.update(send_ns=at, timestamp_ns=at-1, sequence=int(frame.sequence.max())+1,
             trade_id=int(frame.trade_id.max())+1, price_1e4=price, sale_flags=flag)
    return pd.concat([frame, pd.DataFrame([r])], ignore_index=True)


class ClockTests(unittest.TestCase):
    def test_large_price_median_exact(self):
        self.assertEqual(median_twice([2**60+1, 2**60+3]), 2**61+4)
        x = fixture(); t = clock('10:00')
        f = append_at(x, t+60*SECOND, price=2**60+3)
        self.assertEqual(label_at(f, t, 2*(2**60+1), t+120*SECOND)[0], 3)

    def test_missing_future_not_flat(self):
        t = clock('10:00')
        self.assertEqual(label_at(fixture(), t, 2000000, t+120*SECOND)[0], 0)

    def test_unobserved_capture_not_no_trade(self):
        t = clock('10:00')
        self.assertIsNone(label_at(fixture(), t, 2000000, t+119*SECOND)[0])

    def test_future_both_endpoints_included(self):
        t = clock('10:00')
        x = append_at(fixture(), t+60*SECOND, price=1000000)
        x = append_at(x, t+120*SECOND, price=1000002)
        cls, count, _ = label_at(x, t, 2000002, t+120*SECOND)
        self.assertEqual((cls, count), (2, 2))

    def test_future_outside_endpoints_excluded(self):
        t = clock('10:00')
        x = append_at(fixture(), t+60*SECOND-1)
        x = append_at(x, t+120*SECOND+1)
        self.assertEqual(label_at(x, t, 2000000, t+200*SECOND)[:2], (0, 0))

    def test_prefix_feature_unchanged_by_future(self):
        x = fixture(); t = clock('10:00')
        first, _ = prefix_feature(x, x, t, 'AAPL')
        whole = append_at(x, t+SECOND, price=40000000)
        other, _ = prefix_feature(whole, whole, t, 'AAPL')
        self.assertEqual(first, other)

    def test_future_arrival_not_used_in_pause_denominator(self):
        x = fixture(); t = clock('10:01')
        first, _ = prefix_feature(x, x, t, 'AAPL')
        whole = append_at(x, clock('10:04'))
        other, _ = prefix_feature(whole, whole, t, 'AAPL')
        self.assertEqual(first['normalized_pause'], other['normalized_pause'])

    def test_filtered_quiet_has_other_activity(self):
        x = fixture(); t = clock('10:01')
        all_x = append_at(x, t-SECOND, flag=128)
        r, reason = prefix_feature(x, all_x, t, 'AAPL')
        self.assertEqual(reason, 'ELIGIBLE')
        self.assertGreaterEqual(r['standard_age_seconds'], 60)
        self.assertEqual(r['std60_count'], 0)
        self.assertEqual(r['all60_count'], 1)
        self.assertEqual(r['all_age_seconds'], 1)

    def test_stale_reference_separate_from_future(self):
        x = fixture(); t = clock('10:06')
        r, reason = prefix_feature(x, x, t, 'AAPL')
        self.assertIsNone(r)
        self.assertIn('OLDER_THAN', reason)

    def test_insufficient_history_count(self):
        x = fixture().iloc[:19]
        self.assertEqual(prefix_feature(x, x, clock('10:00'), 'AAPL')[1], 'INSUFFICIENT_STANDARD_HISTORY')

    def test_same_stamp_group_included_at_cutoff(self):
        x = fixture(); t = clock('10:00')
        x = append_at(x, t); x = append_at(x, t)
        r, _ = prefix_feature(x, x, t, 'AAPL')
        self.assertEqual(r['last_sequence'], int(x.sequence.max()))
        self.assertEqual(r['standard_age_seconds'], 0)

    def test_riskset_unchanged_by_future(self):
        x = fixture(); t = clock('10:00')
        a, _ = panel(x, [t], observed_through_ns=t+120*SECOND)
        x = append_at(x, t+60*SECOND)
        b, _ = panel(x, [t], observed_through_ns=t+120*SECOND)
        self.assertEqual(len(a), len(b))
        np.testing.assert_allclose(a[BASE+NEW], b[BASE+NEW], rtol=0, atol=0)
        self.assertEqual(a['class'].iloc[0], 0)
        self.assertNotEqual(b['class'].iloc[0], 0)

    def test_complete_probability_simplex(self):
        p = combine(np.array([.2,.8]), np.array([[.1,.2,.7],[.3,.5,.2]]))
        np.testing.assert_allclose(p.sum(1), 1)
        np.testing.assert_allclose(p[:,0], [.8,.2])

    def test_logloss_decomposes(self):
        a = np.array([.2,.8,.6,.9]);d = np.tile([.2,.3,.5], (4,1))
        m, losses = metrics(np.array([0,1,2,3]), combine(a,d), a,d)
        self.assertTrue(m['logloss_decomposition_exact'])
        self.assertEqual(m['conditional_direction_n'], 3)
        self.assertTrue(np.isnan(losses['direction'][0]))

    def test_all_unobserved_no_direction_claim(self):
        a=np.array([.2,.3]);d=np.tile([.2,.3,.5], (2,1))
        m, _ = metrics(np.array([0,0]), combine(a,d), a,d)
        self.assertIsNone(m['conditional_direction_brier'])
        self.assertIsNone(m['conditional_direction_accuracy'])

    def test_grid_requires_strict_exact_order(self):
        with self.assertRaises(ValueError): panel(fixture(), [1,1], labels=False)
        with self.assertRaises(ValueError): panel(fixture(), [1.0], labels=False)

    def test_boundary_count_has_no_double_count(self):
        t = clock('10:00');arr=np.array([t-60*SECOND,t], dtype=np.uint64)
        self.assertEqual(count_window(arr,t-60*SECOND,t),2)
        self.assertEqual(count_window(arr,t-300*SECOND,t-60*SECOND-1),0)

    def test_halfhour_terminal_origin_not_singleton_block(self):
        t=clock('13:00');test=pd.DataFrame({'decision_ns':[t+i*1800*SECOND for i in range(6)]})
        r=paired_interval(test,np.zeros(6))
        self.assertEqual(r['blocks'],5)
        self.assertFalse(r['population_significance_established'])


if __name__ == '__main__': unittest.main(verbosity=2)
