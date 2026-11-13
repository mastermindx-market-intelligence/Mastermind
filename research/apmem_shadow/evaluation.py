"""Fixed retrospective evaluation. Historical dates are not availability clocks."""
from __future__ import annotations
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .model import adjusted_range, qlike, walk_forward


def daily_frame(frame: pd.DataFrame) -> pd.DataFrame:
    d = frame.copy()
    if "date" in d.columns:
        d = d.set_index("date")
    d.index = pd.to_datetime(d.index, errors="raise")
    if d.index.tz is not None or d.index.hasnans or not d.index.is_unique:
        raise ValueError("expected unique timezone-free economic session dates")
    if not d.index.is_monotonic_increasing or (d.index != d.index.normalize()).any():
        raise ValueError("session dates must be increasing midnight dates")
    return d


def validate_prices(frame: pd.DataFrame) -> pd.DataFrame:
    d = daily_frame(frame)
    if len(d) < 3 or not {"open", "high", "low", "close"}.issubset(d.columns):
        raise ValueError("insufficient OHLC input")
    x = d[["open", "high", "low", "close"]].astype(float)
    if not np.isfinite(x).all().all() or (x <= 0).any().any():
        raise ValueError("OHLC must be positive and finite")
    if ((x.high <= x.low) | (x.high+1e-8 < x[["open", "close"]].max(axis=1)) |
            (x.low-1e-8 > x[["open", "close"]].min(axis=1))).any():
        raise ValueError("inconsistent OHLC range")
    return x


def fixed_events(prices: pd.DataFrame, forecast: np.ndarray,
                 options: pd.DataFrame | None) -> pd.DataFrame:
    """No creator labels, target returns, future quantiles or neutral imputation."""
    d = prices.copy()
    if len(forecast) != len(d):
        raise ValueError("forecast length mismatch")
    f = pd.Series(forecast, index=d.index)
    q80 = f.shift(1).rolling(252, min_periods=126).quantile(.8)
    vol = (f > q80) & (f < f.shift(1))
    price = (d.close/d.close.rolling(20).max()-1 <= -.05) & (d.close.diff() > 0)
    option = pd.Series(False, index=d.index)
    option_valid = pd.Series(False, index=d.index)
    if options is not None:
        opt = daily_frame(options)
        if not {"net_gex_bn", "iv30"}.issubset(opt.columns):
            raise ValueError("required options fields missing")
        # Reindex BEFORE shifting: a missing economic session stays missing.
        gex = pd.to_numeric(opt.net_gex_bn, errors="raise").reindex(d.index)
        iv = pd.to_numeric(opt.iv30, errors="raise").reindex(d.index)
        if np.isinf(gex).any() or np.isinf(iv).any() or (iv.dropna() <= 0).any():
            raise ValueError("invalid GEX or IV values")
        g = gex.shift(1)
        med = gex.shift(2).rolling(20, min_periods=20).median()
        option_valid = g.notna() & med.notna() & iv.shift(1).notna() & iv.shift(2).notna()
        option = option_valid & (g > med) & (iv.shift(1) < iv.shift(2))
    eligible = f.notna() & q80.notna() & f.shift(1).notna() & option_valid
    # Paired eligibility for EVERY strategy; missing inputs are never positive votes.
    return pd.DataFrame({"eligible": eligible, "options_available": option_valid,
                         "price_only": price & eligible, "volatility_only": vol & eligible,
                         "options_only": option & eligible,
                         "combined": vol & option & eligible,
                         "all_three": price & vol & option & eligible}, index=d.index)


def long_cash_replay(opens: Any, signals: Any, *, delay: int = 1, holding: int = 20,
                     one_way_cost: float = .0005, dates: Any = None
                     ) -> dict[str, Any]:
    """EOD event t enters at open t+delay; never trade in the signal-day bar.

    Ignore events originating while occupied. Hold for exactly `holding`
    open-to-open intervals unless censored by the sample endpoint. No shorts,
    leverage, interest, dividends, tax or financing. This is simulation only.
    """
    p, sig = np.asarray(opens, dtype=float), np.asarray(signals)
    if (p.ndim != 1 or len(p) < 3 or not np.isfinite(p).all() or np.any(p <= 0) or
            sig.shape != p.shape or sig.dtype.kind != "b"):
        raise ValueError("invalid open prices or boolean event vector")
    if delay < 1 or holding < 1 or not 0 <= one_way_cost < 1:
        raise ValueError("invalid execution policy")
    w = np.zeros(len(p)-1)
    remaining = 0
    for i in range(len(w)):
        if remaining:
            w[i] = 1
            remaining -= 1
        elif i >= delay and sig[i-delay] and w[i-delay] == 0:
            w[i] = 1
            remaining = holding-1
    return score_exposure(p, w, one_way_cost, dates, holding)


