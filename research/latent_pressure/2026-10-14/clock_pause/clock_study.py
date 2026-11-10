"""LP-CLOCK-04: fixed-clock, observation-aware historical research only.

Uses already qualified IEX L records. Does not decode book events or trade signs.
A missing future standard print is a data outcome, not a flat market price.
"""
from __future__ import annotations
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logsumexp, softmax

HERE = Path(__file__).resolve().parent
DEPENDENCY = HERE.parent / 'event_recovery' / 'event_study.py'
_spec = importlib.util.spec_from_file_location('qualified_event_study', DEPENDENCY)
assert _spec is not None and _spec.loader is not None
_event = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_event)
NAMES = list(_event.NAMES)
EXPECTED_INPUT_SHA256 = 'd967e15a6148b96d155f733b64154c2256df07cfb3443c62c2df3be8ca54afe1'
SECOND = 1_000_000_000
BASE = ['momentum5', 'momentum20', 'vol20', 'logvolume20', 'log_age_standard',
        'log_age_all', 'log_std60', 'log_std300', 'log_all60', 'log_all300',
        'clock'] + ['is_' + s for s in NAMES[1:]]
NEW = ['normalized_pause', 'gap_trend', 'rate_change', 'pause_x_other_activity',
       'repeat_share', 'pause_x_repeat']
CLASS_NAMES = ['NO_STANDARD_OBSERVATION', 'DOWN', 'SAME', 'UP']


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clock(value: str) -> int:
    return _event.clock(value)


def load(path: Path, *, check_identity: bool = True) -> pd.DataFrame:
    if check_identity and digest(path) != EXPECTED_INPUT_SHA256:
        raise ValueError('UNQUALIFIED_INPUT_IDENTITY: new data require separate qualification')
    return _event.load(path)


