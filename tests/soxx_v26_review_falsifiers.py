#!/usr/bin/env python3
"""Independent falsifiers for repaired V26 utility.

Tests: UTC-fold ordering, label maturity, cohort denominators,
unknown/nofill handling, profit/loss zero crossings, overflow/ratio.

Usage: python falsifiers.py /absolute/path/to/utility.py
"""
import importlib.util
import math
import sys
from datetime import datetime, timedelta, timezone


def _load(path):
    spec = importlib.util.spec_from_file_location('utility', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['utility'] = mod
    spec.loader.exec_module(mod)
    return mod


UTC = timezone.utc
EST = timezone(timedelta(hours=-5))
EDT = timezone(timedelta(hours=-4))


def main():
    if len(sys.argv) != 2:
        print('usage: falsifiers.py PATH')
        return 2
    u = _load(sys.argv[1])
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    # 1. UTC-fold ordering
    winter = datetime(2024, 1, 15, 12, 0, tzinfo=EST)
    summer = datetime(2024, 7, 15, 12, 0, tzinfo=EDT)
    check('utc-winter-not-summer',
          winter.astimezone(UTC) != summer.astimezone(UTC))
    pre = datetime(2024, 3, 10, 1, 30, tzinfo=EST)
    post = datetime(2024, 3, 10, 3, 30, tzinfo=EDT)
    check('utc-spring-forward-ordering',
          pre.astimezone(UTC) < post.astimezone(UTC))
    try:
        u._clock(datetime(2024, 1, 15), 'naive')
        check('utc-rejects-naive', False)
    except ValueError:
        check('utc-rejects-naive', True)

    # 2. Both-path label maturity
    base = datetime(2024, 1, 1, tzinfo=UTC)
    L_avail = u.TrainingLabel('avail', base + timedelta(days=10), base,
                              base + timedelta(days=20),
                              base + timedelta(days=20),
                              base + timedelta(days=30))
    L_unknown = u.TrainingLabel('unk', base + timedelta(days=10), base,
                                base + timedelta(days=20),
                                base + timedelta(days=20), None)
    mat = u.mature_training_labels([L_avail, L_unknown],
                                   fit_at=base + timedelta(days=31))
    check('maturity-selects-available-only',
          len(mat) == 1 and mat[0].episode == 'avail')
    mat_eq = u.mature_training_labels([L_avail],
                                       fit_at=base + timedelta(days=30))
    check('maturity-strictly-less-than', len(mat_eq) == 0)
    try:
        u.TrainingLabel('early_out', base + timedelta(days=10), base,
                        base + timedelta(days=20),
                        base + timedelta(days=20),
                        base + timedelta(days=5))
        check('maturity-rejects-early-outcome', False)
    except ValueError:
        check('maturity-rejects-early-outcome', True)
    try:
        u.TrainingLabel('early_base', base + timedelta(days=10), base,
                        base + timedelta(days=5),
                        base + timedelta(days=20),
                        base + timedelta(days=30))
        check('maturity-rejects-early-baseline-end', False)
    except ValueError:
        check('maturity-rejects-early-baseline-end', True)

    # 3. Whole-cohort denominators
    rows = [u.PairedOutcome(f'r{i}', 'FILLED', baseline_pp=1.0,
                            intervention_pp=2.0, baseline_preserved=False,
                            sold_fraction=1.0, sale_to_entry=1.0)
            for i in range(4)]
    res = u.summarize([f'r{i}' for i in range(4)], rows)
    check('denominator-equals-cohort-size',
          res['original_episodes'] == 4
          and abs(res['mean_delta_pp'] - 1.0) < 1e-12)
    try:
        u.summarize(['a', 'a'],
                    [u.PairedOutcome('a', 'FILLED', 0.0, 1.0,
                                     baseline_preserved=False,
                                     sold_fraction=1.0, sale_to_entry=1.0)])
        check('denominator-rejects-duplicate-cohort', False)
    except ValueError:
        check('denominator-rejects-duplicate-cohort', True)
    try:
        u.summarize(['x'], [u.PairedOutcome('y', 'FILLED', 0.0, 1.0,
                                            baseline_preserved=False,
                                            sold_fraction=1.0,
                                            sale_to_entry=1.0)])
        check('denominator-rejects-mismatch', False)
    except ValueError:
        check('denominator-rejects-mismatch', True)

    # 4. Unknown / nofill
    try:
        u.PairedOutcome('na1', 'NO_ACTION', baseline_pp=1.0,
                        intervention_pp=2.0, baseline_preserved=True)
        check('nofill-rejects-mismatched-paired-returns', False)
    except ValueError:
        check('nofill-rejects-mismatched-paired-returns', True)
    pa = u.PairedOutcome('na2', 'NO_ACTION', baseline_preserved=True)
    r2 = u.summarize(['na2'], [pa])
    check('nofill-counts-and-zero-delta',
          r2['no_action_episodes'] == 1 and r2['mean_delta_pp'] == 0.0)
    try:
        u.summarize(['u1'], [u.PairedOutcome(
            'u1', 'UNRESOLVED', delta_bounds=(-1.0, 1.0),
            bounds_cover_slippage_bps=0.)],
            extra_sell_slippage_bps=10.0)
        check('unresolved-rejects-insufficient-bounds', False)
    except ValueError:
        check('unresolved-rejects-insufficient-bounds', True)
    r3 = u.summarize(['u2'],
                     [u.PairedOutcome('u2', 'UNRESOLVED')])
    check('unresolved-no-bounds-mean-is-None',
          r3['mean_delta_pp'] is None
          and r3['mean_delta_lower_pp'] is None
          and r3['mean_delta_upper_pp'] is None)

    # 5. Profit/loss zero crossings
    r_z = u.PairedOutcome('z1', 'FILLED', baseline_pp=0.0,
                          intervention_pp=1.0, baseline_preserved=False,
                          sold_fraction=1.0, sale_to_entry=1.0)
    r4 = u.summarize(['z1'], [r_z])
    check('zero-baseline-bucket-is-benefit',
          r4['resolved_components']['zero_baseline_benefit_pp'] == 1.0
          and r4['resolved_components']['baseline_loser_improvement_pp'] == 0.0
          and r4['resolved_components']['baseline_winner_improvement_pp'] == 0.0)
    r_imp = u.PairedOutcome('z2', 'FILLED', baseline_pp=-2.0,
                            intervention_pp=1.0, baseline_preserved=False,
                            sold_fraction=1.0, sale_to_entry=1.0)
    r5 = u.summarize(['z2'], [r_imp])
    # baseline=-2, intervention=1 -> loss avoided = 2.0, profit created = 1.0
    # The bridge must split zero-crossings: avoid loss is loss_reduction,
    # NOT folded into profit_increase.
    check('loser-improves-bridge-splits-zero-crossing',
          r5['resolved_components']['baseline_loser_improvement_pp'] == 3.0
          and abs(r5['resolved_economic_bridge']['loss_reduction_pp'] - 2.0) < 1e-12
          and abs(r5['resolved_economic_bridge']['profit_increase_pp'] - 1.0) < 1e-12
          and r5['resolved_economic_bridge']['loss_increase_pp'] == 0.0
          and r5['resolved_economic_bridge']['profit_surrender_pp'] == 0.0)

    # 6. Finite / overflow / ratio
    r_b1 = u.break_even_share(1e308, 1e308)
    check('break-even-1e308-equal-half-finite',
          math.isfinite(r_b1) and abs(r_b1 - 0.5) < 1e-12)
    check('break-even-harm-zero-returns-zero',
          u.break_even_share(1.0, 0.0) == 0.0)
    try:
        u.break_even_share(1.0, 1.0, decision_cost_pp=-1.0)
        check('break-even-rejects-negative-cost', False)
    except ValueError:
        check('break-even-rejects-negative-cost', True)
    huge = [u.PairedOutcome(f'h{i}', 'FILLED', baseline_pp=0.0,
                            intervention_pp=1e307, baseline_preserved=False,
                            sold_fraction=1.0, sale_to_entry=1.0)
            for i in range(100)]
    try:
        u.summarize([f'h{i}' for i in range(100)], huge)
        check('summarize-rejects-overflowing-component-sum', False)
    except ValueError:
        check('summarize-rejects-overflowing-component-sum', True)

    total = 19
    print(f'failures={len(fails)} total={total}')
    for f in fails:
        print(f'  FAIL: {f}')
    print('PASS' if not fails else 'FAIL')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