def score_exposure(p: np.ndarray, w: np.ndarray, cost: float, dates: Any = None,
                   holding: int | None = None) -> dict[str, Any]:
    p, w = np.asarray(p, float), np.asarray(w, float)
    if (len(w) != len(p)-1 or not np.isfinite(p).all() or np.any(p <= 0) or
            not np.isin(w, [0., 1.]).all() or not 0 <= cost < 1):
        raise ValueError("invalid binary exposure path")
    returns = p[1:]/p[:-1]-1
    turnover = np.abs(w-np.r_[0., w[:-1]])
    step = (1-cost*turnover)*(1+w*returns)
    equity = np.r_[1., np.cumprod(step)]
    if w[-1]:
        equity[-1] *= 1-cost
    dd = equity/np.maximum.accumulate(equity)-1
    net_steps = equity[1:]/equity[:-1]-1
    daily_std = float(np.std(net_steps, ddof=1)) if len(net_steps) > 1 else 0.0
    spans = []
    entry = None
    for i, pos in enumerate(np.r_[w, 0.]):
        prev = w[i-1] if i else 0.
        if pos and not prev:
            entry = i
        if prev and not pos:
            spans.append({"entry_index": entry, "exit_index": i,
                          "intervals": i-entry,
                          "net_return": float((p[i]/p[entry])*(1-cost)**2-1),
                          "censored": bool(i == len(p)-1 and holding is not None and i-entry < holding)})
            entry = None
    years = ((pd.Timestamp(dates[-1])-pd.Timestamp(dates[0])).days/365.25
             if dates is not None else len(w)/252)
    if years <= 0:
        raise ValueError("invalid evaluation duration")
    return {"total_return": float(equity[-1]-1), "cagr": float(equity[-1]**(1/years)-1),
            "max_open_mark_drawdown": float(dd.min()), "exposure_fraction": float(w.mean()),
            "annualized_open_mark_volatility": daily_std*float(np.sqrt(252)),
            "zero_cash_rate_sharpe": float(np.mean(net_steps)/daily_std*np.sqrt(252)) if daily_std > 0 else None,
            "trades": spans, "turnover_including_liquidation": float(turnover.sum()+w[-1]),
            "equity": equity.tolist(), "exposure": w.tolist()}


def event_outcomes(opens: np.ndarray, events: np.ndarray, horizon: int = 20
                   ) -> dict[str, Any]:
    p = np.asarray(opens, float)
    ix = np.flatnonzero(np.asarray(events, bool))
    mature = ix[ix+1+horizon < len(p)]
    values = p[mature+1+horizon]/p[mature+1]-1
    independent = []
    last = -10**9
    for i in mature:
        if i-last >= horizon:
            independent.append(i)
            last = i
    independent = np.asarray(independent, dtype=int)
    nonoverlap = p[independent+1+horizon]/p[independent+1]-1
    return {"events": int(len(ix)), "matured": int(len(mature)),
            "censored": int(len(ix)-len(mature)),
            "positive_fraction": float(np.mean(values > 0)) if len(values) else None,
            "median_forward_open_return": float(np.median(values)) if len(values) else None,
            "nonoverlapping_events": int(len(independent)),
            "nonoverlap_mean_return": float(np.mean(nonoverlap)) if len(nonoverlap) else None,
            "event_indices": ix.tolist()}


def known_correction_forecast(high: Any, low: Any, returns: Any, retention: float) -> np.ndarray:
    """EWMA raw range times c[t+1], whose lagged inputs are known at t.

    Forecasts the same adjusted target as APMEM. In particular, the literal
    low retention can make a simple unconditional adjusted-proxy baseline weak.
    """
    from .model import vector, VARIANCE_FLOOR
    h, l = vector(high, "high", positive=True), vector(low, "low", positive=True)
    r = vector(returns, "returns")
    if len(h) != len(l) or len(h) != len(r) or np.any(h <= l) or not 0 < retention < 1:
        raise ValueError("invalid range/control input")
    raw = np.log(h/l)**2/(4*np.log(2.0))
    erange, ereturn, raw_forecast = raw[0], r[0]**2, raw[0]
    result = np.empty(len(raw))
    for i in range(len(raw)):
        # Move the lagged EWM to the next-session correction factor.
        erange = (1-retention)*raw[i]+retention*erange
        ereturn = (1-retention)*r[i]**2+retention*ereturn
        raw_forecast = .06*raw[i]+.94*raw_forecast
        result[i] = max(float(raw_forecast*ereturn/erange), VARIANCE_FLOOR)
    return result