def median_twice(values: Any) -> int:
    """Twice the exact median: no float conversion of prices or identifiers."""
    a = sorted(int(v) for v in values)
    if not a:
        raise ValueError('median of empty price set')
    n = len(a)
    return 2 * a[n // 2] if n % 2 else a[n // 2 - 1] + a[n // 2]


def count_window(times: np.ndarray, start: int, end: int) -> int:
    return int(np.searchsorted(times, np.uint64(end), side='right') -
               np.searchsorted(times, np.uint64(start), side='left'))


def prefix_feature(standard: pd.DataFrame, all_events: pd.DataFrame,
                   at_ns: int, ticker: str) -> tuple[dict[str, Any] | None, str]:
    """Caller may pass a full frame; each operation below takes only its prefix."""
    ts = standard.send_ns.to_numpy(dtype=np.uint64)
    ta = all_events.send_ns.to_numpy(dtype=np.uint64)
    n = int(np.searchsorted(ts, np.uint64(at_ns), side='right'))
    na = int(np.searchsorted(ta, np.uint64(at_ns), side='right'))
    if n < 20:
        return None, 'INSUFFICIENT_STANDARD_HISTORY'
    age = (at_ns - int(ts[n - 1])) / SECOND
    if age > 300:
        return None, 'STANDARD_REFERENCE_OLDER_THAN_300_SECONDS'
    if na == 0:
        raise ValueError('standard records cannot exist without all-L records')
    w = standard.iloc[n - 20:n]
    prices = [int(v) for v in w.price_1e4]
    last = median_twice(prices[-5:])
    previous = median_twice(prices[-10:-5])
    qty = w['size'].to_numpy(dtype=float)
    # Only completed gaps are used. The current incomplete gap is the observed age.
    gaps = np.diff(ts[n - 20:n].astype(np.int64)) / SECOND
    positive = gaps[gaps > 0]
    median_gap = float(np.median(positive)) if len(positive) else 0.0
    recent = gaps[-5:]
    positive_recent = recent[recent > 0]
    recent_gap = float(np.median(positive_recent)) if len(positive_recent) else 0.0
    std60 = count_window(ts[:n], at_ns - 60 * SECOND, at_ns)
    std300 = count_window(ts[:n], at_ns - 300 * SECOND, at_ns)
    all60 = count_window(ta[:na], at_ns - 60 * SECOND, at_ns)
    all300 = count_window(ta[:na], at_ns - 300 * SECOND, at_ns)
    prior240 = count_window(ts[:n], at_ns - 300 * SECOND, at_ns - 60 * SECOND - 1)
    all_age = (at_ns - int(ta[na - 1])) / SECOND
    pause = float(np.log1p(age / max(1.0, median_gap)))
    counts = collections.Counter(int(v) for v in w.order_id)
    repeated = sum(float(q) for oid, q in zip(w.order_id, qty) if counts[int(oid)] > 1)
    repeat_share = repeated / float(qty.sum())
    r = {
        'ticker': ticker, 'decision_ns': int(at_ns), 'last_sequence': int(w.sequence.iloc[-1]),
        'last_standard_ns': int(ts[n - 1]), 'last_all_ns': int(ta[na - 1]),
        'reference_price_twice': last, 'standard_age_seconds': age,
        'all_age_seconds': all_age, 'std60_count': std60, 'all60_count': all60,
        'momentum5': float(np.log(last / previous)),
        'momentum20': float(np.log(prices[-1] / prices[0])),
        'vol20': float(np.std(np.diff(np.log(np.asarray(prices, dtype=float))))),
        'logvolume20': float(np.log1p(qty.sum())),
        'log_age_standard': float(np.log1p(age)), 'log_age_all': float(np.log1p(all_age)),
        'log_std60': float(np.log1p(std60)), 'log_std300': float(np.log1p(std300)),
        'log_all60': float(np.log1p(all60)), 'log_all300': float(np.log1p(all300)),
        'clock': (at_ns - clock('10:00')) / SECOND,
        'normalized_pause': pause,
        'gap_trend': float(np.log((recent_gap + 1.0) / (median_gap + 1.0))),
        'rate_change': float(np.log1p(std60) - np.log1p(prior240 / 4.0)),
        'pause_x_other_activity': pause * float(np.log1p(age) - np.log1p(all_age)),
        'repeat_share': repeat_share, 'pause_x_repeat': pause * repeat_share,
    }
    r.update({'is_' + s: float(s == ticker) for s in NAMES[1:]})
    return r, 'ELIGIBLE'


def label_at(standard: pd.DataFrame, at_ns: int, reference_twice: int,
             observed_through_ns: int) -> tuple[int | None, int, int]:
    lower, upper = at_ns + 60 * SECOND, at_ns + 120 * SECOND
    if observed_through_ns < upper:
        return None, 0, upper
    ts = standard.send_ns.to_numpy(dtype=np.uint64)
    lo = int(np.searchsorted(ts, np.uint64(lower), side='left'))
    hi = int(np.searchsorted(ts, np.uint64(upper), side='right'))
    if lo == hi:
        return 0, 0, upper
    price = median_twice(standard.price_1e4.iloc[lo:hi])
    label = 1 if price < reference_twice else (3 if price > reference_twice else 2)
    return label, hi - lo, upper


def panel(frame: pd.DataFrame, origins: list[int], *, labels: bool = True,
          observed_through_ns: int | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    if any(type(t) is not int for t in origins) or origins != sorted(set(origins)):
        raise ValueError('origins must be strictly increasing exact integers')
    if labels and observed_through_ns is None:
        raise ValueError('explicit capture-observation endpoint required for labels')
    rows, coverage = [], {}
    for ticker in NAMES:
        all_events = frame[(frame.ticker == ticker) & (frame.send_ns >= clock('09:45'))]
        standard = all_events[all_events.sale_flags == 0]
        reasons = collections.Counter()
        for at in origins:
            r, reason = prefix_feature(standard, all_events, at, ticker)
            reasons[reason] += 1
            if r is None:
                continue
            if labels:
                y, count, end = label_at(standard, at, r['reference_price_twice'], int(observed_through_ns))
                if y is None:
                    reasons['HORIZON_NOT_FULLY_OBSERVED'] += 1
                    r.update({'class': -1, 'future_standard_n': count, 'label_end_ns': end})
                else:
                    r.update({'class': y, 'future_standard_n': count, 'label_end_ns': end})
            rows.append(r)
        coverage[ticker] = dict(reasons)
    return pd.DataFrame(rows), coverage


def design(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]):
    a, b = train[columns].to_numpy(float), test[columns].to_numpy(float)
    mu, scale = a.mean(axis=0), a.std(axis=0)
    scale[scale < 1e-12] = 1.0
    return (np.c_[np.ones(len(a)), np.clip((a - mu) / scale, -5, 5)],
            np.c_[np.ones(len(b)), np.clip((b - mu) / scale, -5, 5)])


def fit_availability(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]):
    a, b = design(train, test, columns)
    y = (train['class'].to_numpy() > 0).astype(float)
    if len(np.unique(y)) < 2:
        return np.full(len(test), (y.sum() + 1) / (len(y) + 2)), {'constant_fallback': True}
    def objective(w):
        z = a @ w
        loss = np.mean(np.logaddexp(0, z) - y * z) + .005 * np.dot(w[1:], w[1:])
        grad = a.T @ (expit(z) - y) / len(a)
        grad[1:] += .01 * w[1:]
        return loss, grad
    fit = minimize(objective, np.zeros(a.shape[1]), jac=True, method='L-BFGS-B',
                   options={'maxiter': 800, 'ftol': 1e-12, 'gtol': 1e-8})
    if not fit.success:
        raise ValueError('availability optimizer failed: ' + str(fit.message))
    return expit(b @ fit.x), {'iterations': int(fit.nit), 'converged': True}


