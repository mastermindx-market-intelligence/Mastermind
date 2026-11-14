"""Frozen, development-only VIX/VVIX incremental forecast diagnostic.

No online data access, strategy results, fitting on sealed dates, or promotion.
The caller supplies exact frozen pre-2020 panels and the incumbent index stores.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
import numpy as np
import pandas as pd
from .core import ContractError, calendar_index

MODELS = ("own_risk", "plus_vix", "plus_vvix_level", "plus_vvix_trend")
HORIZONS = (5, 20)
CUTOFF = pd.Timestamp("2019-12-31")


@dataclass(frozen=True)
class RidgeLogFit:
    center: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    smear: float

    def predict(self, x: np.ndarray) -> np.ndarray:
        z = np.clip((np.asarray(x, float)-self.center)/self.scale, -5, 5)
        linear = self.coefficients[0]+z@self.coefficients[1:]
        if not np.isfinite(linear).all() or (abs(linear) > 100).any():
            raise ContractError("forecast overflow or invalid feature")
        return np.exp(linear)*self.smear


def fit_log_ridge(x: np.ndarray, y: np.ndarray, penalty: float = .01) -> RidgeLogFit:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.ndim != 2 or y.ndim != 1 or len(x) != len(y) or len(y) < 32:
        raise ContractError("invalid regression shape or training population")
    if not np.isfinite(x).all() or not np.isfinite(y).all() or (y <= 0).any() or penalty <= 0:
        raise ContractError("nonfinite/nonpositive regression input")
    center, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1.)
    z = np.clip((x-center)/scale, -5, 5)
    design = np.column_stack((np.ones(len(z)), z))
    reg = np.eye(design.shape[1])*penalty
    reg[0, 0] = 0.
    coef = np.linalg.solve(design.T@design/len(y)+reg, design.T@np.log(y)/len(y))
    residual = np.log(y)-design@coef
    if not np.isfinite(coef).all() or (abs(residual) > 100).any():
        raise ContractError("fit failed numerical qualification")
    smear = float(np.exp(residual).mean())
    return RidgeLogFit(center, scale, coef, smear)


def mean_future(v: np.ndarray, horizon: int) -> np.ndarray:
    if horizon not in HORIZONS:
        raise ContractError("undeclared horizon")
    return pd.Series(np.asarray(v, float)).rolling(horizon, min_periods=horizon).mean().shift(-horizon).to_numpy()


def features(p: pd.DataFrame, vix: pd.Series, vvix: pd.Series) -> dict[str, np.ndarray]:
    idx = calendar_index(p.index)
    if idx[-1] > CUTOFF or not {"variance", "return_log"}.issubset(p):
        raise ContractError("only qualified pre-2020 panels are admissible")
    v = pd.to_numeric(p.variance, errors="coerce")
    v = v.where(np.isfinite(v) & (v > 0))
    own = np.column_stack([np.log(v.rolling(w, min_periods=w).mean()) for w in (1, 5, 22)])

    def index_columns(s):
        calendar_index(s.index)
        # Economic observations are aligned BEFORE lagging; no forward fill.
        s = pd.to_numeric(s.reindex(idx), errors="coerce").where(lambda z: np.isfinite(z) & (z > 0)).shift(1)
        m = s.rolling(20, min_periods=20).mean()
        return np.column_stack([np.log(s), np.log(s/m), np.log(m/m.shift(5))])

    ix, vx = index_columns(vix), index_columns(vvix)
    return {MODELS[0]: own, MODELS[1]: np.column_stack((own, ix)),
            MODELS[2]: np.column_stack((own, ix, vx[:, 0])),
            MODELS[3]: np.column_stack((own, ix, vx))}


def walk_forward(p: pd.DataFrame, vix: pd.Series, vvix: pd.Series,
                 *, minimum: int = 504, window: int = 1260, refit: int = 63) -> tuple[pd.DataFrame, list[dict]]:
    """Parameter controls exist for synthetic tests; market runner freezes defaults."""
    if minimum < 32 or window < minimum or refit < 1:
        raise ContractError("invalid chronological fit schedule")
    x = features(p, vix, vvix)
    good = np.logical_and.reduce([np.isfinite(z).all(axis=1) for z in x.values()])
    rows, fits = [], []
    idx = p.index
    for h in HORIZONS:
        target = mean_future(p.variance, h)
        square = mean_future(p.return_log.to_numpy()**2, h)
        eligible_positions = np.flatnonzero(good)
        fit_cache: dict[str, RidgeLogFit] = {}
        last_refit, fit_origin = None, None
        for ordinal, t in enumerate(eligible_positions):
            if idx[t] < pd.Timestamp("2013-01-02") or t+h >= len(p):
                continue
            if last_refit is None or ordinal-last_refit >= refit:
                last_refit = ordinal
                # label at s covers s+1..s+h and must end by current origin t.
                candidates = np.flatnonzero(good & np.isfinite(target) & (np.arange(len(p))+h <= t))
                train = candidates[-window:]
                fit_cache = {}
                fit_origin = t
                if len(train) >= minimum:
                    for model in MODELS:
                        try:
                            fit_cache[model] = fit_log_ridge(x[model][train], target[train])
                            fits.append({"model": model, "horizon": h, "origin": str(idx[t].date()),
                                         "n_train": len(train), "latest_training_label_end": str(idx[train[-1]+h].date()),
                                         "status": "FITTED"})
                        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
                            fits.append({"model": model, "horizon": h, "origin": str(idx[t].date()),
                                         "n_train": len(train), "status": "FAILED", "reason": type(exc).__name__})
            if len(fit_cache) != len(MODELS):
                continue
            preds = {}
            try:
                preds = {m: float(fit_cache[m].predict(x[m][t:t+1])[0]) for m in MODELS}
            except (ValueError, FloatingPointError):
                continue
            if not all(np.isfinite(v) and v > 0 for v in preds.values()):
                continue
            for m, prediction in preds.items():
                for label, observed in (("variance", target[t]), ("return_square", square[t])):
                    if not np.isfinite(observed) or observed < 0:
                        continue
                    ratio = max(float(observed), 1e-12)/prediction
                    rows.append({"origin": str(idx[t].date()), "label_end": str(idx[t+h].date()),
                                 "fit_origin": str(idx[fit_origin].date()), "model": m, "horizon": h,
                                 "target": label, "forecast": prediction, "realized": float(observed),
                                 "qlike": float(ratio-np.log(ratio)-1.)})
    return pd.DataFrame(rows), fits


def paired_block_summary(values: np.ndarray, *, block: int = 63, draws: int = 2000, seed: int = 20261114) -> dict:
    """Circular calendar-block bootstrap, descriptive; draws are not new data."""
    v = np.asarray(values, float)
    if v.ndim != 1 or len(v) < 2*block or not np.isfinite(v).all():
        raise ContractError("insufficient finite common-date blocks")
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    steps = np.arange(block)
    count = int(np.ceil(len(v)/block))
    for i in range(draws):
        starts = rng.integers(0, len(v), count)
        sample = ((starts[:, None]+steps)%len(v)).ravel()[:len(v)]
        means[i] = v[sample].mean()
    estimate = float(v.mean())
    # Centered bootstrap null; a directional tally of raw bootstraps is not a p-value.
    null = means-estimate
    p = float((1+np.sum(abs(null) >= abs(estimate)))/(draws+1))
    return {"n_dates": len(v), "mean_loss_difference": estimate,
            "pointwise95": np.quantile(means, [.025, .975]).tolist(),
            "centered_bootstrap_p": p, "block_observations": block, "draws": draws}


def holm(values: Sequence[float]) -> list[float]:
    p = np.asarray(values, float)
    if p.ndim != 1 or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ContractError("invalid comparison family")
    order = np.argsort(p)
    adjusted = np.maximum.accumulate(p[order]*(len(p)-np.arange(len(p))))
    out = np.empty(len(p));out[order] = np.minimum(adjusted, 1.)
    return out.tolist()
