#!/usr/bin/env python3
"""Mutation-discriminating clock falsifier. Synthetic-only, no shared-source mods."""
import importlib.util, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
OK, FAIL = [], []


def load(p):
    s = importlib.util.spec_from_file_location('t', p)
    m = importlib.util.module_from_spec(s); sys.modules['t'] = m; s.loader.exec_module(m)
    return m


def run(name, fn, mod):
    try: fn(mod); OK.append(name)
    except Exception as e: FAIL.append((name, f'{type(e).__name__}: {e}'))


def t_fold1_outcome_cannot_train_fold0_fit(mod):
    f0 = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=0)  # 05:30 UTC
    f1 = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=1)  # 06:30 UTC
    assert f1.astimezone(timezone.utc) > f0.astimezone(timezone.utc)
    lab = mod.TrainingLabel('A1', f0, f0, f0, f0, f1)
    assert lab not in mod.mature_training_labels([lab], fit_at=f0)


def t_availability_precedes_path_end_rejected(mod):
    f0 = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=0)
    er = datetime(2026, 11, 1, 0, 30, tzinfo=NY, fold=0)
    try:
        mod.TrainingLabel('A2', f0, f0, f0, f0, er)
    except ValueError:
        return
    raise AssertionError('TrainingLabel accepted availability before path end')


def t_fill_precedes_submission_rejected(mod):
    a = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=0)
    b = datetime(2026, 11, 1, 1, 45, tzinfo=NY, fold=0)
    c = datetime(2026, 11, 1, 1, 40, tzinfo=NY, fold=0)
    try:
        mod.check_decision_clocks(a, a, b, b, c)
    except ValueError:
        return
    raise AssertionError('check_decision_clocks accepted fill before submission')


def t_decreasing_wall_strict_utc_accepted(mod):
    # Wall 01:00 EDT -> 01:30 EDT -> 01:00 EST: wall goes up then DOWN; UTC strictly UP.
    w1 = datetime(2026, 11, 1, 1, 0, tzinfo=NY, fold=0)
    w2 = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=0)
    w3 = datetime(2026, 11, 1, 1, 0, tzinfo=NY, fold=1)
    fill = datetime(2026, 11, 1, 2, 15, tzinfo=NY, fold=1)  # 07:15 UTC, post w3
    mod.TrainingLabel('A4', w1, w1, w3, w3, w3)
    mod.check_decision_clocks(w1, w1, w2, w3, fill)


def t_nonoverlap_utc_same_wall(mod):
    # Same wall fields 01:00-01:30 across folds: UTC [05:00,05:30) vs [06:00,06:30).
    s0 = datetime(2026, 11, 1, 1, 0, tzinfo=NY, fold=0)
    e0 = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=0)
    s1 = datetime(2026, 11, 1, 1, 0, tzinfo=NY, fold=1)
    e1 = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=1)
    groups = mod.overlap_components([('A5a', s0, e0), ('A5b', s1, e1)])
    assert len(groups) == 2, f'expected 2 separate UTC groups, got {groups}'


def t_future_feature_across_folds(mod):
    bar = datetime(2026, 11, 1, 0, 30, tzinfo=NY, fold=0)
    dec = datetime(2026, 11, 1, 0, 45, tzinfo=NY, fold=0)
    sub = datetime(2026, 11, 1, 2, 15, tzinfo=NY, fold=1)
    fill = datetime(2026, 11, 1, 2, 30, tzinfo=NY, fold=1)
    mod.check_decision_clocks(bar, bar, dec, sub, fill)


def main():
    if len(sys.argv) != 2:
        print('usage: clock_falsifier.py /path/to/utility.py'); sys.exit(2)
    m = load(sys.argv[1])
    for n, f in [('fold1_outcome_cannot_train_fold0_fit', t_fold1_outcome_cannot_train_fold0_fit),
                 ('availability_precedes_path_end_rejected', t_availability_precedes_path_end_rejected),
                 ('fill_precedes_submission_rejected', t_fill_precedes_submission_rejected),
                 ('decreasing_wall_strict_utc_accepted', t_decreasing_wall_strict_utc_accepted),
                 ('nonoverlap_utc_same_wall', t_nonoverlap_utc_same_wall),
                 ('future_feature_across_folds', t_future_feature_across_folds)]:
        run(n, f, m)
    n = len(OK) + len(FAIL)
    print(f'EXECUTED {n}')
    for k in OK: print(f'PASS {k}')
    for k, v in FAIL: print(f'FAIL {k}: {v}')
    sys.exit(0 if not FAIL else 1)


if __name__ == '__main__':
    main()