def fit_direction(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]):
    # This is explicitly conditional on a future observed standard print, not a market-wide return.
    observed = train[train['class'] > 0]
    if len(observed) < 30:
        raise ValueError('insufficient conditional-direction training observations')
    a, b = design(observed, test, columns)
    y = observed['class'].to_numpy(int) - 1
    target = np.eye(3)[y]
    def objective(flat):
        w = flat.reshape(a.shape[1], 3)
        z = a @ w
        loss = np.mean(logsumexp(z, axis=1) - z[np.arange(len(y)), y]) + .005 * np.sum(w[1:] ** 2)
        grad = a.T @ (softmax(z, axis=1) - target) / len(a)
        grad[1:] += .01 * w[1:]
        return loss, grad.ravel()
    fit = minimize(objective, np.zeros(a.shape[1] * 3), jac=True, method='L-BFGS-B',
                   options={'maxiter': 800, 'ftol': 1e-12, 'gtol': 1e-8})
    if not fit.success:
        raise ValueError('direction optimizer failed: ' + str(fit.message))
    return softmax(b @ fit.x.reshape(a.shape[1], 3), axis=1), {'iterations': int(fit.nit), 'converged': True}


def combine(availability: np.ndarray, direction: np.ndarray) -> np.ndarray:
    p = np.c_[1 - availability, availability[:, None] * direction]
    if not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError('invalid probability')
    np.testing.assert_allclose(p.sum(axis=1), 1, atol=1e-12)
    return p


