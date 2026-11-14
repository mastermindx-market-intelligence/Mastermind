"""Chronological conditional-risk estimates with fixed model capacity.

No shuffled split, future preprocessing or in-sample prediction grading. The
three classes are stop first / target first / timeout under the registered path
contract. Predicting fewer stops is not itself predicting positive returns.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp, softmax
from .risk import FEATURE_GROUPS


@dataclass(frozen=True)
class LearningSettings:
    minimum: int = 300
    minimum_class: int = 30
    refit_sessions: int = 63
    window_sessions: int = 1260
    ridge: float = 1.0

    def validate(self):
        if (any(type(v) is not int for v in (self.minimum,self.minimum_class,self.refit_sessions,self.window_sessions))
                or self.minimum < 3 or self.minimum_class < 1 or self.refit_sessions < 1
                or self.window_sessions < 63 or not np.isfinite(self.ridge) or self.ridge <= 0):
            raise ValueError('invalid learning settings')


def fit_multinomial(x, y, ridge=1.0):
    x, y = np.asarray(x, float), np.asarray(y)
    if (x.ndim != 2 or y.shape != (len(x),) or len(x) < 3 or not np.isfinite(x).all()
            or not np.isin(y, [0, 1, 2]).all() or not np.isfinite(ridge) or ridge <= 0):
        raise ValueError('invalid classifier training inputs')
    y = y.astype(int)
    count = np.bincount(y, minlength=3)
    if (count == 0).any():
        raise ValueError('all outcome classes must be represented')
    center, spread = x.mean(axis=0), x.std(axis=0)
    spread = np.where(spread > 1e-12, spread, 1.)
    z = np.column_stack([np.ones(len(x)), np.clip((x-center)/spread, -8, 8)])
    initial = np.zeros((z.shape[1], 2))
    initial[0] = np.log(count[:2]/count[2])
    observed = np.eye(3)[y]

    def objective(flat):
        beta = flat.reshape(z.shape[1], 2)
        logits = np.column_stack([z@beta, np.zeros(len(z))])
        probs = softmax(logits, axis=1)
        nll = np.sum(logsumexp(logits, axis=1)-logits[np.arange(len(z)), y])
        value = nll + .5*ridge*np.sum(beta[1:]**2)
        grad = z.T@(probs[:, :2]-observed[:, :2])
        grad[1:] += ridge*beta[1:]
        return float(value), grad.ravel()

    fitted = minimize(objective, initial.ravel(), jac=True, method='L-BFGS-B',
                      options={'maxiter': 500, 'ftol': 1e-11, 'gtol': 1e-6, 'maxls': 40})
    success = bool(fitted.success and np.isfinite(fitted.fun) and np.isfinite(fitted.x).all())
    return {'success': success, 'center': center, 'spread': spread,
            'beta': fitted.x.reshape(z.shape[1], 2), 'n': len(x),
            'class_counts': count, 'ridge_on_total_log_likelihood': ridge,
            'objective': float(fitted.fun), 'message': str(fitted.message),
            'iterations': int(fitted.nit)}


def predict_multinomial(fit, x):
    x = np.asarray(x, float)
    if (not fit.get('success') or x.ndim != 2 or x.shape[1] != len(fit['center'])
            or not np.isfinite(x).all()):
        raise ValueError('unqualified fit or prediction features')
    scaled = (x-fit['center'])/fit['spread']
    z = np.column_stack([np.ones(len(x)), np.clip(scaled, -8, 8)])
    logits = np.column_stack([z@fit['beta'], np.zeros(len(x))])
    p = softmax(logits, axis=1)
    if not np.isfinite(p).all() or not np.allclose(p.sum(axis=1), 1., atol=1e-12):
        raise ValueError('invalid predicted probabilities')
    return p, np.any(np.abs(scaled) > 8, axis=1)


def walk_forward(events: pd.DataFrame, calendar: pd.DatetimeIndex,
                 config: LearningSettings = LearningSettings(), start='2020-01-01'):
    config.validate()
    required = {'event_id', 'ticker', 'origin', 'label_end', 'class_id', 'net_return'} | set(FEATURE_GROUPS['interaction'])
    if not required.issubset(events) or not events.event_id.is_unique:
        raise ValueError('missing/duplicate event data')
    if not calendar.is_unique or not calendar.is_monotonic_increasing:
        raise ValueError('invalid learning calendar')
    e = events.copy().reset_index(drop=True)
    origin = pd.to_datetime(e.origin)
    endpoint = pd.to_datetime(e.label_end)
    if (endpoint <= origin).any():
        raise ValueError('outcome must mature strictly after signal')
    numeric = e[list(FEATURE_GROUPS['interaction'])].to_numpy(float)
    common = np.isfinite(numeric).all(axis=1) & np.isfinite(e.net_return) & e.class_id.isin([0,1,2])
    fit_bundle = None
    last_attempt = -config.refit_sessions
    predictions, receipts = [], []
    for t, day in enumerate(calendar):
        if day < pd.Timestamp(start):
            continue
        today = np.flatnonzero(common & origin.eq(day))
        if not len(today):
            continue
        if t-last_attempt >= config.refit_sessions:
            last_attempt = t
            fit_bundle = None
            earliest = calendar[max(0, t-config.window_sessions)]
            eligible = common & (origin >= earliest) & (origin < day) & (endpoint <= day)
            ids = np.flatnonzero(eligible)
            counts = np.bincount(e.class_id.iloc[ids].to_numpy(int), minlength=3)
            if len(ids) >= config.minimum and min(counts) >= config.minimum_class:
                fitted = {}
                for name, names in FEATURE_GROUPS.items():
                    fitted[name] = fit_multinomial(e.loc[ids, list(names)].to_numpy(float),
                                                  e.class_id.iloc[ids].to_numpy(int), config.ridge)
                means = np.array([e.net_return.iloc[ids][e.class_id.iloc[ids].to_numpy() == c].mean()
                                  for c in (0,1,2)])
                fit_bundle = {'models': fitted, 'prior': (counts+1)/(len(ids)+3),
                              'class_net_payoff': means, 'origin': day,
                              'latest_label': endpoint.iloc[ids].max(), 'n': len(ids),
                              'training_first_origin': origin.iloc[ids].min()}
                receipts.append({'fit_origin': str(day.date()), 'n': len(ids),
                                 'class_counts': counts.tolist(),
                                 'training_first_origin': str(origin.iloc[ids].min().date()),
                                 'latest_training_label_end': str(endpoint.iloc[ids].max().date()),
                                 'class_net_payoff': means.tolist(),
                                 'models': {k: {'success': v['success'], 'iterations': v['iterations'],
                                                'message': v['message']} for k,v in fitted.items()}})
            else:
                receipts.append({'fit_origin':str(day.date()),'status':'TRAINING_UNAVAILABLE',
                                 'n':len(ids),'class_counts':counts.tolist()})
        if fit_bundle is None:
            continue
        if fit_bundle['latest_label'] > fit_bundle['origin'] or fit_bundle['origin'] > day:
            raise AssertionError('future outcome entered classifier')
        for name in ('frequency', *FEATURE_GROUPS):
            if name == 'frequency':
                prob = np.tile(fit_bundle['prior'], (len(today), 1))
                clipped = np.zeros(len(today), bool)
            else:
                fit = fit_bundle['models'][name]
                if not fit['success']:
                    continue
                prob, clipped = predict_multinomial(fit, e.loc[today, list(FEATURE_GROUPS[name])].to_numpy(float))
            mean_net = prob@fit_bundle['class_net_payoff']
            for j, i in enumerate(today):
                y = int(e.class_id.iloc[i])
                predictions.append({'event_id': e.event_id.iloc[i], 'ticker': e.ticker.iloc[i],
                                    'origin': str(day.date()), 'model': name, 'class_id': y,
                                    'p_stop': float(prob[j,0]), 'p_target': float(prob[j,1]),
                                    'p_timeout': float(prob[j,2]), 'expected_net_payoff': float(mean_net[j]),
                                    'log_loss': float(-np.log(max(prob[j,y],1e-15))),
                                    'brier': float(np.sum((prob[j]-np.eye(3)[y])**2)),
                                    'fit_origin': str(fit_bundle['origin'].date()),
                                    'latest_training_label_end': str(fit_bundle['latest_label'].date()),
                                    'training_n': fit_bundle['n'], 'feature_clipped': bool(clipped[j]),
                                    'may_rank': False, 'may_size': False, 'may_trade': False})
    return pd.DataFrame(predictions), receipts, fit_bundle


def calibration_table(predictions: pd.DataFrame):
    rows = []
    for name, sub in predictions.groupby('model'):
        for target, column in ((0,'p_stop'),(1,'p_target'),(2,'p_timeout')):
            bins = np.minimum((sub[column]*10).astype(int), 9)
            for b in range(10):
                part = sub.loc[bins == b]
                if len(part):
                    rows.append({'model': name, 'class_id': target, 'bin': b, 'n': len(part),
                                 'mean_probability': float(part[column].mean()),
                                 'observed_fraction': float((part.class_id == target).mean()),
                                 'small_bin': len(part) < 30, 'prospective': False})
    return pd.DataFrame(rows)
