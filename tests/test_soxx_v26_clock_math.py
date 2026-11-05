"""Post-review UTC-fold and finite-arithmetic falsifiers. Synthetic inputs only."""
import importlib.util
from pathlib import Path
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'research/soxx-multitimeframe-cycle-2026-10-11/prospective_validation_v26/utility.py'
spec = importlib.util.spec_from_file_location('soxx_v26_clock_math', MODULE)
M = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = M
spec.loader.exec_module(M)

class ClockMathTests(unittest.TestCase):
    def filled(self, key='a', **changes):
        values = dict(episode=key, state='FILLED', baseline_pp=-1.5,
                      intervention_pp=-.5, sold_fraction=.75, sale_to_entry=.99)
        values.update(changes)
        return M.PairedOutcome(**values)

    def summary(self, rows, **kw):
        return M.summarize([r.episode for r in rows], rows, **kw)

    def test_dst_fold_cannot_admit_a_future_label(self):
        zone = ZoneInfo('America/New_York')
        def at(h, m, fold=0):
            return datetime(2026, 11, 1, h, m, tzinfo=zone, fold=fold)
        row = M.TrainingLabel('dst', at(0,30), at(0,30), at(1,10), at(1,15), at(1,30,1))
        self.assertEqual(M.mature_training_labels([row], at(1,45)), [])

    def test_dst_fold_rejects_availability_before_path_completion(self):
        zone = ZoneInfo('America/New_York')
        def at(h,m,fold=0):
            return datetime(2026,11,1,h,m,tzinfo=zone,fold=fold)
        with self.assertRaises(ValueError):
            M.TrainingLabel('dst',at(0,30),at(0,30),at(1,30,1),at(1,15),at(1,45))

    def test_dst_fold_rejects_a_fill_before_submission(self):
        zone = ZoneInfo('America/New_York')
        def at(h,m,fold=0):
            return datetime(2026,11,1,h,m,tzinfo=zone,fold=fold)
        with self.assertRaises(ValueError):
            M.check_decision_clocks(at(0,30),at(0,30),at(0,30),at(1,30,1),at(1,45))

    def test_valid_fold_ordering_uses_instants_not_wall_clock(self):
        zone = ZoneInfo('America/New_York')
        def at(h,m,fold=0):
            return datetime(2026,11,1,h,m,tzinfo=zone,fold=fold)
        try:
            M.check_decision_clocks(at(1,45),at(1,15,1),at(1,20,1),at(1,25,1),at(1,30,1))
        except ValueError as exc:
            self.fail('Valid chronological UTC instants rejected: '+str(exc))

    def test_fold_separated_exposures_are_not_overlapped_by_wall_clock(self):
        zone = ZoneInfo('America/New_York')
        def at(h,m,fold=0):
            return datetime(2026,11,1,h,m,tzinfo=zone,fold=fold)
        groups=M.overlap_components([('early',at(1,30),at(1,45)),
                                     ('late',at(1,20,1),at(1,40,1))])
        self.assertEqual(groups,[['early'],['late']])

    def test_finite_inputs_cannot_produce_infinite_accounting_components(self):
        rows=[]
        for i in range(2):
            rows.extend([self.filled('loss'+str(i),baseline_pp=-1e308,intervention_pp=0.),
                         self.filled('win'+str(i),baseline_pp=1e308,intervention_pp=1.)])
        with self.assertRaises(ValueError): self.summary(rows)

    def test_extreme_breakeven_does_not_collapse_to_zero_or_nan(self):
        self.assertEqual(M.break_even_share(1e308,1e308),.5)
        self.assertEqual(M.break_even_share(1e308,1e308,decision_cost_pp=1e308),1.)

    def test_unrepresentable_input_is_a_validation_error(self):
        with self.assertRaises(ValueError): self.filled(baseline_pp=10**1000)

if __name__ == '__main__': unittest.main()
