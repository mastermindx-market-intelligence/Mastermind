"""Original causal APMEM research primitives; not the creator's private model.

Reference: NYU V-Lab /docs/volatility/APMEM. Forecasts are daily variance,
not annualized percent and not market-direction probabilities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.signal import lfilter

VARIANCE_FLOOR = 1e-12


def vector(x: Any, name: str, *, positive: bool = False) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.ndim != 1 or not len(a) or not np.isfinite(a).all():
        raise ValueError(f"{name}: expected nonempty finite one-dimensional data")
    if positive and np.any(a <= 0):
        raise ValueError(f"{name}: nonpositive observations")
    return a


@dataclass(frozen=True)
class Parameters:
    omega: float
    alpha: float
    beta: float
    gamma: float
    delta: float

    def validate(self) -> None:
        if not np.isfinite(list(asdict(self).values())).all():
            raise ValueError("nonfinite parameters")
        if min(self.omega, self.alpha, self.beta, self.delta) <= 0:
            raise ValueError("omega, alpha, beta and delta must be positive")
        if not -1 < self.gamma < 1:
            raise ValueError("gamma must be strictly between -1 and 1")


def filter_variance(v: Any, r: Any, p: Parameters, initial_mu: float) -> np.ndarray:
    """Return mu[0..n]: mu[i] uses observations strictly before i.

    mu[n] is the next-session forecast. The initial value must be determined
    inside the training set. Powered states admit an exact linear filter.
    """
    v, r = vector(v, "variance", positive=True), vector(r, "returns")
    p.validate()
    if len(v) != len(r) or not np.isfinite(initial_mu) or initial_mu <= 0:
        raise ValueError("shape or initial variance invalid")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        intercepts = p.omega + p.alpha * (v * (1 - p.gamma * np.sign(r))) ** p.delta
        z, _ = lfilter([1.0], [1.0, -p.beta], intercepts,
                       zi=[p.beta * initial_mu ** p.delta])
        out = np.r_[initial_mu, z ** (1.0 / p.delta)]
    if not np.isfinite(out).all() or np.any(out <= 0):
        raise ValueError("nonfinite or nonpositive filtered variance")
    return out


def adjusted_range(high: Any, low: Any, returns: Any, retention: float = 0.05
                   ) -> tuple[np.ndarray, dict[str, Any]]:
    """Causal NYU-style overnight correction; all rows already have returns.

    Literal NYU retention=.05 weights the newest lagged observation .95.
    A separate retention=.94 experiment is NOT represented as NYU's setting.
    Zero returns are valid; the positive variance floor is counted explicitly.
    Zero/malformed intraday ranges are invalid, not missing-data imputations.
    """
    high, low = vector(high, "high", positive=True), vector(low, "low", positive=True)
    r = vector(returns, "returns")
    if not (len(high) == len(low) == len(r)) or np.any(high <= low):
        raise ValueError("high/low/return shapes or ranges invalid")
    if not np.isfinite(retention) or not 0 < retention < 1:
        raise ValueError("retention outside (0,1)")
    raw = np.log(high / low) ** 2 / (4 * np.log(2.0))
    e_range, e_return = float(raw[0]), float(r[0] ** 2)
    out = np.empty(len(raw))
    floored = 0
    for i in range(len(raw)):
        if i:
            e_range = (1-retention)*raw[i-1] + retention*e_range
            e_return = (1-retention)*r[i-1]**2 + retention*e_return
        value = raw[i] * e_return / e_range
        floored += int(value < VARIANCE_FLOOR)
        out[i] = max(float(value), VARIANCE_FLOOR)
    if not np.isfinite(out).all():
        raise ValueError("nonfinite adjusted range proxy")
    return out, {"retention": retention, "variance_floor": VARIANCE_FLOOR,
                 "floored_rows": floored, "target": "adjusted_parkinson_daily_variance"}


@dataclass(frozen=True)
class Fit:
    parameters: Parameters | None
    scale: float
    objective: float | None
    success: bool
    observations: int
    input_sha256: str
    attempts: tuple[dict[str, Any], ...]
    empirical_power_persistence: float | None = None
    boundary_parameters: tuple[str, ...] = ()

    def record(self) -> dict[str, Any]:
        return asdict(self)


def fit_qml(v: Any, r: Any, *, maxiter: int = 400) -> Fit:
    """Two fixed starts; select successful fit by TRAINING likelihood only.

    Bounds and a 20-row initialization burn-in are engineering choices, not a
    claim to reproduce V-Lab's optimizer. No silent fallback on fit failure.
    Empirical powered persistence is a diagnostic, not a stationarity proof.
    """
    v, r = vector(v, "variance", positive=True), vector(r, "returns")
    if len(v) != len(r) or len(v) < 64 or maxiter < 1:
        raise ValueError("need >=64 aligned training rows and a positive iteration limit")
    scale = float(np.mean(v))
    x = v / scale
    digest = hashlib.sha256(np.column_stack((v, r)).astype("<f8").tobytes()).hexdigest()
    bounds = [(-9.0, 2.0), (1e-5, .6), (1e-5, .995), (-.95, .95), (.5, 2.0)]
    starts = [(np.log(.03), .1, .85, .1, 1.0),
              (np.log(.05), .05, .9, .25, .7)]

    def unpack(theta: np.ndarray) -> Parameters:
        return Parameters(float(np.exp(theta[0])), *map(float, theta[1:]))

    def objective(theta: np.ndarray) -> float:
        try:
            mu = filter_variance(x, r, unpack(theta), 1.0)[:-1]
            score = .5 * np.mean(np.log(mu[20:]) + x[20:]/mu[20:])
            return float(score) if np.isfinite(score) else 1e100
        except (ValueError, FloatingPointError, OverflowError):
            return 1e100

    candidates, attempts = [], []
    for start in starts:
        z = minimize(objective, start, method="L-BFGS-B", bounds=bounds,
                     options={"maxiter": maxiter, "ftol": 1e-10, "gtol": 1e-6,
                              "maxls": 40})
        ok = bool(z.success and np.isfinite(z.fun) and z.fun < 1e90)
        attempts.append({"success": ok, "message": str(z.message),
                         "iterations": int(z.nit), "evaluations": int(z.nfev)})
        if ok:
            candidates.append(z)
    if not candidates:
        return Fit(None, scale, None, False, len(v), digest, tuple(attempts))
    best = min(candidates, key=lambda z: z.fun)
    p = unpack(best.x)
    mu = filter_variance(x, r, p, 1.0)[:-1]
    eps = x[20:] / mu[20:]
    persistence = p.alpha*np.mean((eps*(1-p.gamma*np.sign(r[20:])))**p.delta)+p.beta
    names = ("log_omega", "alpha", "beta", "gamma", "delta")
    edge = tuple(name for name, value, (lo, hi) in zip(names, best.x, bounds)
                 if min(abs(value-lo), abs(value-hi)) < 1e-4)
    return Fit(p, scale, float(best.fun), True, len(v), digest, tuple(attempts),
               float(persistence), edge)


def walk_forward(v: Any, r: Any, *, minimum: int = 252, window: int = 504,
                 refit_every: int = 63, maxiter: int = 400
                 ) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """forecast[t] predicts v[t+1] using v[:t+1], never v[t+1].

    Fits happen at scheduled origins. Failed fits yield an unavailable block;
    old coefficients are not silently retained or relabeled as successful.
    """
    v, r = vector(v, "variance", positive=True), vector(r, "returns")
    if len(v) != len(r) or minimum < 64 or window < minimum or refit_every < 1:
        raise ValueError("invalid walk-forward input/configuration")
    out = np.full(len(v), np.nan)
    records: list[dict[str, Any]] = []
    fit, state = None, None
    for i in range(minimum-1, len(v)):
        if (i-(minimum-1)) % refit_every == 0:
            start = max(0, i-window+1)
            fit = fit_qml(v[start:i+1], r[start:i+1], maxiter=maxiter)
            records.append({"train_start_index": start, "train_end_index": i,
                            **fit.record()})
            state = (filter_variance(v[start:i+1]/fit.scale, r[start:i+1],
                                     fit.parameters, 1.0)[-1] if fit.success else None)
        elif fit is not None and fit.success and state is not None:
            state = filter_variance([v[i]/fit.scale], [r[i]], fit.parameters, state)[-1]
        if fit is not None and fit.success and state is not None:
            out[i] = state*fit.scale
    return out, records


def qlike(realized: Any, forecast: Any) -> np.ndarray:
    realized = vector(realized, "realized", positive=True)
    forecast = vector(forecast, "forecast", positive=True)
    if len(realized) != len(forecast):
        raise ValueError("QLIKE shapes mismatch")
    ratio = realized/forecast
    return ratio-np.log(ratio)-1