def evaluate(prices: pd.DataFrame, options: pd.DataFrame | None, *, retention: float,
             minimum: int = 252, window: int = 504, refit_every: int = 63,
             maxiter: int = 400) -> tuple[dict[str, Any], pd.DataFrame]:
    p = validate_prices(prices)
    returns = np.log(p.close).diff().iloc[1:].to_numpy()
    p = p.iloc[1:]
    v, preprocessing = adjusted_range(p.high, p.low, returns, retention)
    forecast, fits = walk_forward(v, returns, minimum=minimum, window=window,
                                  refit_every=refit_every, maxiter=maxiter)
    s = pd.Series(v, index=p.index)
    estimates = {
        "apmem": forecast,
        "last_proxy": v.copy(),
        "ewma_range_known_next_c": known_correction_forecast(p.high, p.low, returns, retention),
        "ewma_094": s.ewm(alpha=.06, adjust=False).mean().to_numpy(),
        "mean_20": s.rolling(20).mean().to_numpy(),
        "expanding_mean": s.expanding(min_periods=minimum).mean().to_numpy(),
    }
    target = v[1:]
    valid = np.ones(len(target), bool)
    for f in estimates.values():
        valid &= np.isfinite(f[:-1]) & (f[:-1] > 0)
    metrics = {}
    for name, f in estimates.items():
        a = f[:-1][valid]
        metrics[name] = {"n": int(valid.sum()),
                         "mean_qlike": float(qlike(target[valid], a).mean()) if valid.any() else None,
                         "mean_squared_error": float(np.mean((target[valid]-a)**2)) if valid.any() else None}
    events = fixed_events(p, forecast, options)
    rows = p.copy()
    rows["return_log"] = returns
    rows["variance_proxy"] = v
    rows["forecast_next_daily_variance"] = forecast
    rows = rows.join(events)
    rows["refit_origin"] = False
    for record in fits:
        rows.loc[rows.index[record["train_end_index"]], "refit_origin"] = True
    strategies = []
    summaries = {}
    eligible_indices = np.flatnonzero(events.eligible)
    start = int(eligible_indices[0]) if len(eligible_indices) else None
    if start is not None and len(p)-start >= 3:
        q = p.iloc[start:]
        e = events.iloc[start:]
        for name in ("price_only", "volatility_only", "options_only", "combined", "all_three"):
            summaries[name] = event_outcomes(q.open.to_numpy(), e[name].to_numpy())
            summaries[name]["events_on_refit_origin"] = int((e[name] & rows.loc[q.index, "refit_origin"]).sum())
            for delay in (1, 2):
                for cost in (.0005, .002):
                    z = long_cash_replay(q.open.to_numpy(), e[name].to_numpy(), delay=delay,
                                         one_way_cost=cost, dates=q.index)
                    yearly = {}
                    eq = np.array(z.pop("equity"))
                    z.pop("exposure")
                    for year in sorted(set(q.index.year)):
                        ids = np.flatnonzero(q.index.year == year)
                        before = max(0, ids[0]-1)
                        yearly[str(year)] = float(eq[ids[-1]]/eq[before]-1)
                    strategies.append({"policy": name, "delay_sessions": delay,
                                       "one_way_cost": cost, "year_returns": yearly, **z})
        for cost in (.0005, .002):
            z = score_exposure(q.open.to_numpy(), np.ones(len(q)-1), cost, q.index)
            z.pop("equity"); z.pop("exposure")
            strategies.append({"policy": "buy_hold", "delay_sessions": None,
                               "one_way_cost": cost, **z})
    for record in fits:
        record["train_start_session"] = str(p.index[record["train_start_index"]].date())
        record["train_end_session"] = str(p.index[record["train_end_index"]].date())
    result = {"schema": "mastermind.apmem_retrospective_evaluation.v1",
              "evidence_mode": "retrospective_reconstruction_not_prospective",
              "promotion_eligible": False, "price_basis": "raw_ohlc_price_return_not_total_return",
              "forecast_origin_convention": "origin t predicts adjusted variance at t+1",
              "options_availability": "unknown_historical_clock_one_session_lag_assumption",
              "preprocessing": preprocessing,
              "price_sessions": len(p), "first_session": str(p.index[0].date()),
              "last_session": str(p.index[-1].date()),
              "comparison_start": str(p.index[start].date()) if start is not None else None,
              "paired_eligible_decisions": int(events.eligible.sum()),
              "missing_options_decisions": int((~events.options_available).sum()),
              "fits": fits, "forecast_metrics": metrics,
              "event_summaries": summaries, "strategies": strategies,
              "warnings": ["Current-vintage prices and reconstructed options do not establish historical availability.",
                           "Raw-price paths omit distributions and are not total-return benchmarks.",
                           "Many frozen comparisons are reported; no winner is promoted.",
                           "Model parameter walk-forward is not an untouched strategy-selection holdout."]}
    return result, rows


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")
