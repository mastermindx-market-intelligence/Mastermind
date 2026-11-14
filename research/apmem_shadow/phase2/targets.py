"""Independent targets and causal features for the frozen phase-2 study."""
from __future__ import annotations
import numpy as np
import pandas as pd

FLOOR = 1e-12
HORIZONS = (1, 5, 20)


def validate_prices(prices: pd.DataFrame) -> pd.DataFrame:
    required = ("open", "high", "low", "close", "dividends", "stock_splits")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("prices require a DatetimeIndex")
    if (len(prices) < 3 or prices.index.hasnans or not prices.index.is_unique
            or not prices.index.is_monotonic_increasing):
        raise ValueError("prices require unique ascending finite dates")
    if prices.index.tz is not None or not (prices.index == prices.index.normalize()).all():
        raise ValueError("normalized timezone-naive economic-session dates required")
    if any(c not in prices for c in required):
        raise ValueError("missing OHLC or corporate-action columns")
    p = prices.copy()
    a = p[list(required)].to_numpy(dtype=float)
    if not np.isfinite(a).all() or (a[:, :4] <= 0).any():
        raise ValueError("nonfinite or nonpositive prices")
    if (p.high < p[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high below open, close or low")
    if (p.low > p[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low above open, close or high")
    if (p.high <= p.low).any() or (p.dividends < 0).any():
        raise ValueError("zero range or negative distribution")
    if (~p.stock_splits.isin([0.0, 1.0])).any():
        raise ValueError("split-bearing panel requires separately qualified adapter")
    if "capital_gains" not in p:
        p["capital_gains"] = 0.0
    if not np.isfinite(p.capital_gains).all() or (p.capital_gains < 0).any():
        raise ValueError("invalid capital-gain distribution")
    p["distributions"] = p.dividends + p.capital_gains
    return p


def prepare_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Raw prices, explicit distributions; never use future-adjusted price levels."""
    p = validate_prices(prices)
    prior = p.close.shift(1)
    r = np.log((p.close + p.distributions) / prior)
    gap = np.log((p.open + p.distributions) / prior)
    range_var = np.log(p.high / p.low) ** 2 / (4.0 * np.log(2.0))
    p["return_log"], p["range_var"], p["gap_var"] = r, range_var, gap**2
    p["variance"] = (range_var + gap**2).clip(lower=FLOOR)
    p["return_square"] = r**2
    p["total_index"] = np.exp(r.fillna(0).cumsum())
    # Exact raw-price algebra of incumbent Macro engine.vol_forecast.har_vol.
    raw_r = p.close.pct_change(fill_method=None)
    comps = [raw_r.rolling(w, min_periods=max(2, w//2)).std(ddof=0)
             for w in (2, 5, 22, 66)]
    p["incumbent_variance"] = pd.concat(comps, axis=1).mean(axis=1)**2
    return p.iloc[1:].copy()


def future_mean(values: np.ndarray | pd.Series, horizon: int) -> np.ndarray:
    """At t, mean(values[t+1:t+h+1]); the last h labels are unavailable."""
    if not isinstance(horizon, int) or horizon < 1:
        raise ValueError("positive integer horizon required")
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < 1:
        raise ValueError("nonempty vector required")
    return pd.Series(x).rolling(horizon, min_periods=horizon).mean().shift(-horizon).to_numpy()


def causal_features(p: pd.DataFrame, options: pd.DataFrame | None = None,
                    instrument: str | None = None) -> dict[str, np.ndarray]:
    v, r = p.variance, p.return_log
    basic = np.column_stack([np.log(v.rolling(w, min_periods=w).mean())
                             for w in (1, 5, 22)])
    negative = np.maximum(-r, 0) / np.sqrt(v.rolling(22).mean())
    gap_share = p.gap_var.rolling(5).mean() / v.rolling(5).mean()
    instability = np.log(v).rolling(22).std(ddof=0)
    extended = np.column_stack([basic, negative, gap_share, instability])
    out = {"har": basic, "har_extended": extended}
    if options is not None:
        if (not isinstance(options.index, pd.DatetimeIndex) or options.index.hasnans
                or not options.index.is_unique or not options.index.is_monotonic_increasing
                or options.index.tz is not None):
            raise ValueError("options require unique ordered economic dates")
        if not {"iv30", "net_gex_bn", "root"}.issubset(options):
            raise ValueError("missing options fields")
        if not instrument or not options.root.eq(instrument).all():
            raise ValueError("options instrument mismatch")
        o = options.reindex(p.index)
        # Lag by PRICE sessions. Never forward-fill a missing options date.
        iv = pd.to_numeric(o.iv30, errors="raise").shift(1)
        gex = pd.to_numeric(o.net_gex_bn, errors="raise").shift(1)
        iv = iv.where(np.isfinite(iv) & (iv > 0))
        gex = gex.where(np.isfinite(gex))
        normalized = (gex / gex.abs().rolling(252, min_periods=63).mean()).clip(-5, 5)
        out["har_options"] = np.column_stack([extended, np.log(iv**2/252), normalized])
    return out