def metrics(y: np.ndarray, p: np.ndarray, availability: np.ndarray, direction: np.ndarray):
    y = np.asarray(y, int)
    observed = y > 0
    onehot = np.eye(4)[y]
    joint_loss = np.sum((p - onehot) ** 2, axis=1)
    available_loss = (availability - observed) ** 2
    conditional_loss = np.full(len(y), np.nan)
    conditional_loss[observed] = np.sum((direction[observed] - np.eye(3)[y[observed] - 1]) ** 2, axis=1)
    log_joint = -np.log(np.clip(p[np.arange(len(y)), y], 1e-14, 1))
    log_a = -np.log(np.clip(np.where(observed, availability, 1 - availability), 1e-14, 1))
    log_d = np.zeros(len(y))
    log_d[observed] = -np.log(np.clip(direction[observed, y[observed] - 1], 1e-14, 1))
    np.testing.assert_allclose(log_joint, log_a + log_d, atol=1e-10)
    calibration = []
    for k in range(5):
        mask = (availability >= k / 5) & (availability < (k + 1) / 5)
        if mask.any():
            calibration.append({'lower': k / 5, 'n': int(mask.sum()),
                                'predicted': float(availability[mask].mean()),
                                'observed': float(observed[mask].mean())})
    summary = {'n': len(y), 'class_counts': np.bincount(y, minlength=4).tolist(),
               'brier4': float(joint_loss.mean()), 'logloss4': float(log_joint.mean()),
               'availability_brier': float(available_loss.mean()),
               'conditional_direction_n': int(observed.sum()),
               'conditional_direction_brier': float(np.nanmean(conditional_loss)) if observed.any() else None,
               'conditional_direction_accuracy': float(np.mean(direction[observed].argmax(axis=1) == y[observed] - 1)) if observed.any() else None,
               'availability_calibration': calibration, 'logloss_decomposition_exact': True}
    return summary, {'joint': joint_loss, 'availability': available_loss, 'direction': conditional_loss}


