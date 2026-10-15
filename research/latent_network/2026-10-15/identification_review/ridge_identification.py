"""Controlled feature-basis checks for LP-NETWORK-08. No market data or forecasts.

The published experiment remains immutable. This module supplies an independently
executable information-set control, not a rerun or a substitute for denied results.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import numpy as np


def matrix(a: Any, name: str) -> np.ndarray:
    out = np.asarray(a, dtype=float)
    if out.ndim != 2 or len(out) < 2 or not np.isfinite(out).all():
        raise ValueError(f'{name} must be a finite matrix with at least two rows')
    return out


@dataclass(frozen=True)
class Transform:
    mean: np.ndarray
    scale: np.ndarray
    clip: float = 5.

    def apply(self, a: np.ndarray) -> np.ndarray:
        a = np.asarray(a, dtype=float)
        if a.ndim != 2 or a.shape[1] != len(self.mean) or not np.isfinite(a).all():
            raise ValueError('invalid inference feature matrix')
        return np.clip((a-self.mean)/self.scale, -self.clip, self.clip)


def standardizer(a: np.ndarray) -> Transform:
    mean = a.mean(0)
    scale = a.std(0)
    scale[scale < 1e-12] = 1.
    return Transform(mean, scale)


def solve_ridge(a: np.ndarray, y: np.ndarray, penalty: float) -> np.ndarray:
    if not np.isfinite(penalty) or penalty <= 0:
        raise ValueError('penalty must be positive and finite')
    y = np.asarray(y, dtype=float)
    if y.shape != (len(a),) or not np.isfinite(y).all():
        raise ValueError('finite, correctly aligned target required')
    p = np.eye(a.shape[1])*penalty
    p[0, 0] = 0
    return np.linalg.solve(a.T@a/len(a)+p, a.T@y/len(a))


def published_ridge_formula(x: np.ndarray, y: np.ndarray, test: np.ndarray,
                            penalty: float=.01) -> np.ndarray:
    """Reproduce the published scaler/clipping/mean-loss penalty, not its dataset."""
    x = matrix(x, 'baseline')
    t = standardizer(x)
    a = np.c_[np.ones(len(x)), t.apply(x)]
    b = np.c_[np.ones(len(test)), t.apply(test)]
    return b@solve_ridge(a, y, penalty)


@dataclass
class ControlledRidge:
    base_transform: Transform
    candidate_transform: Transform
    projection: np.ndarray
    keep: np.ndarray
    residual_scale: np.ndarray
    coefficients: np.ndarray
    diagnostics: dict

    def predict(self, baseline: np.ndarray, candidate: np.ndarray) -> np.ndarray:
        if len(baseline) != len(candidate):
            raise ValueError('inference matrices must have the same rows')
        base = self.base_transform.apply(baseline)
        a = np.c_[np.ones(len(base)), base]
        n = self.candidate_transform.apply(candidate)
        residual = n-a@self.projection
        b = np.c_[a, residual[:, self.keep]/self.residual_scale[self.keep]]
        return b@self.coefficients


def fit_controlled(baseline: np.ndarray, candidate: np.ndarray, y: np.ndarray,
                   penalty: float=.01, tolerance: float=1e-9) -> ControlledRidge:
    """Fit on training rows only, projecting extra columns off the baseline span.

    This removes LINEAR redundancy in the supplied transformed inputs. It does not
    establish causation or remove all nonlinear/shared-factor explanations. The
    residual features are scaled, not re-clipped, to preserve orthogonality.
    """
    x, n = matrix(baseline, 'baseline'), matrix(candidate, 'candidate')
    if len(x) != len(n):
        raise ValueError('baseline/candidate training rows must match')
    if not np.isfinite(tolerance) or not 0 < tolerance < 1:
        raise ValueError('invalid numerical tolerance')
    xt, nt = standardizer(x), standardizer(n)
    a = np.c_[np.ones(len(x)), xt.apply(x)]
    c = nt.apply(n)
    projection = np.linalg.lstsq(a, c, rcond=1e-12)[0]
    residual = c-a@projection
    scale = np.sqrt(np.mean(residual**2, axis=0))
    reference = np.maximum(1., np.sqrt(np.mean(c**2, axis=0)))
    keep = scale > tolerance*reference
    b = np.c_[a, residual[:, keep]/scale[keep]]
    beta = solve_ridge(b, y, penalty)
    diagnostics = {'candidate_columns': n.shape[1], 'kept_residual_columns': int(keep.sum()),
                   'residual_rms': scale.tolist(), 'discarded_columns': np.flatnonzero(~keep).tolist(),
                   'max_training_base_residual_cross_moment': float(np.max(np.abs(a.T@residual/len(a))))
                   if residual.size else 0.,
                   'projection_scope': 'TRAINING_ONLY_TRANSFORMED_LINEAR_SPAN',
                   'forecast_authority': 'NONE; CONSTRUCTED_METHOD_CHECK_ONLY'}
    return ControlledRidge(xt, nt, projection, keep, scale, beta, diagnostics)


def rank_target(relative_returns: np.ndarray) -> np.ndarray:
    # Same mid-rank target definition as the retained network implementation.
    from scipy.stats import rankdata
    a = np.asarray(relative_returns, float)
    if a.ndim != 1 or len(a) < 2 or not np.isfinite(a).all():
        raise ValueError('invalid cross-section')
    return 2*((rankdata(a, method='average')-.5)/len(a)-.5)