def paired_interval(test: pd.DataFrame, gain: np.ndarray) -> dict[str, Any]:
    a = pd.DataFrame({'block': np.minimum((test.decision_ns.astype('int64') - clock('13:00')) // (1800 * SECOND), 4), 'gain': gain}).dropna()
    blocks = a.groupby('block').gain.agg(['sum', 'count'])
    if blocks.empty:
        return {'mean': None, 'interval': None, 'blocks': 0}
    rng = np.random.default_rng(2026101504)
    samples = []
    for _ in range(1000):
        b = blocks.iloc[rng.integers(len(blocks), size=len(blocks))]
        samples.append(float(b['sum'].sum() / b['count'].sum()))
    return {'mean': float(a.gain.mean()), 'descriptive_block_interval95': np.quantile(samples, [.025, .975]).tolist(),
            'blocks': len(blocks), 'replicates': 1000, 'independent_days': 1,
            'population_significance_established': False}


def run(executions: Path, output: Path) -> None:
    if output.exists():
        raise ValueError('output exists: do not overwrite a prior experiment')
    x = load(executions)
    origins = list(range(clock('10:00'), clock('15:30') + 1, 30 * SECOND))
    z, coverage = panel(x, origins, observed_through_ns=clock('15:45'))
    if not np.isfinite(z[BASE + NEW]).all().all():
        raise ValueError('nonfinite features')
    # Feature equality at an arbitrary quiet-clock prefix, not merely at an execution time.
    cut = clock('12:17:30')
    prior_origins = [t for t in origins if t <= cut]
    prefix, _ = panel(x[x.send_ns <= cut], prior_origins, labels=False)
    expected = z[z.decision_ns <= cut]
    assert list(zip(prefix.ticker, prefix.decision_ns)) == list(zip(expected.ticker, expected.decision_ns))
    np.testing.assert_allclose(prefix[BASE + NEW], expected[BASE + NEW], rtol=0, atol=0)
    train = z[(z.decision_ns >= clock('10:00')) & (z.label_end_ns < clock('12:00')) & (z['class'] >= 0)]
    test = z[(z.decision_ns >= clock('13:00')) & (z.decision_ns <= clock('15:30')) & (z['class'] >= 0)].copy()
    assert train.label_end_ns.max() < test.decision_ns.min()
    if len(train) < 200 or len(test) < 200:
        raise ValueError('insufficient panel')
    y = test['class'].to_numpy(int)
    freq = (np.bincount(train['class'], minlength=4) + 1) / (len(train) + 4)
    const_p = np.tile(freq, (len(test), 1))
    const_a = np.full(len(test), 1 - freq[0])
    const_d = np.tile(freq[1:] / freq[1:].sum(), (len(test), 1))
    report: dict[str, Any] = {
        'id': 'LP-CLOCK-04', 'run_at': datetime.now(timezone.utc).isoformat(),
        'status': 'RESEARCH_ONLY_PREVIOUSLY_SEEN_SINGLE_DAY', 'training_n': len(train), 'evaluation_n': len(test),
        'input_sha256': digest(executions), 'code_sha256': digest(Path(__file__)),
        'dependency_sha256': digest(DEPENDENCY), 'protocol_sha256': digest(HERE / 'PROTOCOL.json'),
        'source_scope': 'IEX displayed L executions only; source-send clock, not end-user availability',
        'class_names': CLASS_NAMES, 'coverage': coverage, 'metrics': {}, 'fit': {},
        'training_last_outcome_ns': str(int(train.label_end_ns.max())),
        'evaluation_first_origin_ns': str(int(test.decision_ns.min())),
        'checks': {'prefix_exact_equality': True, 'future_based_eligibility': False,
                   'unobserved_future_kept_distinct': True, 'strict_label_embargo': True},
    }
    losses = {}
    report['metrics']['constant'], losses['constant'] = metrics(y, const_p, const_a, const_d)
    for name, cols in [('baseline', BASE), ('pause', BASE + NEW)]:
        pa, fa = fit_availability(train, test, cols)
        pdirection, fd = fit_direction(train, test, cols)
        joint = combine(pa, pdirection)
        report['metrics'][name], losses[name] = metrics(y, joint, pa, pdirection)
        report['fit'][name] = {'availability': fa, 'conditional_direction': fd, 'feature_count': len(cols)}
        for k in range(4):
            test[name + '_p' + str(k)] = joint[:, k]
    report['gains'] = {kind: paired_interval(test, losses['baseline'][kind] - losses['pause'][kind])
                       for kind in ['joint', 'availability', 'direction']}
    for kind in ['joint', 'availability', 'direction']:
        test[kind + '_gain'] = losses['baseline'][kind] - losses['pause'][kind]
    report['per_ticker'] = {
        ticker: {'n': len(g), 'direction_n': int((g['class'] > 0).sum()),
                 'joint_gain': float(g.joint_gain.mean()), 'direction_gain': float(g.direction_gain.mean()) if g.direction_gain.notna().any() else None,
                 'no_standard_observation_fraction': float((g['class'] == 0).mean())}
        for ticker, g in test.groupby('ticker')}
    quiet = test.standard_age_seconds >= 60
    other = quiet & (test.all60_count > 0)
    report['filtered_silence'] = {'eligible_origins': len(test), 'standard_age_ge60_origins': int(quiet.sum()),
                                  'with_other_L_activity_in_last60s': int(other.sum()),
                                  'fraction_of_standard_quiet': float(other.sum() / quiet.sum()) if quiet.any() else None,
                                  'not_market_wide_or_directional': True}
    gain = report['gains']
    report['candidate_to_replicate_only_gate'] = bool(
        gain['joint']['mean'] >= .002 and gain['direction']['mean'] >= .002 and
        gain['joint']['descriptive_block_interval95'][0] > 0 and
        gain['direction']['descriptive_block_interval95'][0] > 0 and
        sum(g['direction_n'] >= 30 and g['direction_gain'] > 0 for g in report['per_ticker'].values()) >= 5)
    report['forecast_authority'] = 'NONE_REGARDLESS_OF_GATE'
    assert digest(executions) == EXPECTED_INPUT_SHA256
    output.mkdir(parents=True)
    test.to_csv(output / 'predictions.csv.gz', index=False, compression='gzip')
    report['private_predictions_sha256'] = digest(output / 'predictions.csv.gz')
    (output / 'results.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executions', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.executions, args.out)
